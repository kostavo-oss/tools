"""Whose table is it — and so what stevin may do with it.

dbt's tables take no spec at all: dbt's config carries their grants and tags, and
a `table` materialisation recreates them. A dlt pipeline's — known by the
`_dlt_*` tables beside them — and any owner `owned_elsewhere` names can be
*governed*: a spec with no columns' types puts tags, grants, masks, a row filter
and an owner on the live table and never claims, reshapes or drops it. The
tables no spec names are reported as theirs, not as unmanaged.
"""

import json
from pathlib import Path

import pytest

from fake_warehouse import FakeWarehouse
from helpers import col, run, table
from stevin import api
from stevin.connect import Connection
from stevin.introspect import Introspector
from stevin.loader import Project, SpecError, dump_spec, load_table
from stevin.model.plan import Plan
from stevin.model.table import MANAGED_PROPERTY, Grant, RowFilter, Table
from stevin.model.types import GovernedColumn, Mask
from stevin.model.view import Relation
from stevin.owned import (
    OwnedError,
    Owners,
    dbt_refusal,
    is_dlt_schema,
    matches,
    read_manifest,
)
from stevin.planning import PlanningError, plan_tables
from stevin.render.markdown import render_markdown
from stevin.render.rich import plan_text

CUSTOMERS = table(
    col("id", "bigint"),
    col("email", "string"),
    col("region", "string"),
    name="dev.raw.customers",
    comment="Landed by the crm pipeline",
)
EVENTS = table(col("id", "bigint"), name="dev.raw.events")
DLT_LOADS = table(col("load_id", "string"), name="dev.raw._dlt_loads")
DLT_VERSION = table(col("version", "bigint"), name="dev.raw._dlt_version")

#: Says who may see the customers, and nothing about their shape.
GOVERN = Table(
    name="dev.raw.customers",
    columns=(),
    tags=(("domain", "sales"),),
    grants=(Grant("analysts", ("SELECT",)),),
    row_filter=RowFilter("dev.security.by_region", ("region",)),
    governed_columns=(
        GovernedColumn(
            "email", tags=(("pii", "email"),), mask=Mask("dev.security.mask_email")
        ),
    ),
)


def dlt_schema() -> FakeWarehouse:
    """A schema a dlt pipeline loads into: its tables, and its bookkeeping."""
    fake = FakeWarehouse.of(CUSTOMERS, EVENTS, DLT_LOADS, DLT_VERSION)
    return fake


def planned(
    specs: list[Relation], fake: FakeWarehouse, owners: Owners | None = None
) -> Plan:
    return plan_tables(
        specs, Introspector(fake), target="dev", tool_version="0", owners=owners
    )


# ---------------------------------------------------------------------------
# who owns what: patterns, the manifest, the _dlt_ tables
# ---------------------------------------------------------------------------


def test_a_pattern_covers_one_name_part_at_a_time() -> None:
    assert matches("dev.silver.*", "dev.silver.orders")
    assert matches("*.silver.orders", "DEV.Silver.Orders"), "the catalog's own case"
    assert not matches("dev.silver.*", "dev.silverware.orders"), "a part, not a prefix"
    assert not matches("dev.silver.*", "dev.silver"), "three parts to three parts"


def test_an_exact_name_wins_over_a_pattern() -> None:
    owners = Owners(
        names=(("dev.silver.dim_date", "the calendar team"),),
        patterns=(("dev.silver.*", "dbt"),),
    )
    assert owners.owner_of("dev.silver.orders") == "dbt"
    assert owners.owner_of("dev.silver.dim_date") == "the calendar team"
    assert owners.owner_of("dev.raw.customers") is None


def test_a_dlt_schema_has_both_bookkeeping_tables() -> None:
    assert is_dlt_schema(
        ["dev.raw.customers", "dev.raw._dlt_loads", "dev.raw._dlt_version"]
    )
    assert not is_dlt_schema(["dev.raw.customers", "dev.raw._dlt_loads"]), "one is a copy"
    assert is_dlt_schema(["_DLT_LOADS", "_dlt_version"]), "short names, any case"


MANIFEST = {
    "nodes": {
        "model.shop.orders": {
            "resource_type": "model",
            "database": "dev",
            "schema": "silver",
            "name": "orders",
            "alias": "fct_orders",
            "config": {"materialized": "table"},
        },
        "model.shop.staging": {
            "resource_type": "model",
            "database": "dev",
            "schema": "silver",
            "name": "staging",
            "config": {"materialized": "ephemeral"},
        },
        "seed.shop.countries": {
            "resource_type": "seed",
            "database": "dev",
            "schema": "silver",
            "name": "countries",
            "config": {},
        },
        "snapshot.shop.customers": {
            "resource_type": "snapshot",
            "database": "dev",
            "schema": "history",
            "name": "customers_snapshot",
        },
        "test.shop.not_null": {"resource_type": "test", "name": "not_null"},
        "model.shop.broken": {"resource_type": "model", "name": "broken"},
    },
    "sources": {
        "source.shop.crm.customers": {
            "resource_type": "source",
            "database": "dev",
            "schema": "raw",
            "name": "customers",
        }
    },
}


def test_the_manifest_says_what_dbt_builds(tmp_path: Path) -> None:
    """Models, seeds and snapshots by their alias; not ephemeral models, not tests,
    never sources — those are the tables dbt reads, which is what stevin is for."""
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(MANIFEST), encoding="utf-8")
    owners = read_manifest(path)
    assert [name for name, _ in owners.names] == [
        "dev.history.customers_snapshot",
        "dev.silver.countries",
        "dev.silver.fct_orders",
    ]
    assert all(owner == "dbt" for _, owner in owners.names)
    assert owners.owner_of("dev.raw.customers") is None, "a source isn't dbt's"
    assert owners.notes == (
        "1 node in manifest.json could not be read as a relation and were passed over",
    )


def test_a_manifest_that_is_not_there_names_itself(tmp_path: Path) -> None:
    with pytest.raises(OwnedError, match="nope/manifest.json.*run dbt first"):
        read_manifest(tmp_path / "nope" / "manifest.json")
    (tmp_path / "manifest.json").write_text("{", encoding="utf-8")
    with pytest.raises(OwnedError, match="isn't JSON"):
        read_manifest(tmp_path / "manifest.json")
    (tmp_path / "manifest.json").write_text("[]", encoding="utf-8")
    with pytest.raises(OwnedError, match="no `nodes`"):
        read_manifest(tmp_path / "manifest.json")


def project(tmp_path: Path, extra: str = "", manifest: bool = True) -> Project:
    (tmp_path / "stevin.yml").write_text(
        "specs: [tables]\n"
        "targets:\n  dev:\n    vars: {catalog: dev}\n"
        "owned_elsewhere:\n"
        "  ${catalog}.silver.*: dbt\n"
        "  ${catalog}.science.*: the data-science team\n"
        + ("dbt:\n  manifest: target/manifest.json\n" if manifest else "")
        + extra,
        encoding="utf-8",
    )
    if manifest:
        (tmp_path / "target").mkdir(exist_ok=True)
        (tmp_path / "target" / "manifest.json").write_text(
            json.dumps(MANIFEST), encoding="utf-8"
        )
    (tmp_path / "tables").mkdir(exist_ok=True)
    return Project.load(tmp_path / "stevin.yml")


def test_the_project_file_says_who_owns_what(tmp_path: Path) -> None:
    # RULES.md: OWN-6.
    found = project(tmp_path)
    owners = found.owners(found.target("dev"))
    assert owners.owner_of("dev.silver.orders") == "dbt", "the hand list, with ${catalog}"
    assert owners.owner_of("dev.history.customers_snapshot") == "dbt", "the manifest"
    assert owners.owner_of("dev.science.features") == "the data-science team"
    assert owners.owner_of("dev.raw.customers") is None


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("owned_elsewhere:\n  silver.*: dbt\n", "keyed catalog.schema.table"),
        ("owned_elsewhere:\n  dev.silver.*: ''\n", "say who owns"),
        ("dbt:\n  project: ../x\n", "unknown key 'project'"),
        ("dbt: {}\n", "needs a 'manifest' key"),
    ],
)
def test_what_the_project_file_refuses(tmp_path: Path, text: str, message: str) -> None:
    (tmp_path / "stevin.yml").write_text(
        f"specs: [tables]\ntargets:\n  dev: {{}}\n{text}", encoding="utf-8"
    )
    with pytest.raises(SpecError, match=message):
        Project.load(tmp_path / "stevin.yml")


def test_a_named_manifest_that_is_missing_stops_a_plan(tmp_path: Path) -> None:
    found = project(
        tmp_path, manifest=False, extra="dbt:\n  manifest: target/manifest.json\n"
    )
    with pytest.raises(OwnedError, match="manifest.json"):
        found.owners(found.target("dev"))


# ---------------------------------------------------------------------------
# dbt's take no spec; dlt's and a team's take a governance-only one
# ---------------------------------------------------------------------------

DBT_OWNS_SILVER = Owners(patterns=(("dev.silver.*", "dbt"),))


def test_a_spec_for_dbts_table_is_refused() -> None:
    orders = table(col("id", "bigint"), name="dev.silver.orders")
    with pytest.raises(PlanningError, match="dev.silver.orders is dbt's: put grants"):
        planned([orders], FakeWarehouse.of(orders), DBT_OWNS_SILVER)


def test_even_a_governance_only_spec_for_dbts_table_is_refused() -> None:
    # RULES.md: OWN-7.
    govern = Table(name="dev.silver.orders", columns=(), tags=(("domain", "sales"),))
    with pytest.raises(PlanningError, match="is dbt's"):
        planned(
            [govern],
            FakeWarehouse.of(table(col("id", "bigint"), name="dev.silver.orders")),
            DBT_OWNS_SILVER,
        )


def test_a_governance_only_spec_governs_a_dlt_table() -> None:
    """Only governance is planned — no claim, no shape — and it converges."""
    # RULES.md: OWN-7.
    fake = dlt_schema()
    plan = planned([GOVERN], fake)
    titles = [step.title for step in plan.steps]
    assert not any("CLAIM" in title for title in titles), titles
    kinds = {change.kind for change in plan.changes}
    assert kinds == {
        "set_tag",
        "set_column_tag",
        "grant",
        "set_mask",
        "set_row_filter",
    }, kinds
    desired = plan.diffs[0].desired
    assert isinstance(desired, Table)
    assert desired.column_names == ("id", "email", "region"), "the live shape"
    assert desired.comment == "Landed by the crm pipeline", "the owner's comment, kept"
    assert plan.diffs[0].notes == (
        "governs a table another tool makes: shape left to them",
    )
    run(plan, fake)
    assert planned([GOVERN], fake).empty, "applied once, nothing to do"
    assert MANAGED_PROPERTY not in dict(fake.tables["dev.raw.customers"].properties)


def test_a_governance_only_spec_needs_an_owner() -> None:
    fake = FakeWarehouse.of(CUSTOMERS)  # no _dlt_ tables, nothing in owned_elsewhere
    with pytest.raises(PlanningError, match="name the owner in owned_elsewhere"):
        planned([GOVERN], fake)


def test_a_team_named_in_owned_elsewhere_counts_as_an_owner() -> None:
    fake = FakeWarehouse.of(CUSTOMERS)
    team = Owners(patterns=(("dev.raw.*", "the data-science team"),))
    plan = planned([GOVERN], fake, team)
    assert not plan.empty
    assert not any("CLAIM" in step.title for step in plan.steps)


def test_a_shape_spec_for_a_dlt_table_is_refused() -> None:
    # RULES.md: OWN-7.
    with pytest.raises(PlanningError, match="is dlt's: leave the columns' types out"):
        planned([CUSTOMERS], dlt_schema())


def test_a_governed_column_the_table_lacks_is_refused() -> None:
    govern = Table(
        name="dev.raw.customers",
        columns=(),
        governed_columns=(GovernedColumn("ssn", tags=(("pii", "ssn"),)),),
    )
    with pytest.raises(PlanningError, match="has no column 'ssn' to govern"):
        planned([govern], dlt_schema())


def test_a_governed_table_that_is_not_there_yet_is_theirs_to_make() -> None:
    fake = FakeWarehouse.of(DLT_LOADS, DLT_VERSION)
    with pytest.raises(PlanningError, match="isn't there yet.*owns it makes it first"):
        planned([GOVERN], fake)


def test_owned_tables_are_theirs_not_unmanaged() -> None:
    # RULES.md: OWN-6.
    fake = dlt_schema()
    plan = planned([GOVERN], fake)
    assert plan.unmanaged_tables == ()
    assert plan.owned_tables == (
        ("dev.raw._dlt_loads", "dlt"),
        ("dev.raw._dlt_version", "dlt"),
        ("dev.raw.events", "dlt"),
    )
    assert "dev.raw.events — dlt's" in plan_text(plan)
    assert "(dlt's)" in render_markdown(plan)


def test_the_owned_tables_survive_the_plan_file() -> None:
    from stevin.render.json import dumps, loads

    plan = planned([GOVERN], dlt_schema())
    assert loads(dumps(plan)).owned_tables == plan.owned_tables


# ---------------------------------------------------------------------------
# through the API: plan and validate with files, import with a workspace
# ---------------------------------------------------------------------------

SHAPE = "table: ${catalog}.silver.orders\ncolumns:\n  - {name: id, type: bigint}\n"
GOVERN_YAML = """\
table: ${catalog}.raw.customers
tags: {domain: sales}
columns:
  - {name: email, mask: "${catalog}.security.mask_email", tags: {pii: email}}
grants:
  - {principal: analysts, privileges: [SELECT]}
"""


def test_plan_refuses_dbts_table_by_file_before_select(tmp_path: Path) -> None:
    found = project(tmp_path)
    (tmp_path / "tables" / "orders.yml").write_text(SHAPE, encoding="utf-8")
    (tmp_path / "tables" / "customers.yml").write_text(GOVERN_YAML, encoding="utf-8")
    with pytest.raises(PlanningError, match=r"orders.yml: dev.silver.orders is dbt's"):
        api.plan(
            found,
            found.target("dev"),
            Connection(runner=dlt_schema()),
            select="customers",
        )


def test_validate_refuses_dbts_and_warns_about_the_unowned(tmp_path: Path) -> None:
    found = project(tmp_path)
    (tmp_path / "tables" / "orders.yml").write_text(SHAPE, encoding="utf-8")
    (tmp_path / "tables" / "customers.yml").write_text(GOVERN_YAML, encoding="utf-8")
    diagnostics = api.validate(found, found.target("dev"))
    by_severity = {d.severity: d.message for d in diagnostics}
    assert "is dbt's" in by_severity["error"]
    assert "nothing here says whose" in by_severity["warning"], "dlt's is only known live"


def test_validate_says_when_the_manifest_is_missing(tmp_path: Path) -> None:
    found = project(
        tmp_path, manifest=False, extra="dbt:\n  manifest: target/manifest.json\n"
    )
    (tmp_path / "tables" / "customers.yml").write_text(GOVERN_YAML, encoding="utf-8")
    messages = [
        d.message
        for d in api.validate(found, found.target("dev"))
        if d.severity == "error"
    ]
    assert any("manifest.json" in m for m in messages)


def test_import_governs_dlts_tables_and_skips_dbts() -> None:
    from dataclasses import replace

    governed_live = replace(
        CUSTOMERS,
        grants=(Grant("analysts", ("SELECT",)),),
        columns=tuple(
            replace(c, mask=Mask("dev.security.mask_email")) if c.name == "email" else c
            for c in CUSTOMERS.columns
        ),
    )
    orders = table(col("id", "bigint"), name="dev.raw.orders")
    fake = FakeWarehouse.of(governed_live, EVENTS, DLT_LOADS, DLT_VERSION, orders)
    found = api.import_schema(
        Connection(runner=fake),
        "dev.raw",
        owners=Owners(patterns=(("dev.raw.orders", "dbt"),)),
    )
    written = {spec.filename: spec.text for spec in found}
    assert list(written) == ["customers.yml"], "the governed one, and only it"
    assert "type:" not in written["customers.yml"], "no shape: it is dlt's"
    assert "mask: dev.security.mask_email" in written["customers.yml"]
    assert "principal: analysts" in written["customers.yml"]
    assert dict(found.skipped) == {
        "dev.raw.orders": dbt_refusal("dev.raw.orders"),
        "dev.raw.events": "dlt's, with nothing to govern",
        "dev.raw._dlt_loads": "dlt's, with nothing to govern",
        "dev.raw._dlt_version": "dlt's, with nothing to govern",
    }


def test_a_governance_only_spec_round_trips(tmp_path: Path) -> None:
    text = dump_spec(GOVERN)
    assert "type:" not in text
    path = tmp_path / "customers.yml"
    path.write_text(text, encoding="utf-8")
    assert load_table(path) == GOVERN
    assert load_table(path).governed_columns == GOVERN.governed_columns


def test_a_governance_only_spec_cannot_say_a_shape(tmp_path: Path) -> None:
    path = tmp_path / "customers.yml"
    path.write_text(
        "table: dev.raw.customers\ntags: {domain: sales}\n"
        "constraints:\n  - primary_key: [id]\n",
        encoding="utf-8",
    )
    with pytest.raises(SpecError, match="can't say 'constraints'"):
        load_table(path)


# ---------------------------------------------------------------------------
# a schema the bundle deploys, named the way the bundle names it
# ---------------------------------------------------------------------------

#: A development target deploys `raw` as `dev_jane_raw`; production as `raw`.
DEPLOYS = """\
bundle:
  name: shop
variables:
  catalog:
    default: main
resources:
  schemas:
    raw:
      catalog_name: ${var.catalog}
      name: raw
    silver:
      catalog_name: ${var.catalog}
      name: silver
targets:
  dev:
    default: true
    mode: development
  prod: {}
"""
BY_REFERENCE = """\
specs: [tables]
bundle: databricks.yml
owned_elsewhere:
  ${catalog}.${resources.schemas.raw.name}.*: dlt
  ${catalog}.${resources.schemas.silver.name}.*: dbt
"""
GOVERN_BY_REFERENCE = """\
table: ${catalog}.${resources.schemas.raw.name}.customers
tags: {domain: sales}
grants:
  - {principal: analysts, privileges: [SELECT]}
"""
SHAPE_BY_REFERENCE = (
    "table: ${catalog}.${resources.schemas.silver.name}.orders\n"
    "columns:\n  - {name: id, type: bigint}\n"
)


def as_the_cli_says(prefix: str) -> dict[str, object]:
    """What `databricks bundle validate -o json` prints for a target whose
    schemas are deployed with this in front of their names."""
    return {
        "variables": {"catalog": {"value": "main"}},
        "resources": {
            "schemas": {
                key: {"catalog_name": "main", "name": f"{prefix}{key}"}
                for key in ("raw", "silver")
            }
        },
    }


def by_reference(tmp_path: Path, text: str = BY_REFERENCE) -> Project:
    (tmp_path / "databricks.yml").write_text(DEPLOYS, encoding="utf-8")
    (tmp_path / "stevin.yml").write_text(text, encoding="utf-8")
    (tmp_path / "tables").mkdir(exist_ok=True)
    return Project.load(tmp_path / "stevin.yml")


@pytest.mark.parametrize(
    ("target", "prefix"), [("dev", "dev_jane_"), ("prod", "")], ids=["dev", "prod"]
)
def test_a_key_names_a_schema_the_way_the_bundle_does(
    tmp_path: Path, target: str, prefix: str
) -> None:
    """The reference is one part of the key, dots and all, and stands for the
    name this target deploys: its tables are covered, and no other schema's."""
    # RULES.md: OWN-6.
    found = by_reference(tmp_path)
    resolved = found.resolve(found.target(target), bundle_config=as_the_cli_says(prefix))
    owners = found.owners(resolved)
    assert owners.patterns == (
        (f"main.{prefix}raw.*", "dlt"),
        (f"main.{prefix}silver.*", "dbt"),
    )
    assert owners.owner_of(f"main.{prefix}raw.customers") == "dlt"
    assert owners.owner_of(f"main.{prefix}silver.orders") == "dbt"
    assert owners.owner_of("main.gold.customers") is None
    assert owners.owner_of("main.other_raw.customers") is None
    if prefix:
        assert owners.owner_of("main.raw.customers") is None, "another target's name"


def test_production_needs_no_cli_for_a_name_the_file_settles(tmp_path: Path) -> None:
    found = by_reference(tmp_path)
    owners = found.owners(found.target("prod"))
    assert owners.owner_of("main.raw.customers") == "dlt"


@pytest.mark.parametrize(
    ("target", "prefix"), [("dev", "dev_jane_"), ("prod", "")], ids=["dev", "prod"]
)
def test_a_key_by_reference_decides_what_a_spec_may_say(
    tmp_path: Path, target: str, prefix: str
) -> None:
    """The map says the raw schema is dlt's, so a spec without types governs a
    table in it — no `_dlt_` tables are there to say so. The silver schema is
    dbt's, and a spec for a table in it is refused, as it is by a written name."""
    found = by_reference(tmp_path)
    resolved = found.resolve(found.target(target), bundle_config=as_the_cli_says(prefix))
    (tmp_path / "tables" / "customers.yml").write_text(
        GOVERN_BY_REFERENCE, encoding="utf-8"
    )
    live = table(col("id", "bigint"), name=f"main.{prefix}raw.customers")
    assert [d for d in api.validate(found, resolved) if d.severity == "warning"] == []
    plan = api.plan(found, resolved, Connection(runner=FakeWarehouse.of(live)))
    assert {change.kind for change in plan.changes} == {"set_tag", "grant"}
    assert not any("CLAIM" in step.title for step in plan.steps)

    (tmp_path / "tables" / "orders.yml").write_text(SHAPE_BY_REFERENCE, encoding="utf-8")
    refusal = rf"orders.yml: main.{prefix}silver.orders is dbt's"
    assert any(
        "is dbt's" in d.message
        for d in api.validate(found, resolved)
        if d.severity == "error"
    )
    with pytest.raises(PlanningError, match=refusal):
        api.plan(found, resolved, Connection(runner=FakeWarehouse.of(live)))


def test_a_reference_with_no_value_is_an_error_at_the_key(tmp_path: Path) -> None:
    """A pattern that was quietly left out would let stevin claim another tool's
    table. So the key is named, with its file, line and column."""
    # RULES.md: OWN-8.
    found = by_reference(tmp_path)
    # A development target renames, and no Databricks CLI is here to say how.
    with pytest.raises(SpecError) as unsettled:
        found.owners(found.resolve(found.target("dev")))
    assert unsettled.value.loc.file == tmp_path / "stevin.yml"
    assert (unsettled.value.loc.line, unsettled.value.loc.column) == (4, 3)
    said = unsettled.value.message
    assert "owned_elsewhere key '${catalog}.${resources.schemas.raw.name}.*'" in said
    assert "for target 'dev'" in said and "comes from the bundle" in said

    # A resource the bundle doesn't declare.
    typo = by_reference(
        tmp_path,
        "specs: [tables]\nbundle: databricks.yml\n"
        "owned_elsewhere:\n  main.silver.*: dbt\n"
        "  ${catalog}.${resources.schemas.rwa.name}.*: dlt\n",
    )
    with pytest.raises(SpecError, match="undefined variable") as unknown:
        typo.owners(typo.target("prod"))
    assert str(unknown.value).startswith(f"{(tmp_path / 'stevin.yml').as_posix()}:5:3: ")
    assert "${resources.schemas.rwa.name}" in unknown.value.message

    # No bundle at all, so nothing by that name.
    (tmp_path / "stevin.yml").write_text(
        "specs: [tables]\ntargets:\n  dev:\n    vars: {catalog: dev}\n"
        "owned_elsewhere:\n  ${catalog}.${resources.schemas.raw.name}.*: dlt\n",
        encoding="utf-8",
    )
    alone = Project.load(tmp_path / "stevin.yml")
    with pytest.raises(SpecError, match=r"stevin.yml:6:3: .*undefined variable"):
        alone.owners(alone.target("dev"))
    [diagnostic] = api.validate(alone, alone.target("dev"))
    assert diagnostic.severity == "error" and diagnostic.where.endswith("stevin.yml:6:3")


@pytest.mark.parametrize(
    ("value", "shown"), [("dev.raw", "'dev.raw'"), ("*", "'*'"), ("", "''")]
)
def test_what_a_reference_stands_for_is_one_name(
    tmp_path: Path, value: str, shown: str
) -> None:
    """A value with a dot is not two parts, and a `*` from a variable is not a
    pattern: either would cover names nobody wrote down."""
    # RULES.md: OWN-8.
    (tmp_path / "stevin.yml").write_text(
        "specs: [tables]\n"
        f"targets:\n  dev:\n    vars: {{catalog: dev, where: '{value}'}}\n"
        "owned_elsewhere:\n  ${catalog}.${where}.*: dbt\n",
        encoding="utf-8",
    )
    found = Project.load(tmp_path / "stevin.yml")
    with pytest.raises(SpecError, match="a name with no dot and no") as refused:
        found.owners(found.target("dev"))
    assert f"${{where}} is {shown} for target 'dev'" in refused.value.message
    assert (refused.value.loc.line, refused.value.loc.column) == (6, 3)


@pytest.mark.parametrize(
    "key",
    [
        "${resources.schemas.raw.name}.*",
        "${catalog}.${resources.schemas.raw.name}",
        "${catalog}.${resources.schemas.raw.name}.orders.v2",
        "${catalog}..orders",
    ],
)
def test_a_key_is_three_parts_however_many_dots_a_reference_holds(
    tmp_path: Path, key: str
) -> None:
    with pytest.raises(SpecError, match="keyed catalog.schema.table"):
        by_reference(
            tmp_path,
            f"specs: [tables]\nbundle: databricks.yml\nowned_elsewhere:\n  {key}: dbt\n",
        )


def test_validate_reads_a_key_by_reference_without_asking_the_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`validate` runs nothing, so a development target's name is not known to
    it. The same name stands in for the reference in the key and in a spec:
    dbt's table is still refused, and the governed one is known to be dlt's."""
    from typer.testing import CliRunner

    from helpers import fake_databricks
    from stevin import cli

    by_reference(tmp_path)
    (tmp_path / "tables" / "customers.yml").write_text(
        GOVERN_BY_REFERENCE, encoding="utf-8"
    )
    asked = tmp_path / "asked.txt"
    monkeypatch.setenv("PATH", fake_databricks(tmp_path, "{}\n", asked=asked))
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli.app, ["validate"])
    said = " ".join(result.output.split())
    assert result.exit_code == 0, result.output
    assert "nothing here says whose" not in said
    assert "Not settled here: ${resources.schemas.raw.name}" in said
    assert "${resources.schemas.silver.name}" in said, "the key that uses it is named"

    (tmp_path / "tables" / "orders.yml").write_text(SHAPE_BY_REFERENCE, encoding="utf-8")
    result = CliRunner().invoke(cli.app, ["validate"])
    assert result.exit_code == 1, result.output
    assert "is dbt's" in result.output
    assert not asked.exists()

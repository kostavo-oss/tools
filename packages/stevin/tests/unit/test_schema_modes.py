"""`schemas:` in the project file: a schema's own mode, by `catalog.schema`.

A key may name its schema the way a bundle does. The reference is one part of
the key and stands for the name the target deploys, and a key that has no one
name for a target is an error at the key: a key that was left out would give
its schema the target's mode, which is not what the file says.
"""

from pathlib import Path

import pytest

from fake_warehouse import FakeWarehouse
from helpers import col, table
from stevin import api
from stevin.connect import Connection
from stevin.loader import Project, SpecError
from stevin.model.table import MANAGED_PROPERTY

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
targets:
  dev:
    default: true
    mode: development
  prod: {}
"""
BY_REFERENCE = """\
specs: [tables]
bundle: databricks.yml
schemas:
  ${catalog}.${resources.schemas.raw.name}: strict
"""
ORDERS = (
    "table: ${catalog}.${resources.schemas.raw.name}.orders\n"
    "columns:\n  - {name: id, type: bigint}\n"
)
MANAGED = ((MANAGED_PROPERTY, "true"),)


def as_the_cli_says(prefix: str) -> dict[str, object]:
    """What `databricks bundle validate -o json` prints for a target whose
    schema is deployed with this in front of its name."""
    return {
        "variables": {"catalog": {"value": "main"}},
        "resources": {
            "schemas": {"raw": {"catalog_name": "main", "name": f"{prefix}raw"}}
        },
    }


def by_reference(tmp_path: Path, text: str = BY_REFERENCE) -> Project:
    (tmp_path / "databricks.yml").write_text(DEPLOYS, encoding="utf-8")
    (tmp_path / "stevin.yml").write_text(text, encoding="utf-8")
    (tmp_path / "tables").mkdir(exist_ok=True)
    (tmp_path / "tables" / "orders.yml").write_text(ORDERS, encoding="utf-8")
    return Project.load(tmp_path / "stevin.yml")


@pytest.mark.parametrize(
    ("target", "prefix"), [("dev", "dev_jane_"), ("prod", "")], ids=["dev", "prod"]
)
def test_a_key_names_a_schema_the_way_the_bundle_does(
    tmp_path: Path, target: str, prefix: str
) -> None:
    """The reference is one part of the key, dots and all, and stands for the
    name this target deploys: that schema is strict, and no other is."""
    # RULES.md: OWN-9.
    found = by_reference(tmp_path)
    resolved = found.resolve(found.target(target), bundle_config=as_the_cli_says(prefix))
    assert found.modes(resolved) == {f"main.{prefix}raw": "strict"}
    assert found.mode_for(resolved, f"MAIN.{prefix}RAW") == "strict"
    assert found.mode_for(resolved, "main.other") == "additive"
    if prefix:
        assert found.mode_for(resolved, "main.raw") == "additive", "another target's"

    # And a plan keeps to it: what stevin made and no spec describes is dropped
    # in the schema the key names, and stays in the one beside it.
    fake = FakeWarehouse.of(
        table(col("id", "bigint"), name=f"main.{prefix}raw.orders", properties=MANAGED),
        table(col("id", "bigint"), name=f"main.{prefix}raw.gone", properties=MANAGED),
    )
    plan = api.plan(found, resolved, Connection(runner=fake))
    assert [(c.table, c.kind) for c in plan.changes] == [
        (f"main.{prefix}raw.gone", "drop_table")
    ]


def test_a_reference_with_no_value_is_an_error_at_the_key(tmp_path: Path) -> None:
    """Left out, the schema would get the target's mode: under a strict target a
    schema the file says to keep would have its orphans dropped. So the key is
    named, with its file, line and column, and nothing is read or planned."""
    # RULES.md: OWN-9.
    found = by_reference(tmp_path)
    # A development target renames, and no Databricks CLI is here to say how.
    dev = found.resolve(found.target("dev"))
    with pytest.raises(SpecError) as unsettled:
        found.modes(dev)
    assert unsettled.value.loc.file == tmp_path / "stevin.yml"
    assert (unsettled.value.loc.line, unsettled.value.loc.column) == (4, 3)
    said = unsettled.value.message
    assert "schemas key '${catalog}.${resources.schemas.raw.name}'" in said
    assert "for target 'dev'" in said and "comes from the bundle" in said

    # A variable one target has and the other does not, under a strict target.
    (tmp_path / "stevin.yml").write_text(
        "specs: [tables]\n"
        "targets:\n"
        "  dev:\n    vars: {catalog: dev, keep: archive}\n"
        "  prod:\n    vars: {catalog: prod}\n    mode: strict\n"
        "schemas:\n  ${catalog}.${keep}: additive\n",
        encoding="utf-8",
    )
    (tmp_path / "tables" / "orders.yml").write_text(
        "table: ${catalog}.archive.orders\ncolumns:\n  - {name: id, type: bigint}\n",
        encoding="utf-8",
    )
    uneven = Project.load(tmp_path / "stevin.yml")
    assert uneven.mode_for(uneven.target("dev"), "dev.archive") == "additive"
    prod = uneven.target("prod")
    fake = FakeWarehouse.of(
        table(col("id", "bigint"), name="prod.archive.orders", properties=MANAGED),
        table(col("id", "bigint"), name="prod.archive.kept", properties=MANAGED),
    )
    with pytest.raises(SpecError, match=r"stevin.yml:9:3: .*undefined variable"):
        api.plan(uneven, prod, Connection(runner=fake))
    assert fake.statements == [], "refused before the workspace is read"
    with pytest.raises(SpecError, match=r"\$\{keep\}"):
        uneven.mode_for(prod, "prod.archive")
    [diagnostic] = api.validate(uneven, prod)
    assert diagnostic.severity == "error" and diagnostic.where.endswith("stevin.yml:9:3")
    assert "schemas key '${catalog}.${keep}', for target 'prod'" in diagnostic.message


@pytest.mark.parametrize(
    ("value", "shown"), [("dev.raw", "'dev.raw'"), ("*", "'*'"), ("", "''")]
)
def test_what_a_reference_stands_for_is_one_name(
    tmp_path: Path, value: str, shown: str
) -> None:
    (tmp_path / "stevin.yml").write_text(
        "specs: [tables]\n"
        f"targets:\n  dev:\n    vars: {{catalog: dev, where: '{value}'}}\n"
        "schemas:\n  ${catalog}.${where}: strict\n",
        encoding="utf-8",
    )
    found = Project.load(tmp_path / "stevin.yml")
    with pytest.raises(SpecError, match="one part of catalog.schema — a name") as refused:
        found.modes(found.target("dev"))
    assert f"${{where}} is {shown} for target 'dev'" in refused.value.message
    assert (refused.value.loc.line, refused.value.loc.column) == (6, 3)


@pytest.mark.parametrize(
    "key",
    [
        "${resources.schemas.raw.name}",
        "${catalog}.${resources.schemas.raw.name}.orders",
        "${catalog}.",
        ".${resources.schemas.raw.name}",
    ],
)
def test_a_key_is_two_parts_however_many_dots_a_reference_holds(
    tmp_path: Path, key: str
) -> None:
    with pytest.raises(SpecError, match=r"stevin.yml:4:3: schemas are keyed"):
        by_reference(
            tmp_path,
            f"specs: [tables]\nbundle: databricks.yml\nschemas:\n  {key}: strict\n",
        )


def test_validate_reads_a_key_by_reference_without_asking_the_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`validate` runs nothing, so a development target's name is not known to
    it. A name stands in for the reference, as it does in a spec, and the line
    at the end says which references were left unsettled."""
    from typer.testing import CliRunner

    from helpers import fake_databricks
    from stevin import cli

    by_reference(tmp_path)
    (tmp_path / "tables" / "orders.yml").write_text(
        "table: ${catalog}.sales.orders\ncolumns:\n  - {name: id, type: bigint}\n",
        encoding="utf-8",
    )
    asked = tmp_path / "asked.txt"
    monkeypatch.setenv("PATH", fake_databricks(tmp_path, "{}\n", asked=asked))
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli.app, ["validate"])
    said = " ".join(result.output.split())
    assert result.exit_code == 0, result.output
    assert "Not settled here: ${resources.schemas.raw.name}" in said
    assert not asked.exists()

    (tmp_path / "stevin.yml").write_text(
        BY_REFERENCE + "  ${catalog}.${resources.schemas.rwa.name}: strict\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(cli.app, ["validate"])
    said = " ".join(result.output.split())
    assert result.exit_code == 1, result.output
    assert "stevin.yml:5:3: schemas key" in said and "undefined variable" in said
    assert not asked.exists()

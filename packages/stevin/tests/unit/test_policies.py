"""The ABAC policies a table is under: read into the plan, never written.

A policy defined on a catalog or a schema reaches every table below it, so a
table stevin plans can be filtered or masked by something no spec mentions.
These hold stevin to reading those policies (`SHOW EFFECTIVE POLICIES`, then
`DESCRIBE POLICY`), to showing them wherever a plan is shown, to warning where a
spec's own mask or row filter meets one — and to never making a step of any of
it, and never failing a plan because a workspace wouldn't say.

What they can't hold it to is what a workspace answers. The fake speaks as one
did on 2026-10-10 — `tests/integration/test_live_policies.py` and the three
policy probes in `probes.py` are what asked it.
https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-show-policies
https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-describe-policy
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion
from typer.testing import CliRunner

from fake_warehouse import FakeSqlError, FakeWarehouse
from helpers import col, table
from stevin import api, cli, doctor
from stevin.connect import Connection
from stevin.differ import ONE_FILTER_ONE_MASK, POLICY_LIMITS, policy_conflicts
from stevin.executor import ExecutionError, StalePlan
from stevin.history import MemoryHistory
from stevin.introspect import Introspector, Row
from stevin.loader import Project
from stevin.manage import Manage
from stevin.model.plan import Plan, fingerprint
from stevin.model.policy import Policy
from stevin.model.table import MANAGED_PROPERTY, Grant, RowFilter, Table
from stevin.model.types import GovernedColumn, Mask
from stevin.owned import Owners
from stevin.planning import plan_tables
from stevin.render.html import render_html
from stevin.render.json import dumps, loads, plan_to_dict
from stevin.render.labels import policy_line
from stevin.render.markdown import render_markdown
from stevin.render.rich import plan_text

NAME = "main.sales.customers"

CUSTOMERS = replace(
    table(
        col("id", "bigint"),
        col("email", "string"),
        col("region", "string"),
        name=NAME,
    ),
    properties=((MANAGED_PROPERTY, "true"),),
)
ORDERS = replace(
    table(col("id", "bigint"), name="main.sales.orders"),
    properties=((MANAGED_PROPERTY, "true"),),
)

MASK_PII = Policy(
    "mask_pii",
    "column_mask",
    "main.sales",
    "schema",
    function="main.governance.redact",
    to=("account users",),
    except_=("data_admins",),
    match_columns="has_tag('pii') AS c",
    on_column="c",
    comment="Hide personal data",
)
OWN_REGION = Policy(
    "own_region",
    "row_filter",
    "main",
    "catalog",
    function="main.governance.in_region",
    to=("analysts",),
    when="has_tag('regional')",
)
ON_THE_TABLE = Policy(
    "eu_only", "row_filter", NAME, "table", function="main.governance.eu", to=("eu",)
)


def warehouse(*policies: Policy) -> FakeWarehouse:
    return FakeWarehouse.of(CUSTOMERS, ORDERS).under(*policies)


def planned(
    fake: FakeWarehouse,
    *specs: Table,
    manage: Manage | None = None,
    owners: Owners | None = None,
    strict: bool = False,
    clone: bool = False,
) -> Plan:
    manage = manage or Manage()
    return plan_tables(
        list(specs) or [CUSTOMERS],
        Introspector(fake, manage),
        target="dev",
        tool_version="0",
        manage=manage,
        owners=owners,
        mode_for=lambda _schema: "strict" if strict else "additive",
        clone=clone,
    )


def about_policies(fake: FakeWarehouse) -> list[str]:
    return [s for s in fake.statements if "POLIC" in s.upper()]


class Answering:
    """A warehouse that answers the two policy statements with canned rows."""

    def __init__(
        self, fake: FakeWarehouse, shown: tuple[Row, ...], described: tuple[Row, ...]
    ) -> None:
        self.fake, self.shown, self.described = fake, shown, described

    def query(self, statement: str) -> tuple[Row, ...]:
        if statement.startswith("SHOW EFFECTIVE POLICIES"):
            return self.shown
        if statement.startswith("DESCRIBE POLICY"):
            return self.described
        return self.fake.query(statement)


# ---------------------------------------------------------------------------
# the reader
# ---------------------------------------------------------------------------


def test_the_policies_in_scope_are_read_into_the_model() -> None:
    """On the table, on its schema and on its catalog — sorted, each with what
    `DESCRIBE POLICY` adds."""
    fake = warehouse(OWN_REGION, MASK_PII, ON_THE_TABLE)
    live = Introspector(fake).table(NAME)
    assert live is not None
    assert live.policies == (ON_THE_TABLE, MASK_PII, OWN_REGION)
    assert live.policies_unread is None
    assert (
        "SHOW EFFECTIVE POLICIES ON TABLE `main`.`sales`.`customers`" in fake.statements
    )
    assert "DESCRIBE POLICY `mask_pii` ON SCHEMA `main`.`sales`" in fake.statements
    assert "DESCRIBE POLICY `own_region` ON CATALOG `main`" in fake.statements


def test_a_policy_on_another_table_is_not_this_tables() -> None:
    fake = warehouse(ON_THE_TABLE)
    other = Introspector(fake).table("main.sales.orders")
    assert other is not None
    assert other.policies == ()


def test_a_policy_is_described_once_however_many_tables_it_reaches() -> None:
    fake = warehouse(MASK_PII)
    Introspector(fake).schema("main", "sales")
    assert len([s for s in fake.statements if s.startswith("DESCRIBE POLICY")]) == 1
    assert len([s for s in fake.statements if s.startswith("SHOW EFFECTIVE")]) == 2


def test_only_the_tables_read_in_full_are_asked_about() -> None:
    """A table no spec describes gets a light read: listing it doesn't need
    its policies, and each is a statement."""
    fake = warehouse(MASK_PII)
    Introspector(fake).schema("main", "sales", full=[NAME])
    assert about_policies(fake) == [
        "SHOW EFFECTIVE POLICIES ON TABLE `main`.`sales`.`customers`",
        "DESCRIBE POLICY `mask_pii` ON SCHEMA `main`.`sales`",
    ]


def test_columns_the_workspace_leaves_out_are_done_without() -> None:
    """The reader goes by column name and takes what is there: a name is
    enough for a policy, and where it is defined is worked out from the
    catalog, schema and table columns when the two `on_securable_*` are not."""
    shown: tuple[Row, ...] = (
        {"Policy Name": "bare"},
        {"policy_name": "placed", "POLICY TYPE": "ROW_FILTER", "Catalog": "main"},
        {"Policy Type": "COLUMN_MASK", "Comment": "no name: not a policy"},
    )
    runner = Answering(warehouse(), shown, described=())
    live = Introspector(runner).table(NAME)
    assert live is not None
    assert live.policies == (
        Policy("bare", "policy", "", "metastore"),
        Policy("placed", "row_filter", "main", "catalog"),
    )
    assert live.policies_unread is None


@pytest.mark.parametrize(
    "described",
    [
        (
            {"info_name": "Name", "info_value": "mask_pii"},
            {"info_name": "To Principals", "info_value": "`b team`, a"},
            {"info_name": "  Function Name", "info_value": "main.governance.redact"},
            {"info_name": "Created At", "info_value": "2026-01-01"},
            {"info_name": "Except Principals", "info_value": None},
        ),
        (
            {"report": "Name                    mask_pii"},
            {"report": "To Principals           `b team`, a"},
            {"report": "  Function Name         main.governance.redact"},
            {"report": "Created At              2026-01-01"},
            {"report": ""},
        ),
    ],
    ids=["two columns", "one column of text"],
)
def test_a_description_is_read_by_position_not_by_column_name(
    described: tuple[Row, ...],
) -> None:
    """The manual shows `DESCRIBE POLICY`'s labels and not its columns, so the
    first value of a row is the label and the second the value — or, where the
    report is one column of text, the two sides of its gap. Labels stevin
    doesn't know are ignored; ones that aren't there leave their field empty."""
    shown: tuple[Row, ...] = (
        {
            "Policy Name": "mask_pii",
            "Policy Type": "COLUMN_MASK",
            "on_securable_type": "SCHEMA",
            "on_securable_fullname": "main.sales",
        },
    )
    live = Introspector(Answering(warehouse(), shown, described)).table(NAME)
    assert live is not None
    assert live.policies == (
        Policy(
            "mask_pii",
            "column_mask",
            "main.sales",
            "schema",
            function="main.governance.redact",
            to=("a", "b team"),
        ),
    )


def test_handing_policies_over_sends_no_statement_about_them() -> None:
    fake = warehouse(MASK_PII, OWN_REGION)
    plan = planned(fake, manage=Manage(("policies",)))
    assert about_policies(fake) == []
    assert plan.diffs[0].facts.policies == ()
    assert plan.policies_unread is None
    assert "policies are managed elsewhere" in plan_text(plan)


def test_the_project_file_can_hand_policies_over(tmp_path: Path) -> None:
    (tmp_path / "stevin.yml").write_text(
        "specs: [tables]\nmanage:\n  policies: false\n"
        "targets:\n  dev:\n    default: true\n    vars: {catalog: main}\n"
    )
    project = Project.load(tmp_path / "stevin.yml")
    assert project.manage.elsewhere == ("policies",)
    assert not project.manage.manages("policies")


def test_import_and_adopt_show_no_policies_and_so_ask_for_none(
    tmp_path: Path,
) -> None:
    """Each table's policies are a statement apiece. A command that writes
    spec files has nowhere to say them, so it doesn't ask."""
    fake = warehouse(MASK_PII, OWN_REGION)
    connection = Connection(runner=fake)
    api.import_schema(connection, "main.sales")
    project = project_at(tmp_path)
    assert project.default is not None
    api.adopt(project, project.default, connection)
    assert about_policies(fake) == []
    assert Manage(("grants",)).without_policies() == Manage(("grants", "policies"))


# ---------------------------------------------------------------------------
# a workspace that won't say
# ---------------------------------------------------------------------------

REFUSAL = "[PARSE_SYNTAX_ERROR] Syntax error at or near 'EFFECTIVE'. SQLSTATE: 42601"


def test_a_refused_statement_does_not_fail_the_plan_and_is_said_once() -> None:
    fake = warehouse(MASK_PII)
    fake.refusals["SHOW EFFECTIVE POLICIES"] = REFUSAL
    wanted = replace(ORDERS, comment="Order facts")
    plan = planned(fake, CUSTOMERS, wanted)
    assert [d.facts.policies for d in plan.diffs] == [(), ()]
    assert plan.policies_unread == ((NAME, ORDERS.name), f"FAILED: {REFUSAL}")
    assert [step.title for step in plan.steps] == ["COMMENT ON TABLE"]
    said = f"policies could not be read: FAILED: {REFUSAL} (2 tables;"
    for rendered in (
        plan_text(plan, width=400),
        render_markdown(plan),
        render_html(plan).replace("&#x27;", "'"),
    ):
        assert rendered.count(said) == 1, rendered
        # The statement itself stays out of it: the reason is one line.
        assert "SHOW EFFECTIVE POLICIES ON TABLE" not in rendered


def test_a_refused_read_is_still_a_plan_that_applies() -> None:
    fake = warehouse(MASK_PII)
    fake.refusals["SHOW EFFECTIVE POLICIES"] = REFUSAL
    plan = planned(fake, replace(CUSTOMERS, comment="Customers"))
    result = api.apply(plan, Connection(runner=fake), history=MemoryHistory())
    assert result.ok, result.error
    assert fake.tables[NAME].comment == "Customers"


def test_only_the_workspaces_refusal_is_taken_quietly() -> None:
    """A statement shape the fake doesn't know is a bug in stevin's SQL, and
    whatever else goes wrong is not an answer about policies: both still stop."""
    fake = warehouse()
    fake.failures["SHOW EFFECTIVE POLICIES"] = "boom"
    with pytest.raises(FakeSqlError, match="boom"):
        planned(fake)


def test_a_policy_that_cant_be_described_is_still_shown() -> None:
    """Describing takes a privilege on the securable the policy is defined on,
    which a reader of the table needn't have: the policy is named, placed, and
    said to be unreadable beyond that."""
    fake = warehouse(MASK_PII)
    fake.refusals["DESCRIBE POLICY"] = "[INSUFFICIENT_PERMISSIONS] no READ METADATA"
    plan = planned(fake)
    assert plan.diffs[0].facts.policies == (
        Policy(
            "mask_pii", "column_mask", "main.sales", "schema", comment=MASK_PII.comment
        ),
    )
    assert plan.policies_unread is None
    assert (
        "policy mask_pii (column mask, on schema main.sales) — its details can't "
        "be read from here"
    ) in plan_text(plan, width=400)


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------


def test_policies_are_facts_and_never_a_step_or_a_change() -> None:
    # RULES.md: ACC-3.
    plan = planned(warehouse(MASK_PII, OWN_REGION))
    [diff] = plan.diffs
    assert diff.facts.policies == (MASK_PII, OWN_REGION)
    assert diff.changes == ()
    assert plan.steps == ()
    assert plan.empty


def test_the_line_says_what_who_and_from_where() -> None:
    assert policy_line(MASK_PII) == (
        "policy mask_pii (column mask, on schema main.sales) masks columns matching "
        "has_tag('pii') AS c with main.governance.redact, for account users except "
        "data_admins"
    )
    assert policy_line(OWN_REGION) == (
        "policy own_region (row filter, on catalog main) filters rows with "
        "main.governance.in_region when has_tag('regional'), for analysts"
    )
    assert policy_line(Policy("p", "grant", "", "metastore", to=("a", "b"))) == (
        "policy p (grant, on the metastore) applies, for a and b"
    )


def test_the_terminal_shows_them_under_the_table(snapshot: SnapshotAssertion) -> None:
    wanted = replace(CUSTOMERS, columns=(*CUSTOMERS.columns, col("signed_up", "date")))
    assert plan_text(planned(warehouse(MASK_PII, OWN_REGION), wanted)) == snapshot


def test_an_unchanged_table_under_a_policy_is_still_shown() -> None:
    """Nothing to do is not nothing to see: the table is in sync, and filtered
    by something its spec doesn't mention."""
    plan = planned(warehouse(OWN_REGION))
    rich = plan_text(plan, width=400)
    assert "sales.customers" in rich
    assert f"· {policy_line(OWN_REGION)} — not stevin's, left untouched" in rich
    assert "No changes." in rich
    markdown = render_markdown(plan)
    assert (
        f"<sub>`sales.customers`: {policy_line(OWN_REGION)} — not stevin's, left "
        "untouched</sub>"
    ) in markdown
    assert "No changes." in markdown
    assert policy_line(OWN_REGION) in render_html(plan).replace("&#x27;", "'")


def test_markdown_and_the_page_show_them_under_a_changing_table() -> None:
    wanted = replace(CUSTOMERS, comment="Customers")
    plan = planned(warehouse(MASK_PII), wanted)
    line = policy_line(MASK_PII)
    markdown = render_markdown(plan)
    assert f"<sub>{line} — not stevin's, left untouched</sub>" in markdown
    assert markdown.index("<details open>") < markdown.index(line)
    assert markdown.index(line) < markdown.rindex("</details>")
    page = render_html(plan).replace("&#x27;", "'")
    assert "in scope, not stevin's, left alone:<br>" + line in page


def test_a_plan_file_carries_them_there_and_back() -> None:
    fake = warehouse(MASK_PII, OWN_REGION)
    spec = replace(
        CUSTOMERS,
        row_filter=RowFilter("main.security.by_region", ("region",)),
        comment="Customers",
    )
    plan = planned(fake, spec)
    assert plan.diffs[0].cautions, "the round trip should carry a warning too"
    assert loads(dumps(plan)) == plan
    facts = plan_to_dict(plan)["tables"][0]["facts"]
    assert facts["policies"][0] == {
        "name": "mask_pii",
        "kind": "column_mask",
        "on": "main.sales",
        "level": "schema",
        "function": "main.governance.redact",
        "to": ["account users"],
        "except": ["data_admins"],
        "when": None,
        "match_columns": "has_tag('pii') AS c",
        "on_column": "c",
        "comment": "Hide personal data",
    }
    assert facts["policies_unread"] is None


def test_a_plan_file_from_before_policies_were_read_still_loads() -> None:
    document = plan_to_dict(planned(warehouse()))
    for entry in document["tables"]:
        del entry["cautions"], entry["facts"]["policies"]
        del entry["facts"]["policies_unread"]
    plan = loads(json.dumps(document))
    assert plan.diffs[0].facts.policies == ()
    assert plan.diffs[0].cautions == ()
    assert api.is_stale(plan, Connection(runner=warehouse())) is False


# ---------------------------------------------------------------------------
# the plan goes stale with them, as it does with a table's own mask
# ---------------------------------------------------------------------------


def test_a_workspace_without_policies_fingerprints_as_it_always_did() -> None:
    assert fingerprint([CUSTOMERS]) == fingerprint([CUSTOMERS], {NAME: ()})
    assert fingerprint([CUSTOMERS]) != fingerprint([CUSTOMERS], {NAME: (MASK_PII,)})


def test_a_plan_is_not_stale_the_moment_it_is_made() -> None:
    fake = warehouse(MASK_PII, OWN_REGION)
    plan = loads(dumps(planned(fake, replace(CUSTOMERS, comment="Customers"))))
    assert api.is_stale(plan, Connection(runner=fake)) is False
    assert api.apply(plan, Connection(runner=fake), history=MemoryHistory()).ok


def test_a_policy_that_arrives_after_the_plan_makes_it_stale() -> None:
    """What was reviewed was a table under one policy. Under two it is not the
    table that was reviewed — and the new one may meet the spec's own mask."""
    # RULES.md: ACC-5.
    fake = warehouse(MASK_PII)
    plan = planned(fake, replace(CUSTOMERS, comment="Customers"), ORDERS)
    fake.under(ON_THE_TABLE)
    connection = Connection(runner=fake)
    assert api.is_stale(plan, connection) is True
    with pytest.raises(StalePlan, match=r"\(main\.sales\.customers\)"):
        api.apply(plan, connection, history=MemoryHistory())
    assert fake.tables[NAME].comment is None


def test_a_table_dropped_from_a_strict_schema_is_read_with_its_policies() -> None:
    """An orphan gets a light read until strict mode decides to drop it; then
    it is read in full, policies and all — as `apply` will read it again."""
    fake = warehouse(MASK_PII)
    plan = planned(fake, ORDERS, strict=True)
    [drop] = [d for d in plan.diffs if d.table == NAME]
    assert drop.facts.policies == (MASK_PII,)
    assert api.is_stale(plan, Connection(runner=fake)) is False


# ---------------------------------------------------------------------------
# a rewrite of a table under a policy
# ---------------------------------------------------------------------------

#: `id` from bigint to string is no widening: the values are converted, so the
#: rewrite is staged.
CONVERTED = replace(CUSTOMERS, columns=(col("id", "string"), *CUSTOMERS.columns[1:]))
#: Partitioning changes only by a rewrite, and converts nothing: one statement.
PARTITIONED = replace(CUSTOMERS, partitioned_by=("region",))

NOT_READ = "stevin did not read the ABAC policies in scope of this table"


def titles(plan: Plan) -> list[str]:
    return [step.title for step in plan.steps]


def refuses(fake: FakeWarehouse, plan: Plan) -> None:
    """`apply` runs nothing of a plan that holds a step without SQL."""
    with pytest.raises(ExecutionError, match="can't run"):
        api.apply(plan, Connection(runner=fake), history=MemoryHistory())
    assert fake.ddl == []


@pytest.mark.parametrize(
    ("policy", "named"),
    [
        (ON_THE_TABLE, "the row filter policy eu_only is in scope of this table"),
        (MASK_PII, "the column mask policy mask_pii is in scope of this table"),
        (OWN_REGION, "the row filter policy own_region is in scope of this table"),
    ],
    ids=["a row filter on the table", "a mask on the schema", "a filter on the catalog"],
)
def test_a_table_under_a_policy_is_never_rewritten(policy: Policy, named: str) -> None:
    """The staging copy is a table the policy needn't cover, and what the
    rewrite reads is what the applying principal may see. Neither is planned."""
    # RULES.md: RW-4.
    fake = warehouse(policy)
    plan = planned(fake, CONVERTED)
    assert [(s.title, s.risk, s.sql) for s in plan.steps] == [
        ("REWRITE", "rewrite", None)
    ]
    assert plan.steps[0].note == (
        f"{named}. A rewrite would read the table as the applying principal sees "
        "it, masked or filtered, into a staging table the policy may not cover, "
        "and write that back over the table. Rewrite it by hand"
    )
    refuses(fake, plan)


def test_every_policy_in_the_way_is_named() -> None:
    plan = planned(warehouse(ON_THE_TABLE, MASK_PII), CONVERTED)
    assert (plan.steps[0].note or "").startswith(
        "the row filter policy eu_only and the column mask policy mask_pii are in "
        "scope of this table. "
    )


def test_the_one_statement_rewrite_is_refused_too() -> None:
    """It has no staging table, and still writes what the principal reads over
    the table."""
    fake = warehouse(ON_THE_TABLE)
    plan = planned(fake, PARTITIONED)
    assert [(s.title, s.sql) for s in plan.steps] == [("REWRITE", None)]
    note = plan.steps[0].note or ""
    assert "masked or filtered, and write that back over the table" in note
    assert "staging" not in note
    refuses(fake, plan)
    # Without the policy it is the one statement.
    assert titles(planned(warehouse(), PARTITIONED)) == ["REPLACE TABLE"]


def test_a_policy_that_is_not_this_tables_refuses_nothing() -> None:
    """One on another table, and one that is neither a filter nor a mask."""
    elsewhere = replace(ON_THE_TABLE, on=ORDERS.name)
    granting = Policy("let_in", "grant", "main.sales", "schema", to=("analysts",))
    fake = warehouse(elsewhere, granting)
    plan = planned(fake, CONVERTED, ORDERS)
    assert titles(plan) == ["STAGE rewritten data", "REPLACE TABLE", "DROP staging"]
    assert all(step.sql and not step.warnings for step in plan.steps)
    result = api.apply(plan, Connection(runner=fake), history=MemoryHistory())
    assert result.ok, result.error


def test_what_is_no_rewrite_is_planned_as_before_under_a_policy() -> None:
    """A policy stops the copy and nothing else: a column, a grant, a comment."""
    wanted = replace(
        CUSTOMERS,
        columns=(*CUSTOMERS.columns, col("segment", "string")),
        comment="Customers",
        grants=(Grant("analysts", ("SELECT",)),),
    )
    fake = warehouse(ON_THE_TABLE, MASK_PII)
    plan = planned(fake, wanted)
    assert titles(plan) == ["COMMENT ON TABLE", "ADD COLUMN segment", "GRANT to analysts"]
    assert all(step.sql and not step.warnings for step in plan.steps)
    result = api.apply(plan, Connection(runner=fake), history=MemoryHistory())
    assert result.ok, result.error


@pytest.mark.parametrize("handed_over", [False, True], ids=["refused", "handed over"])
def test_a_rewrite_says_when_the_policies_were_not_read(handed_over: bool) -> None:
    """Nothing was read, so nothing can be refused: the workspace wouldn't list
    them, or the project hands them over. The rewrite is planned, and the step
    that copies the data says what stevin doesn't know."""
    # RULES.md: RW-5.
    fake = warehouse(ON_THE_TABLE)
    if not handed_over:
        fake.refusals["SHOW EFFECTIVE POLICIES"] = REFUSAL
    manage = Manage(("policies",)) if handed_over else None
    plan = planned(fake, CONVERTED, manage=manage)
    assert titles(plan) == ["STAGE rewritten data", "REPLACE TABLE", "DROP staging"]
    why = (
        "`manage: {policies: false}`"
        if handed_over
        else ("the workspace would not list them")
    )
    assert [step.warnings for step in plan.steps] == [
        (
            f"{NOT_READ} ({why}), so it cannot tell whether one masks or filters "
            "it. If one does, this rewrite reads the table as the applying "
            "principal sees it, masked or filtered, and copies that to where the "
            "policy may not reach",
        ),
        (),
        (),
    ]
    assert plan.summary.warnings == 1
    result = api.apply(plan, Connection(runner=fake), history=MemoryHistory())
    assert result.ok, result.error


def test_the_one_statement_rewrite_says_it_too_and_nothing_else_does() -> None:
    # RULES.md: RW-5.
    manage = Manage(("policies",))
    [step] = planned(warehouse(), PARTITIONED, manage=manage).steps
    assert step.title == "REPLACE TABLE"
    [warning] = step.warnings
    assert warning.startswith(f"{NOT_READ} (`manage: {{policies: false}}`)")
    # A change that copies nothing has nothing to say about it.
    commented = planned(warehouse(), replace(CUSTOMERS, comment="C"), manage=manage)
    assert [s.warnings for s in commented.steps] == [()]
    # And where the policies were read and there are none, neither has a rewrite.
    assert [s.warnings for s in planned(warehouse(), PARTITIONED).steps] == [()]


def test_a_table_under_a_policy_is_not_cloned() -> None:
    """`--clone` makes a second table over the same rows, and keeps it: the
    same copy outside the policy, so it isn't planned either."""
    # RULES.md: RW-6.
    fewer = replace(CUSTOMERS, columns=CUSTOMERS.columns[:2])
    fake = warehouse(MASK_PII)
    plan = planned(fake, fewer, clone=True)
    clone = next(step for step in plan.steps if step.title == "CLONE backup")
    assert clone.sql is None
    assert clone.note == (
        "the column mask policy mask_pii is in scope of this table, and a clone "
        "would be a copy of its data the policy may not cover. Plan without "
        "--clone: the table's Delta version is recorded either way"
    )
    refuses(fake, plan)
    # Without `--clone` the column is dropped as before.
    assert "DROP COLUMN" in titles(planned(warehouse(MASK_PII), fewer))


def test_a_clone_says_when_the_policies_were_not_read() -> None:
    """Each of the two copies says what follows for it: the clone, the rewrite."""
    plan = planned(warehouse(), CONVERTED, manage=Manage(("policies",)), clone=True)
    assert titles(plan)[:2] == ["CLONE backup", "STAGE rewritten data"]
    [[cloned], [staged]] = [step.warnings for step in plan.steps[:2]]
    assert cloned.startswith(NOT_READ)
    assert cloned.endswith("the clone is a copy the policy may not cover")
    assert staged.startswith(NOT_READ) and "this rewrite reads" in staged
    assert plan.summary.warnings == 2


FILLED = replace(
    CUSTOMERS,
    columns=(*CUSTOMERS.columns, replace(col("segment", "string"), using="'retail'")),
)


@pytest.mark.parametrize(
    ("policy", "named"),
    [
        (ON_THE_TABLE, "the row filter policy eu_only is in scope of this table"),
        (MASK_PII, "the column mask policy mask_pii is in scope of this table"),
    ],
    ids=["a row filter", "a column mask"],
)
def test_a_table_under_a_policy_is_not_backfilled(policy: Policy, named: str) -> None:
    """A `using:` fill is an UPDATE by the applying principal, who may see fewer
    rows and masked values. Under a policy that is not planned, as a rewrite and
    a clone are not."""
    # RULES.md: RW-7.
    fake = warehouse(policy)
    plan = planned(fake, FILLED)
    assert [(s.title, s.risk) for s in plan.steps] == [
        ("ADD COLUMN segment", "meta"),
        ("BACKFILL segment", "rewrite"),
    ]
    assert plan.steps[1].sql is None
    assert plan.steps[1].note == (
        f"{named}. The backfill is an UPDATE that runs as the applying principal: "
        "it fills only the rows that principal can see, whatever `using:` reads, "
        "and it writes a masked column as that principal sees it, into a column "
        "without the mask. Add the column without `using:`, and fill it by hand "
        "as a principal that sees every row"
    )
    refuses(fake, plan)
    # A policy that is neither a filter nor a mask, or on another table, stops
    # nothing.
    granting = Policy("let_in", "grant", "main.sales", "schema", to=("analysts",))
    elsewhere = replace(ON_THE_TABLE, on=ORDERS.name)
    fake = warehouse(granting, elsewhere)
    plan = planned(fake, FILLED)
    assert (plan.steps[1].sql or "").startswith("UPDATE `main`.`sales`.`customers`")
    assert plan.steps[1].warnings == ()
    result = api.apply(plan, Connection(runner=fake), history=MemoryHistory())
    assert result.ok, result.error


@pytest.mark.parametrize("handed_over", [False, True], ids=["refused", "handed over"])
def test_a_backfill_says_when_the_policies_were_not_read(handed_over: bool) -> None:
    """Nothing was read, so nothing can be refused: the fill is planned, and its
    step says what stevin doesn't know and what follows if a policy is there."""
    # RULES.md: RW-7.
    fake = warehouse(ON_THE_TABLE)
    if not handed_over:
        fake.refusals["SHOW EFFECTIVE POLICIES"] = REFUSAL
    plan = planned(fake, FILLED, manage=Manage(("policies",)) if handed_over else None)
    assert titles(plan) == ["ADD COLUMN segment", "BACKFILL segment"]
    [warning] = plan.steps[1].warnings
    assert warning.startswith(NOT_READ)
    assert warning.endswith(
        "so it cannot tell whether one masks or filters it. If one does, this "
        "backfill fills only the rows the applying principal can see, and writes "
        "a masked column as that principal sees it"
    )
    assert plan.steps[0].warnings == ()
    result = api.apply(plan, Connection(runner=fake), history=MemoryHistory())
    assert result.ok, result.error


# ---------------------------------------------------------------------------
# a spec's own mask or row filter, beside a policy's
# ---------------------------------------------------------------------------


def masked() -> Table:
    email = replace(CUSTOMERS.columns[1], mask=Mask("main.security.mask_email"))
    return replace(CUSTOMERS, columns=(CUSTOMERS.columns[0], email, CUSTOMERS.columns[2]))


def test_the_requirement_is_quoted_from_the_page_it_is_on() -> None:
    """The sentence as Databricks writes it (read 2026-10-10), and where."""
    assert ONE_FILTER_ONE_MASK == (
        "If multiple distinct row filters or column masks apply to the same user "
        "and table or column, Databricks blocks access and returns an error."
    )
    assert POLICY_LIMITS == (
        "https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/"
        "requirements"
    )


def test_a_spec_mask_beside_a_mask_policy_is_warned_about() -> None:
    [warning] = policy_conflicts(masked(), (MASK_PII, OWN_REGION))
    assert warning == (
        "the spec sets a column mask on email, and the column mask policy mask_pii "
        "is in scope of this table too. Where both reach the same reader, their "
        f"queries fail: “{ONE_FILTER_ONE_MASK}” ({POLICY_LIMITS})"
    )


def test_a_spec_row_filter_beside_filter_policies_is_warned_about() -> None:
    filtered = replace(CUSTOMERS, row_filter=RowFilter("main.security.by_region"))
    [warning] = policy_conflicts(filtered, (MASK_PII, OWN_REGION, ON_THE_TABLE))
    assert warning.startswith(
        "the spec sets a row filter, and the row filter policies own_region, "
        "eu_only are in scope of this table too."
    )
    assert ONE_FILTER_ONE_MASK in warning
    assert POLICY_LIMITS in warning


def test_different_kinds_do_not_meet() -> None:
    filtered = replace(CUSTOMERS, row_filter=RowFilter("main.security.by_region"))
    assert policy_conflicts(filtered, (MASK_PII,)) == ()
    assert policy_conflicts(masked(), (OWN_REGION,)) == ()
    assert policy_conflicts(CUSTOMERS, (MASK_PII, OWN_REGION)) == ()
    assert policy_conflicts(masked(), ()) == ()


def test_the_warning_is_on_the_table_in_every_rendering() -> None:
    """Already applied, so no step carries it: it holds of the table itself,
    and counts as a warning of the plan."""
    fake = FakeWarehouse.of(masked()).under(MASK_PII)
    plan = planned(fake, masked())
    [diff] = plan.diffs
    assert diff.changes == ()
    assert diff.cautions == policy_conflicts(masked(), (MASK_PII,))
    assert diff.warnings == diff.cautions
    assert plan.summary.warnings == 1
    [caution] = diff.cautions
    assert f"⚠ {caution}" in plan_text(plan, width=1000)
    markdown = render_markdown(plan)
    assert f"> [!WARNING]\n> `sales.customers`: {caution}" in markdown
    assert f'<div class="warn">⚠ {caution}</div>' in render_html(plan)


def test_a_governed_table_is_warned_about_too() -> None:
    """A governance-only spec sets a mask on somebody else's table: the same
    two masks meet."""
    govern = Table(
        name=NAME,
        columns=(),
        governed_columns=(GovernedColumn("email", mask=Mask("main.security.m")),),
    )
    plan = planned(
        warehouse(MASK_PII), govern, owners=Owners(patterns=(("main.sales.*", "crm"),))
    )
    [diff] = plan.diffs
    assert len(diff.cautions) == 1
    assert "a column mask on email" in diff.cautions[0]


# ---------------------------------------------------------------------------
# drift
# ---------------------------------------------------------------------------

CONFIG = (
    "specs: [tables]\ntargets:\n  dev:\n    default: true\n    vars: {catalog: main}\n"
)
SPEC = (
    "table: ${catalog}.sales.customers\n"
    "columns:\n"
    "  - {name: id, type: bigint}\n"
    "  - {name: email, type: string}\n"
    "  - {name: region, type: string}\n"
)


def project_at(tmp_path: Path, config: str = CONFIG) -> Project:
    (tmp_path / "stevin.yml").write_text(config)
    (tmp_path / "tables").mkdir(exist_ok=True)
    (tmp_path / "tables" / "customers.yml").write_text(SPEC)
    return Project.load(tmp_path / "stevin.yml")


def test_drift_lists_them_as_not_stevins_and_stays_in_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A policy is present and somebody else's, like a grant no spec names: it
    is said, and it is not drift."""
    # RULES.md: ACC-5.
    project_at(tmp_path)
    fake = warehouse(MASK_PII, OWN_REGION)
    monkeypatch.setattr(cli, "_connect", lambda *_a, **_k: Connection(runner=fake))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "400")
    result = CliRunner().invoke(cli.app, ["drift"])
    assert result.exit_code == 0, result.output
    assert "policy mask_pii (column mask, on schema main.sales)" in result.output
    assert "policy own_region (row filter, on catalog main)" in result.output
    assert result.output.count("— not stevin's, left untouched") == 2
    assert "Drift:" not in result.output


def test_drift_is_still_drift_beside_a_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_at(tmp_path)
    fake = FakeWarehouse.of(replace(CUSTOMERS, columns=CUSTOMERS.columns[:2]))
    fake.under(MASK_PII)
    monkeypatch.setattr(cli, "_connect", lambda *_a, **_k: Connection(runner=fake))
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli.app, ["drift"])
    assert result.exit_code == 2, result.output


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def looked(tmp_path: Path, fake: FakeWarehouse, config: str = CONFIG) -> list:
    project = project_at(tmp_path, config)
    target = project.default
    assert target is not None
    return list(doctor._policies(Connection(runner=fake), project, target))


def test_doctor_says_the_statement_is_accepted(tmp_path: Path) -> None:
    fake = warehouse(MASK_PII, OWN_REGION, ON_THE_TABLE)
    [finding] = looked(tmp_path, fake)
    assert (finding.about, finding.verdict) == ("policies", "ok")
    assert finding.found == "SHOW EFFECTIVE POLICIES accepted on main.sales (2 in scope)"
    assert "SHOW EFFECTIVE POLICIES ON SCHEMA `main`.`sales`" in fake.statements


def test_doctor_says_why_a_workspace_wont_list_them(tmp_path: Path) -> None:
    """Not a problem — a plan goes on without them — and the remedy is what the
    manual says listing them takes, with the way to stop asking."""
    fake = warehouse()
    fake.refusals["SHOW EFFECTIVE POLICIES"] = REFUSAL
    [finding] = looked(tmp_path, fake)
    assert (finding.about, finding.verdict) == ("policies", "warning")
    assert finding.found == f"can't be listed on main.sales: FAILED: {REFUSAL}"
    assert finding.remedy is not None
    for said in (
        "Runtime 16.4",
        "READ METADATA or MANAGE",
        "sql-ref-syntax-aux-show-policies",
        "manage: {policies: false}",
    ):
        assert said in finding.remedy


def test_doctor_asks_nothing_of_a_schema_that_isnt_there_yet(tmp_path: Path) -> None:
    fake = FakeWarehouse()
    assert looked(tmp_path, fake) == []
    assert about_policies(fake) == []


def test_doctor_asks_nothing_when_policies_are_handed_over(tmp_path: Path) -> None:
    fake = warehouse(MASK_PII)
    assert looked(tmp_path, fake, CONFIG + "manage:\n  policies: false\n") == []
    assert fake.statements == []


# ---------------------------------------------------------------------------
# the fake stays loud
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE POLICY p ON SCHEMA `main`.`sales` ROW FILTER f TO a FOR TABLES",
        "DROP POLICY `mask_pii` ON SCHEMA `main`.`sales`",
        "ALTER POLICY `mask_pii` ON SCHEMA `main`.`sales` RENAME TO x",
        "SHOW POLICIES ON TABLE `main`.`sales`.`customers`",
        "SHOW EFFECTIVE POLICIES ON CATALOG `main`",
        "SHOW EFFECTIVE POLICIES ON TABLE",
        "DESCRIBE POLICY `mask_pii` ON METASTORE",
    ],
)
def test_the_fake_knows_the_statements_stevin_reads_with_and_no_other(
    statement: str,
) -> None:
    """stevin never writes a policy. A statement that would is one the fake
    has never heard of, so no test can pass by sending it."""
    # RULES.md: ACC-3.
    with pytest.raises(FakeSqlError, match="does not know this statement"):
        warehouse(MASK_PII).query(statement)


def test_the_fake_refuses_a_policy_nobody_defined() -> None:
    with pytest.raises(FakeSqlError, match="POLICY_NOT_FOUND"):
        warehouse().query("DESCRIBE POLICY `nope` ON SCHEMA `main`.`sales`")

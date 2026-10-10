"""`stevin verify`, without a workspace.

What can be held to offline is the machinery: that every probe produces exactly
one result whatever the warehouse does, that a probe which says the workspace
differs is reported in the workspace's own words, that the scratch schema is
made and dropped, and that the command's exit code and JSON say what a host
reads.

What can *not* be held to offline is whether an assumption holds. The fake
warehouse interprets stevin's own SQL, so a ✓ from it would be stevin
repeating its own assumptions back — which is the whole reason the probes exist.
Only `tests/integration/test_live_assumptions.py`, which runs this same list
against a real workspace, answers that.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from typer.testing import CliRunner

from fake_warehouse import FakeWarehouse
from stevin import api, cli, probes
from stevin.connect import Connection
from stevin.introspect import Introspector, Row
from stevin.probes import Bench, Disagrees, Probe, Result, run, scratch

runner = CliRunner()


def bench_on(fake: FakeWarehouse, schema: str = "main.scratch") -> Bench:
    return Bench(fake, Introspector(fake), schema)


def held(_bench: Bench) -> None:
    pass


def differs(_bench: Bench) -> None:
    raise Disagrees("it said 7")


def asserts(_bench: Bench) -> None:
    raise AssertionError("7 != 8")


def breaks(_bench: Bench) -> None:
    raise RuntimeError("The request could not be processed by the warehouse.")


def probe(name: str, check, **rest) -> Probe:  # noqa: ANN001,ANN003 - a test builder
    return Probe(
        name,
        "https://docs.databricks.com/aws/en/delta/history",
        "what it costs when this one doesn't hold",
        check,
        **rest,
    )


HELD = probe("this one holds", held)
DIFFERED = probe("this one differs", differs)
ASSERTED = probe("this one fails an assert", asserts)
BROKE = probe("this one couldn't be tried", breaks)


# ---------------------------------------------------------------------------
# the list itself
# ---------------------------------------------------------------------------


def test_every_probe_says_what_it_is_and_what_rests_on_it() -> None:
    """A probe nobody can act on is worse than none: each names the Databricks
    page it rests on, and what stevin does because of it."""
    names = [one.name for one in probes.PROBES]
    assert len(names) == len(set(names)), "two probes share a name"
    for one in probes.PROBES:
        assert one.docs.startswith("https://docs.databricks.com/"), one.name
        assert len(one.matters) > 40, one.name


def test_the_slow_and_recoverable_ones_can_be_left_out() -> None:
    """`verify` runs the quick ones by default: one probe starts a Databricks
    pipeline, and one needs a schema that holds the metastore's table quota for
    its whole recovery period."""
    assert not [one for one in probes.chosen() if one.slow]
    assert [one for one in probes.chosen(slow=True) if one.slow]
    assert not [one for one in probes.chosen(keeps_dropped=False) if one.keeps_dropped]
    assert len(probes.chosen(slow=True, creates_policy=True)) == len(probes.PROBES)


def test_a_probe_that_creates_a_policy_runs_only_when_asked() -> None:
    """stevin never writes an ABAC policy. Two probes have to create one on a
    scratch table to read it back, so they are marked, a plain `verify` leaves
    them out, and every probe whose check sends `CREATE POLICY` carries the mark."""
    marked = [one for one in probes.PROBES if one.creates_policy]
    assert marked, "the probes that read a policy back are gone"
    assert not [one for one in probes.chosen(slow=True) if one.creates_policy]
    assert [one for one in probes.chosen(creates_policy=True) if one.creates_policy]

    class Noting:
        """Takes every statement and answers nothing, so each check goes on as
        far as it can and what it would send is on the record."""

        def __init__(self) -> None:
            self.statements: list[str] = []

        def query(self, statement: str) -> tuple[Row, ...]:
            self.statements.append(statement)
            return ()

        @property
        def client(self) -> None:  # pragma: no cover - never asked for
            return None

    for one in probes.PROBES:
        noting = Noting()
        list(run(Bench(noting, Introspector(noting), "main.scratch"), [one]))
        writes = [
            statement
            for statement in noting.statements
            if statement.split()[0] in ("CREATE", "ALTER", "DROP")
            and "POLICY" in statement.split()[:4]
        ]
        assert bool(writes) == one.creates_policy, (one.name, writes)


def test_no_probe_can_break_the_report() -> None:
    """Against a warehouse that understands none of it, every probe still comes
    back with a result: the report is the output, not an exception."""

    class Refusing:
        def query(self, statement: str) -> tuple[Row, ...]:
            raise RuntimeError(f"no: {statement[:20]}")

        @property
        def client(self) -> None:  # pragma: no cover - never asked for
            return None

    refusing = Refusing()
    bench = Bench(refusing, Introspector(refusing), "main.scratch")
    results = list(run(bench, probes.chosen(slow=True, creates_policy=True)))
    assert len(results) == len(probes.PROBES)
    assert not [result for result in results if result.held]


def test_each_probe_names_its_own_objects() -> None:
    """Probes share one scratch schema, so no two can make the same table."""
    seen: list[str] = []

    def note(bench: Bench) -> None:
        seen.append(bench.named("t"))

    listed = [probe(f"probe {index}", note) for index in range(3)]
    assert all(result.held for result in run(bench_on(FakeWarehouse()), listed))
    assert seen == [
        "`main`.`scratch`.`p01_t`",
        "`main`.`scratch`.`p02_t`",
        "`main`.`scratch`.`p03_t`",
    ]


# ---------------------------------------------------------------------------
# what a probe can say
# ---------------------------------------------------------------------------


def test_a_workspace_that_differs_is_reported_in_its_own_words() -> None:
    differed, asserted = run(bench_on(FakeWarehouse()), [DIFFERED, ASSERTED])
    assert (differed.outcome, differed.detail) == ("differed", "it said 7")
    assert (asserted.outcome, asserted.detail) == ("differed", "7 != 8")
    assert differed.mark == "✗"


def test_a_probe_that_could_not_be_tried_carries_the_advice() -> None:
    """A stopped warehouse is not an answer about behaviour — and its message is
    one stevin already knows how to explain."""
    [result] = list(run(bench_on(FakeWarehouse()), [BROKE]))
    assert (result.outcome, result.mark) == ("unknown", "!")
    assert result.detail is not None
    assert "stopped or unstartable serverless warehouse" in result.detail


def test_expect_and_refuses_say_which_way_round_it_went() -> None:
    bench = bench_on(FakeWarehouse())
    bench.expect(True, "never raised")
    with pytest.raises(Disagrees, match="it said 7"):
        bench.expect(False, "it said 7")
    with bench.refuses("no such thing"):
        raise RuntimeError("no such thing here")
    with (
        pytest.raises(Disagrees, match="it was refused, but with"),
        bench.refuses("no such thing"),
    ):
        raise RuntimeError("something else entirely")
    with (
        pytest.raises(Disagrees, match="it was allowed"),
        bench.refuses("no such thing"),
    ):
        pass


def test_a_probe_reads_its_own_objects_out_of_an_info_view() -> None:
    one = replace(bench_on(FakeWarehouse()), prefix="p07_")
    assert one.full("orders") == "main.scratch.p07_orders"
    assert one.named("orders") == "`main`.`scratch`.`p07_orders`"
    assert one.info == "`main`.information_schema"
    assert one.about("orders") == (
        "WHERE table_schema = 'scratch' AND table_name = 'p07_orders'"
    )
    assert one.about("orders", schema_column="schema_name").startswith(
        "WHERE schema_name = 'scratch'"
    )


# ---------------------------------------------------------------------------
# the scratch schema
# ---------------------------------------------------------------------------


def test_the_scratch_schema_is_made_and_dropped() -> None:
    fake = FakeWarehouse()
    with scratch(fake, "main.temporary") as schema:
        assert schema == "main.temporary"
        assert "CREATE SCHEMA `main`.`temporary`" in fake.statements
    assert "DROP SCHEMA `main`.`temporary` CASCADE" in fake.statements


def test_a_catalog_on_its_own_gets_a_name_of_stevins() -> None:
    fake = FakeWarehouse()
    with scratch(fake, "main") as schema:
        assert schema.startswith("main.stevin_verify_")
    assert [s for s in fake.statements if s.startswith("DROP SCHEMA")]


def test_the_scratch_schema_keeps_nothing_it_drops() -> None:
    """A dropped table counts against the metastore's table quota for its
    recovery period, and nothing a probe makes is worth a week of that."""
    fake = FakeWarehouse()
    with scratch(fake, "main.temporary"):
        pass
    assert [s for s in fake.statements if "SET RETAIN DROPPED TO 0 HOURS" in s]

    keeping = FakeWarehouse()
    with scratch(keeping, "main.temporary", keeps_dropped=True):
        pass
    assert not [s for s in keeping.statements if "RETAIN DROPPED" in s]


def test_an_existing_schema_is_left_alone() -> None:
    """`verify` drops the schema it made; it will never drop one it found."""
    fake = FakeWarehouse(schemas={"main.mine"})
    with pytest.raises(Exception, match="already exists"), scratch(fake, "main.mine"):  # noqa: PT011
        pass
    assert not [s for s in fake.statements if s.startswith("DROP SCHEMA")]


def test_keep_leaves_the_schema_to_look_at() -> None:
    fake = FakeWarehouse()
    with scratch(fake, "main.temporary", keep=True):
        pass
    assert not [s for s in fake.statements if s.startswith("DROP SCHEMA")]


def test_a_schema_named_like_a_table_is_refused() -> None:
    with (  # noqa: PT011
        pytest.raises(Exception, match="catalog.schema"),
        scratch(FakeWarehouse(), "main.sales.orders"),
    ):
        pass


# ---------------------------------------------------------------------------
# the SDK verb and the command
# ---------------------------------------------------------------------------


def test_the_sdk_verb_runs_the_probes_and_drops_the_schema(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(probes, "PROBES", (HELD, DIFFERED))
    fake = FakeWarehouse()
    watched: list[Result] = []
    results = api.verify(
        Connection(runner=fake), "main", observer=watched.append, undrop=False
    )
    assert [result.outcome for result in results] == ["held", "differed"]
    assert watched == list(results)
    assert [s for s in fake.statements if s.startswith("DROP SCHEMA")]


def test_the_undrop_probe_gets_a_schema_that_keeps_what_it_drops(monkeypatch) -> None:  # noqa: ANN001
    """And nothing else does: it is the one schema a run leaves holding quota."""

    def asks(bench: Bench) -> None:
        assert bench.recoverable is not None
        assert bench.recoverable().startswith("main.stevin_verify_")

    monkeypatch.setattr(probes, "PROBES", (HELD, probe("asks", asks, keeps_dropped=True)))
    fake = FakeWarehouse()
    results = api.verify(Connection(runner=fake), "main")
    assert [result.outcome for result in results] == ["held", "held"]
    made = [s for s in fake.statements if s.startswith("CREATE SCHEMA")]
    assert len(made) == 2, made
    assert len([s for s in fake.statements if "RETAIN DROPPED" in s]) == 1
    assert len([s for s in fake.statements if s.startswith("DROP SCHEMA")]) == 2


def test_the_command_says_which_held_and_exits_1_when_one_did_not(monkeypatch) -> None:  # noqa: ANN001
    fake = FakeWarehouse()
    monkeypatch.setattr(cli, "_connect", lambda *_a, **_k: Connection(runner=fake))
    monkeypatch.setattr(probes, "PROBES", (HELD, DIFFERED))
    result = runner.invoke(cli.app, ["verify", "--schema", "main", "--no-undrop"])
    assert result.exit_code == 1, result.output
    assert "✓ this one holds" in result.output
    assert "✗ this one differs" in result.output
    assert "it said 7" in result.output
    assert "what it costs when this one doesn't hold" in result.output
    assert "1 held, 1 didn't." in result.output


def test_the_command_exits_0_when_everything_held(monkeypatch) -> None:  # noqa: ANN001
    fake = FakeWarehouse()
    monkeypatch.setattr(cli, "_connect", lambda *_a, **_k: Connection(runner=fake))
    monkeypatch.setattr(probes, "PROBES", (HELD, probe("slow one", held, slow=True)))
    result = runner.invoke(cli.app, ["verify", "--schema", "main.probing", "--no-undrop"])
    assert result.exit_code == 0, result.output
    assert "main.probing" in result.output, "it says where it is working"
    assert "1 held." in result.output
    assert "1 not run" in result.output, "the slow one is left out, and said so"


def test_the_command_creates_no_policy_unless_asked(monkeypatch) -> None:  # noqa: ANN001
    """A plain `verify` leaves out the probes that create a policy, and says so
    in a line of its own that names the flag; with the flag they run."""
    sent: list[str] = []

    def creates(bench: Bench) -> None:
        sent.append("CREATE POLICY")

    listed = (HELD, probe("reads a policy back", creates, creates_policy=True))
    fake = FakeWarehouse()
    monkeypatch.setattr(cli, "_connect", lambda *_a, **_k: Connection(runner=fake))
    monkeypatch.setattr(probes, "PROBES", listed)
    plain = runner.invoke(cli.app, ["verify", "--schema", "main", "--no-undrop"])
    assert plain.exit_code == 0, plain.output
    assert sent == []
    assert "reads a policy back" not in plain.output
    said = " ".join(plain.output.split())
    assert "1 not run: reading a policy back means creating one" in said
    assert "(--create-policy)" in said
    assert "(--slow, --undrop)" not in said

    asked = runner.invoke(
        cli.app, ["verify", "--schema", "main", "--no-undrop", "--create-policy"]
    )
    assert asked.exit_code == 0, asked.output
    assert sent == ["CREATE POLICY"]
    assert "✓ reads a policy back" in asked.output
    assert "not run" not in asked.output


def test_the_sdk_verb_creates_no_policy_unless_asked(monkeypatch) -> None:  # noqa: ANN001
    listed = (HELD, probe("reads a policy back", held, creates_policy=True))
    monkeypatch.setattr(probes, "PROBES", listed)
    plain = api.verify(Connection(runner=FakeWarehouse()), "main", undrop=False)
    assert [result.probe.name for result in plain] == ["this one holds"]
    asked = api.verify(
        Connection(runner=FakeWarehouse()), "main", undrop=False, create_policy=True
    )
    assert [result.probe.name for result in asked] == [
        "this one holds",
        "reads a policy back",
    ]


def test_the_command_reports_json_for_a_host(monkeypatch) -> None:  # noqa: ANN001
    fake = FakeWarehouse()
    monkeypatch.setattr(cli, "_connect", lambda *_a, **_k: Connection(runner=fake))
    monkeypatch.setattr(probes, "PROBES", (HELD, BROKE))
    result = runner.invoke(
        cli.app, ["verify", "--schema", "main", "--no-undrop", "--json"]
    )
    assert result.exit_code == 1
    reported = json.loads(result.output)
    assert [entry["outcome"] for entry in reported] == ["held", "unknown"]
    assert reported[0]["docs"].startswith("https://docs.databricks.com/")
    assert reported[1]["detail"] is not None


def test_a_schema_that_exists_stops_the_command_before_anything_runs(
    monkeypatch,  # noqa: ANN001
) -> None:
    fake = FakeWarehouse(schemas={"main.mine"})
    monkeypatch.setattr(cli, "_connect", lambda *_a, **_k: Connection(runner=fake))
    result = runner.invoke(cli.app, ["verify", "--schema", "main.mine"])
    assert result.exit_code == 1
    assert "already exists" in result.output
    assert not [s for s in fake.statements if s.startswith(("CREATE", "DROP"))]

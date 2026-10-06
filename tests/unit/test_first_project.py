"""The first hour: an empty directory, `import`, `plan`, `apply`.

`import` without a project writes `stevin.yml` — one target whose catalog is
the one imported from, so the specs say `${catalog}` — and the commands after it
work as they are, with no editing. This is the path the getting-started page
walks, so it is tested end to end against the fake warehouse.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from fake_warehouse import FakeWarehouse
from helpers import col, table
from stevin import cli
from stevin.connect import Connection
from stevin.history import MemoryHistory
from stevin.model.table import Grant

runner = CliRunner()


@pytest.fixture
def workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeWarehouse:
    fake = FakeWarehouse.of(
        table(
            col("customer_id", "bigint", nullable=False),
            col("email", "string"),
            name="main.crm.customers",
            comment="One row per customer",
            grants=(Grant("analysts", ("SELECT",)),),
        ),
        table(col("event_id", "bigint"), name="main.crm.events"),
    )
    history = MemoryHistory()
    monkeypatch.setattr(cli, "_connect", lambda *_a, **_k: Connection(runner=fake))
    monkeypatch.setattr(cli, "_history", lambda *_a, **_k: history)
    monkeypatch.chdir(tmp_path)
    return fake


def test_import_plan_apply_from_nothing(workspace: FakeWarehouse, tmp_path: Path) -> None:
    imported = runner.invoke(cli.app, ["import", "main.crm", "--warehouse-id", "abc123"])
    assert imported.exit_code == 0, imported.output
    assert "+ stevin.yml (target dev: catalog main)" in imported.output
    assert "Next: stevin plan" in imported.output

    project = (tmp_path / "stevin.yml").read_text()
    assert "catalog: main" in project and "warehouse_id: abc123" in project
    spec = (tmp_path / "tables" / "customers.yml").read_text()
    assert "table: ${catalog}.crm.customers" in spec

    planned = runner.invoke(cli.app, ["plan"])
    assert planned.exit_code == 0, planned.output
    assert "CLAIM ownership" in planned.output
    assert "2 change, 0 destroy · 2 steps" in planned.output

    applied = runner.invoke(cli.app, ["apply", "--yes"])
    assert applied.exit_code == 0, applied.output
    assert "No changes." in runner.invoke(cli.app, ["plan"]).output


def test_an_existing_project_is_left_as_it_is(
    workspace: FakeWarehouse, tmp_path: Path
) -> None:
    (tmp_path / "stevin.yml").write_text(
        "version: 1\nspecs: [specs]\ntargets:\n  prod:\n    vars: {catalog: main}\n"
    )
    result = runner.invoke(cli.app, ["import", "main.crm"])
    assert result.exit_code == 0, result.output
    assert "stevin.yml" not in result.output
    assert (tmp_path / "specs" / "customers.yml").exists()


def test_a_specs_entry_that_isnt_there_is_a_spec_error(tmp_path: Path) -> None:
    """A typo in `specs:` is a mistake in a file, and reads like one.

    It used to raise a bare FileNotFoundError, which the CLI turned into a Rich
    traceback — the only bad input in the loader that didn't say where it was.
    """
    from stevin.loader import SpecError, load_project, spec_files

    (tmp_path / "stevin.yml").write_text("specs: [tabels]\ntargets:\n  dev: {}\n")
    project = load_project(tmp_path / "stevin.yml")
    with pytest.raises(SpecError) as raised:
        spec_files(project)
    said = str(raised.value)
    assert "tabels" in said and "isn't there" in said
    assert "stevin.yml" in said, "and it names the file that says so"


def test_the_cli_says_it_in_one_line(tmp_path: Path) -> None:
    (tmp_path / "stevin.yml").write_text("specs: [tabels]\ntargets:\n  dev: {}\n")
    result = CliRunner().invoke(
        cli.app, ["validate", "--config", str(tmp_path / "stevin.yml")]
    )
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "isn't there" in result.output

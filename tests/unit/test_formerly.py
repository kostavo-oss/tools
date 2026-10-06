"""What still answers to the name stevin had before: deltaplan.

The rename changed what people type and read. It could not change what was
already written — on tables in a workspace, in somebody's repository — and
that is pinned here, where an innocent search-and-replace fails loudly.
"""

import importlib
import re
import sys
import tomllib
from importlib.metadata import entry_points
from pathlib import Path

import pytest
from typer.testing import CliRunner

import stevin
from stevin import formerly
from stevin.cli import app
from stevin.loader import find_project_file, project_file

runner = CliRunner()

# typer colours its help wherever it believes it has a terminal, and on a
# GitHub runner it always believes so
COLOUR = re.compile(r"\x1b\[[0-9;]*m")

CONFIG = """
version: 1
specs: [tables]
targets:
  dev:
    vars: {catalog: main}
    warehouse_id: abc123
"""

SPEC = """
table: ${catalog}.sales.orders
columns:
  - name: order_id
    type: bigint
"""


@pytest.fixture
def former(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project as deltaplan left it, and the directory a command is run from."""
    (tmp_path / "deltaplan.yml").write_text(CONFIG)
    (tmp_path / "tables").mkdir()
    (tmp_path / "tables" / "orders.yml").write_text(SPEC)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_what_is_written_on_tables_kept_its_name() -> None:
    """A table deltaplan made is a table stevin manages for exactly as long as
    these are the same strings. Change one and every table carrying it is a
    stranger: not claimed, seeded again, its staging table left behind."""
    assert formerly.MANAGED_PROPERTY == "deltaplan.managed"
    assert formerly.SEED_PROPERTY == "deltaplan.seed"
    assert formerly.STAGING_SUFFIX == "__deltaplan_rewrite"
    assert formerly.BACKUP_SUFFIX == "__deltaplan_backup"


def test_only_formerly_spells_the_old_name() -> None:
    package = Path(stevin.__file__).parent
    spelling_it = sorted(
        path.relative_to(package).as_posix()
        for path in package.rglob("*.py")
        if "deltaplan" in path.read_text(encoding="utf-8").lower()
    )
    assert spelling_it == ["formerly.py"]


# ---------------------------------------------------------------------------
# the project file
# ---------------------------------------------------------------------------


def test_a_project_file_under_its_former_name_is_found(former: Path) -> None:
    assert find_project_file(former / "tables") == former / "deltaplan.yml"
    assert project_file(former) == former / "deltaplan.yml"


def test_todays_name_wins_where_both_are_there(former: Path) -> None:
    (former / "stevin.yml").write_text(CONFIG)
    assert find_project_file(former) == former / "stevin.yml"
    assert project_file(former) == former / "stevin.yml"


def test_a_command_runs_on_it_and_says_it_could_be_renamed(former: Path) -> None:
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0, result.output
    assert "deltaplan.yml" in result.stderr
    assert "rename it to stevin.yml" in result.stderr
    # said beside the output, never in it: a plan piped to a file stays a plan
    assert "deltaplan" not in result.stdout


def test_it_says_so_when_the_file_is_named_outright_too(former: Path) -> None:
    result = runner.invoke(app, ["validate", "--config", "deltaplan.yml"])
    assert result.exit_code == 0, result.output
    assert "rename it to stevin.yml" in result.stderr


def test_a_project_under_todays_name_hears_nothing(former: Path) -> None:
    (former / "deltaplan.yml").rename(former / "stevin.yml")
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0, result.output
    assert "rename" not in result.stderr


# ---------------------------------------------------------------------------
# the command
# ---------------------------------------------------------------------------


def as_deltaplan(
    *arguments: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str, str]:
    """Run the old command the way its console script does."""
    monkeypatch.setattr(sys, "argv", ["deltaplan", *arguments])
    with pytest.raises(SystemExit) as stopped:
        formerly.main()
    said = capsys.readouterr()
    code = stopped.value.code
    return (code if isinstance(code, int) else 1), said.out, said.err


def test_the_old_command_is_installed_beside_the_new_one() -> None:
    scripts = {
        script.name: script.value
        for script in entry_points(group="console_scripts")
        if script.value.startswith("stevin.")
    }
    assert scripts == {
        "stevin": "stevin.cli:main",
        "deltaplan": "stevin.formerly:main",
    }


def test_it_says_its_new_name_and_then_is_stevin(
    former: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (former / "deltaplan.yml").rename(former / "stevin.yml")
    code, out, err = as_deltaplan("validate", monkeypatch=monkeypatch, capsys=capsys)
    assert code == 0
    assert "deltaplan is now stevin" in err
    assert out == runner.invoke(app, ["validate"]).stdout


def test_what_it_says_stays_out_of_the_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = as_deltaplan("--version", monkeypatch=monkeypatch, capsys=capsys)
    assert code == 0
    assert out == f"stevin {stevin.__version__}\n"
    assert "deltaplan is now stevin" in err


def test_its_help_is_stevins_and_stevins_help_never_mentions_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = as_deltaplan("--help", monkeypatch=monkeypatch, capsys=capsys)
    assert code == 0
    assert "Usage: stevin" in COLOUR.sub("", out)
    assert "deltaplan" not in out
    assert "deltaplan" not in runner.invoke(app, ["--help"]).output


def test_a_failure_is_still_a_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)  # no project here
    code, _, _ = as_deltaplan("validate", monkeypatch=monkeypatch, capsys=capsys)
    assert code != 0


# ---------------------------------------------------------------------------
# the last release under the old name
# ---------------------------------------------------------------------------

SHIM = Path(__file__).parents[2] / "deltaplan-shim"


def test_the_last_deltaplan_release_installs_stevin_and_its_old_command() -> None:
    project = tomllib.loads((SHIM / "pyproject.toml").read_text())["project"]
    assert project["name"] == "deltaplan"
    assert [d.split(">=")[0] for d in project["dependencies"]] == ["stevin"]
    assert project["scripts"] == {"deltaplan": "stevin.formerly:main"}


def test_importing_it_is_importing_stevin_with_a_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(SHIM / "src"))
    monkeypatch.delitem(sys.modules, "deltaplan", raising=False)
    with pytest.warns(DeprecationWarning, match="deltaplan is now stevin"):
        deltaplan = importlib.import_module("deltaplan")
    monkeypatch.delitem(sys.modules, "deltaplan")

    assert deltaplan.DeltaplanError is stevin.StevinError
    assert deltaplan.Project is stevin.Project
    assert deltaplan.__version__ == stevin.__version__
    assert set(deltaplan.__all__) == {*stevin.__all__, "DeltaplanError"}


def test_stevin_does_not_ship_it() -> None:
    """One wheel must not carry both names: the old one is a release of its own."""
    root = SHIM.parent
    build = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["hatch"]["build"]
    assert build["targets"]["wheel"]["packages"] == ["src/stevin"]
    assert SHIM.name in build["targets"]["sdist"]["exclude"]

"""The `command` step: a plan command that prints JSON, or a plain run."""

import json
import sys
from pathlib import Path

import pytest

from lely.errors import LelyError
from lely.model import Change
from lely.steps.command import Command
from lely.testing import check_plan, context


def printing(document: object) -> tuple[str, ...]:
    return (sys.executable, "-c", f"print({json.dumps(json.dumps(document))})")


def test_without_a_plan_command_it_runs_every_time() -> None:
    plan = check_plan(
        Command(), context(Command.Options(apply=("./seed.sh", "--fast")), name="seed")
    )
    assert plan.changes == (Change("seed", "run", "runs ./seed.sh --fast"),)


def test_a_plan_command_prints_the_steps_plan(tmp_path: Path) -> None:
    printed = {
        "changes": [{"key": "users", "action": "create", "summary": "seed 3 users"}],
        "outputs": {"count": 3},
    }
    options = Command.Options(apply=("true",), plan=printing(printed))
    plan = check_plan(Command(), context(options, root=tmp_path))
    assert plan.changes == (Change("users", "create", "seed 3 users"),)
    assert plan.outputs == {"count": 3}


def test_the_plan_command_knows_where_it_runs(tmp_path: Path) -> None:
    names = "('LELY_TARGET', 'LELY_STEP', 'LELY_PHASE', 'EXTRA')"
    script = (
        "import json, os; print(json.dumps({'outputs': "
        f"{{k: os.environ[k] for k in {names}}}}}))"
    )
    options = Command.Options(
        apply=("true",), plan=(sys.executable, "-c", script), env={"EXTRA": "yes"}
    )
    plan = Command().plan(
        context(options, target="prod", name="seed", phase="pre", root=tmp_path)
    )
    assert plan.outputs == {
        "LELY_TARGET": "prod",
        "LELY_STEP": "seed",
        "LELY_PHASE": "pre",
        "EXTRA": "yes",
    }


def test_a_plan_command_must_print_json(tmp_path: Path) -> None:
    options = Command.Options(apply=("true",), plan=(sys.executable, "-c", "print('hi')"))
    with pytest.raises(LelyError, match="must print JSON on stdout"):
        Command().plan(context(options, root=tmp_path))


def test_a_plan_commands_plan_is_checked(tmp_path: Path) -> None:
    options = Command.Options(
        apply=("true",), plan=printing({"changes": [{"key": "a", "action": "nuke"}]})
    )
    with pytest.raises(LelyError, match="action must be one of"):
        Command().plan(context(options, root=tmp_path))


def test_a_failing_plan_command_is_shown(tmp_path: Path) -> None:
    script = "import sys; print('no access', file=sys.stderr); sys.exit(3)"
    options = Command.Options(apply=("true",), plan=(sys.executable, "-c", script))
    with pytest.raises(
        LelyError, match="(?s)plan command failed \\(exit 3\\).*no access"
    ):
        Command().plan(context(options, name="seed", root=tmp_path))

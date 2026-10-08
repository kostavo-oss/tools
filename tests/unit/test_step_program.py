"""`Program`: a program as a step, one `run` every apply (`spec/011`, R13)."""

from __future__ import annotations

import dataclasses
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from fakes import Heard
from lely.errors import LelyError
from lely.model import Change, Output, Secret
from lely.step import Context, Program, destroys, lists
from lely.testing import check_apply, check_plan, context

PYTHON = sys.executable


class Notify(Program):
    """Tells the channel the deploy is done."""

    command = [PYTHON, "-c", "print('told'); print('{\"sent\": 1}')"]
    outputs = (Output("sent", known="run"),)


class Loud(Program):
    command = [
        PYTHON,
        "-c",
        "import os; print(os.environ['LELY_STEP'], os.environ['LELY_TARGET'])",
    ]


class Dropping(Program):
    command = ["./drop.sh"]
    destructive = True


class Failing(Program):
    command = [PYTHON, "-c", "import sys; sys.exit(3)"]


class Quiet(Program):
    command = [PYTHON, "-c", "print('nothing like json')"]
    outputs = (Output("sent", known="run"),)


class WithSecret(Program):
    command = [PYTHON, "-c", "import os; print(os.environ['TOKEN'])"]
    env = {"TOKEN": Secret("t0p-s3cret")}


def test_the_plan_is_one_run(tmp_path: Path) -> None:
    plan = check_plan(Notify(), context(Notify.Options(), name="notify", root=tmp_path))

    assert len(plan.changes) == 1
    change = plan.changes[0]
    assert (change.key, change.action, change.destructive) == ("notify", "run", False)
    assert change.summary.startswith("runs ")


def test_destructive_is_declared_on_the_run(tmp_path: Path) -> None:
    plan = check_plan(Dropping(), context(Dropping.Options(), root=tmp_path))

    assert plan.changes == (Change("step", "run", "runs ./drop.sh", destructive=True),)


def test_apply_runs_it_and_gives_what_it_printed(tmp_path: Path) -> None:
    outputs = check_apply(Notify(), context(Notify.Options(), root=tmp_path))

    assert outputs == {"sent": 1}


def test_the_program_hears_the_step_and_the_target(tmp_path: Path) -> None:
    heard = Heard()
    ctx = context(Loud.Options(), name="loud", target="prod", root=tmp_path)
    ctx = dataclasses.replace(ctx, log=heard)

    Loud().apply(ctx, Loud().plan(ctx))

    assert any("loud prod" in line for line in heard.lines)


def test_a_failing_program_fails_the_step(tmp_path: Path) -> None:
    ctx = context(Failing.Options(), root=tmp_path)

    with pytest.raises(LelyError, match="exit"):
        Failing().apply(ctx, Failing().plan(ctx))


def test_declared_outputs_need_json_on_the_last_line(tmp_path: Path) -> None:
    ctx = context(Quiet.Options(), root=tmp_path)

    with pytest.raises(LelyError, match="last line isn't a JSON object"):
        Quiet().apply(ctx, Quiet().plan(ctx))


def test_a_secret_reaches_the_program_through_its_environment(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    ctx = context(WithSecret.Options(), root=tmp_path)
    plan = check_plan(WithSecret(), ctx)

    assert "t0p-s3cret" not in str(plan)
    WithSecret().apply(ctx, plan)


def test_a_program_has_no_destroy_and_nothing_to_list() -> None:
    assert not destroys(Notify)
    assert not lists(Notify)


def test_an_empty_command_is_an_error(tmp_path: Path) -> None:
    class Empty(Program):
        pass

    with pytest.raises(LelyError, match="`command` is empty"):
        Empty().plan(context(Empty.Options(), root=tmp_path))


def test_doctor_is_told_the_program() -> None:
    """Asked of the class, as `lely doctor` asks every plugin."""
    assert Notify.programs({}) == (PYTHON,)
    assert Notify().programs({}) == (PYTHON,)


class Told(Program):
    """A command built from the options."""

    @dataclass(frozen=True, slots=True)
    class Options:
        #: What to say.
        word: str

    def command(self, ctx: Context) -> list[str]:
        return [PYTHON, "-c", f"print({ctx.options.word!r})"]


def test_a_command_may_be_built_from_the_options(tmp_path: Path) -> None:
    ctx = context(Told.Options(word="hi"), name="told", root=tmp_path)

    plan = check_plan(Told(), ctx)

    assert "hi" in plan.changes[0].summary
    assert Told().programs({}) == ()  # not known without the options
    check_apply(Told(), ctx)

"""The `command` plugin: a plan command that prints JSON, or a plain run; an
apply command that writes its outputs; and optionally a destroy command."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from lely.errors import LelyError
from lely.model import Change, Output, Secret, Skip, StepPlan
from lely.steps.command import Command
from lely.testing import check_overview, check_plan, context

PYTHON = sys.executable


def printing(document: object) -> tuple[str, ...]:
    return (PYTHON, "-c", f"print({json.dumps(json.dumps(document))})")


def script(tmp_path: Path, body: str, name: str = "run.py") -> tuple[str, ...]:
    (tmp_path / name).write_text(f"import json, os, sys\n{body}\n")
    return (PYTHON, name)


# -- plan --------------------------------------------------------------------------


def test_without_a_plan_command_it_runs_every_time() -> None:
    plan = check_plan(
        Command(), context(Command.Options(apply=("./seed.sh", "--fast")), name="seed")
    )
    assert plan.changes == (Change("seed", "run", "runs ./seed.sh --fast"),)


def test_a_plan_command_prints_the_steps_plan(tmp_path: Path) -> None:
    printed = {
        "changes": [{"key": "users", "action": "create", "summary": "seed 3 users"}],
        "outputs": {"count": 3},
        "notes": ["from seeds/users.csv"],
    }
    options = Command.Options(apply=("true",), plan=printing(printed), outputs=("count",))
    written: dict[str, Any] = {"apply": ["true"], "plan": ["x"], "outputs": ["count"]}
    plan = check_plan(Command(), context(options, root=tmp_path), written=written)
    assert plan.changes == (Change("users", "create", "seed 3 users"),)
    assert plan.outputs == {"count": 3}
    assert plan.notes == ("from seeds/users.csv",)
    assert plan.later == ()


def test_every_command_knows_where_it_runs(tmp_path: Path) -> None:
    """R4. `LELY_PHASE` is gone: there are no phases any more."""
    names = "('LELY_TARGET', 'LELY_STEP', 'EXTRA', 'TOKEN')"
    body = (
        "assert 'LELY_PHASE' not in os.environ\n"
        f"print(json.dumps({{'notes': [os.environ[k] for k in {names}]}}))"
    )
    options = Command.Options(
        apply=("true",),
        plan=script(tmp_path, body),
        env={"EXTRA": Secret("yes"), "TOKEN": Secret("t0k")},
    )
    plan = Command().plan(context(options, target="prod", name="seed", root=tmp_path))
    assert plan.notes == ("prod", "seed", "yes", "t0k")


def test_a_plan_command_must_print_json(tmp_path: Path) -> None:
    options = Command.Options(apply=("true",), plan=(PYTHON, "-c", "print('hi')"))
    with pytest.raises(LelyError, match="must print JSON on stdout"):
        Command().plan(context(options, root=tmp_path))


def test_a_plan_commands_plan_is_checked(tmp_path: Path) -> None:
    options = Command.Options(
        apply=("true",), plan=printing({"changes": [{"key": "a", "action": "nuke"}]})
    )
    with pytest.raises(LelyError, match="action must be one of"):
        Command().plan(context(options, root=tmp_path))


def test_a_failing_plan_command_is_shown(tmp_path: Path) -> None:
    body = "print('no access', file=sys.stderr); sys.exit(3)"
    options = Command.Options(apply=("true",), plan=script(tmp_path, body))
    with pytest.raises(
        LelyError, match="(?s)plan command failed \\(exit 3\\).*no access"
    ):
        Command().plan(context(options, name="seed", root=tmp_path))


# -- outputs -----------------------------------------------------------------------


def test_what_a_step_lists_is_what_it_declares() -> None:
    """Decided in 010: the step lists them. Without a plan command they can
    only come from a run; with one, lely can't know which it prints."""
    assert Command.outputs({"apply": ["x"], "outputs": ["count"]}) == (
        Output("count", "run"),
    )
    assert Command.outputs(
        {"apply": ["x"], "plan": ["y"], "outputs": ["count", "id"]}
    ) == (Output("count", "exists"), Output("id", "exists"))
    assert Command.outputs({"apply": ["x"]}) == ()
    with pytest.raises(LelyError, match="`outputs` must list plain names"):
        Command.outputs({"outputs": ["a.b"]})


def test_an_output_the_plan_command_prints_must_be_listed(tmp_path: Path) -> None:
    options = Command.Options(apply=("true",), plan=printing({"outputs": {"n": 1}}))
    with pytest.raises(LelyError) as caught:
        Command().plan(context(options, name="seed", root=tmp_path))
    assert "gives `n`, which the step doesn't list under `outputs`" in str(caught.value)


def test_a_listed_output_the_plan_command_leaves_out_comes_later(
    tmp_path: Path,
) -> None:
    options = Command.Options(apply=("true",), plan=printing({}), outputs=("count", "id"))
    assert Command().plan(context(options, root=tmp_path)).later == ("count", "id")
    plain = Command.Options(apply=("true",), outputs=("count",))
    assert Command().plan(context(plain, root=tmp_path)).later == ("count",)


def test_a_command_cant_give_a_secret(tmp_path: Path) -> None:
    options = Command.Options(
        apply=("true",),
        plan=printing({"outputs": {"token": {"$secret": True}}}),
        outputs=("token",),
    )
    with pytest.raises(LelyError, match="a `command` step can't give a secret"):
        Command().plan(context(options, root=tmp_path))


# -- apply -------------------------------------------------------------------------


def applied(tmp_path: Path, body: str, **options: Any) -> tuple[Any, Path]:
    built = Command.Options(apply=script(tmp_path, body, "apply.py"), **options)
    ctx = context(built, target="prod", name="seed", root=tmp_path)
    return Command().apply(ctx, Command().plan(ctx)), tmp_path


def test_apply_runs_the_command_in_the_projects_directory(tmp_path: Path) -> None:
    body = "open('ran.txt', 'w').write(os.getcwd())"
    outputs, root = applied(tmp_path, body)
    assert outputs == {}
    assert Path((root / "ran.txt").read_text()).resolve() == root.resolve()


def test_apply_is_given_the_plan_and_a_file_for_its_outputs(tmp_path: Path) -> None:
    """R4: `LELY_PLAN` holds the plan that was approved for this step;
    `LELY_OUTPUTS` is a file it writes `name=value` lines to."""
    body = (
        "plan = json.load(open(os.environ['LELY_PLAN']))\n"
        "open('seen.json', 'w').write(json.dumps("
        "[plan['changes'][0]['summary'], os.environ['LELY_TARGET'], "
        "os.environ['LELY_STEP']]))\n"
        "open(os.environ['LELY_OUTPUTS'], 'a').write('count=3\\n\\nurl=https://x/?a=b\\n')"
    )
    outputs, root = applied(tmp_path, body, outputs=("count", "url"))
    assert outputs == {"count": "3", "url": "https://x/?a=b"}
    summary, target, step = json.loads((root / "seen.json").read_text())
    assert (target, step) == ("prod", "seed")
    assert summary.startswith("runs ")


def test_a_non_zero_exit_is_a_failed_step_and_what_it_printed_is_shown(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        LelyError, match="(?s)step `seed`'s apply command failed \\(exit 4\\).*boom"
    ):
        applied(tmp_path, "print('boom', file=sys.stderr); sys.exit(4)")


def test_a_listed_output_given_in_neither_way_is_a_failed_step(tmp_path: Path) -> None:
    with pytest.raises(LelyError) as caught:
        applied(tmp_path, "pass", outputs=("count",))
    assert "lists `count` under `outputs`" in str(caught.value)
    assert "neither its plan command printed it nor its apply command wrote it" in str(
        caught.value
    )


def test_an_output_it_writes_must_be_listed(tmp_path: Path) -> None:
    body = "open(os.environ['LELY_OUTPUTS'], 'a').write('surprise=1\\n')"
    with pytest.raises(LelyError, match="gives `surprise`, which the step doesn't list"):
        applied(tmp_path, body)


def test_a_line_that_isnt_name_value_is_an_error(tmp_path: Path) -> None:
    body = "open(os.environ['LELY_OUTPUTS'], 'a').write('just words\\n')"
    with pytest.raises(LelyError, match="which isn't `name=value`: 'just words'"):
        applied(tmp_path, body, outputs=("count",))


def test_what_the_plan_command_gave_is_kept_after_apply(tmp_path: Path) -> None:
    options = Command.Options(
        apply=script(tmp_path, "open(os.environ['LELY_OUTPUTS'], 'a').write('id=9\\n')"),
        plan=printing(
            {"changes": [{"key": "k", "action": "create"}], "outputs": {"count": 3}}
        ),
        outputs=("count", "id"),
    )
    ctx = context(options, root=tmp_path)
    assert Command().apply(ctx, Command().plan(ctx)) == {"count": 3, "id": "9"}


# -- destroy, status ------------------------------------------------------------------


def test_without_a_destroy_command_it_is_skipped(tmp_path: Path) -> None:
    ctx = context(Command.Options(apply=("true",)), root=tmp_path)
    assert Command().plan_destroy(ctx) == Skip("it has no `destroy` command")


def test_a_destroy_command_is_shown_in_full_and_marked_destructive(
    tmp_path: Path,
) -> None:
    """R6: lely can't vouch for what the command removes, so it shows all of it."""
    options = Command.Options(
        apply=("true",), destroy=script(tmp_path, "open('gone.txt', 'w').write('x')")
    )
    ctx = context(options, name="seed", root=tmp_path)
    plan = Command().plan_destroy(ctx)
    assert plan == StepPlan(
        changes=(Change("seed", "run", f"runs {PYTHON} run.py", destructive=True),),
        notes=("lely can't vouch for what this command removes",),
    )
    assert not (tmp_path / "gone.txt").exists()  # planning ran nothing
    Command().destroy(ctx, plan)
    assert (tmp_path / "gone.txt").exists()


def test_a_failing_destroy_command_is_shown(tmp_path: Path) -> None:
    options = Command.Options(
        apply=("true",), destroy=script(tmp_path, "sys.exit('locked')")
    )
    ctx = context(options, name="seed", root=tmp_path)
    with pytest.raises(LelyError, match="(?s)destroy command failed.*locked"):
        Command().destroy(ctx, StepPlan())


def test_status_has_nothing_to_list(tmp_path: Path) -> None:
    ctx = context(Command.Options(apply=("true",)), root=tmp_path)
    assert check_overview(Command(), ctx) == Skip("runs a command; nothing to list")


def test_the_programs_it_runs_are_named_for_doctor() -> None:
    written: dict[str, Any] = {
        "apply": ["./a.sh"],
        "plan": ["./p.sh", "--plan"],
        "destroy": [],
    }
    assert Command.programs(written) == ("./p.sh", "./a.sh")

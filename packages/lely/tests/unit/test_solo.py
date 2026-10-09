"""A step on its own (`spec/011`): the command line `Step.main()` gives,
against the fake Databricks CLI and a step that keeps a marker file."""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import re
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import project
from lely import cli, planfile
from lely.solo import app_for

runner = CliRunner()

#: A step that makes a file: no workspace needed, every method there.
MARKER = '''\
from dataclasses import dataclass
from pathlib import Path

from lely.model import Change, Item, Output, Overview, Secret, Skip, StepPlan
from lely.step import Context, Step


class Marker(Step):
    """Keeps a marker file with a word in it."""

    @dataclass(frozen=True, slots=True)
    class Options:
        #: The word to write.
        word: str
        #: How many times.
        times: int = 1
        #: Shout it.
        loud: bool = False
        #: Tags, any number.
        tags: tuple[str, ...] = ()
        #: A token the file never shows.
        token: Secret | None = None

    outputs = (Output("file"), Output("written", known="run"))

    def _path(self, ctx: Context) -> Path:
        return ctx.root / f"{ctx.target}-marker.txt"

    def _text(self, ctx: Context) -> str:
        word = ctx.options.word.upper() if ctx.options.loud else ctx.options.word
        return " ".join([word] * ctx.options.times) + "\\n"

    def plan(self, ctx: Context) -> StepPlan:
        path = self._path(ctx)
        outputs = {"file": path.name}
        if path.exists() and path.read_text() == self._text(ctx):
            return StepPlan(outputs=outputs)
        action = "update" if path.exists() else "create"
        return StepPlan(
            changes=(Change(path.name, action, f"writes {ctx.options.word}"),),
            outputs=outputs,
        )

    def apply(self, ctx: Context, plan: StepPlan) -> dict:
        self._path(ctx).write_text(self._text(ctx))
        return {"file": self._path(ctx).name, "written": ctx.options.times}

    def overview(self, ctx: Context) -> Overview | Skip:
        path = self._path(ctx)
        if not path.exists():
            return Skip("no marker yet")
        return Overview((Item("file", path.name, path.name, True),))

    def plan_destroy(self, ctx: Context) -> StepPlan | Skip:
        path = self._path(ctx)
        if not path.exists():
            return Skip("no marker to remove")
        return StepPlan(changes=(Change(path.name, "delete", f"removes {path.name}"),))

    def destroy(self, ctx: Context, plan: StepPlan) -> None:
        self._path(ctx).unlink()


if __name__ == "__main__":
    Marker.main()
'''


@dataclasses.dataclass(frozen=True)
class Ran:
    exit_code: int
    out: str
    err: str

    @property
    def output(self) -> str:
        return self.out + self.err


class Solo:
    """A step's own command line, run in a project folder: what `Step.main()`
    runs, with its output caught."""

    def __init__(self, cls: type, root: Path) -> None:
        self.group = app_for(cls)
        self.root = root

    def __call__(self, *args: str) -> Ran:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                self.group.main(list(args), prog_name="marker.py", standalone_mode=True)
                code = 0
            except SystemExit as exit_:
                code = exit_.code if isinstance(exit_.code, int) else 1
        return Ran(code, _ANSI.sub("", out.getvalue()), _ANSI.sub("", err.getvalue()))


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture
def marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Solo:
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "marker.py").write_text(MARKER)
    monkeypatch.chdir(tmp_path)
    fake = (sys.executable, str(project.FAKE_DATABRICKS), str(project.world(tmp_path)))
    monkeypatch.setattr(cli, "DATABRICKS", fake)
    monkeypatch.setattr(cli, "WHOAMI", lambda profile: project.WORKSPACE)
    monkeypatch.setattr(cli, "CONNECT", lambda profile: None)
    monkeypatch.setattr(cli, "_interactive", lambda: False)
    # the class as `uses: ./ops/marker.py:Marker` would load it
    from lely.registry import find

    found = find("./ops/marker.py:Marker", tmp_path)
    return Solo(found.cls, tmp_path)


# -- plan -------------------------------------------------------------------------


def test_plan_shows_the_change_and_changes_nothing(marker: Solo) -> None:
    result = marker("plan", "-t", "dev", "--word", "hi")

    assert result.exit_code == 0, result.output
    assert "writes hi" in result.output
    assert not (marker.root / "dev-marker.txt").exists()


def test_the_options_are_the_flags_with_their_help(marker: Solo) -> None:
    result = marker("plan", "--help")

    assert "--word" in result.output and "The word to write." in result.output
    assert "--times" in result.output and "--loud" in result.output
    assert "--tags" in result.output and "--token" in result.output
    assert "--target" in result.output and "--profile" in result.output


def test_a_missing_required_option_is_refused_by_name(marker: Solo) -> None:
    result = marker("plan", "-t", "dev")

    assert result.exit_code == 2
    assert "--word" in result.output


def test_a_reference_is_refused_with_what_to_do(marker: Solo) -> None:
    result = marker("plan", "-t", "dev", "--word", "${steps.other.word}")

    assert result.exit_code == 2
    assert "Run it under lely, or pass the value" in result.output


def test_plan_writes_a_one_step_lely_plan(marker: Solo) -> None:
    result = marker("plan", "-t", "dev", "--word", "hi", "-o", "plan.json")

    assert result.exit_code == 0, result.output
    plan = planfile.loads((marker.root / "plan.json").read_text())
    assert plan.kind == "apply" and plan.target == "dev"
    assert [s.name for s in plan.steps] == ["marker"]
    assert plan.steps[0].uses == "./ops/marker.py:Marker"
    assert plan.steps[0].plan.outputs == {"file": "dev-marker.txt"}


def test_a_secret_option_never_reaches_the_plan_file(marker: Solo) -> None:
    marker("plan", "-t", "dev", "--word", "hi", "--token", "t0p-s3cret", "-o", "p.json")

    assert "t0p-s3cret" not in (marker.root / "p.json").read_text()


# -- apply -------------------------------------------------------------------------


def test_apply_with_a_target_plans_asks_and_applies(marker: Solo) -> None:
    result = marker("apply", "-t", "dev", "--word", "hi", "--times", "2", "--yes")

    assert result.exit_code == 0, result.output
    assert (marker.root / "dev-marker.txt").read_text() == "hi hi\n"
    again = marker("plan", "-t", "dev", "--word", "hi", "--times", "2")
    assert "writes" not in again.output


def test_without_a_terminal_apply_needs_yes(marker: Solo) -> None:
    result = marker("apply", "-t", "dev", "--word", "hi")

    assert result.exit_code == 2
    assert not (marker.root / "dev-marker.txt").exists()


def test_apply_runs_a_reviewed_plan_file(marker: Solo) -> None:
    marker("plan", "-t", "dev", "--word", "hi", "-o", "plan.json")

    result = marker("apply", "--plan-file", "plan.json", "--word", "hi", "--yes")

    assert result.exit_code == 0, result.output
    assert (marker.root / "dev-marker.txt").read_text() == "hi\n"


def test_a_plan_file_made_with_other_options_is_refused(marker: Solo) -> None:
    marker("plan", "-t", "dev", "--word", "hi", "-o", "plan.json")

    result = marker("apply", "--plan-file", "plan.json", "--word", "bye", "--yes")

    assert result.exit_code == 2
    assert not (marker.root / "dev-marker.txt").exists()


def test_a_plan_file_for_another_target_is_refused(marker: Solo) -> None:
    marker("plan", "-t", "dev", "--word", "hi", "-o", "plan.json")

    result = marker("apply", "--plan-file", "plan.json", "-t", "prod", "--word", "hi")

    assert result.exit_code == 2
    assert "made for target `dev`" in result.output


def test_lely_itself_runs_the_steps_plan_file(marker: Solo, tmp_path: Path) -> None:
    """One format: a plan the step wrote is a plan `lely apply` takes, given the
    config that names the same step the same way."""
    marker("plan", "-t", "dev", "--word", "hi", "-o", "plan.json")
    (tmp_path / "lely.yml").write_text(
        "steps:\n  - name: marker\n    uses: ./ops/marker.py:Marker\n    with:\n"
        "      word: hi\n"
    )

    result = runner.invoke(cli.app, ["apply", "plan.json", "--yes"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "dev-marker.txt").read_text() == "hi\n"


def test_a_lely_plan_of_several_steps_is_not_for_a_step_alone(
    marker: Solo, tmp_path: Path
) -> None:
    (tmp_path / "lely.yml").write_text(
        "steps:\n  - name: marker\n    uses: ./ops/marker.py:Marker\n"
        "    with: {word: hi}\n  - name: other\n    uses: ./ops/marker.py:Marker\n"
        "    with: {word: ho}\n"
    )
    runner.invoke(cli.app, ["plan", "-t", "dev", "-o", "both.json"])

    result = marker("apply", "--plan-file", "both.json", "--word", "hi", "--yes")

    assert result.exit_code == 2
    assert "not for this step alone" in result.output


# -- destroy, status ------------------------------------------------------------


def test_destroy_takes_it_down(marker: Solo) -> None:
    marker("apply", "-t", "dev", "--word", "hi", "--yes")

    result = marker("destroy", "-t", "dev", "--word", "hi", "--yes")

    assert result.exit_code == 0, result.output
    assert not (marker.root / "dev-marker.txt").exists()


def test_status_lists_what_exists(marker: Solo) -> None:
    before = marker("status", "-t", "dev", "--word", "hi", "-f", "json")
    marker("apply", "-t", "dev", "--word", "hi", "--yes")
    after = marker("status", "-t", "dev", "--word", "hi", "-f", "json")

    assert "no marker yet" in before.out
    assert "dev-marker.txt" in json.dumps(json.loads(after.out))


# -- check -------------------------------------------------------------------


def test_check_holds_the_step_to_the_rules(marker: Solo) -> None:
    result = marker("check", "-t", "dev", "--word", "hi")

    assert result.exit_code == 0, result.output
    assert "plan changes nothing" in result.output
    assert "overview changes nothing" in result.output
    assert "--live" in result.output


def test_check_live_applies_and_destroys(marker: Solo) -> None:
    result = marker("check", "-t", "dev", "--word", "hi", "--live")

    assert result.exit_code == 0, result.output
    assert "apply does what the plan says, and destroy undoes it" in result.output
    assert not (marker.root / "dev-marker.txt").exists()


def test_check_fails_a_step_whose_plan_deploys(tmp_path: Path, monkeypatch) -> None:
    """What `check` can see: a plan that calls the Databricks CLI for anything but
    a read. A plan that writes a file of its own is past what it can see."""
    (tmp_path / "ops").mkdir()
    head = (
        "    def plan(self, ctx: Context) -> StepPlan:\n        path = self._path(ctx)\n"
    )
    deploying = head + "        ctx.databricks.run(['bundle', 'deploy'], ctx.root)\n"
    assert head in MARKER
    (tmp_path / "ops" / "bad.py").write_text(MARKER.replace(head, deploying))
    monkeypatch.chdir(tmp_path)
    fake = (sys.executable, str(project.FAKE_DATABRICKS), str(project.world(tmp_path)))
    monkeypatch.setattr(cli, "DATABRICKS", fake)
    monkeypatch.setattr(cli, "WHOAMI", lambda profile: project.WORKSPACE)
    monkeypatch.setattr(cli, "CONNECT", lambda profile: None)
    from lely.registry import find

    solo = Solo(find("./ops/bad.py:Marker", tmp_path).cls, tmp_path)

    result = solo("check", "-t", "dev", "--word", "hi")

    assert result.exit_code == 1
    assert "failed" in result.output and "isn't a read" in result.output


# -- the flags -----------------------------------------------------------------


def test_lists_and_words_arrive_typed(marker: Solo) -> None:
    result = marker(
        "plan",
        "-t",
        "dev",
        "--word",
        "hi",
        "--loud",
        "yes",
        "--tags",
        "a",
        "--tags",
        "b",
        "-f",
        "json",
    )

    assert result.exit_code == 0, result.output
    plan = planfile.loads(result.out)
    assert plan.steps[0].plan.changes[0].summary == "writes hi"


def test_a_wrong_value_is_refused_by_the_flag(marker: Solo) -> None:
    result = marker("plan", "-t", "dev", "--word", "hi", "--times", "many")

    assert result.exit_code == 2
    assert "--times" in result.output

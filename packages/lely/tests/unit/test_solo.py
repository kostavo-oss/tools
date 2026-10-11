"""A step on its own (SOLO-1): the command line `Step.main()` gives,
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


def variant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> Solo:
    """The marker step with something changed, as its own command line."""
    (tmp_path / "ops").mkdir(exist_ok=True)
    (tmp_path / "ops" / "other.py").write_text(text)
    monkeypatch.chdir(tmp_path)
    fake = (sys.executable, str(project.FAKE_DATABRICKS), str(project.world(tmp_path)))
    monkeypatch.setattr(cli, "DATABRICKS", fake)
    monkeypatch.setattr(cli, "WHOAMI", lambda profile: project.WORKSPACE)
    monkeypatch.setattr(cli, "CONNECT", lambda profile: None)
    monkeypatch.setattr(cli, "_interactive", lambda: False)
    from lely.registry import find

    return Solo(find("./ops/other.py:Marker", tmp_path).cls, tmp_path)


def changed(old: str, new: str, text: str = MARKER) -> str:
    assert old in text, old
    return text.replace(old, new)


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
    """SOLO-1."""
    result = marker("plan", "-t", "dev", "--word", "hi")

    assert result.exit_code == 0, result.output
    assert "writes hi" in result.output
    assert not (marker.root / "dev-marker.txt").exists()


def test_the_options_are_the_flags_with_their_help(marker: Solo) -> None:
    """SOLO-3."""
    result = marker("plan", "--help")

    assert "--word" in result.output and "The word to write." in result.output
    assert "--times" in result.output and "--loud" in result.output
    assert "--tags" in result.output and "--token" in result.output
    assert "--target" in result.output and "--profile" in result.output


def test_a_missing_required_option_is_refused_by_name(marker: Solo) -> None:
    """SOLO-3."""
    result = marker("plan", "-t", "dev")

    assert result.exit_code == 2
    assert "--word" in result.output


def test_a_reference_is_refused_with_what_to_do(marker: Solo) -> None:
    """SOLO-4."""
    result = marker("plan", "-t", "dev", "--word", "${steps.other.word}")

    assert result.exit_code == 2
    assert "Run it under lely, or pass the value" in result.output


def test_plan_writes_a_one_step_lely_plan(marker: Solo) -> None:
    """SOLO-5."""
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
    """SOLO-2."""
    result = marker("apply", "-t", "dev", "--word", "hi", "--times", "2", "--yes")

    assert result.exit_code == 0, result.output
    assert (marker.root / "dev-marker.txt").read_text() == "hi hi\n"
    again = marker("plan", "-t", "dev", "--word", "hi", "--times", "2")
    assert "writes" not in again.output


def test_without_a_terminal_apply_needs_yes(marker: Solo) -> None:
    """SOLO-2."""
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
    """SOLO-5. One format: a plan the step wrote is a plan `lely apply` takes, given the
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
    """SOLO-7."""
    result = marker("check", "-t", "dev", "--word", "hi")

    assert result.exit_code == 0, result.output
    assert "plan changes nothing" in result.output
    assert "overview changes nothing" in result.output
    assert "--live" in result.output


def test_check_live_applies_and_destroys(marker: Solo) -> None:
    """SOLO-7."""
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


def test_a_mapping_of_numbers_arrives_as_numbers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SOLO-3: a pair's value is read as the mapping declares it."""
    text = changed(
        "        #: How many times.\n",
        "        #: Limits, by name.\n        limits: Mapping[str, int] = None\n"
        "        #: Ratios, by name.\n        ratios: Mapping[str, float] = None\n"
        "        #: Switches, by name.\n        on: Mapping[str, bool] = None\n"
        "        #: How many times.\n",
    )
    text = changed(
        'f"writes {ctx.options.word}"',
        'f"writes {ctx.options.limits} {ctx.options.ratios} {ctx.options.on}"',
        text,
    )
    text = "from collections.abc import Mapping\n" + text
    solo = variant(tmp_path, monkeypatch, text)

    result = solo(
        *("plan", "-t", "dev", "--word", "hi", "--limits", "rows=3", "--limits", "n=-1"),
        *("--ratios", "half=0.5", "--on", "fast=yes"),
    )

    assert result.exit_code == 0, result.output
    assert "writes {'rows': 3, 'n': -1} {'half': 0.5} {'fast': True}" in result.output
    wrong = solo("plan", "-t", "dev", "--word", "hi", "--limits", "rows=many")
    assert wrong.exit_code == 2
    assert "--limits" in wrong.output and "not a whole number" in wrong.output


def test_a_literal_dollar_brace_is_written_as_in_a_config(marker: Solo) -> None:
    """SOLO-4: `$${` is no reference, and reaches the step as `${`."""
    result = marker("plan", "-t", "dev", "--word", "$${HOME}/x")

    assert result.exit_code == 0, result.output
    assert "writes ${HOME}/x" in result.output
    refused = marker("plan", "-t", "dev", "--word", "${HOME}/x")
    assert refused.exit_code == 2
    assert "For a literal `${`, write `$${`." in " ".join(refused.output.split())


# -- what the step gives ----------------------------------------------------------


def test_plan_prints_what_the_step_knows_and_names_what_comes_later(
    marker: Solo,
) -> None:
    """SOLO-8."""
    result = marker("plan", "-t", "dev", "--word", "hi")

    assert result.exit_code == 0, result.output
    gives = result.out[result.out.index("Gives:") :]
    assert "→ file = dev-marker.txt" in gives
    assert "→ written  known after every run" in gives
    # with `-f json`, stdout is the plan and nothing else: it is said on stderr
    as_json = marker("plan", "-t", "dev", "--word", "hi", "-f", "json")
    assert planfile.loads(as_json.out).target == "dev"
    assert "→ file = dev-marker.txt" in as_json.err
    # a destroy gives nothing
    assert "Gives:" not in marker("plan", "-t", "dev", "--word", "hi", "--destroy").output


def test_apply_prints_what_the_step_returned(marker: Solo) -> None:
    """SOLO-8."""
    result = marker("apply", "-t", "dev", "--word", "hi", "--times", "2", "--yes")

    assert result.exit_code == 0, result.output
    gives = result.out[result.out.index("Gives:") :]
    assert "→ file = dev-marker.txt" in gives
    assert "→ written = 2" in gives
    # a step with nothing left to do returned nothing: it gives what it knows
    again = marker("apply", "-t", "dev", "--word", "hi", "--times", "2", "--yes")
    assert "→ file = dev-marker.txt" in again.out and "written" not in again.out


def test_no_secret_is_printed_with_what_the_step_gives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SOLO-8: a `Secret` is `***`, and so is an output that hands back what a
    `Secret` option was given, whole or inside something."""
    text = changed(
        'outputs = (Output("file"), Output("written", known="run"))',
        'outputs = (Output("file"), Output("key"), Output("plain"), Output("deep"),'
        ' Output("written", known="run"))',
    )
    text = changed(
        'outputs = {"file": path.name}',
        "token = ctx.options.token.reveal()\n"
        '        outputs = {"file": path.name, "key": ctx.options.token,'
        ' "plain": f"Bearer {token}", "deep": {"a": [token]}}',
        text,
    )
    solo = variant(tmp_path, monkeypatch, text)
    flags = ("-t", "dev", "--word", "hi", "--token", "t0p-s3cret")

    planned = solo("plan", *flags)
    applied = solo("apply", *flags, "--yes")

    for result in (planned, applied):
        assert result.exit_code == 0, result.output
        assert "t0p-s3cret" not in result.output
        gives = result.out[result.out.index("Gives:") :]
        assert "→ file = dev-marker.txt" in gives
        assert "→ key = ***" in gives
        assert "→ plain = ***" in gives
        assert "→ deep = ***" in gives


# -- check --live says first --------------------------------------------------------


def test_check_live_says_what_it_will_do_before_it_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SOLO-7."""
    logs = changed(
        "        self._path(ctx).write_text(self._text(ctx))\n",
        "        import sys\n"
        '        print("marker: writing now", file=sys.stderr)\n'
        "        self._path(ctx).write_text(self._text(ctx))\n",
    )
    solo = variant(tmp_path, monkeypatch, logs)

    result = solo("check", "-t", "dev", "--word", "hi", "--live")

    assert result.exit_code == 0, result.output
    said = " ".join(result.err.split())
    first = (
        "--live: about to apply the step, destroy it and plan again, on target `dev` "
        f"on {project.WORKSPACE}. It makes what the plan shows, and removes it."
    )
    assert said.startswith(first)
    assert said.index(first) < said.index("marker: writing now")
    # without --live it says what --live would do, and does none of it
    dry = solo("check", "-t", "dev", "--word", "hi")
    assert "--live would apply the step, destroy it and plan again" in dry.err
    assert "about to" not in dry.err and "writing now" not in dry.err


def test_check_doesnt_speak_of_a_destroy_the_step_doesnt_have(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start, end = MARKER.index("    def plan_destroy"), MARKER.index("if __name__ ==")
    solo = variant(tmp_path, monkeypatch, MARKER[:start] + "\n" + MARKER[end:])

    dry = solo("check", "-t", "dev", "--word", "hi")
    live = solo("check", "-t", "dev", "--word", "hi", "--live")

    assert dry.exit_code == 0 and live.exit_code == 0, dry.output + live.output
    for result in (dry, live):
        said = " ".join(result.err.split())
        assert "apply the step and plan again, on" in said
        assert "The step has no destroy: what it makes stays." in said
        assert "destroy it" not in said
    assert (tmp_path / "dev-marker.txt").exists()


# -- a destroy, planned first ------------------------------------------------------


def test_a_destroy_can_be_planned_saved_and_run(marker: Solo) -> None:
    """SOLO-2: `plan --destroy -o` writes what `destroy --plan-file` runs."""
    marker("apply", "-t", "dev", "--word", "hi", "--yes")

    planned = marker("plan", "-t", "dev", "--word", "hi", "--destroy", "-o", "d.json")

    assert planned.exit_code == 0, planned.output
    assert "removes dev-marker.txt" in planned.output
    assert planfile.loads((marker.root / "d.json").read_text()).kind == "destroy"
    assert (marker.root / "dev-marker.txt").exists()
    # `apply` doesn't take it; `destroy` does
    assert (
        marker("apply", "--plan-file", "d.json", "--word", "hi", "--yes").exit_code == 2
    )
    result = marker(
        "destroy", "--plan-file", "d.json", "-t", "dev", "--word", "hi", "--yes"
    )
    assert result.exit_code == 0, result.output
    assert not (marker.root / "dev-marker.txt").exists()

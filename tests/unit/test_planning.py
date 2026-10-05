"""From the config to a plan: every step in order, and what flows between them."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

import project
from fakes import FakeDatabricks, deploy, write_bundle
from lely import planfile, planning
from lely.config import ConfigError, load
from lely.errors import LelyError
from lely.model import Change, Input, Plan, PlanKind
from lely.step import NullLog
from lely.steps.bundle import UPLOAD


def no_workspace() -> Any:
    raise AssertionError("no step here needs a workspace")


def plan(
    root: Path,
    fake: FakeDatabricks | None = None,
    target: str = "dev",
    kind: PlanKind = "apply",
    env: dict[str, str] | None = None,
) -> Plan:
    config_file = root / "lely.yml"
    if not config_file.exists():
        config_file = root / "pyproject.toml"
    return planning.plan(
        load(config_file),
        target=target,
        workspace=project.WORKSPACE,
        source=project.SOURCE,
        env=env or {},
        databricks=fake or project.databricks(root),
        log=NullLog(),
        connect=no_workspace,
        kind=kind,
    )


def printer(document: object) -> str:
    """A `plan:` command, as YAML, that prints `document`."""
    return json.dumps([sys.executable, "-c", f"print({json.dumps(document)!r})"])


# -- the scenario ------------------------------------------------------------------


def test_every_step_is_in_the_plan_in_the_order_written(tmp_path: Path) -> None:
    project.write(tmp_path)
    built = plan(tmp_path)
    assert [(s.name, s.uses, s.state) for s in built.steps] == [
        ("model", "./ops/steps.py:LatestModel", "ready"),
        ("app", "bundle", "ready"),
        ("notify", "command", "waiting"),
        ("backfill", "bundle.run", "ready"),
        ("warm", "command", "skipped"),
    ]
    assert (built.kind, built.target) == ("apply", "dev")
    assert built.workspace == project.WORKSPACE


def test_a_step_above_the_bundle_feeds_it_a_variable(tmp_path: Path) -> None:
    project.write(tmp_path)
    fake = project.databricks(tmp_path)
    built = plan(tmp_path, fake)
    model, app = built.steps[:2]
    assert model.plan.outputs == {"version": 14}
    assert app.inputs == (Input("model_version", "model.version", 14),)
    assert all("--var=model_version=14" in call for call in fake.calls)
    assert fake.verbs == ["summary", "plan"]


def test_the_bundles_plan_is_one_steps_plan_like_any_other(tmp_path: Path) -> None:
    project.write(tmp_path)
    app = plan(tmp_path).steps[1]
    assert app.plan.changes == (
        Change("jobs.bar", "create", "jobs.bar"),
        Change("pipelines.foo", "create", "pipelines.foo"),
        UPLOAD,
    )
    assert isinstance(app.plan.payload, dict)
    assert app.plan.payload["plan_version"] == 2  # the CLI's own plan, kept whole


def test_a_step_that_takes_what_doesnt_exist_yet_is_waiting(tmp_path: Path) -> None:
    project.write(tmp_path)
    notify = plan(tmp_path).steps[2]
    assert notify.state == "waiting"
    assert notify.waits_for == ("app.resources.jobs.bar.id",)
    assert notify.waiting == "waiting for app.resources.jobs.bar.id"
    assert notify.plan.changes == ()  # nobody can know them
    assert notify.inputs == (Input("", "app.resources.jobs.bar.id", None, known=False),)


def test_what_is_deployed_already_is_known(tmp_path: Path) -> None:
    text = project.LELY_YML.replace("resources.jobs.bar.id", "resources.jobs.backfill.id")
    project.write(tmp_path, text)
    notify = plan(tmp_path).steps[2]
    assert notify.state == "ready"
    assert notify.plan.changes[0].summary == "runs ./ops/notify.sh 771"
    assert notify.inputs == (Input("", "app.resources.jobs.backfill.id", "771"),)


def test_a_step_that_names_a_bundle_step_takes_it(tmp_path: Path) -> None:
    project.write(tmp_path)
    backfill = plan(tmp_path).steps[3]
    assert backfill.inputs == (Input("bundle", "app"),)
    assert backfill.plan.changes == (
        Change("jobs.backfill", "run", "runs jobs.backfill"),
    )


def test_targets_skip_a_step_and_the_plan_says_so(tmp_path: Path) -> None:
    project.write(tmp_path)
    warm = plan(tmp_path).steps[4]
    assert warm.skipped == "not for target `dev`"
    assert warm.plan.changes == ()
    assert plan(tmp_path, target="prod").steps[4].state == "ready"


def test_the_summary_counts(tmp_path: Path) -> None:
    project.write(tmp_path)
    summary = plan(tmp_path).summary
    assert (summary.changes, summary.runs, summary.destructive, summary.waiting) == (
        2,
        2,
        0,
        1,
    )
    assert [step.name for step in plan(tmp_path).waiting] == ["notify"]


def test_the_plan_keeps_the_outputs_another_step_takes(tmp_path: Path) -> None:
    """Not every field of every resource: the plan file isn't the bundle's config."""
    text = project.LELY_YML.replace("resources.jobs.bar.id", "resources.jobs.backfill.id")
    project.write(tmp_path, text)
    app = plan(tmp_path).steps[1]
    assert app.plan.outputs == {
        "target": "dev",
        "name": "shop",
        "resources.jobs.backfill.id": "771",
    }


def test_the_same_project_in_pyproject_gives_the_same_plan(tmp_path: Path) -> None:
    """003, done when: the same steps, changes and outputs, and the same "made
    from", so a plan made from one is accepted with the other."""
    yml, toml = tmp_path / "yml", tmp_path / "toml"
    yml.mkdir()
    toml.mkdir()
    project.write(yml)
    project.write(toml, toml=True)
    assert plan(yml) == plan(toml)


def test_made_from_follows_what_the_config_says_not_how(tmp_path: Path) -> None:
    project.write(tmp_path)
    before = [s.made_from for s in plan(tmp_path).steps]
    project.write(tmp_path, project.LELY_YML + "\n# a note, and nothing else\n")
    assert [s.made_from for s in plan(tmp_path).steps] == before
    project.write(tmp_path, project.LELY_YML.replace("jobs.backfill}", "jobs.bar}"))
    after = [s.made_from for s in plan(tmp_path).steps]
    assert after[:3] == before[:3]
    assert after[3] != before[3]


def test_made_from_counts_the_environment_by_name(tmp_path: Path) -> None:
    """A rotated token isn't a new plan, and its value is in no plan file."""
    text = project.LELY_YML.replace(
        "with: {apply: [./ops/warm.sh]}",
        "with: {apply: [./ops/warm.sh], env: {T: '${env.TOKEN}'}}",
    ).replace("targets: [prod]", "targets: [dev]")
    project.write(tmp_path, text)
    one = plan(tmp_path, env={"TOKEN": "t0k-one"})
    two = plan(tmp_path, env={"TOKEN": "t0k-two"})
    assert one.steps[-1].made_from == two.steps[-1].made_from
    assert "t0k-one" not in planfile.dumps(one)


def test_a_value_from_the_environment_cant_reach_an_argument(tmp_path: Path) -> None:
    """005/R34, 010/R8: a value from the environment is a secret, and a
    command's arguments are visible to every process on the machine."""
    text = project.LELY_YML.replace(
        "with: {apply: [./ops/warm.sh]}",
        "with: {apply: [./ops/warm.sh, '${env.TOKEN}']}",
    ).replace("targets: [prod]", "targets: [dev]")
    project.write(tmp_path, text)
    with pytest.raises(LelyError, match="`apply` would hold a secret"):
        plan(tmp_path, env={"TOKEN": "t0k"})


# -- waiting, wherever the step stands ---------------------------------------------


def test_a_bundle_fed_by_a_run_waits_and_so_does_what_is_below_it(
    tmp_path: Path,
) -> None:
    """005/R26: one rule. A step that takes an *after every run* output waits —
    here it is the bundle, above which a script produces its variable."""
    text = project.LELY_YML.replace(
        "uses: ./ops/steps.py:LatestModel\n    with:\n      model: dev.ml.churn",
        "uses: command\n    with: {apply: [./ops/warm.sh], outputs: [version]}",
    )
    project.write(tmp_path, text)
    fake = project.databricks(tmp_path)
    model, app, notify, backfill, _ = plan(tmp_path, fake).steps
    assert model.state == "ready"
    assert app.waits_for == ("model.version",)
    assert app.every_deploy  # only a run produces it
    assert app.waiting == "waiting for model.version — on every deploy"
    assert not notify.every_deploy  # the job's id exists once it is deployed
    assert fake.calls == []  # the plugin isn't called with half its options
    assert notify.waits_for == ("app.resources.jobs.bar.id",)
    assert backfill.waits_for == ("app",)


def test_a_plan_command_that_gives_the_value_keeps_the_bundle_ready(
    tmp_path: Path,
) -> None:
    """010/R5: a command that feeds the bundle gives its value from its plan
    command — a lookup changes nothing, and planning is where it belongs."""
    command = (
        "uses: command\n    with:\n      apply: [./ops/warm.sh]\n"
        f"      plan: {printer({'outputs': {'version': 15}})}\n"
        "      outputs: [version]"
    )
    text = project.LELY_YML.replace(
        "uses: ./ops/steps.py:LatestModel\n    with:\n      model: dev.ml.churn", command
    )
    project.write(tmp_path, text)
    app = plan(tmp_path).steps[1]
    assert app.state == "ready"
    assert app.inputs == (Input("model_version", "model.version", 15),)


def test_a_resource_the_bundle_doesnt_have_is_refused_at_plan(tmp_path: Path) -> None:
    """002/R14a: offline the reference fits the shape; that the job exists is
    checked when the step is planned, before anything changes."""
    text = project.LELY_YML.replace("resources.jobs.bar.id", "resources.jobs.bra.id")
    project.write(tmp_path, text)
    planning.check(load(tmp_path / "lely.yml"))
    with pytest.raises(LelyError) as caught:
        plan(tmp_path)
    assert "step `app` has no `resources.jobs.bra.id`" in str(caught.value)
    assert "resources.jobs.bar.id" in str(caught.value)


def test_two_bundles_in_one_project(tmp_path: Path) -> None:
    """004/R3a: each has its own name, path and outputs, and one feeds another."""
    project.write(tmp_path)
    api = {
        "name": "api",
        "variables": {"job": None},
        "resources": {"apps": {"web": {"name": "web", "description": "${var.job}"}}},
    }
    write_bundle(tmp_path / "api", api)
    text = (
        "steps:\n"
        "  - name: data\n    uses: bundle\n    with: {vars: {model_version: 1}}\n"
        "  - name: api\n    uses: bundle\n    with:\n      path: api\n"
        "      vars: {job: '${steps.data.resources.jobs.backfill.id}'}\n"
    )
    (tmp_path / "lely.yml").write_text(text)
    fake = project.databricks(tmp_path)
    deploy(fake.world, {}, name="api")
    data, api_step = plan(tmp_path, fake).steps
    assert [c.key for c in data.plan.changes] == ["jobs.bar", "pipelines.foo", "files"]
    assert api_step.inputs == (Input("job", "data.resources.jobs.backfill.id", "771"),)
    assert [c.key for c in api_step.plan.changes] == ["apps.web", "files"]
    assert data.plan.outputs["name"] == "shop"
    assert api_step.plan.outputs["name"] == "api"


# -- a plan to destroy -------------------------------------------------------------


def test_a_destroy_plan_says_per_step_what_would_be_removed(tmp_path: Path) -> None:
    project.write(tmp_path)
    built = plan(tmp_path, kind="destroy")
    assert built.kind == "destroy"
    states = {s.name: (s.state, s.skipped) for s in built.steps}
    assert states == {
        "model": ("skipped", "`./ops/steps.py:LatestModel` has nothing to destroy"),
        "app": ("ready", None),
        "notify": ("skipped", "it needs app.resources.jobs.bar.id, which isn't there"),
        "backfill": ("skipped", "`bundle.run` has nothing to destroy"),
        "warm": ("skipped", "not for target `dev`"),
    }
    app = built.steps[1]
    assert [(c.key, c.action, c.destructive) for c in app.plan.changes] == [
        ("jobs.backfill", "delete", True)
    ]
    assert app.plan.outputs == {}  # a destroy gives nothing


def test_a_destroy_resolves_inputs_from_the_top_down(tmp_path: Path) -> None:
    """002/R21: a step above the bundle that only looks something up still does
    its lookup, so the bundle is asked with the variable it was deployed with."""
    project.write(tmp_path)
    fake = project.databricks(tmp_path)
    plan(tmp_path, fake, kind="destroy")
    assert all("--var=model_version=14" in call for call in fake.calls)


def test_a_command_with_a_destroy_command_is_in_the_destroy_plan(
    tmp_path: Path,
) -> None:
    text = project.LELY_YML.replace(
        'apply: [./ops/notify.sh, "${steps.app.resources.jobs.bar.id}"]',
        "apply: [./ops/notify.sh]\n      destroy: [./ops/warm.sh, --drop]",
    )
    project.write(tmp_path, text)
    notify = plan(tmp_path, kind="destroy").steps[2]
    assert notify.plan.changes == (
        Change("notify", "run", "runs ./ops/warm.sh --drop", destructive=True),
    )


def test_nothing_deployed_is_a_destroy_plan_with_nothing_in_it(tmp_path: Path) -> None:
    project.write(tmp_path)
    fake = FakeDatabricks(project.world(tmp_path, deployed=False))
    built = plan(tmp_path, fake, kind="destroy")
    assert built.summary.empty
    assert built.steps[1].plan.notes[0].startswith("not deployed, as far as")


# -- check: what validate finds, with no workspace ----------------------------------


def problems(root: Path, text: str) -> list[str]:
    project.write(root, text)
    with pytest.raises(ConfigError) as caught:
        planning.check(load(root / "lely.yml"))
    return list(caught.value.problems)


def test_check_passes_the_scenario_and_returns_the_wiring(tmp_path: Path) -> None:
    project.write(tmp_path)
    wires = planning.check(load(tmp_path / "lely.yml"))
    assert [(w.name, w.takes) for w in wires] == [
        ("model", ()),
        ("app", (("model_version", "model.version"),)),
        ("notify", (("", "app.resources.jobs.bar.id"),)),
        ("backfill", (("bundle", "app"),)),
        ("warm", ()),
    ]
    assert [output.name for output in wires[0].gives] == ["version"]
    assert wires[3].gives == ()
    assert not any(w.warnings for w in wires)


def test_check_finds_an_unknown_plugin(tmp_path: Path) -> None:
    [problem] = problems(tmp_path, "steps:\n  - uses: bundel\n")
    assert problem.startswith(f"{tmp_path / 'lely.yml'}:2:5: No plugin named `bundel`")


def test_check_finds_a_bad_option(tmp_path: Path) -> None:
    [problem] = problems(tmp_path, "steps:\n  - uses: bundle\n    with: {paht: x}\n")
    assert "unknown option `paht`; known: path, vars" in problem


def test_check_refuses_a_reference_down_the_list(tmp_path: Path) -> None:
    """002, done when: the message says what to change."""
    text = project.LELY_YML.replace("model: dev.ml.churn", "model: ${steps.app.name}")
    [problem] = problems(tmp_path, text)
    assert problem.endswith(
        "${steps.app.name}: step `app` is listed below step `model`, and a step can "
        "only use what is above it; move `app` up, or `model` down"
    )


def test_check_refuses_an_output_that_doesnt_exist(tmp_path: Path) -> None:
    text = project.LELY_YML.replace("${steps.model.version}", "${steps.model.verison}")
    [problem] = problems(tmp_path, text)
    assert problem.endswith(
        "${steps.model.verison}: step `model` gives no output `verison`; "
        "it gives: version"
    )


def test_check_refuses_a_reference_that_fits_no_shape(tmp_path: Path) -> None:
    text = project.LELY_YML.replace("resources.jobs.bar.id", "resources.jobs")
    [problem] = problems(tmp_path, text)
    assert (
        "step `app` gives no output `resources.jobs`; it gives: target, name" in problem
    )


def test_check_refuses_the_spellings_from_before(tmp_path: Path) -> None:
    text = project.LELY_YML.replace("model: dev.ml.churn", "model: ${var.catalog}")
    [problem] = problems(tmp_path, text)
    assert "write `${steps.<bundle step>.var.catalog}`" in problem


def test_check_refuses_a_step_that_runs_for_more_targets_than_what_it_takes(
    tmp_path: Path,
) -> None:
    text = project.LELY_YML.replace(
        "    uses: bundle\n", "    uses: bundle\n    targets: [dev]\n"
    )
    found = problems(tmp_path, text)
    assert len(found) == 2  # notify and backfill both lean on `app`
    assert (
        "step `app` runs only for dev, and step `notify` also runs for every" in found[0]
    )
    assert "`app`: step `app` runs only for dev, and step `backfill`" in found[1]


def test_check_refuses_a_run_placed_above_its_bundle(tmp_path: Path) -> None:
    """010/R12: it needs that bundle deployed — the same rule as any reference."""
    text = (
        "steps:\n"
        "  - name: backfill\n    uses: bundle.run\n"
        "    with: {bundle: app, resource: jobs.backfill}\n"
        "  - name: app\n    uses: bundle\n"
    )
    [problem] = problems(tmp_path, text)
    assert "`app`: step `app` is listed below step `backfill`" in problem


def test_check_warns_about_a_step_that_waits_on_every_deploy(tmp_path: Path) -> None:
    """002/R19: such a step can never be approved ahead of time."""
    text = (
        "steps:\n"
        "  - name: seed\n    uses: command\n"
        "    with: {apply: [./ops/warm.sh], outputs: [count]}\n"
        "  - name: tell\n    uses: command\n"
        "    with: {apply: [./ops/notify.sh, '${steps.seed.count}']}\n"
    )
    project.write(tmp_path, text)
    seed, tell = planning.check(load(tmp_path / "lely.yml"))
    assert [(o.name, o.known) for o in seed.gives] == [("count", "run")]
    assert tell.warnings == (
        "step `tell` takes `seed.count`, which is known only after every run: it "
        "waits on every deploy, and a plan applied from a file always stops before it",
    )


def test_check_refuses_an_output_a_command_step_doesnt_list(tmp_path: Path) -> None:
    text = (
        "steps:\n"
        "  - name: seed\n    uses: command\n    with: {apply: [./ops/warm.sh]}\n"
        "  - name: tell\n    uses: command\n"
        "    with: {apply: [./ops/notify.sh, '${steps.seed.count}']}\n"
    )
    [problem] = problems(tmp_path, text)
    assert "step `seed` gives no output `count`; it gives nothing" in problem


# -- what a plugin may and may not do ----------------------------------------------

BROKEN = """\
from dataclasses import dataclass
from lely.model import Change, Output, Secret, StepPlan

class Raises:
    @dataclass(frozen=True)
    class Options:
        pass
    outputs = (Output("version"), Output("id", "exists"), Output("count", "run"))
    def plan(self, ctx):
        raise KeyError("model")
    def apply(self, ctx, plan):
        return {}

class Wrong(Raises):
    def plan(self, ctx):
        return {"changes": []}

class Leaks(Raises):
    def plan(self, ctx):
        return StepPlan(outputs={"version": 1}, payload={"token": Secret("t0k")})

class Undeclared(Raises):
    def plan(self, ctx):
        return StepPlan(outputs={"version": 1, "surprise": 2})

class Withholds(Raises):
    def plan(self, ctx):
        return StepPlan()

class TooEarly(Raises):
    def plan(self, ctx):
        return StepPlan(outputs={"version": 1, "count": 3})

class Promises(Raises):
    def plan(self, ctx):
        return StepPlan(outputs={"version": 1}, later=("version",))

class Twice(Raises):
    def plan(self, ctx):
        change = Change("a", "create", "a")
        return StepPlan(changes=(change, change), outputs={"version": 1})
"""


@pytest.mark.parametrize(
    ("cls", "message"),
    [
        ("Raises", "step `x` (./broken.py:Raises) failed to plan: KeyError: 'model'"),
        ("Wrong", "`plan` returned dict, not a StepPlan"),
        ("Leaks", "holds a secret; a plan file never does"),
        ("Undeclared", "gave an output `surprise` its plugin doesn't declare"),
        ("Withholds", "declares `version` as known at plan, and its plan gave none"),
        ("TooEarly", "declares `count` as known after every run, and its plan gave it"),
        ("Promises", "names `version` as coming later"),
        ("Twice", "two changes share a key"),
    ],
)
def test_a_misbehaving_plugin_is_named(tmp_path: Path, cls: str, message: str) -> None:
    (tmp_path / "broken.py").write_text(BROKEN)
    project.write(tmp_path, f"steps:\n  - name: x\n    uses: ./broken.py:{cls}\n")
    with pytest.raises(LelyError, match=message.replace("(", r"\(").replace(")", r"\)")):
        plan(tmp_path)


# -- found in review ---------------------------------------------------------------


def test_a_value_is_shown_under_its_own_options_name(tmp_path: Path) -> None:
    """002/R20. In a `pyproject.toml` written with dotted keys the positions of
    two values can't be told apart; the option each fills still can."""
    (tmp_path / "pair.py").write_text(
        "from dataclasses import dataclass\n"
        "from lely.model import Output, StepPlan\n"
        "class Pair:\n"
        "    @dataclass(frozen=True)\n"
        "    class Options:\n"
        "        pass\n"
        "    outputs = (Output('catalog'), Output('version'))\n"
        "    def plan(self, ctx):\n"
        "        return StepPlan(outputs={'catalog': 'prod_catalog', 'version': 14})\n"
        "    def apply(self, ctx, plan):\n"
        "        return {}\n"
    )
    text = (
        "[[tool.lely.steps]]\n"
        'name = "model"\nuses = "./pair.py:Pair"\n\n'
        "[[tool.lely.steps]]\n"
        'name = "app"\nuses = "bundle"\n'
        'with.vars.catalog = "${steps.model.catalog}"\n'
        'with.vars.model_version = "${steps.model.version}"\n'
    )
    project.write(tmp_path, text, toml=True)
    wires = planning.check(load(tmp_path / "pyproject.toml"))
    assert wires[1].takes == (
        ("catalog", "model.catalog"),
        ("model_version", "model.version"),
    )
    fake = project.databricks(tmp_path)
    app = plan(tmp_path, fake).steps[1]
    assert app.inputs == (
        Input("catalog", "model.catalog", "prod_catalog"),
        Input("model_version", "model.version", 14),
    )
    assert "--var=catalog=prod_catalog" in fake.calls[0]


def test_a_yaml_alias_used_twice_keeps_both_names(tmp_path: Path) -> None:
    text = (
        "steps:\n"
        "  - name: model\n    uses: ./ops/steps.py:LatestModel\n"
        "    with: {model: dev.ml.churn}\n"
        "  - name: seed\n    uses: command\n    with:\n      apply: [./ops/warm.sh]\n"
        "      env: {FIRST: &v '${steps.model.version}', SECOND: *v}\n"
    )
    project.write(tmp_path, text)
    seed = planning.check(load(tmp_path / "lely.yml"))[1]
    assert [label for label, _ in seed.takes] == ["FIRST", "SECOND"]


def test_validate_already_knows_where_an_environment_value_may_not_go(
    tmp_path: Path,
) -> None:
    """002/R18: as much as can be is checked offline. A value from the
    environment is a secret whatever it turns out to be."""
    text = project.LELY_YML.replace(
        "with: {apply: [./ops/warm.sh]}",
        "with: {apply: [./ops/warm.sh, '${env.TOKEN}']}",
    )
    [problem] = problems(tmp_path, text)
    assert "`apply` would hold a secret; only a `Secret` option may" in problem
    allowed = project.LELY_YML.replace(
        "with: {apply: [./ops/warm.sh]}",
        "with: {apply: [./ops/warm.sh], env: {T: '${env.TOKEN}'}}",
    )
    project.write(tmp_path, allowed)
    planning.check(load(tmp_path / "lely.yml"))  # no environment needed to check it


RAISES = """\
from dataclasses import dataclass
from lely.model import StepPlan

class BadOptions:
    @dataclass(frozen=True)
    class Options:
        size: int = 1
        def __post_init__(self):
            raise ValueError("size must be even")
    def plan(self, ctx):
        return StepPlan()
    def apply(self, ctx, plan):
        return {}

class BadOutputs(BadOptions):
    @dataclass(frozen=True)
    class Options:
        pass
    @staticmethod
    def outputs(written):
        return written["nope"]
"""


def test_a_plugin_whose_own_code_raises_is_named_not_a_traceback(tmp_path: Path) -> None:
    (tmp_path / "raises.py").write_text(RAISES)
    [options] = problems(
        tmp_path, "steps:\n  - name: x\n    uses: ./raises.py:BadOptions\n"
    )
    assert "its options can't be built: ValueError: size must be even" in options
    [outputs] = problems(
        tmp_path, "steps:\n  - name: x\n    uses: ./raises.py:BadOutputs\n"
    )
    assert "`./raises.py:BadOutputs`: its `outputs` failed: KeyError: 'nope'" in outputs


# -- found in the second review ------------------------------------------------------

PICKY = """\
from dataclasses import dataclass
from lely.model import Secret, StepPlan

class Picky:
    '''Checks its token when its options are built.'''
    @dataclass(frozen=True)
    class Options:
        token: Secret
        def __post_init__(self):
            if len(self.token.reveal()) < 8:
                raise ValueError("token is too short to be one")
    def plan(self, ctx):
        return StepPlan()
    def apply(self, ctx, plan):
        return {}
"""


def test_validate_doesnt_hand_a_plugin_a_made_up_secret(tmp_path: Path) -> None:
    """Offline, an environment value is unknown and known to be a secret. It is
    not stood in for: a plugin that checks its token would refuse the stand-in."""
    (tmp_path / "picky.py").write_text(PICKY)
    text = (
        "steps:\n  - name: hook\n    uses: ./picky.py:Picky\n"
        "    with: {token: '${env.HOOK_TOKEN}'}\n"
    )
    project.write(tmp_path, text)
    planning.check(load(tmp_path / "lely.yml"))
    assert plan(tmp_path, env={"HOOK_TOKEN": "long-enough-to-be-one"}).steps[0].state == (
        "ready"
    )
    with pytest.raises(LelyError, match="token is too short to be one"):
        plan(tmp_path, env={"HOOK_TOKEN": "short"})


def test_validate_refuses_an_environment_value_as_a_bundle_variable(
    tmp_path: Path,
) -> None:
    """002/R18. A bundle's variables end up in its deployed config, so one can't
    hold a secret — and that is known without the value."""
    text = project.LELY_YML.replace(
        "model_version: ${steps.model.version}", "model_version: ${env.VERSION}"
    )
    [problem] = problems(tmp_path, text)
    assert "`vars` would hold a secret; only a `Secret` option may" in problem


def test_a_bundle_variable_is_passed_as_it_was_written(tmp_path: Path) -> None:
    text = (
        "steps:\n  - name: app\n    uses: bundle\n"
        "    with: {vars: {model_version: 3.10, catalog: 0123}}\n"
    )
    project.write(tmp_path, text)
    fake = project.databricks(tmp_path)
    plan(tmp_path, fake)
    assert [word for word in fake.calls[0] if word.startswith("--var")] == [
        "--var=model_version=3.10",
        "--var=catalog=0123",
    ]


# -- found in the third review -------------------------------------------------------


def test_what_a_step_is_made_from_follows_the_text_a_plugin_is_handed(
    tmp_path: Path,
) -> None:
    """`1.10` edited to `1.1` is the same number and another `--var`: outside
    git nothing else would notice."""
    text = (
        "steps:\n  - name: app\n    uses: bundle\n"
        "    with: {vars: {model_version: 1.10}}\n"
    )
    project.write(tmp_path, text)
    before = planning.made_from(load(tmp_path / "lely.yml").steps[0])
    project.write(tmp_path, text.replace("1.10", "1.1"))
    assert planning.made_from(load(tmp_path / "lely.yml").steps[0]) != before


def test_a_bundle_variable_can_be_a_null_from_another_step(tmp_path: Path) -> None:
    (tmp_path / "nothing.py").write_text(
        "from dataclasses import dataclass\n"
        "from lely.model import Output, StepPlan\n"
        "class Nothing:\n"
        "    @dataclass(frozen=True)\n"
        "    class Options:\n"
        "        pass\n"
        "    outputs = (Output('value'),)\n"
        "    def plan(self, ctx):\n"
        "        return StepPlan(outputs={'value': None})\n"
        "    def apply(self, ctx, plan):\n"
        "        return {}\n"
    )
    text = (
        "steps:\n  - name: lookup\n    uses: ./nothing.py:Nothing\n"
        "  - name: app\n    uses: bundle\n"
        "    with: {vars: {model_version: '${steps.lookup.value}'}}\n"
    )
    project.write(tmp_path, text)
    fake = project.databricks(tmp_path)
    assert plan(tmp_path, fake).steps[1].state == "ready"
    assert "--var=model_version=" in fake.calls[0]


def test_no_step_runs_for_a_target_when_none_names_one(tmp_path: Path) -> None:
    text = "steps:\n  - name: app\n    uses: bundle\n    targets: []\n"
    project.write(tmp_path, text)
    with pytest.raises(LelyError, match=r"leave it out \(they name no target at all\)"):
        plan(tmp_path)

"""From `sluis.yml` to a plan: the steps, the bundle, what flows between them."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

import project
from fakes import FakeDatabricks
from sluis import planning
from sluis.config import ConfigError, load
from sluis.errors import SluisError
from sluis.model import Change, Plan
from sluis.step import NullLog


def no_workspace(host: str | None) -> Any:
    raise AssertionError("no step here needs a workspace")


def plan(
    root: Path, fake: FakeDatabricks | None = None, target: str | None = None
) -> Plan:
    return planning.plan(
        load(root / "sluis.yml"),
        target=target,
        databricks=fake or project.databricks(),
        env={},
        log=NullLog(),
        connect=no_workspace,
    )


def test_a_pre_steps_output_becomes_a_bundle_variable(tmp_path: Path) -> None:
    project.write(tmp_path)
    fake = project.databricks()
    built = plan(tmp_path, fake)
    assert built.pre[0].plan.outputs == {"version": 14}
    assert built.deploy.variables == (("model_version", "14"),)
    assert fake.calls[:3] == [
        ("validate", None, {"model_version": planning.PENDING}),
        ("validate", "dev", {"model_version": "14"}),
        ("plan", "dev", {"model_version": "14"}),
    ]
    assert fake.calls[3] == ("summary", "dev", {})


def test_the_bundles_plan_is_kept_whole_for_deploy(tmp_path: Path) -> None:
    project.write(tmp_path)
    built = plan(tmp_path)
    assert [c.key for c in built.deploy.changes] == [
        "resources.jobs.bar",
        "resources.pipelines.foo",
    ]
    assert built.deploy.document == project.fixture("cli/plan-create.json")


def test_post_steps_plan_in_order(tmp_path: Path) -> None:
    project.write(tmp_path)
    built = plan(tmp_path)
    assert [(s.name, s.phase) for s in built.steps] == [
        ("model", "pre"),
        ("tables", "post"),
        ("notify", "post"),
        ("backfill", "post"),
    ]
    tables, _, backfill = built.post
    assert [c.key for c in tables.plan.changes] == [
        "dev.sales.customers",
        "dev.sales.orders",
        "dev.sales.big_orders",
    ]
    assert backfill.plan.changes == (
        Change("resources.jobs.backfill", "run", "runs jobs.backfill"),
    )


def test_a_step_needing_what_this_deploy_creates_is_decided_at_apply(
    tmp_path: Path,
) -> None:
    project.write(tmp_path)
    notify = plan(tmp_path).post[1]
    assert notify.plan.changes == ()
    assert notify.plan.deferred == "resources.jobs.bar is created by this deploy"


def test_an_id_of_something_deployed_already_is_resolved(tmp_path: Path) -> None:
    text = project.sluis_yml().replace(
        "resources.jobs.bar.id", "resources.jobs.backfill.id"
    )
    project.write(tmp_path, text)
    notify = plan(tmp_path).post[1]
    assert notify.plan.deferred is None
    assert notify.plan.changes[0].summary == "runs ./notify.sh 771"


def test_targets_leave_a_step_out(tmp_path: Path) -> None:
    project.write(tmp_path)
    assert "warm" not in [s.name for s in plan(tmp_path).steps]


def test_the_summary_counts(tmp_path: Path) -> None:
    project.write(tmp_path)
    summary = plan(tmp_path).summary
    assert (summary.changes, summary.runs, summary.destructive, summary.deferred) == (
        5,
        1,
        0,
        1,
    )


def test_a_variable_decided_at_apply_defers_the_bundle(tmp_path: Path) -> None:
    printed = json.dumps({"deferred": "not yet"})
    printer = json.dumps([sys.executable, "-c", f"print({printed!r})"])
    looked_up = (
        "uses: ./ops/steps.py:LatestModel\n"
        "    with:\n"
        "      model: ${var.catalog}.ml.churn"
    )
    deferred = f"uses: command\n    with:\n      apply: [./x.sh]\n      plan: {printer}"
    text = project.sluis_yml().replace(looked_up, deferred)
    project.write(tmp_path, text)
    fake = project.databricks()
    built = plan(tmp_path, fake)
    assert built.pre[0].plan.deferred == "not yet"
    assert built.deploy.deferred == (
        "its variables are decided at apply: "
        "model_version (step `model` is decided at apply)"
    )
    assert [call[0] for call in fake.calls] == ["validate", "summary"]
    # nothing is known to exist, so every id waits for the deploy
    assert built.post[1].plan.deferred == "resources.jobs.bar is created by this deploy"


def test_options_hash_ignores_environment_values(tmp_path: Path) -> None:
    text = project.sluis_yml().replace(
        "apply: [./warm.sh]", "apply: [./warm.sh, '${env.TOKEN}']"
    )
    project.write(tmp_path, text.replace("targets: [prod]", "targets: [dev]"))
    config = load(tmp_path / "sluis.yml")

    def hashed(token: str) -> str:
        built = planning.plan(
            config,
            target=None,
            databricks=project.databricks(),
            env={"TOKEN": token},
            log=NullLog(),
            connect=no_workspace,
        )
        return built.post[-1].options_hash

    assert hashed("one") == hashed("two")


# -- check: what validate finds, with no workspace ------------------------------


def problems(root: Path, text: str) -> list[str]:
    project.write(root, text)
    with pytest.raises(ConfigError) as caught:
        planning.check(load(root / "sluis.yml"))
    return list(caught.value.problems)


def test_check_passes_the_scenario(tmp_path: Path) -> None:
    project.write(tmp_path)
    planning.check(load(tmp_path / "sluis.yml"))


def test_check_finds_an_unknown_step(tmp_path: Path) -> None:
    [problem] = problems(tmp_path, "post:\n  - uses: deltaplna\n")
    assert problem.startswith(f"{tmp_path / 'sluis.yml'}:2:5: No step named `deltaplna`")


def test_check_finds_a_bad_option(tmp_path: Path) -> None:
    [problem] = problems(
        tmp_path, "post:\n  - uses: deltaplan\n    with: {confg: x.yml}\n"
    )
    assert "unknown option `confg`; known: config, target, select, executable" in problem


def test_check_finds_a_reference_that_cant_stand_there(tmp_path: Path) -> None:
    text = project.sluis_yml().replace(
        "model: ${var.catalog}.ml.churn", "model: ${var.model_version}"
    )
    [problem] = problems(tmp_path, text)
    assert problem.endswith(
        "${var.model_version}: `model_version` is set by bundle_vars from the pre "
        "steps' outputs, so step `model` can't read it"
    )


def test_check_finds_a_bundle_variable_from_a_post_step(tmp_path: Path) -> None:
    text = project.sluis_yml().replace("${steps.model.version}", "${steps.tables.x}")
    [problem] = problems(tmp_path, text)
    assert problem.endswith("${steps.tables.x}: step `tables` runs after bundle_vars")


# -- what a step may and may not do ----------------------------------------------

BROKEN = """\
from dataclasses import dataclass
from sluis.model import StepPlan, Secret

class Raises:
    @dataclass(frozen=True)
    class Options:
        pass
    def plan(self, ctx):
        raise KeyError("model")
    def apply(self, ctx, plan):
        return {}

class Wrong(Raises):
    def plan(self, ctx):
        return {"changes": []}

class Leaks(Raises):
    def plan(self, ctx):
        return StepPlan(payload={"token": Secret("t0k")})
"""


@pytest.mark.parametrize(
    ("cls", "message"),
    [
        ("Raises", "step `x` (./broken.py:Raises) failed to plan: KeyError: 'model'"),
        ("Wrong", "`plan` returned dict, not a StepPlan"),
        ("Leaks", "holds a secret; a plan file never does"),
    ],
)
def test_a_misbehaving_step_is_named(tmp_path: Path, cls: str, message: str) -> None:
    (tmp_path / "broken.py").write_text(BROKEN)
    project.write(tmp_path, f"pre:\n  - name: x\n    uses: ./broken.py:{cls}\n")
    with pytest.raises(SluisError, match=message.replace("(", r"\(").replace(")", r"\)")):
        plan(tmp_path)

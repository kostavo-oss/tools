"""The step contract, as checks a test can run — for sluis's steps and yours.

    from sluis.testing import check_plan, context

    def test_plans_the_alias():
        ctx = context(MyStep.Options(model="main.ml.churn"), target="dev")
        plan = check_plan(MyStep(), ctx)
        assert [c.key for c in plan.changes] == ["alias champion"]

`check_plan` holds a plan to what every step's plan must be: a `StepPlan`,
unique change keys, and a round trip through the plan file that loses nothing
and leaks no secret. Milestone 2 adds the apply half: plan, apply, plan again
is empty.

`context` builds a `Context` with nothing behind it: a step that reaches for the
Databricks CLI or the workspace without the test giving it one fails loudly.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn, TypeVar

from sluis.model import Json, Outputs, Phase, StepPlan
from sluis.planfile import step_plan_from_json, step_plan_to_json
from sluis.step import Context, NullLog

OptionsT = TypeVar("OptionsT")


class NoDatabricks:
    """A Databricks CLI that isn't there: any use fails the test."""

    def validate(self, target: str | None, variables: Mapping[str, str]) -> NoReturn:
        _refuse()

    def plan(self, target: str, variables: Mapping[str, str]) -> NoReturn:
        _refuse()

    def summary(self, target: str) -> NoReturn:
        _refuse()


def _refuse() -> NoReturn:
    raise AssertionError(
        "the step ran the Databricks CLI; give the context a `databricks=` fake"
    )


def _no_workspace() -> NoReturn:
    raise AssertionError("the step connected to a workspace; give the context `connect=`")


def context(
    options: OptionsT,
    *,
    target: str = "dev",
    phase: Phase = "post",
    name: str = "step",
    bundle: Mapping[str, Json] | None = None,
    deployed: Mapping[str, Json] | None = None,
    outputs: Mapping[str, Outputs] | None = None,
    root: Path | None = None,
    env: Mapping[str, str] | None = None,
    databricks: Any = None,
    connect: Any = None,
) -> Context[OptionsT]:
    root = root or Path.cwd()
    return Context(
        target=target,
        phase=phase,
        name=name,
        options=options,
        bundle=bundle
        or {
            "bundle": {"name": "test", "target": target},
            "variables": {},
            "resources": {},
        },
        deployed=deployed,
        outputs=outputs or {},
        root=root,
        bundle_root=root,
        env=dict(os.environ) if env is None else env,
        databricks=databricks or NoDatabricks(),
        log=NullLog(),
        connect=connect or _no_workspace,
    )


def check_plan(step: Any, ctx: Context[Any]) -> StepPlan:
    """Plan once, and hold the result to the contract. Returns the plan."""
    result = step.plan(ctx)
    assert isinstance(result, StepPlan), f"plan returned {type(result).__name__}"
    keys = [change.key for change in result.changes]
    assert len(set(keys)) == len(keys), f"change keys repeat: {keys}"
    written = json.dumps(step_plan_to_json(result))  # refuses secrets in the payload
    back = step_plan_from_json(json.loads(written))
    assert back == result, "the plan changed on its way through the plan file"
    return result

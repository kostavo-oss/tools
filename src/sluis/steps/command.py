"""`command`: a step as a pair of commands, for steps that don't need Python.

    - name: seed
      uses: command
      with:
        plan: [./ops/seed.sh, --plan]   # optional
        apply: [./ops/seed.sh]

The `plan` command prints the step's plan as JSON on stdout — the same shape a
plan file holds for a step:

    {"changes": [{"key": "…", "action": "update", "summary": "…"}],
     "outputs": {"version": 14}, "deferred": null}

Without one, the step's plan is a single `run`: it runs on every apply.

Both commands run in the directory of `sluis.yml`, with sluis's environment
plus `SLUIS_TARGET`, `SLUIS_STEP` and `SLUIS_PHASE`, and the `env` option.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field

from sluis import process
from sluis.errors import SluisError
from sluis.model import Change, Outputs, StepPlan
from sluis.planfile import step_plan_from_json
from sluis.step import Context


class Command:
    """A step as commands: an optional plan command and an apply command."""

    @dataclass(frozen=True, slots=True)
    class Options:
        #: Run at apply, as a list: `[./ops/seed.sh, --fast]`.
        apply: tuple[str, ...]
        #: Prints the step's plan as JSON; without it the step always runs.
        plan: tuple[str, ...] | None = None
        #: Extra environment for both commands.
        env: Mapping[str, str] = field(default_factory=dict)

    def plan(self, ctx: Context[Command.Options]) -> StepPlan:
        if not ctx.options.apply:
            raise SluisError(f"step `{ctx.name}`: `apply` needs a command to run")
        if ctx.options.plan is None:
            shown = shlex.join(ctx.options.apply)
            return StepPlan(
                changes=(Change(key=ctx.name, action="run", summary=f"runs {shown}"),)
            )
        result = process.run(ctx.options.plan, ctx.root, env=_env(ctx))
        if result.returncode != 0:
            raise process.failure(f"step `{ctx.name}`'s plan command", result)
        try:
            document = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise SluisError(
                f"step `{ctx.name}`'s plan command must print JSON on stdout: {error}"
            ) from None
        return step_plan_from_json(document, where=f"step `{ctx.name}`'s plan command")

    def apply(self, ctx: Context[Command.Options], plan: StepPlan) -> Outputs:
        raise NotImplementedError("apply is milestone 2")


def _env(ctx: Context[Command.Options]) -> dict[str, str]:
    return {
        **ctx.env,
        **ctx.options.env,
        "SLUIS_TARGET": ctx.target,
        "SLUIS_STEP": ctx.name,
        "SLUIS_PHASE": ctx.phase,
    }

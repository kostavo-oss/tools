"""The plugin contract, as checks a test can run — for lely's plugins and yours.

    from lely.testing import check_apply, check_plan, context

    def test_plans_the_alias():
        ctx = context(MyPlugin.Options(model="main.ml.churn"), target="dev")
        plan = check_plan(MyPlugin(), ctx)
        assert [c.key for c in plan.changes] == ["alias champion"]

Each rule of the contract is something here that can fail:

- `check_plan` — *plan changes nothing*: it runs with a Databricks CLI that
  refuses every call outside a list of reads. The plan is a `StepPlan` with
  unique change keys, its outputs are as declared, and it survives a round trip
  through the plan file without losing anything or leaking a secret.
- `check_apply` — *apply does what the plan said*: plan, apply, plan again
  shows nothing left but runs. What `apply` gives is as declared.
- `check_destroy` — *destroy undoes it*: plan, apply, destroy, and the plan
  shows again what the first plan showed.
- `check_overview` — *an overview changes nothing*, and every line has a kind,
  a key and a name.

`context` builds a `Context` with nothing behind it: a plugin that reaches for
the Databricks CLI or the workspace without the test giving it one fails
loudly.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn, TypeVar

from lely import step as contract
from lely.model import Json, Output, Outputs, Overview, Skip, StepPlan
from lely.planfile import normalised, step_plan_from_json, step_plan_to_json
from lely.refs import match
from lely.step import Cli, Context, NullLog

OptionsT = TypeVar("OptionsT")

#: Calls of the Databricks CLI that change nothing, by how they start.
READS: tuple[tuple[str, ...], ...] = (
    ("bundle", "validate"),
    ("bundle", "plan"),
    ("bundle", "summary"),
    ("current-user", "me"),
    ("auth", "describe"),
    ("--version",),
)


class NoDatabricks:
    """A Databricks CLI that isn't there: any use fails the test."""

    def run(self, args: Sequence[str], cwd: Path) -> NoReturn:
        raise AssertionError(
            "the plugin ran the Databricks CLI; give the context a `databricks=` fake"
        )


@dataclasses.dataclass(frozen=True, slots=True)
class ReadOnly:
    """A Databricks CLI that lets reads through and fails the test on anything
    else — what `plan` and `overview` are run with."""

    inner: Cli
    reads: tuple[tuple[str, ...], ...] = READS

    def run(self, args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if not any(tuple(args[: len(read)]) == read for read in self.reads):
            raise AssertionError(
                f"`databricks {' '.join(args)}` isn't a read: planning and listing "
                "change nothing"
            )
        return self.inner.run(args, cwd)


def _no_workspace() -> NoReturn:
    raise AssertionError(
        "the plugin connected to a workspace; give the context `connect=`"
    )


def context(
    options: OptionsT,
    *,
    target: str = "dev",
    name: str = "step",
    root: Path | None = None,
    host: str = "https://dbc-example.cloud.databricks.com",
    env: Mapping[str, str] | None = None,
    databricks: Cli | None = None,
    connect: Any = None,
) -> Context[OptionsT]:
    return Context(
        target=target,
        name=name,
        options=options,
        root=root or Path.cwd(),
        host=host,
        env=dict(os.environ) if env is None else env,
        databricks=databricks or NoDatabricks(),
        log=NullLog(),
        connect=connect or _no_workspace,
    )


def check_plan(
    plugin: Any,
    ctx: Context[Any],
    *,
    written: Mapping[str, Json] | None = None,
    reads: tuple[tuple[str, ...], ...] = READS,
) -> StepPlan:
    """Plan once, reading only, and hold the result to the contract.

    `written` is the step's `with:` block as a project would write it, for a
    plugin whose outputs depend on its options.
    """
    result = plugin.plan(_reading(ctx, reads))
    assert isinstance(result, StepPlan), f"plan returned {type(result).__name__}"
    keys = [change.key for change in result.changes]
    assert len(set(keys)) == len(keys), f"change keys repeat: {keys}"
    declared = contract.declared(type(plugin), written or {})
    _as_declared(result.outputs, declared, "plan")
    if result.waiting is None:
        for output in declared:
            if output.known == "plan" and not output.shape:
                assert output.name in result.outputs, (
                    f"`{output.name}` is declared as known at plan, and the plan "
                    "gave none"
                )
    for name in result.outputs:
        named = match(declared, tuple(name.split(".")))
        assert named is not None and named.output.known != "run", (
            f"`{name}` is declared as known after every run, and the plan gave it"
        )
    # as lely itself takes a plan: made plain first — a tuple is a list, a
    # change with no summary is named by its key — and refused if it holds a
    # secret or something JSON has no word for
    plain = normalised(result)
    written_out = json.dumps(step_plan_to_json(plain))
    back = step_plan_from_json(json.loads(written_out))
    assert back == plain, "the plan changed on its way through the plan file"
    return result


def check_apply(
    plugin: Any,
    ctx: Context[Any],
    *,
    written: Mapping[str, Json] | None = None,
    reads: tuple[tuple[str, ...], ...] = READS,
) -> Outputs:
    """Plan, apply, plan again: nothing is left to change. Returns the outputs.

    Changes that are `run`s happen on every apply, so they may remain.
    """
    first = check_plan(plugin, ctx, written=written, reads=reads)
    outputs = plugin.apply(ctx, first)
    outputs = {} if outputs is None else outputs
    assert isinstance(outputs, Mapping), f"apply returned {type(outputs).__name__}"
    declared = contract.declared(type(plugin), written or {})
    _as_declared(outputs, declared, "apply")
    again = check_plan(plugin, ctx, written=written, reads=reads)
    left = [change for change in again.changes if change.action != "run"]
    assert not left, f"after apply, the plan still shows: {[c.key for c in left]}"
    return outputs


def check_destroy(
    plugin: Any,
    ctx: Context[Any],
    *,
    written: Mapping[str, Json] | None = None,
    reads: tuple[tuple[str, ...], ...] = READS,
) -> StepPlan:
    """Plan, apply, destroy: the plan shows again what the first plan showed.

    Returns the destroy plan that was run.
    """
    first = check_plan(plugin, ctx, written=written, reads=reads)
    plugin.apply(ctx, first)
    removal = plugin.plan_destroy(_reading(ctx, reads))
    assert isinstance(removal, StepPlan), (
        f"plan_destroy returned {type(removal).__name__} for a step that was applied"
    )
    assert removal.changes, "after apply, the destroy plan shows nothing to remove"
    plugin.destroy(ctx, removal)
    after = check_plan(plugin, ctx, written=written, reads=reads)
    assert after.changes == first.changes, (
        "after destroy, the plan doesn't show what the first plan showed: "
        f"{[c.key for c in after.changes]} != {[c.key for c in first.changes]}"
    )
    return removal


def check_overview(
    plugin: Any,
    ctx: Context[Any],
    *,
    reads: tuple[tuple[str, ...], ...] = READS,
) -> Overview | Skip:
    """List, reading only: every line has a kind, a key and a name."""
    result = plugin.overview(_reading(ctx, reads))
    assert isinstance(result, Overview | Skip), (
        f"overview returned {type(result).__name__}"
    )
    if isinstance(result, Overview):
        for item in result.items:
            assert item.kind and item.key and item.name, f"an incomplete line: {item}"
    return result


def _reading(ctx: Context[Any], reads: tuple[tuple[str, ...], ...]) -> Context[Any]:
    return dataclasses.replace(ctx, databricks=ReadOnly(ctx.databricks, reads))


def _as_declared(outputs: Outputs, declared: tuple[Output, ...], verb: str) -> None:
    for name in outputs:
        named = match(declared, tuple(name.split(".")))
        assert named is not None and not named.rest, (
            f"{verb} gave an output `{name}` the plugin doesn't declare"
        )

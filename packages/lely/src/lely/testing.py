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
- `check_no_state` — *it keeps no state*: every call is made on a new plugin,
  as lely makes one for every call, and `apply` is handed the plan as it reads
  back from a plan file. Nothing is left to change afterwards.
- `check_only_its_own` — *only what its options name, and only its own*: a
  second step of the same plugin, whose options name other things, plans and
  lists the same before and after this step is applied and destroyed.

`context` builds a `Context` with nothing behind it: a plugin that reaches for
the Databricks CLI or the workspace without the test giving it one fails
loudly.

Every check takes the plugin as an instance, or as its class: then each call is
made on a new instance, as under lely.

**What the kit sees, and what it does not.** It sees a plugin through three
things: the Databricks CLI the context hands it, what the plugin itself
answers, and what a test shows it (`untouched`). So:

- "Changes nothing" is held for calls of the Databricks CLI through
  `ctx.databricks`, and for nothing else. A write `plan` or `overview` makes
  through the SDK (`ctx.workspace`), or by a program the plugin starts itself,
  is not seen.
- "No state" is held for what a plugin keeps on itself between two calls, and
  for what does not survive a plan file. State kept on the class, in a module,
  in a file or in a service is not seen.
- "Only its own" is held for what a second step's plan and overview show of
  its things, and for what `untouched` answers. Anything else in a workspace
  is not seen.

A test of your own can see more: give the context a stand-in for the workspace
(`connect=`) that records what it is asked.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn, TypeVar

from lely import step as contract
from lely.model import Json, Output, Outputs, Overview, Skip, StepPlan
from lely.planfile import normalised, step_plan_from_json, step_plan_to_json
from lely.refs import match
from lely.render.html import framed
from lely.step import Cli, Context, NullLog, Purpose

OptionsT = TypeVar("OptionsT")

#: Calls of the Databricks CLI that change nothing, by how they start.
#: `bundle validate` is not one of them: it creates the bundle's `files` folder
#: in the workspace (seen on CLI v1.19.0).
READS: tuple[tuple[str, ...], ...] = (
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
    purpose: Purpose = "apply",
    approved: StepPlan | None = None,
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
        purpose=purpose,
        approved=approved,
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
    result = _one(plugin).plan(_reading(ctx, reads))
    assert isinstance(result, StepPlan), f"plan returned {type(result).__name__}"
    keys = [change.key for change in result.changes]
    assert len(set(keys)) == len(keys), f"change keys repeat: {keys}"
    declared = contract.declared(_class(plugin), written or {})
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
    if result.view is not None:
        # what the page shows of it: its structure and its words, in a frame
        assert "could not be read" not in framed(result.view), (
            "the plan's view isn't HTML lely can read"
        )
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
    outputs = _one(plugin).apply(ctx, first)
    outputs = {} if outputs is None else outputs
    assert isinstance(outputs, Mapping), f"apply returned {type(outputs).__name__}"
    declared = contract.declared(_class(plugin), written or {})
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
    _one(plugin).apply(ctx, first)
    removal = _one(plugin).plan_destroy(_reading(ctx, reads))
    assert isinstance(removal, StepPlan), (
        f"plan_destroy returned {type(removal).__name__} for a step that was applied"
    )
    assert removal.changes, "after apply, the destroy plan shows nothing to remove"
    _one(plugin).destroy(ctx, removal)
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
    result = _one(plugin).overview(_reading(ctx, reads))
    assert isinstance(result, Overview | Skip), (
        f"overview returned {type(result).__name__}"
    )
    if isinstance(result, Overview):
        for item in result.items:
            assert item.kind and item.key and item.name, f"an incomplete line: {item}"
    return result


def check_no_state(
    make: Callable[[], Any],
    ctx: Context[Any],
    *,
    written: Mapping[str, Json] | None = None,
    reads: tuple[tuple[str, ...], ...] = READS,
) -> Outputs:
    """Plan on one plugin, apply on another, with a plan file between them:
    nothing is left to change. Returns the outputs.

    `make` makes the plugin, and the class itself will do. `plan` and `apply`
    may run on different machines, days apart, so each call here is made on a
    new plugin, and `apply` is handed the plan as it reads back from a plan
    file, with the same plan as `ctx.approved`. A plugin that keeps on itself
    what it found while planning has nothing to apply from.

    State kept anywhere else is not seen: on the class, in a module, in a
    file, in a service.
    """
    first = check_plan(make(), ctx, written=written, reads=reads)
    back = step_plan_from_json(
        json.loads(json.dumps(step_plan_to_json(normalised(first))))
    )
    outputs = make().apply(dataclasses.replace(ctx, approved=back), back)
    outputs = {} if outputs is None else outputs
    assert isinstance(outputs, Mapping), f"apply returned {type(outputs).__name__}"
    _as_declared(outputs, contract.declared(_class(make()), written or {}), "apply")
    again = check_plan(make(), ctx, written=written, reads=reads)
    left = [change for change in again.changes if change.action != "run"]
    assert not left, (
        "applied on a new plugin, from the plan as a plan file keeps it, the plan "
        f"still shows: {[c.key for c in left]}. A plugin keeps no state: only the "
        "plan passes from `plan` to `apply`"
    )
    return outputs


def check_only_its_own(
    plugin: Any,
    ctx: Context[Any],
    other: Context[Any],
    *,
    written: Mapping[str, Json] | None = None,
    other_written: Mapping[str, Json] | None = None,
    reads: tuple[tuple[str, ...], ...] = READS,
    untouched: Callable[[], object] | None = None,
) -> None:
    """Apply a step, and destroy it if the plugin can: what another step's
    options name is as it was.

    `other` is the context of a second step of the same plugin, whose options
    name other things. Its plan and its overview are the kit's eyes: they are
    taken before and after this step is applied and destroyed, twice. First
    while the other step's things do not exist, so applying this one must not
    make them; then, with the other step applied, so applying and destroying
    this one must not change or remove them.

    `untouched`, when a test gives one, answers with anything that neither
    step names, as the test's stand-in holds it; it has to answer the same
    every time. Without it the kit sees only what the plugin itself shows of
    the other step.
    """

    def look() -> tuple[object, ...]:
        planned = check_plan(plugin, other, written=other_written, reads=reads)
        listed = (
            check_overview(plugin, other, reads=reads)
            if contract.lists(_class(plugin))
            else None
        )
        return (planned.changes, listed, untouched() if untouched is not None else None)

    def cycle(was: tuple[object, ...], state: str) -> None:
        planned = check_plan(plugin, ctx, written=written, reads=reads)
        if planned.changes:  # as lely: a step with nothing to do isn't applied
            _one(plugin).apply(ctx, planned)
        assert look() == was, (
            f"applying the step changed what it doesn't name ({state}): a step "
            "touches only what its options name"
        )
        if not contract.destroys(_class(plugin)):
            return
        removal = _one(plugin).plan_destroy(_reading(ctx, reads))
        if isinstance(removal, StepPlan) and removal.changes:
            _one(plugin).destroy(ctx, removal)
        assert look() == was, (
            f"destroying the step changed what isn't its own ({state}): a step "
            "destroys only what it can show is its own"
        )

    cycle(look(), "another step's things, before they exist")
    planned = check_plan(plugin, other, written=other_written, reads=reads)
    if planned.changes:
        _one(plugin).apply(other, planned)
    cycle(look(), "another step's things, once it is applied")


def _one(plugin: Any) -> Any:
    """The plugin to make a call on: a class gives a new instance for every
    call, as lely makes one for every call."""
    return plugin() if isinstance(plugin, type) else plugin


def _class(plugin: Any) -> type:
    return plugin if isinstance(plugin, type) else type(plugin)


def _reading(ctx: Context[Any], reads: tuple[tuple[str, ...], ...]) -> Context[Any]:
    return dataclasses.replace(ctx, databricks=ReadOnly(ctx.databricks, reads))


def _as_declared(outputs: Outputs, declared: tuple[Output, ...], verb: str) -> None:
    for name in outputs:
        named = match(declared, tuple(name.split(".")))
        assert named is not None and not named.rest, (
            f"{verb} gave an output `{name}` the plugin doesn't declare"
        )

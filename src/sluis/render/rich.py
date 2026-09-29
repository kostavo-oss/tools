"""The plan in a terminal.

    sluis plan · shop · target prod

    pre
      model  ./ops/steps.py:LatestModel
        → version = 14

    bundle
        + jobs.backfill
        ± pipelines.ingest  destructive
            replaced: storage (immutable)
        vars  model_version = 14

    post
      tables  deltaplan
        + dev.sales.orders
            CREATE TABLE orders
      backfill  bundle.run
        ▶ runs jobs.backfill

    Plan: 3 changes · 1 run · 1 destructive

Pure: a plan in, Rich renderables out.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from rich.console import Console, Group, RenderableType
from rich.text import Text

from sluis.model import Change, Plan, PlannedStep, Secret, StepPlan, Value

SYMBOLS = {"create": "+", "update": "~", "delete": "-", "replace": "±", "run": "▶"}
STYLES = {
    "create": "green",
    "update": "yellow",
    "delete": "red",
    "replace": "red",
    "run": "cyan",
}


def render_plan(plan: Plan, console: Console) -> None:
    console.print(plan_view(plan), highlight=False)


def plan_view(plan: Plan) -> RenderableType:
    return Group(*_lines(plan))


def _lines(plan: Plan) -> Iterator[Text]:
    yield Text.assemble(
        ("sluis plan", "bold"),
        " · ",
        (plan.bundle, "bold"),
        " · target ",
        (plan.target, "bold"),
    )
    if plan.pre:
        yield Text()
        yield Text("pre", style="bold")
        for step in plan.pre:
            yield from _step(step)
    yield Text()
    yield Text("bundle", style="bold")
    if plan.deploy.deferred:
        yield Text(f"    ⏸ decided at apply: {plan.deploy.deferred}", style="yellow")
    for change in plan.deploy.changes:
        yield from _change(change, indent=4)
    if not plan.deploy.changes and not plan.deploy.deferred:
        yield Text("    no changes", style="dim")
    for name, value in plan.deploy.variables:
        yield Text.assemble(("    vars  ", "dim"), f"{name} = {value}")
    if plan.post:
        yield Text()
        yield Text("post", style="bold")
        for step in plan.post:
            yield from _step(step)
    yield Text()
    yield _summary(plan)


def _step(step: PlannedStep) -> Iterator[Text]:
    yield Text.assemble("  ", (step.name, "bold"), "  ", (step.uses, "dim"))
    yield from _step_plan(step.plan)


def _step_plan(plan: StepPlan) -> Iterator[Text]:
    if plan.deferred:
        yield Text(f"    ⏸ decided at apply: {plan.deferred}", style="yellow")
    for change in plan.changes:
        yield from _change(change, indent=4)
    for name, value in plan.outputs.items():
        yield Text.assemble(("    → ", "dim"), f"{name} = {_shown(value)}")
    if plan.empty and not plan.outputs:
        yield Text("    no changes", style="dim")


def _change(change: Change, *, indent: int) -> Iterator[Text]:
    style = STYLES[change.action]
    line = Text(" " * indent)
    line.append(f"{SYMBOLS[change.action]} {change.summary}", style=style)
    if change.destructive:
        line.append("  destructive", style="bold red")
    yield line
    for detail in change.detail:
        yield Text(" " * (indent + 4) + detail, style="dim")


def _summary(plan: Plan) -> Text:
    summary = plan.summary
    if summary.empty:
        return Text("No changes. Everything matches.", style="green")
    parts = [
        f"{summary.changes} change{'s' if summary.changes != 1 else ''}",
        f"{summary.runs} run{'s' if summary.runs != 1 else ''}",
        f"{summary.destructive} destructive",
    ]
    if summary.deferred:
        parts.append(f"{summary.deferred} decided at apply")
    text = Text("Plan: ", style="bold")
    text.append(" · ".join(parts), style="bold red" if summary.destructive else "bold")
    return text


def _shown(value: Value) -> str:
    if isinstance(value, Secret):
        return "***"
    if isinstance(value, str):
        return value
    return json.dumps(value)

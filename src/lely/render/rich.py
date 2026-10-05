"""lely in a terminal: the plan, the wiring, a run's result, what exists.

    lely plan · target dev · https://dbc-example.cloud.databricks.com as jane@example.com

      model  ./ops/steps.py:LatestModel
        → version = 14
      app  bundle
        model_version = 14  ← model.version
        + jobs.backfill
        ± pipelines.ingest  destructive
            replaced: storage (immutable)
        ▶ uploads the bundle's files
      notify  command
        ⏸ waiting for app.resources.jobs.backfill.id
      warm  command
        – skipped: not for target `dev`

    Plan: 2 changes · 1 run · 1 destructive · 1 waiting
    Applied from a file, this stops before `notify`.

A destroy plan is shown in the order it runs: from the bottom up.

Pure: a plan in, Rich renderables out. A secret is shown as `***`, and a
plugin's payload is never shown.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping

from rich.console import Console, Group, RenderableType
from rich.text import Text

from lely.model import (
    KNOWN,
    Change,
    Input,
    Overview,
    Plan,
    PlannedStep,
    Result,
    Secret,
    Status,
    StepPlan,
    StepResult,
    Value,
)
from lely.planning import Wire

SYMBOLS = {"create": "+", "update": "~", "delete": "-", "replace": "±", "run": "▶"}
STYLES = {
    "create": "green",
    "update": "yellow",
    "delete": "red",
    "replace": "red",
    "run": "cyan",
}

_OUTCOMES = {
    "done": ("✓", "green"),
    "nothing": ("·", "dim"),
    "skipped": ("–", "dim"),
    "passed": ("·", "dim"),
    "failed": ("✗", "bold red"),
    "refused": ("✗", "bold red"),
    "not started": ("·", "dim"),
}


def render_plan(plan: Plan, console: Console) -> None:
    console.print(plan_view(plan), highlight=False)


def plan_view(plan: Plan) -> RenderableType:
    return Group(*_plan_lines(plan))


def _plan_lines(plan: Plan) -> Iterator[Text]:
    title = "lely plan" if plan.kind == "apply" else "lely destroy plan"
    yield Text.assemble(
        (title, "bold"),
        " · target ",
        (plan.target, "bold"),
        " · ",
        str(plan.workspace),
    )
    yield Text()
    steps = plan.steps if plan.kind == "apply" else tuple(reversed(plan.steps))
    taken = {taken.source for step in plan.steps for taken in step.inputs}
    for step in steps:
        yield from step_lines(step, taken)
    yield Text()
    yield _summary(plan)
    yield from _warnings(plan)


def step_lines(step: PlannedStep, taken: Iterable[str] = ()) -> Iterator[Text]:
    """One step of a plan: what it takes, what it would do, what it gives.

    `taken` are the outputs another step takes, as `<step>.<output>`: those are
    the ones shown where they are given. The rest are in the plan file.
    """
    yield Text.assemble("  ", (step.name, "bold"), "  ", (step.uses, "dim"))
    if step.skipped is not None:
        yield Text(f"    – skipped: {step.skipped}", style="dim")
        return
    for one in step.inputs:
        if one.known:
            yield _input(one)
    if step.waiting is not None:
        yield Text(f"    ⏸ {step.waiting}", style="yellow")
    sources = tuple(taken)
    given = {
        name: value
        for name, value in step.plan.outputs.items()
        if any(
            source == f"{step.name}.{name}" or source.startswith(f"{step.name}.{name}.")
            for source in sources
        )
    }
    yield from _step_plan(step.plan, given, waiting=step.waiting is not None)


def _input(taken: Input) -> Text:
    """`model_version = 14  ← model.version`; an item of a list has no name."""
    line = Text("    ")
    shown = "" if taken.value is None else _shown(taken.value)
    if taken.label and shown:
        line.append(f"{taken.label} = {shown}  ")
    elif taken.label or shown:
        line.append(f"{taken.label or shown}  ")
    line.append(f"← {taken.source}", style="dim")
    return line


def _step_plan(
    plan: StepPlan, given: Mapping[str, Value], *, waiting: bool = False
) -> Iterator[Text]:
    for change in plan.changes:
        yield from _change(change, indent=4)
    for note in plan.notes:
        yield Text(f"    {note}", style="dim")
    for name, value in given.items():
        yield Text.assemble(("    → ", "dim"), f"{name} = {_shown(value)}")
    if not waiting and not plan.changes and not given and not plan.notes:
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
        if plan.kind == "destroy":
            return Text("Nothing to destroy.", style="green")
        return Text("No changes. Everything matches.", style="green")
    parts = [
        _count(summary.changes, "change"),
        _count(summary.runs, "run"),
        f"{summary.destructive} destructive",
    ]
    if summary.waiting:
        parts.append(f"{summary.waiting} waiting")
    text = Text("Plan: " if plan.kind == "apply" else "Destroy plan: ", style="bold")
    text.append(" · ".join(parts), style="bold red" if summary.destructive else "bold")
    return text


def _warnings(plan: Plan) -> Iterator[Text]:
    waiting = plan.waiting
    if plan.kind == "apply" and waiting:
        first = waiting[0]
        yield Text(
            f"Applied from a file, this stops before `{first.name}`: a waiting "
            "step is planned once what it waits for exists.",
            style="yellow",
        )
        if first.every_deploy:
            yield Text(
                f"`{first.name}` waits for what only a run produces, so a file can "
                "never take it further: `lely apply -t <target>` does.",
                style="yellow",
            )
    if plan.source.tree is None:
        yield Text(
            "Not in a git repository: which version of the project this was planned "
            "on couldn't be recorded.",
            style="dim",
        )
    elif plan.source.dirty:
        yield Text(
            "Planned with uncommitted changes: lely can't check that what is "
            "applied is what was planned.",
            style="yellow",
        )


def _count(number: int, word: str) -> str:
    return f"{number} {word}{'s' if number != 1 else ''}"


def _shown(value: Value) -> str:
    if isinstance(value, Secret):
        return "***"
    if isinstance(value, str):
        return value
    return json.dumps(value)


# -- the wiring -----------------------------------------------------------------


def wiring_view(wires: Iterable[Wire]) -> RenderableType:
    return Group(*_wiring_lines(tuple(wires)))


def _wiring_lines(wires: tuple[Wire, ...]) -> Iterator[Text]:
    width = max((len(wire.name) for wire in wires), default=0)
    for wire in wires:
        lines: list[Text] = []
        for label, source in wire.takes:
            lines.append(Text.assemble(("takes  ", "dim"), f"{label} ← {source}".strip()))
        for known, words in KNOWN.items():
            names = [output.name for output in wire.gives if output.known == known]
            if names:
                lines.append(
                    Text.assemble(("gives  ", "dim"), f"{', '.join(names)} ({words})")
                )
        if not lines:
            lines.append(Text("takes and gives nothing", style="dim"))
        for index, line in enumerate(lines):
            name = wire.name if index == 0 else ""
            yield Text.assemble("  ", (name.ljust(width), "bold"), "  ", line)
    for wire in wires:
        for warning in wire.warnings:
            yield Text(f"! {warning}", style="yellow")


# -- a run ------------------------------------------------------------------------


def result_view(result: Result) -> RenderableType:
    return Group(*_result_lines(result))


def _result_lines(result: Result) -> Iterator[Text]:
    title = "lely apply" if result.kind == "apply" else "lely destroy"
    yield Text.assemble(
        (title, "bold"),
        " · target ",
        (result.target, "bold"),
        " · ",
        str(result.workspace),
    )
    yield Text()
    for step in result.steps:
        yield from _step_result(step)
    yield Text()
    if result.outcome == "done":
        yield Text(_done(result), style="bold green")
        return
    stopped = "refused" if result.outcome == "refused" else "failed"
    for title, steps in (
        ("ran", result.ran),
        (stopped, result.failed),
        ("never started", result.not_started),
    ):
        names = ", ".join(step.name for step in steps) or "nothing"
        yield Text.assemble((f"{title}: ", "bold"), names)
    yield Text("Nothing was rolled back.", style="bold")
    yield Text()
    yield Text(result.message, style="red")


def _step_result(step: StepResult) -> Iterator[Text]:
    symbol, style = _OUTCOMES[step.outcome]
    line = Text.assemble(
        "  ", (symbol, style), " ", (step.name, "bold"), "  ", (step.uses, "dim")
    )
    words = _outcome_words(step)
    if words:
        line.append(f"  {words}", style=style if step.outcome != "done" else "dim")
    yield line
    for change in step.changes:
        yield from _change(change, indent=6)
    if step.overview is not None:
        yield from _overview(step.overview, step.happened, indent=6)


def _outcome_words(step: StepResult) -> str:
    if step.outcome == "done":
        return ""
    if step.outcome in ("failed", "refused", "not started"):
        return step.outcome
    return step.detail


def _done(result: Result) -> str:
    did = sum(1 for step in result.steps if step.outcome == "done")
    if not did:
        return "Nothing to do." if result.kind == "apply" else "Nothing to destroy."
    word = "Applied" if result.kind == "apply" else "Destroyed"
    return f"{word}: {_count(did, 'step')}."


# -- what exists ----------------------------------------------------------------


def status_view(status: Status) -> RenderableType:
    return Group(*_status_lines(status))


def _status_lines(status: Status) -> Iterator[Text]:
    yield Text.assemble(
        ("lely status", "bold"),
        " · target ",
        (status.target, "bold"),
        " · ",
        str(status.workspace),
    )
    yield Text()
    for step in status.steps:
        yield Text.assemble("  ", (step.name, "bold"), "  ", (step.uses, "dim"))
        if step.overview is None:
            yield Text(f"    {step.note}", style="dim")
        else:
            yield from _overview(step.overview, None, indent=4)


def _overview(
    overview: Overview, happened: Mapping[str, str] | None, *, indent: int
) -> Iterator[Text]:
    """One line per thing: kind, key, name, id — and, right after a run
    (`happened` is not `None`), what the run did to it: what it didn't touch is
    unchanged. Its link goes on a line of its own, so the columns hold in a
    narrow terminal."""
    after_a_run = happened is not None
    did = happened or {}
    pad = " " * indent
    rows = [
        (
            item.kind,
            item.key,
            item.name,
            (item.id or "") if item.deployed else "not deployed",
            did.get(item.key, "unchanged") if after_a_run else "",
            item.url or "",
        )
        for item in overview.items
    ]
    listed = {item.key for item in overview.items}
    rows += [
        ("", key, "", "", word, "") for key, word in did.items() if key not in listed
    ]
    widths = [max((len(row[i]) for row in rows), default=0) for i in range(5)]
    for row in rows:
        line = Text(pad)
        line.append(row[0].ljust(widths[0]) + "  ", style="dim")
        line.append(row[1].ljust(widths[1]) + "  ", style="bold")
        line.append(row[2].ljust(widths[2]) + "  ")
        line.append(row[3].ljust(widths[3]), style="dim")
        if after_a_run:
            line.append("  " + row[4], style=_happened_style(row[4]))
        line.rstrip()
        yield line
        if row[5]:
            yield Text(f"{pad}    {row[5]}", style="dim")
    if not rows:
        yield Text(f"{pad}nothing declared", style="dim")
    for note in overview.notes:
        yield Text(f"{pad}{note}", style="dim")


def _happened_style(word: str) -> str:
    return {
        "created": "green",
        "changed": "yellow",
        "replaced": "red",
        "deleted": "red",
    }.get(word, "dim")

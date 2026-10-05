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
plugin's payload is never shown. Nothing a plan, a plugin or a program said
reaches the terminal with its control characters: an escape sequence in a
change's summary could otherwise rewrite the lines above it.
"""

from __future__ import annotations

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
    Status,
    StepPlan,
    StepResult,
    Value,
)
from lely.planning import Wire
from lely.render import words
from lely.render.words import clean

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


def _safe(lines: Iterable[Text]) -> Group:
    """Lines for a terminal. Each control character becomes one other
    character, so the styles stay where they were."""
    safe = []
    for line in lines:
        line.plain = clean(line.plain)
        safe.append(line)
    return Group(*safe)


def render_plan(plan: Plan, console: Console, *, saved: bool = True) -> None:
    console.print(plan_view(plan, saved=saved), highlight=False)


def plan_view(plan: Plan, *, saved: bool = True) -> RenderableType:
    """`saved` is false for a plan that is run now and never written: what it
    was made on is held to nothing either way, so nothing is said about it."""
    return _safe(_plan_lines(plan, saved))


def _plan_lines(plan: Plan, saved: bool = True) -> Iterator[Text]:
    project = plan.source.root
    yield Text.assemble(
        (words.title(plan), "bold"),
        # in a repository with several projects, which one this plan is for
        *((" · project ", (project, "bold")) if project not in (None, ".") else ()),
        " · target ",
        (plan.target, "bold"),
        " · ",
        str(plan.workspace),
    )
    yield Text()
    taken = words.taken(plan)
    for step in words.in_order(plan):
        yield from _step_lines(step, taken)
    yield Text()
    yield _summary(plan)
    yield from _warnings(plan, saved)


def step_view(step: PlannedStep) -> RenderableType:
    """One step of a plan, on its own: what `apply` shows before it asks about
    a step that was waiting."""
    return _safe(_step_lines(step))


def _step_lines(step: PlannedStep, taken: Iterable[str] = ()) -> Iterator[Text]:
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
    given = words.given(step, taken)
    yield from _step_plan(step.plan, given, waiting=step.waiting is not None)


def _input(taken: Input) -> Text:
    """`model_version = 14  ← model.version`; an item of a list has no name."""
    line = Text("    ")
    shown = "" if taken.value is None else words.shown(taken.value)
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
        yield Text.assemble(("    → ", "dim"), f"{name} = {words.shown(value)}")
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
    if plan.summary.empty:
        return Text(words.nothing(plan), style="green")
    text = Text("Plan: " if plan.kind == "apply" else "Destroy plan: ", style="bold")
    text.append(
        " · ".join(words.counts(plan)),
        style="bold red" if plan.summary.destructive else "bold",
    )
    return text


def _warnings(plan: Plan, saved: bool = True) -> Iterator[Text]:
    for warning in words.warnings(plan, saved):
        yield Text(warning.words, style="yellow" if warning.loud else "dim")


# -- the wiring -----------------------------------------------------------------


def wiring_view(wires: Iterable[Wire]) -> RenderableType:
    return _safe(_wiring_lines(tuple(wires)))


def _wiring_lines(wires: tuple[Wire, ...]) -> Iterator[Text]:
    width = max((len(wire.name) for wire in wires), default=0)
    for wire in wires:
        lines: list[Text] = []
        for label, source in wire.takes:
            lines.append(Text.assemble(("takes  ", "dim"), f"{label} ← {source}".strip()))
        for known, when in KNOWN.items():
            names = [output.name for output in wire.gives if output.known == known]
            if names:
                lines.append(
                    Text.assemble(("gives  ", "dim"), f"{', '.join(names)} ({when})")
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
    return _safe(_result_lines(result))


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
        yield Text(words.done(result), style="bold green")
        return
    for title, names in words.stopped(result):
        yield Text.assemble((f"{title}: ", "bold"), names)
    yield Text("Nothing was rolled back.", style="bold")
    yield Text()
    yield Text(result.message, style="red")


def _step_result(step: StepResult) -> Iterator[Text]:
    symbol, style = _OUTCOMES[step.outcome]
    line = Text.assemble(
        "  ", (symbol, style), " ", (step.name, "bold"), "  ", (step.uses, "dim")
    )
    said = words.outcome(step)
    if said:
        line.append(f"  {said}", style=style if step.outcome != "done" else "dim")
    yield line
    for change in step.changes:
        yield from _change(change, indent=6)
    if step.overview is not None:
        yield from _overview(step.overview, step.happened, indent=6)


# -- what exists ----------------------------------------------------------------


def status_view(status: Status) -> RenderableType:
    return _safe(_status_lines(status))


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
    pad = " " * indent
    rows = words.rows(overview, happened)
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

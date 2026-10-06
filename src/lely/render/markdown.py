"""lely as Markdown: the plan on a pull request, a run on its page.

    <!-- lely:plan:dev -->
    ### lely plan · target `dev`

    `https://dbc-example.cloud.databricks.com` as `jane@example.com`

    **2 changes · 1 run · 1 destructive · 1 waiting**

    **Destructive:** `app: pipelines.ingest`

    ```diff
      model  ./ops/steps.py:LatestModel
          → version = 14
      app  bundle
          model_version = 14  ← model.version
    +     create   jobs.backfill
    -     replace  pipelines.ingest  destructive
              replaced: storage (immutable)
          run      uploads the bundle's files
      notify  command
          waiting for app.resources.jobs.backfill.id
    ```

    > Applied from a file, this stops before `notify`: …

Pure: a plan in, text out — the same plan the terminal and the plan file show.

**Nothing a plan says is Markdown.** A plan is made from a pull request's own
files, and a plan file can be written by hand; a resource named `@everyone`,
or `![](https://…)`, must not notify anyone or load anything where it is
shown. So every word that isn't lely's own stands inside a fenced block or a
code span, where GitHub shows text and obeys none of it — and each fence is
longer than any run of backticks in what it holds, so nothing inside can end
it. What is left outside is lely's words and its numbers.

The first line is a marker: a comment no reader sees, which says whose text
this is, of which kind, for which target — and for which project, in a
repository with several. It is how lely finds its own comment again.

Changes are a `diff` block for its colours only: `+` is green, `-` red, `!`
orange. The word beside it says what the change is.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from typing import NamedTuple
from urllib.parse import quote

from lely.model import (
    Change,
    Input,
    Overview,
    Plan,
    PlanKind,
    PlannedStep,
    Result,
    Status,
    StepResult,
)
from lely.render import words
from lely.render.words import clean

#: What fits in a comment. GitHub takes 65,536 characters; this is counted in
#: bytes, which is never fewer, and leaves room.
COMMENT_LIMIT = 60_000

#: What fits on a run's page: GitHub takes 1 MiB from one step of a job, and
#: drops the whole summary of a step that wrote more.
SUMMARY_LIMIT = 900_000

#: The first column of a line in a `diff` block, by what a change does.
_GUTTER = {"create": "+", "update": "!", "delete": "-", "replace": "-", "run": " "}

#: The longest text shown outside a block: a name, not a document.
_NAME = 200

#: The longest run of backticks shown as it is. A code span or a block is
#: closed by more backticks than it holds — and GitHub stops counting: past 80
#: for a span, past 255 for a block. A longer run inside one would stand where
#: no delimiter can outnumber it, so it is cut (found in review, 2026-10-06).
_TICKS = 16

_LONG_RUN = re.compile("`{" + str(_TICKS + 1) + ",}")

#: The longest a target or a project's folder is spelled out in the marker.
_FIELD = 200

#: How many destructive changes are named above the plan. All are in it.
_NAMED = 10


class _Line(NamedTuple):
    """One line of a block: what is said, how deep, and in which colour."""

    text: str
    indent: int = 0
    gutter: str = " "


# -- the marker -------------------------------------------------------------------


def marker(kind: PlanKind, target: str, root: str | None = None) -> str:
    """The first line of a plan: whose text this is and what it is the plan for.

    `root` is the project's folder in its repository, as `Source.root` says it;
    it is left out for a project at the top, and where there is no repository.
    """
    fields = ["plan" if kind == "apply" else "destroy", _field(target)]
    if root not in (None, "", "."):
        fields.append(_field(root))
    return f"<!-- lely:{':'.join(fields)} -->"


def _field(text: str) -> str:
    """`text` as part of the marker: nothing in it ends the comment it is in,
    or reads as another part. One too long to spell out ends in a digest of
    the whole of it, so it is still its own."""
    spelled = quote(text, safe="/", errors="replace").replace("--", "-%2D")
    if len(spelled) <= _FIELD:
        return spelled
    whole = hashlib.sha256(text.encode("utf-8", "backslashreplace")).hexdigest()
    return f"{spelled[:_FIELD].rstrip('-')}~{whole[:16]}"


# -- a plan -----------------------------------------------------------------------


def plan_markdown(plan: Plan, *, saved: bool = True, limit: int | None = None) -> str:
    """A plan as Markdown. With a `limit`, in bytes, a plan that is too long is
    told shorter — first without each change's details, then as counts — and
    says so."""
    return _fit(
        (
            lambda: _plan(plan, saved, _steps(plan, detail=True)),
            lambda: _plan(plan, saved, _steps(plan, detail=False), _NO_DETAIL),
            lambda: _plan(plan, saved, _counted(plan), _COUNTED),
            lambda: _plan(plan, saved, (), _NO_STEPS),
        ),
        limit,
    )


_NO_DETAIL = (
    "Shortened to fit: the details of each change are left out. The plan file has "
    "them, and `lely show` shows them."
)
_COUNTED = (
    "Shortened to fit: each step's changes are counted, not listed. The plan file "
    "has them, and `lely show` shows them."
)
_NO_STEPS = (
    "Shortened to fit: the steps are left out. The plan file has them, and "
    "`lely show` shows them."
)


def _plan(plan: Plan, saved: bool, lines: Iterable[_Line], cut: str = "") -> str:
    parts = [
        marker(plan.kind, plan.target, plan.source.root),
        _heading(words.title(plan), plan.target, plan.source.root),
        "",
        _workspace(plan.workspace.host, plan.workspace.identity),
        "",
    ]
    if plan.summary.empty:
        parts.append(f"**{words.nothing(plan)}**")
    else:
        parts.append(f"**{' · '.join(words.counts(plan))}**")
    destructive = _destructive(plan)
    if destructive:
        parts += ["", destructive]
    block = _block(lines, "diff")
    if block:
        parts += ["", block]
    for warning in words.warnings(plan, saved, quoted=_code):
        parts += ["", f"> {warning.words}"]
    if cut:
        parts += ["", f"> {cut}"]
    return "\n".join(parts) + "\n"


def _destructive(plan: Plan) -> str:
    """The destructive changes of a plan to apply, by name, above everything
    else. A plan to destroy is nothing but."""
    if plan.kind != "apply":
        return ""
    found = [
        f"{step.name}: {change.summary}"
        for step in plan.steps
        if step.state != "skipped"
        for change in step.plan.changes
        if change.destructive
    ]
    if not found:
        return ""
    named = ", ".join(_code(name) for name in found[:_NAMED])
    more = len(found) - _NAMED
    return f"**Destructive:** {named}" + (f", and {more} more" if more > 0 else "")


def _steps(plan: Plan, *, detail: bool) -> Iterator[_Line]:
    taken = words.taken(plan)
    for step in words.in_order(plan):
        yield from _step(step, taken, detail=detail)


def _step(step: PlannedStep, taken: Iterable[str], *, detail: bool) -> Iterator[_Line]:
    yield _Line(f"{step.name}  {step.uses}")
    if step.skipped is not None:
        yield _Line(f"skipped: {step.skipped}", 4)
        return
    for one in step.inputs:
        if one.known:
            yield _Line(_input(one), 4)
    if step.waiting is not None:
        yield _Line(step.waiting, 4)
    for change in step.plan.changes:
        yield from _change(change, 4, detail=detail)
    for note in step.plan.notes:
        yield _Line(note, 4)
    given = words.given(step, taken)
    for name, value in given.items():
        yield _Line(f"→ {name} = {words.shown(value)}", 4)
    if (
        step.waiting is None
        and not step.plan.changes
        and not given
        and not step.plan.notes
    ):
        yield _Line("no changes", 4)


def _input(taken: Input) -> str:
    """`model_version = 14  ← model.version`; an item of a list has no name."""
    shown = "" if taken.value is None else words.shown(taken.value)
    if taken.label and shown:
        return f"{taken.label} = {shown}  ← {taken.source}"
    if taken.label or shown:
        return f"{taken.label or shown}  ← {taken.source}"
    return f"← {taken.source}"


def _change(change: Change, indent: int, *, detail: bool = True) -> Iterator[_Line]:
    first, *rest = change.summary.split("\n")
    said = f"{change.action:<7}  {first}"
    if change.destructive:
        said += "  destructive"
    # a summary of several lines: the rest stand under where it starts
    lines = [said, *(" " * 9 + line for line in rest)]
    yield _Line("\n".join(lines), indent, _GUTTER[change.action])
    if detail:
        for line in change.detail:
            yield _Line(line, indent + 4)


def _counted(plan: Plan) -> Iterator[_Line]:
    """A plan too long to list: each step, and how much it would do."""
    for step in words.in_order(plan):
        yield _Line(f"{step.name}  {step.uses}")
        if step.skipped is not None:
            yield _Line("skipped", 4)
            continue
        changes = step.plan.changes
        parts = [
            words.count(sum(1 for c in changes if c.action != "run"), "change"),
            words.count(sum(1 for c in changes if c.action == "run"), "run"),
            f"{sum(1 for c in changes if c.destructive)} destructive",
        ]
        if step.waiting is not None:
            parts.append("waiting")
        yield _Line(" · ".join(parts), 4)


# -- a run ------------------------------------------------------------------------


def result_markdown(result: Result, *, limit: int | None = None) -> str:
    """What a run did, and what exists after it."""
    return _fit(
        (
            lambda: _result(result, changes=True, overview=True),
            lambda: _result(result, changes=True, overview=False),
            lambda: _result(result, changes=False, overview=False),
        ),
        limit,
    )


def _result(result: Result, *, changes: bool, overview: bool) -> str:
    title = "lely apply" if result.kind == "apply" else "lely destroy"
    ended = "" if result.outcome == "done" else result.outcome
    parts = [
        _heading(title, result.target, None, ended),
        "",
        _workspace(result.workspace.host, result.workspace.identity),
        "",
    ]
    if result.outcome == "done":
        parts.append(f"**{words.done(result)}**")
    else:
        parts.append("**Nothing was rolled back.**")
        parts.append("")
        parts += [f"- {what}: {_code(names)}" for what, names in words.stopped(result)]
    lines = [line for step in result.steps for line in _step_result(step, changes)]
    block = _block(lines, "diff")
    if block:
        parts += ["", block]
    if result.outcome != "done" and result.message:
        parts += ["", _block([_Line(words.said(result.message))], "text", margin=False)]
    if overview:
        exists = _exists(
            [
                (step.name, step.overview, step.happened)
                for step in result.steps
                if step.overview is not None
            ]
        )
        if exists:
            parts += ["", "#### What exists now", "", exists]
    else:
        parts += ["", "> Shortened to fit: `lely status` shows what exists now."]
    return "\n".join(parts) + "\n"


def _step_result(step: StepResult, changes: bool) -> Iterator[_Line]:
    said = words.outcome(step)
    yield _Line(
        f"{words.MARKS[step.outcome]} {step.name}  {step.uses}"
        + (f"  {said}" if said else "")
    )
    if changes:
        for change in step.changes:
            yield from _change(change, 6)


# -- what exists ----------------------------------------------------------------


def status_markdown(status: Status) -> str:
    parts = [
        _heading("lely status", status.target),
        "",
        _workspace(status.workspace.host, status.workspace.identity),
    ]
    exists = _exists(
        [
            (step.name, step.overview, None)
            for step in status.steps
            if step.overview is not None
        ]
    )
    if exists:
        parts += ["", exists]
    notes = [
        _Line(f"{step.name}: {step.note}")
        for step in status.steps
        if step.overview is None
    ]
    if notes:
        parts += ["", _block(notes, "text", margin=False)]
    return "\n".join(parts) + "\n"


def _exists(steps: Sequence[tuple[str, Overview, Mapping[str, str] | None]]) -> str:
    """One table for every step that lists what it made, one row per thing —
    with what the run did to it, right after a run (a step's third part is not
    `None`) — and under it what the steps said about their lists."""
    after_a_run = any(happened is not None for _, _, happened in steps)
    head = ["step", "kind", "key", "name", "id"]
    if after_a_run:
        head.append("this run")
    head.append("")
    table = [head, ["---"] * len(head)]
    asides: list[_Line] = []
    for name, overview, happened in steps:
        rows = words.rows(overview, happened)
        for row in rows:
            cells = [_cell(name), *(_cell(text) for text in row[:4])]
            if after_a_run:
                cells.append(_cell(row.happened))
            cells.append(_link(row.url))
            table.append(cells)
        if not rows:
            asides.append(_Line(f"{name}: nothing declared"))
        asides += [_Line(f"{name}: {note}") for note in overview.notes]
    parts = []
    if len(table) > 2:
        parts.append("\n".join(f"| {' | '.join(row)} |" for row in table))
    if asides:
        parts.append(_block(asides, "text", margin=False))
    return "\n\n".join(parts)


# -- what the plan couldn't be --------------------------------------------------------


def failure_markdown(
    kind: PlanKind,
    target: str,
    root: str | None = None,
    *,
    message: str | None = None,
    link: str | None = None,
) -> str:
    """In place of a plan that couldn't be made: a reader of the last one must
    not take it for the plan of what is there now.

    `message` is what went wrong, for where a program's words may be shown;
    `link` is where the rest is.
    """
    title = "lely plan" if kind == "apply" else "lely destroy plan"
    parts = [
        marker(kind, target, root),
        _heading(title, target, root, "failed"),
        "",
        "**The plan could not be made, so there is none to review.** An earlier "
        "plan says nothing about what is here now.",
    ]
    if message:
        parts += ["", _block([_Line(words.said(message))], "text", margin=False)]
    log = _followed(link or "", "The run's log")
    if log:
        parts += ["", f"{log} says what went wrong."]
    return "\n".join(parts) + "\n"


def unshown_markdown(
    kind: PlanKind, target: str, root: str | None = None, *, link: str | None = None
) -> str:
    """In place of a plan that was made and can't be shown where this goes —
    too long for it, or refused: a reader of the last one must not take it
    for this one."""
    title = "lely plan" if kind == "apply" else "lely destroy plan"
    parts = [
        marker(kind, target, root),
        _heading(title, target, root, "not shown"),
        "",
        "**There is a new plan, and it could not be shown here.** An earlier plan "
        "says nothing about what is here now.",
    ]
    run = _followed(link or "", "The run's page")
    if run:
        parts += ["", f"{run} has the plan."]
    return "\n".join(parts) + "\n"


def skipped_markdown(kind: PlanKind, target: str, fork: str) -> str:
    """For a pull request from a fork: why there is no plan."""
    title = "lely plan" if kind == "apply" else "lely destroy plan"
    return (
        f"{_heading(title, target, None, 'skipped')}\n\n"
        f"This pull request comes from a fork, {_code(fork)}. lely makes no plan "
        "for it: planning runs the pull request's own code, and that must not "
        "happen with the credentials of a workspace.\n"
    )


def stopped_markdown(kind: str, target: str | None, refused: bool, message: str) -> str:
    """A run that ended before its first step: nothing ran, and why."""
    title = "lely apply" if kind == "apply" else "lely destroy"
    ended = "refused" if refused else "failed"
    parts = [
        _heading(title, target or "?", None, ended),
        "",
        "**Nothing was run.**",
        "",
        _block([_Line(words.said(message))], "text", margin=False),
    ]
    return "\n".join(parts) + "\n"


def footer(
    *,
    version: str,
    commit: str | None = None,
    tree: str | None = None,
    link: str | None = None,
) -> str:
    """Under a plan on a pull request: what made it, for which commit, on
    which tree — the one `lely apply` holds the plan to — and where the run
    is."""
    parts = [f"lely {_code(version)}"]
    if commit:
        parts.append(f"commit {_code(commit[:12])}")
    if tree:
        parts.append(f"tree {_code(tree[:12])}")
    run = _followed(link or "", "the run")
    if run:
        parts.append(run)
    return f"<sub>{' · '.join(parts)}</sub>\n"


# -- text that is shown, never obeyed ---------------------------------------------------


def _heading(title: str, target: str, root: str | None = None, ended: str = "") -> str:
    parts = [title]
    if root not in (None, "", "."):
        parts.append(f"project {_code(root or '')}")
    parts.append(f"target {_code(target)}")
    if ended:
        parts.append(ended)
    return "### " + " · ".join(parts)


def _workspace(host: str, identity: str) -> str:
    return f"{_code(host)} as {_code(identity)}"


def _code(text: str) -> str:
    """`text` as a code span, on one line: shown as it is. The span's ticks
    outnumber any run of them inside it, so nothing in the text ends it."""
    text = _tamed(" ".join(clean(text).split()))
    if len(text) > _NAME:
        text = text[: _NAME - 1] + "…"
    if not text:
        return ""
    ticks = "`" * (_longest_run(text) + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{ticks}{pad}{text}{pad}{ticks}"


def _cell(text: str) -> str:
    """A code span for a table: a `|` would end the cell, in a span too."""
    return _code(text).replace("|", "\\|")


def _link(url: str) -> str:
    """Where a thing is, for a table: a link, or — for what isn't an address a
    reader can follow — the text as text."""
    return _followed(url, "open") or _cell(url)


def _followed(url: str, words: str) -> str:
    """A link, when `url` is an address a reader can follow and nothing more:
    `https://`, and no character that ends a Markdown link or starts anything
    else. Nothing otherwise."""
    if re.fullmatch(r"https://[A-Za-z0-9._~:/?#@!$&'()*+,;=%\[\]-]+", url):
        return f"[{words}](<{url}>)"
    return ""


def _block(lines: Iterable[_Line], language: str, *, margin: bool = True) -> str:
    """A fenced block, or nothing for no lines. A text of several lines keeps
    its indent and its colour on each; the fence is longer than any run of
    backticks inside it."""
    body = []
    for line in lines:
        start = (f"{line.gutter} " if margin else "") + " " * line.indent
        for part in _tamed(clean(line.text)).split("\n"):
            body.append(f"{start}{part}".rstrip())
    if not body:
        return ""
    text = "\n".join(body)
    fence = "`" * max(3, _longest_run(text) + 1)
    return f"{fence}{language}\n{text}\n{fence}"


def _tamed(text: str) -> str:
    """`text` with no run of backticks longer than `_TICKS`."""
    return _LONG_RUN.sub("`" * _TICKS + "…", text)


def _longest_run(text: str) -> int:
    return max((len(run) for run in re.findall("`+", text)), default=0)


def _fit(renderings: Sequence[Callable[[], str]], limit: int | None) -> str:
    """The first of `renderings` that fits in `limit` bytes; the last, if none."""
    text = ""
    for render in renderings:
        text = render()
        if limit is None or len(text.encode("utf-8")) <= limit:
            break
    return text

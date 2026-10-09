"""What every renderer says the same way: the terminal, Markdown, and the page
after them. The counts, the warnings, which outputs a plan shows, what a run
did to each thing.

Pure words. How they look is each renderer's own.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import NamedTuple
from urllib.parse import urlsplit

from lely.model import Overview, Plan, PlannedStep, Result, Secret, StepResult, Value

#: Characters that show nothing and change how the text around them reads:
#: the bidirectional overrides and isolates, the marks, and the zero-width
#: space and word joiner. (The zero-width joiners stay: scripts and emoji
#: are written with them.)
_INVISIBLE = frozenset(
    "\u061c\u200b\u200e\u200f\u2060\ufeff\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)


def clean(text: str) -> str:
    """`text` with what a terminal would obey, or a reader couldn't see, made
    visible as `�`: every control character but a line break and a tab, the
    invisible characters that reorder text, and half a character — a lone
    surrogate, which no file or terminal can be given. What a plan file or a
    program said is shown, never obeyed."""
    return "".join(
        "�"
        if (unicodedata.category(char) in ("Cc", "Cs") and char not in "\n\t")
        or char in _INVISIBLE
        else char
        for char in text
    )


def count(number: int, word: str) -> str:
    return f"{number} {word}{'s' if number != 1 else ''}"


def shown(value: Value) -> str:
    if isinstance(value, Secret):
        return "***"
    if isinstance(value, str):
        return value
    return json.dumps(value)


# -- a plan ---------------------------------------------------------------------


def title(plan: Plan) -> str:
    return "lely plan" if plan.kind == "apply" else "lely destroy plan"


def in_order(plan: Plan) -> tuple[PlannedStep, ...]:
    """A plan's steps in the order they run: a destroy goes from the bottom up."""
    return plan.steps if plan.kind == "apply" else tuple(reversed(plan.steps))


def taken(plan: Plan) -> frozenset[str]:
    """Every output a step of the plan takes, as `<step>.<output>`."""
    return frozenset(one.source for step in plan.steps for one in step.inputs)


def given(step: PlannedStep, taken: Iterable[str]) -> dict[str, Value]:
    """The outputs of a step that another step takes: those are the ones shown
    where they are given. The rest are in the plan file."""
    sources = tuple(taken)
    return {
        name: value
        for name, value in step.plan.outputs.items()
        if any(
            source == f"{step.name}.{name}" or source.startswith(f"{step.name}.{name}.")
            for source in sources
        )
    }


def counts(plan: Plan) -> list[str]:
    """`2 changes`, `1 run`, `1 destructive`, and `1 waiting` if any is."""
    summary = plan.summary
    parts = [
        count(summary.changes, "change"),
        count(summary.runs, "run"),
        f"{summary.destructive} destructive",
    ]
    if summary.waiting:
        parts.append(f"{summary.waiting} waiting")
    return parts


def nothing(plan: Plan) -> str:
    """What a plan with nothing in it says."""
    if plan.kind == "destroy":
        return "Nothing to destroy."
    return "No changes. Everything matches."


class Warning(NamedTuple):
    words: str
    #: Whether it changes what the reader can do with the plan.
    loud: bool


def _ticked(name: str) -> str:
    return f"`{name}`"


def warnings(
    plan: Plan, saved: bool = True, *, quoted: Callable[[str], str] = _ticked
) -> Iterator[Warning]:
    """What a reader of the plan has to know before running it. `saved` is
    false for a plan that is run now and never written: what it was made on is
    held to nothing either way, so nothing is said about it.

    `quoted` is how a renderer writes a step's name inside a sentence.
    """
    waiting = plan.waiting
    if plan.kind == "apply" and waiting and saved:
        first = waiting[0]
        name = quoted(first.name)
        yield Warning(
            f"Applied from a file, this stops before {name}: a waiting "
            "step is planned once what it waits for exists.",
            loud=True,
        )
        if first.every_deploy:
            yield Warning(
                f"{name} waits for what only a run produces, so a file can "
                "never take it further: `lely apply -t <target>` does.",
                loud=True,
            )
    if not saved:
        return
    if plan.source.tree is None and plan.source.root is not None:
        yield Warning(
            "This repository has no commit yet: which version of the project this "
            "was planned on couldn't be recorded.",
            loud=False,
        )
    elif plan.source.tree is None:
        yield Warning(
            "Not in a git repository: which version of the project this was planned "
            "on couldn't be recorded.",
            loud=False,
        )
    elif plan.source.dirty:
        yield Warning(
            "Planned with uncommitted changes: lely can't say what this was made "
            "on, so it won't run it from a file. Commit first, or run it without one.",
            loud=True,
        )


# -- a run ----------------------------------------------------------------------

#: How a step ended, in one character.
MARKS = {
    "done": "✓",
    "nothing": "·",
    "skipped": "–",
    "passed": "·",
    "failed": "✗",
    "refused": "✗",
    "not started": "·",
}


def outcome(step: StepResult) -> str:
    """What is said beside a step that didn't simply run."""
    if step.outcome == "done":
        return ""
    if step.outcome in ("failed", "refused", "not started"):
        return step.outcome
    return step.detail


def done(result: Result) -> str:
    did = sum(1 for step in result.steps if step.outcome == "done")
    if not did:
        return "Nothing to do." if result.kind == "apply" else "Nothing to destroy."
    word = "Applied" if result.kind == "apply" else "Destroyed"
    return f"{word}: {count(did, 'step')}."


def stopped(result: Result) -> list[tuple[str, str]]:
    """For a run that didn't finish: which steps ran, which one stopped it, and
    which never started."""
    middle = (
        ("refused", result.refused)
        if result.outcome == "refused"
        else ("failed", result.failed)
    )
    return [
        (title, ", ".join(step.name for step in steps) or "nothing")
        for title, steps in (
            ("ran", result.ran),
            middle,
            ("never started", result.not_started),
        )
    ]


# -- what exists ----------------------------------------------------------------


class Row(NamedTuple):
    """One thing a step declares."""

    kind: str
    key: str
    name: str
    #: Its id, or `not deployed`.
    id: str
    #: What the run did to it; empty when no run is being told.
    happened: str
    url: str


def rows(overview: Overview, happened: Mapping[str, str] | None) -> list[Row]:
    """One row per thing — and, right after a run (`happened` is not `None`),
    what the run did to it: what it didn't touch is unchanged, and what it
    removed is listed after what is left."""
    after_a_run = happened is not None
    did = happened or {}
    listed = [
        Row(
            item.kind,
            item.key,
            item.name,
            (item.id or "") if item.deployed else "not deployed",
            did.get(item.key, "unchanged") if after_a_run else "",
            item.url or "",
        )
        for item in overview.items
    ]
    keys = {item.key for item in overview.items}
    return listed + [
        Row("", key, "", "", word, "") for key, word in did.items() if key not in keys
    ]


# -- a program's own words ------------------------------------------------------

#: The most of a program's own words shown in one place; the log has the rest.
SAID = 20_000


def said(message: str) -> str:
    """A program's own words, cut to what one place can hold: where they
    start, and where they end — which is where an error says what it is."""
    if len(message) <= SAID:
        return message
    head, tail = message[: SAID // 10], message[-(SAID - SAID // 10) :]
    left_out = len(message) - len(head) - len(tail)
    return f"{head}\n… ({left_out} characters left out; the run's log has them)\n{tail}"


# -- links ----------------------------------------------------------------------


def into(url: str, workspace: str) -> bool:
    """Whether `url` is a link into the workspace at `workspace`: an https
    address on that very host, with no name or password in it. What a plugin
    says a thing's address is becomes a link only then — a page that says
    "open" beside a job must not lead anywhere else."""
    if not re.fullmatch(r"https://[A-Za-z0-9._~:/?#@!$&'()*+,;=%\[\]-]+", url):
        return False
    try:
        there, here = urlsplit(url), urlsplit(workspace)
    except ValueError:
        return False
    return (
        here.scheme == "https"
        and bool(here.hostname)
        and "@" not in there.netloc
        and there.netloc.lower() == here.netloc.lower()
    )

"""`stevin`: tables, views and the access around them, planned and applied by stevin.

    - name: tables
      uses: stevin
      with:
        config: stevin.yml

The contract is stevin's command line and its plan file, not its Python
modules: lely never imports stevin, so stevin stays a tool of its own with its
own releases.

- **plan** runs `stevin plan --target <t> --config <c> --output <tmp> --format
  json`. The plan file becomes this step's payload, whole, and so travels in
  lely's plan file. Each table is one change, keyed by its full name, with one
  line per step stevin would run and that step's risk class.
  When the plan needs what another tool has yet to make, stevin makes no plan
  and exits 5: a table's schema is one the bundle declares and has not
  deployed, or a spec only governs a table its owner, a dlt pipeline say, has
  not made. That is not a failure: the step is *waiting*, with stevin's own
  line as a note, and lely plans it again once the steps above it have run.
  Any other exit that is not 0 fails the plan. The step does not know whether
  a step above it makes what is missing: it belongs below the `bundle` step
  and below the step that runs the pipeline, and where neither is above it
  the run is refused when it reaches the step, with nothing applied.
- **apply** runs the plan that was approved, never a new one: the approved
  payload is written to a temporary file and handed to `stevin apply <file>`.
  The core has planned the step again right before (APL-3); that fresh plan is
  not what runs. It is what the approved file is held to: the steps stevin
  would run now, and the changes they carry out, must be the ones the approved
  file holds, or the step is refused. Then stevin holds the file to the live
  tables, and refuses it as stale when they moved since it was made.
  A refusal is known by stevin's exit code and never by its words: 3 is a plan
  that will never run, 4 a destructive one stevin was not told to allow, and
  any other exit that is not 0 is a failure.
- **destroy** drops nothing: a dropped table is its rows.
- **status** lists what stevin's specs describe, from `stevin list --json`. No
  plan is made for it.

It needs stevin 0.4.0a3 or newer: the first whose `plan` says with an exit code
that it needs what another tool has yet to make. The exit codes of `apply` and
`list` are there from 0.4.0a2. Every plan file says which stevin wrote it, and
one an older stevin wrote fails the plan with both versions and what to do.

stevin's risk classes onto lely's: `meta`, `feature` and `rewrite` are not
destructive, `destructive` is, and so is a class this does not know: lely would
rather ask than wave through what it can't read.

What lely prints of a plan file is each table's name, and each step's title,
the column it is about, its risk class and stevin's warnings: what stevin's
own plan shows. A title can name the principal of a grant. It reads no owner
and nothing else of the file.

**Not run on a workspace.** What is assumed of stevin is numbered S1 to S10 in
`tests/fake_stevin.py`, which the tests cite. It was read in stevin's source,
and its docs say the exit codes of `apply` and the shape of `list --json`
(https://kostavo-oss.github.io/tools/stevin/cli/#exit-codes); the exit codes
of `plan` are on that page from stevin 0.4.0a3.
S1 to S6 and S8 were also seen from the CLI of stevin 0.4.0a2 against its
in-memory warehouse on 2026-10-11, with the flags used here, S9 from stevin
0.3.0a1, and S10 from the source of what is to be stevin 0.4.0a3:
`docs/tried.md` says what that showed.

Docs: https://kostavo-oss.github.io/tools/stevin/cli/
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from lely import process
from lely.errors import LelyError, Refused
from lely.model import Action, Change, Item, Json, Outputs, Overview, StepPlan
from lely.step import Context

#: The stevin plan-file format this reads (stevin's `PLAN_FORMAT_VERSION`).
FORMAT_VERSION = 1

#: stevin's change kinds that bring an object into being, or remove one
#: (`stevin.model.change`).
_CREATES = frozenset(
    {"create_table", "create_view", "create_function", "create_schema", "create_volume"}
)
_DROPS = frozenset({"drop_table"})

#: stevin's risk classes (`stevin.model.plan.Risk`), and whether a step of that
#: class loses something. A class that is not here is treated as if it does.
_RISKS: dict[str, bool] = {
    "meta": False,
    "feature": False,
    "rewrite": False,
    "destructive": True,
}

#: The oldest stevin this runs: the first whose `plan` says by its exit code
#: that it needs what another tool has yet to make (S10). `apply` says a refusal
#: by its exit code, and there is a `list`, from 0.4.0a2.
NEEDS = "0.4.0a3"

#: The first stevin with `list` (S8, S9).
_HAS_LIST = "0.4.0a2"

#: `stevin apply`'s exit codes for a plan it refuses before any statement runs
#: (stevin's rule APL-8). `_PLAN_AGAIN`: this plan will never run: it is stale,
#: its file is not a plan that stevin reads, or it holds a step without SQL
#: (S4, S5, S6). `_NOT_ALLOWED`: it destroys something and stevin was not given
#: `--allow-destructive` (S3). Any other exit that is not 0 is a failure.
_PLAN_AGAIN, _NOT_ALLOWED = 3, 4

#: `stevin plan`'s exit code when the plan needs what another tool has yet to
#: make (stevin's rule PLAN-5, S10): the bundle's schema, or a table a spec
#: only governs. No plan was made, nothing is wrong with the specs, and the
#: same command makes the plan once that tool has run.
_NOT_YET = 5

#: What a plan says of a step whose tables stevin can't plan yet. It is true of
#: both cases and names neither: stevin's own line, in a note under it, says
#: what is missing and whose it is.
WAITING = (
    "stevin needs something another step or tool has yet to make; "
    "the tables are planned once it is there"
)

#: The most of stevin's own line that a plan keeps.
_NOTE_LIMIT = 400

#: What of a step may differ between two plans of the same specs and the same
#: tables: a size estimate and a restore point follow the table's data. Every
#: other key of a step is held to the fresh plan: stevin obeys them, down to the
#: number it resumes by and the change it checks before it skips a step.
_FOLLOWS_THE_DATA = frozenset({"est_bytes", "undo_hint"})

_HINT = "Install it with `uv tool install stevin`, or set `executable`."


class Stevin:
    """Tables, views, functions and grants, planned and applied by stevin."""

    #: Said in a destroy plan, where the step is skipped.
    nothing_to_destroy = (
        "stevin drops nothing on a destroy: a dropped table is its rows. The tables stay."
    )

    @dataclass(frozen=True, slots=True)
    class Options:
        #: stevin's project file, relative to the config.
        config: str = "stevin.yml"
        #: stevin's target; lely's target when not given.
        target: str | None = None
        #: Only these tables, views or patterns (stevin's `--select`).
        select: tuple[str, ...] = ()
        #: How to run stevin: `[uvx, stevin]` pins it to its own env.
        executable: tuple[str, ...] = ("stevin",)

    @staticmethod
    def programs(written: Mapping[str, Json]) -> tuple[str, ...]:
        executable = written.get("executable")
        if isinstance(executable, list) and executable:
            return (str(executable[0]),)
        return ("stevin",)

    def plan(self, ctx: Context[Stevin.Options]) -> StepPlan:
        if ctx.purpose != "apply":
            # a destroy and a status ask only for what the step gives the ones
            # below it, and it gives nothing: stevin isn't run
            return StepPlan()
        try:
            document = _stevin_plan(ctx)
        except _NotYet as waiting:
            # no changes and no payload: nothing of this step can run from a
            # plan that shows it waiting (WAIT-3). It is planned again when a
            # run reaches it, and that plan is shown before it is applied.
            ctx.log.info(f"{ctx.name}: waiting: {WAITING}")
            return StepPlan(waiting=WAITING, notes=waiting.notes)
        return StepPlan(changes=changes(document), payload=document)

    def apply(self, ctx: Context[Stevin.Options], plan: StepPlan) -> Outputs:
        """`stevin apply` on the plan file that was approved.

        `plan` is the one made right before this. The core let it through, so
        each of its changes was shown, and a destructive one was allowed
        (APL-3, APL-4): `--allow-destructive` goes to stevin only then.
        """
        if plan.waiting is not None or (
            ctx.approved is not None and ctx.approved.waiting is not None
        ):
            # the core stops before this (WAIT-7); said here too, because a
            # plan that is not whole is never one to hand to stevin
            raise Refused(
                f"Step `{ctx.name}` is waiting: stevin has not planned its tables "
                "yet, so there is nothing that was shown to apply."
            )
        document = _approved(ctx, plan)
        with tempfile.TemporaryDirectory(prefix="lely-stevin-") as scratch:
            path = Path(scratch) / "plan.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            # no `--target`: a saved plan says its own, and stevin refuses one
            # beside it (S2). No `--yes`: stevin asks nothing about a saved plan.
            args = [*ctx.options.executable, "apply", str(path)]
            args += ["--config", ctx.options.config]
            if plan.destructive:
                args.append("--allow-destructive")  # S3
            ctx.log.info(f"{ctx.name}: stevin apply")
            result = process.run(
                args,
                ctx.root,
                env=ctx.env,
                hint=_HINT,
                said=lambda line: ctx.log.info(f"{ctx.name}: {line}"),
            )
        if result.returncode == _PLAN_AGAIN:
            raise Refused(
                f"stevin refused the plan for step `{ctx.name}`:\n"
                f"{process.wrote(result)}\n"
                "Plan again with `lely plan`, and review the new plan."
            )
        if result.returncode == _NOT_ALLOWED:
            # lely passes the flag whenever the plan it let through holds a
            # destructive change, so this is a step stevin calls destructive
            # and lely's plan did not: nobody was asked to allow it
            raise Refused(
                f"stevin refused the plan for step `{ctx.name}`: it destroys "
                "something that lely's plan did not show as destructive, so "
                f"stevin was not told to allow it.\n{process.wrote(result)}\n"
                "Nothing ran."
            )
        if result.returncode != 0:
            raise LelyError(
                f"{process.failure('`stevin apply`', result)}\n"
                "A plan file stevin names here was lely's copy of the approved "
                "plan, and is gone. What stevin applied before it stopped stays "
                "applied: fix the cause and run lely again. It asks for a new plan "
                "if part of this one was applied."
            )
        return {}

    def overview(self, ctx: Context[Stevin.Options]) -> Overview:
        """Every table, view and the rest that stevin's specs describe for the
        target, and whether it exists: what `stevin list --json` answers (S8),
        and nothing remembered. No plan is made, so no table is read in full."""
        items = [
            Item(
                kind=str(one.get("kind") or "table"),
                key=str(one.get("name")),
                name=str(one.get("name")).rsplit(".", 1)[-1],
                deployed=one.get("exists") is True,
            )
            for one in _stevin_list(ctx)
        ]
        return Overview(
            tuple(items), ("what stevin's specs describe, as `stevin list` reads it",)
        )


# -- asking stevin ----------------------------------------------------------------


class _NotYet(Exception):
    """`stevin plan` made no plan because it needs what another tool has yet
    to make: exit 5 (S10). `notes` hold stevin's own line, which names it."""

    def __init__(self, result: subprocess.CompletedProcess[str]) -> None:
        super().__init__("stevin can't plan yet")
        # the refusal is the last line stevin writes; what it says is shown
        # and never read: the exit code alone said what this is
        lines = [" ".join(_plain(line).split()) for line in result.stderr.splitlines()]
        said = next((line for line in reversed(lines) if line), "")
        if len(said) > _NOTE_LIMIT:
            said = said[: _NOTE_LIMIT - 1] + "…"
        self.notes: tuple[str, ...] = (f"stevin: {said}",) if said else ()


#: A terminal's escape sequences: colour, a link, a title. stevin colours the
#: line when it is told to (`FORCE_COLOR`), also into a pipe.
_ESCAPES = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"  # CSI: colour, the cursor
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?"  # OSC: a link, a title
    r"|\x1b[ -/]*[0-~]"  # the short ones: a reset, a character set
)


def _plain(line: str) -> str:
    """A line a program wrote, without what a terminal would obey: the escape
    sequences it is likely to hold are taken out whole, and any control
    character that is left is a space. A rarer sequence can leave its letters
    behind; nothing of it is obeyed."""
    line = _ESCAPES.sub("", line)
    return "".join(" " if unicodedata.category(char) == "Cc" else char for char in line)


def _stevin_plan(ctx: Context[Stevin.Options]) -> dict[str, Json]:
    """`stevin plan`, as the plan file it writes. Changes nothing.

    Raises `_NotYet` when stevin says, by its exit code, that the plan needs
    what another tool has yet to make."""
    options = ctx.options
    with tempfile.TemporaryDirectory(prefix="lely-stevin-") as scratch:
        out = Path(scratch) / "plan.json"
        args = [
            *options.executable,
            "plan",
            "--target",
            options.target or ctx.target,
            "--config",
            options.config,
            "--output",
            str(out),
            "--format",
            "json",
        ]
        for pattern in options.select:
            args += ["--select", pattern]
        ctx.log.info(f"{ctx.name}: stevin plan")
        result = process.run(args, ctx.root, env=ctx.env, hint=_HINT)
        if result.returncode == _NOT_YET:
            raise _NotYet(result)
        if result.returncode != 0:
            raise process.failure("`stevin plan`", result)
        try:
            document = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise LelyError(f"stevin wrote no readable plan: {error}") from None
    if not isinstance(document, dict):
        raise LelyError("stevin wrote no readable plan: it is no JSON object")
    _new_enough(document.get("tool_version"))
    return document


def _stevin_list(ctx: Context[Stevin.Options]) -> list[dict[str, Json]]:
    """`stevin list --json`: the objects the specs describe. Changes nothing."""
    options = ctx.options
    args = [
        *options.executable,
        "list",
        "--target",
        options.target or ctx.target,
        "--config",
        options.config,
        "--json",
    ]
    for pattern in options.select:
        args += ["--select", pattern]
    ctx.log.info(f"{ctx.name}: stevin list")
    result = process.run(args, ctx.root, env=ctx.env, hint=_HINT)
    if result.returncode == 2:
        # how a command line answers a command it doesn't have (S9)
        raise LelyError(
            f"{process.failure('`stevin list`', result)}\n"
            f"An older stevin has no `list`: it is there from stevin {_HAS_LIST}. If "
            f"that is what this is: {_UPGRADE}"
        )
    if result.returncode != 0:
        raise process.failure("`stevin list`", result)
    try:
        document = json.loads(result.stdout)
    except ValueError as error:
        raise LelyError(f"`stevin list --json` printed no JSON: {error}") from None
    objects = document.get("objects") if isinstance(document, dict) else None
    if not isinstance(objects, list) or not all(
        isinstance(one, dict) and isinstance(one.get("name"), str) for one in objects
    ):
        raise LelyError(
            "`stevin list --json` printed no list of objects that lely can read: "
            "it wants `objects`, each with a `name`, a `kind` and `exists`."
        )
    return objects


def _new_enough(version: Json) -> None:
    """Fail for a plan an older stevin than `NEEDS` wrote: its `plan` exits 1
    where it needs what another tool has yet to make, which fails a plan where
    the step is to wait; and one older still exits 1 for a refusal of `apply`.

    The version is the one stevin writes into every plan file, so nothing more
    is run to learn it. One that can't be read as a version (stevin run from
    its source says `unknown`) is let through: only a stevin known to be older
    is turned away, and the exit codes decide the rest.
    """
    if not isinstance(version, str):
        return
    wrote, needs = _release(version), _release(NEEDS)
    if wrote is None or needs is None or wrote >= needs:
        return
    raise LelyError(
        f"This plan was written by stevin {version}, and lely needs stevin {NEEDS} "
        f"or newer: the first that says by its exit code that it needs what "
        f"another tool has yet to make. {_UPGRADE}"
    )


_UPGRADE = (
    "Upgrade it with `uv tool upgrade stevin`, or set `executable` to one that is "
    "new enough."
)

_VERSION = re.compile(
    r"v?(\d+(?:\.\d+)*)"
    r"(?:[-_.]?(a|alpha|b|beta|c|rc|pre|preview)[-_.]?(\d+)?)?"
    r"(?:[-_.]?(dev)[-_.]?\d*)?"
    r"(?:[-_.+].*)?",
    re.ASCII,
)
_STAGES = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2, "preview": 2}


def _release(version: str) -> tuple[tuple[int, ...], int, int, int] | None:
    """A version as something to compare, the way Python's packaging orders
    them: its numbers without the zeros at their end, then alpha, beta, release
    candidate or final, then the number of that, then whether it is a
    development build, which comes before the version it is of. `0.4.0a2.dev1`
    is before `0.4.0a2`, which is before `0.4.0`. A local part and a
    post-release are not counted. `None` for what does not read as a version."""
    if len(version) > 100:
        return None  # no version: and Python reads no number of thousands of digits
    found = _VERSION.fullmatch(version.strip().lower())
    if found is None:
        return None
    numbers = [int(part) for part in found[1].split(".")]
    while numbers and numbers[-1] == 0:
        numbers.pop()
    stage = _STAGES.get(found[2], 3)
    if found[2] is None and found[4]:
        stage = -1  # `0.4.0.dev1`: before every alpha of 0.4.0
    return (tuple(numbers), stage, int(found[3] or 0), 0 if found[4] else 1)


def _approved(ctx: Context[Stevin.Options], fresh: StepPlan) -> Mapping[str, Json]:
    """The stevin plan file to apply: the one in the approved plan, held to the
    one made right before this. Raises `Refused` when it is not that plan.

    A step that was waiting when the plan was made has no approved payload:
    what was shown and approved then is `fresh` itself.
    """
    if ctx.approved is None:
        document = fresh.payload
    else:
        document = ctx.approved.payload
        if not isinstance(fresh.payload, dict):
            raise LelyError("the plan made before applying holds no stevin plan")
    if not isinstance(document, dict):
        raise Refused(
            f"The approved plan holds no stevin plan for step `{ctx.name}`. Plan again."
        )
    # nothing the file says is repeated in a refusal: it is not held to anything yet
    target = ctx.options.target or ctx.target
    if document.get("format_version") != FORMAT_VERSION:
        raise Refused(
            f"The approved stevin plan for step `{ctx.name}` is not of format "
            f"{FORMAT_VERSION}, the one lely reads. Plan again."
        )
    if document.get("target") != target:
        raise Refused(
            f"The approved stevin plan for step `{ctx.name}` is for another target "
            f"than `{target}`. Plan again."
        )
    if ctx.approved is not None:
        assert isinstance(fresh.payload, dict)
        was, now = _held(document), _held(fresh.payload)
        if was != now:
            raise Refused(
                f"What stevin would do for step `{ctx.name}` is no longer what the "
                f"approved plan holds: {_count(was)} step(s) then, {_count(now)} now, "
                "or the same number and not the same steps. Plan again."
            )
    return document


# -- reading its plan file: pure ---------------------------------------------------


def changes(document: Mapping[str, Json]) -> tuple[Change, ...]:
    """A stevin plan file, as one lely change per table stevin has steps for.

    Every step is a line of its table's change, with its risk class. A class
    this doesn't know (a newer stevin's) is kept and marks the change
    destructive: lely would rather ask than wave through what it can't read.
    """
    _format(document)
    tables = {str(t.get("table")): t for t in _dicts(document.get("tables"))}
    by_table: dict[str, list[dict[str, Json]]] = {}
    for step in _dicts(document.get("steps")):
        by_table.setdefault(str(step.get("table")), []).append(step)
    result: list[Change] = []
    for name, steps in by_table.items():
        table = tables.get(name, {})
        kinds = {str(c.get("kind")) for c in _dicts(table.get("changes"))}
        facts = table.get("facts")
        exists = isinstance(facts, dict) and bool(facts.get("exists"))
        action: Action = "update"
        if kinds & _DROPS:
            action = "delete"
        elif kinds & _CREATES and not exists:
            action = "create"
        detail: list[str] = []
        for step in steps:
            detail += _lines(step)
        risks = [step.get("risk") for step in steps]
        result.append(
            Change(
                key=name,
                action=action,
                summary=f"{name}  rewrite" if "rewrite" in risks else name,
                destructive=any(_destructive(risk) for risk in risks),
                detail=tuple(detail),
            )
        )
    return tuple(result)


def _lines(step: Mapping[str, Json]) -> list[str]:
    """One step as stevin's own plan names it, its risk class, and what stevin
    warns of."""
    title, path, risk = str(step.get("title")), step.get("path"), step.get("risk")
    if isinstance(path, str) and path and path not in title:
        title += f" {path}"
    lines = [f"{title}  [{risk}]"]
    if not (isinstance(risk, str) and risk in _RISKS):
        lines.append(
            f"⚠ stevin gives this step the risk class `{risk}`, which lely doesn't "
            "know: it is treated as destructive"
        )
    if step.get("sql") is None:
        lines.append(
            "⚠ stevin has no statement for this step, and applies no plan that holds one"
        )
    lines += [f"⚠ {warning}" for warning in _list(step.get("warnings"))]
    return lines


def _destructive(risk: Json) -> bool:
    return _RISKS.get(risk, True) if isinstance(risk, str) else True


def _held(document: Mapping[str, Json]) -> tuple[Json, list[Json], list[Json]]:
    """What of a stevin plan file is held to the plan made right before an
    apply: the specs it was made from, every step, and for every object the
    changes those steps carry out and the shape they build towards.

    Not the fingerprint of the live tables, which is stevin's to hold the file
    to, and not what follows a table's data: its size, its version.
    """
    steps: list[Json] = [
        {k: v for k, v in step.items() if k not in _FOLLOWS_THE_DATA}
        if isinstance(step, dict)
        else step
        for step in _list(document.get("steps"))
    ]
    tables: list[Json] = [
        [table.get("table"), table.get("changes"), table.get("desired")]
        if isinstance(table, dict)
        else table
        for table in _list(document.get("tables"))
    ]
    return (document.get("spec_hash"), steps, tables)


def _count(held: tuple[Json, list[Json], list[Json]]) -> int:
    return len(held[1])


def _format(document: Mapping[str, Json]) -> None:
    version = document.get("format_version")
    if version != FORMAT_VERSION:
        raise LelyError(
            f"stevin wrote plan format {version}; lely reads format "
            f"{FORMAT_VERSION}. Use a stevin and a lely released together."
        )


def _list(value: Json) -> list[Json]:
    return value if isinstance(value, list) else []


def _dicts(value: Json) -> list[dict[str, Json]]:
    return [entry for entry in _list(value) if isinstance(entry, dict)]

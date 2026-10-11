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
- **apply** runs the plan that was approved, never a new one: the approved
  payload is written to a temporary file and handed to `stevin apply <file>`.
  The core has planned the step again right before (APL-3); that fresh plan is
  not what runs. It is what the approved file is held to: the steps stevin
  would run now, and the changes they carry out, must be the ones the approved
  file holds, or the step is refused. Then stevin holds the file to the live
  tables, and refuses it as stale when they moved since it was made.
- **destroy** drops nothing: a dropped table is its rows.
- **status** lists the tables stevin's specs describe, from `stevin plan`.

stevin's risk classes onto lely's: `meta`, `feature` and `rewrite` are not
destructive, `destructive` is, and so is a class this does not know: lely would
rather ask than wave through what it can't read.

What lely prints of a plan file is each table's name, and each step's title,
the column it is about, its risk class and stevin's warnings: what stevin's
own plan shows. A title can name the principal of a grant. It reads no owner
and nothing else of the file.

**Not run on a workspace.** What is assumed of stevin is numbered S1 to S7 in
`tests/fake_stevin.py`, which the tests cite. It was read in stevin's source.
S1 to S5 were also seen from stevin's own CLI against its in-memory warehouse
on 2026-10-11, with the flags used here and plan files that had been through
lely's plan file: `docs/tried.md` says what that showed. stevin has no exit
code and no other sign of its own for a stale plan, so a refusal is known by
its words (`_PLAN_AGAIN`); issue #65 of `kostavo-oss/tools` asks stevin for one.

Docs: https://kostavo-oss.github.io/tools/stevin/cli/
"""

from __future__ import annotations

import json
import tempfile
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

#: What stevin says when it refuses a plan file that a new plan would mend: one
#: the live tables moved on from, one another version saved (both S4), one of
#: another format (S5). Words, because every refusal of stevin's exits 1.
_PLAN_AGAIN = ("Plan again and review the new plan", "Re-run `stevin plan`")

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
        document = _stevin_plan(ctx)
        return StepPlan(changes=changes(document), payload=document)

    def apply(self, ctx: Context[Stevin.Options], plan: StepPlan) -> Outputs:
        """`stevin apply` on the plan file that was approved.

        `plan` is the one made right before this. The core let it through, so
        each of its changes was shown, and a destructive one was allowed
        (APL-3, APL-4): `--allow-destructive` goes to stevin only then.
        """
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
        if result.returncode != 0:
            said = process.wrote(result)
            # stevin wraps a line to the terminal's width
            if any(words in " ".join(said.split()) for words in _PLAN_AGAIN):
                raise Refused(
                    f"stevin refused the plan for step `{ctx.name}`:\n{said}\n"
                    "Plan again with `lely plan`, and review the new plan."
                )
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
        target, and whether it exists: what `stevin plan` reads, and nothing
        remembered. stevin has no command that only lists."""
        document = _stevin_plan(ctx)
        _format(document)
        items = []
        for table in _dicts(document.get("tables")):
            name = str(table.get("table"))
            facts = table.get("facts")
            facts = facts if isinstance(facts, dict) else {}
            items.append(
                Item(
                    kind=str(facts.get("kind") or "table"),
                    key=name,
                    name=name.rsplit(".", 1)[-1],
                    deployed=bool(facts.get("exists")),
                )
            )
        return Overview(
            tuple(items), ("what stevin's specs describe, as `stevin plan` reads it",)
        )


# -- asking stevin ----------------------------------------------------------------


def _stevin_plan(ctx: Context[Stevin.Options]) -> dict[str, Json]:
    """`stevin plan`, as the plan file it writes. Changes nothing."""
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
        if result.returncode != 0:
            raise process.failure("`stevin plan`", result)
        try:
            document = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise LelyError(f"stevin wrote no readable plan: {error}") from None
    if not isinstance(document, dict):
        raise LelyError("stevin wrote no readable plan: it is no JSON object")
    return document


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

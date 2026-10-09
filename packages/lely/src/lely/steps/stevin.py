"""`stevin`: tables, views and the rest, with stevin's own plan.

**Parked.** The owner takes this plugin up separately (`spec/006-stevin.md`).
Its plan half is built and left as it is; it can't apply yet, and says so
before anything runs.

The contract is stevin's CLI and its plan file, not its Python modules, so
stevin stays a standalone tool with its own releases:

- plan: `stevin plan --target <t> --config <c> --output <tmp> --format json`.
  The plan file becomes this step's payload, whole.

stevin's risk classes map onto lely's: `destructive` stays destructive;
`meta`, `feature` and `rewrite` are updates, with a rewrite named in the
detail. Each table is one change, keyed by its full name.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from lely import process
from lely.errors import LelyError
from lely.model import Action, Change, Json, Outputs, StepPlan
from lely.step import Context

#: The stevin plan-file format this reads (stevin's `PLAN_FORMAT_VERSION`).
FORMAT_VERSION = 1

#: stevin's change kinds that bring an object into being, or remove one
#: (`stevin.model.change`).
_CREATES = frozenset(
    {"create_table", "create_view", "create_function", "create_schema", "create_volume"}
)
_DROPS = frozenset({"drop_table"})


class Stevin:
    """Tables, views, functions and grants, planned by stevin. Can't apply yet."""

    #: `apply` refuses a project that uses this plugin before anything runs.
    plan_only = True

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
            result = process.run(
                args,
                ctx.root,
                env=ctx.env,
                hint="Install it with `uv tool install stevin`, or set `executable`.",
            )
            if result.returncode != 0:
                raise process.failure("`stevin plan`", result)
            try:
                document = json.loads(out.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise LelyError(f"stevin wrote no readable plan: {error}") from None
        return StepPlan(changes=changes(document), payload=document)

    def apply(self, ctx: Context[Stevin.Options], plan: StepPlan) -> Outputs:
        raise LelyError(
            "The `stevin` plugin can plan and can't apply yet: it is taken up "
            "separately. Run `stevin apply` yourself for now."
        )


def changes(document: Mapping[str, Json]) -> tuple[Change, ...]:
    """A stevin plan file, as one lely change per table that changes."""
    version = document.get("format_version")
    if version != FORMAT_VERSION:
        raise LelyError(
            f"stevin wrote plan format {version}; lely reads format "
            f"{FORMAT_VERSION}. Use a stevin and a lely released together."
        )
    steps = [s for s in _list(document.get("steps")) if isinstance(s, dict)]
    result: list[Change] = []
    for table in _list(document.get("tables")):
        if not isinstance(table, dict):
            continue
        name = str(table.get("table"))
        kinds = {
            str(c.get("kind")) for c in _list(table.get("changes")) if isinstance(c, dict)
        }
        own = [s for s in steps if s.get("table") == name]
        if not kinds and not own:
            continue
        facts = table.get("facts")
        exists = isinstance(facts, dict) and bool(facts.get("exists"))
        action: Action = "update"
        if kinds & _DROPS:
            action = "delete"
        elif kinds & _CREATES and not exists:
            action = "create"
        detail: list[str] = []
        for step in own:
            risk = step.get("risk")
            tag = f"  [{risk}]" if risk in ("rewrite", "destructive") else ""
            detail.append(f"{step.get('title')}{tag}")
            detail += [f"⚠ {warning}" for warning in _list(step.get("warnings"))]
        result.append(
            Change(
                key=name,
                action=action,
                summary=name,
                destructive=any(s.get("risk") == "destructive" for s in own),
                detail=tuple(detail),
            )
        )
    return tuple(result)


def _list(value: Json) -> list[Json]:
    return value if isinstance(value, list) else []

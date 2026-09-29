"""`deltaplan`: tables, views and the rest, with deltaplan's own plan.

The contract is deltaplan's CLI and its plan file, not its Python modules, so
deltaplan stays a standalone tool with its own releases:

- plan: `deltaplan plan --target <t> --config <c> --output <tmp> --format json`.
  The plan file becomes this step's payload, whole.
- apply (milestone 2): the payload written back to a file, then
  `deltaplan apply <file> --yes`, with `--allow-destructive` only when sluis was
  given it. deltaplan's own state fingerprint refuses a stale plan.

deltaplan's risk classes map onto sluis's: `destructive` stays destructive;
`meta`, `feature` and `rewrite` are updates, with a rewrite named in the
detail. Each table is one change, keyed by its full name.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from sluis import process
from sluis.errors import SluisError
from sluis.model import Action, Change, Json, Outputs, StepPlan
from sluis.step import Context

#: The deltaplan plan-file format this reads (deltaplan's `PLAN_FORMAT_VERSION`).
FORMAT_VERSION = 1

#: deltaplan's change kinds that bring an object into being, or remove one
#: (`deltaplan.model.change`).
_CREATES = frozenset(
    {"create_table", "create_view", "create_function", "create_schema", "create_volume"}
)
_DROPS = frozenset({"drop_table"})


class Deltaplan:
    """Tables, views, functions and grants, planned and applied by deltaplan."""

    @dataclass(frozen=True, slots=True)
    class Options:
        #: deltaplan's project file, relative to `sluis.yml`.
        config: str = "deltaplan.yml"
        #: deltaplan's target; sluis's target when not given.
        target: str | None = None
        #: Only these tables, views or patterns (deltaplan's `--select`).
        select: tuple[str, ...] = ()
        #: How to run deltaplan: `[uvx, deltaplan]` pins it to its own env.
        executable: tuple[str, ...] = ("deltaplan",)

    def plan(self, ctx: Context[Deltaplan.Options]) -> StepPlan:
        options = ctx.options
        with tempfile.TemporaryDirectory(prefix="sluis-deltaplan-") as scratch:
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
            ctx.log.info(f"{ctx.name}: deltaplan plan")
            result = process.run(
                args,
                ctx.root,
                env=ctx.env,
                hint="Install it with `uv tool install deltaplan`, or set `executable`.",
            )
            if result.returncode != 0:
                raise process.failure("`deltaplan plan`", result)
            try:
                document = json.loads(out.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise SluisError(f"deltaplan wrote no readable plan: {error}") from None
        return StepPlan(changes=changes(document), payload=document)

    def apply(self, ctx: Context[Deltaplan.Options], plan: StepPlan) -> Outputs:
        raise NotImplementedError("apply is milestone 2")


def changes(document: Mapping[str, Json]) -> tuple[Change, ...]:
    """A deltaplan plan file, as one sluis change per table that changes."""
    version = document.get("format_version")
    if version != FORMAT_VERSION:
        raise SluisError(
            f"deltaplan wrote plan format {version}; sluis reads format "
            f"{FORMAT_VERSION}. Use a deltaplan and a sluis released together."
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

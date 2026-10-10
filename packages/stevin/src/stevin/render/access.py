"""The access report: for a terminal, and as data.

One table, read top to bottom: who owns it, what each principal may do and
where that is granted, what narrows a read, and what the report is not. The
lines about policies are the plan's own (`labels.policy_line`), so a policy
reads the same here as under a table in a plan.
"""

from __future__ import annotations

import io
import json
import textwrap
from typing import Any

from rich.console import Console
from rich.text import Text

from stevin.access import AccessError
from stevin.model.access import LIMITS, LISTS, Access, Held
from stevin.model.table import RowFilter
from stevin.model.types import Mask
from stevin.render.json import _policy_from_dict, _policy_to_dict
from stevin.render.labels import listed, policy_line

#: The report's JSON, so a reader can tell a later shape from this one.
FORMAT_VERSION = 1


def render_access(access: Access, console: Console) -> None:
    """Print the report."""
    head = Text(access.table, style="bold")
    head.append("   access", style="cyan")
    console.print(head)
    console.print(Text(f"  owner {access.owner or 'unknown'}"))

    console.print()
    console.print(Text("  Granted", style="bold"))
    if not access.grants:
        console.print(
            Text("    · nothing on the table, and nothing inherited", style="dim")
        )
    lines = [
        (principal, ", ".join(privileges), _through(level, on))
        for principal in access.principals
        for level, on, privileges in access.held_by(principal)
    ]
    width = max((len(privileges) for _, privileges, _ in lines), default=0)
    shown: str | None = None
    for principal, privileges, through in lines:
        if principal != shown:
            console.print(Text(f"    {principal}"))
            shown = principal
        line = Text(f"      {privileges.ljust(width)}  ")
        line.append(through, style="dim")
        console.print(line)

    console.print()
    console.print(Text("  What narrows a read", style="bold"))
    if access.row_filter is not None:
        _item(console, _filter_line(access.row_filter))
    for column, mask in access.masks:
        _item(console, _mask_line(column, mask))
    for policy in access.policies:
        _item(console, policy_line(policy))
    if not access.narrowed:
        _item(console, _nothing(access), style="dim")
    if access.policies_unread:
        _item(
            console,
            f"policies could not be read: {access.policies_unread} (the report is "
            "otherwise complete)",
            style="yellow",
            mark="⚠",
        )

    console.print()
    console.print(Text(f"  {LISTS}", style="dim"))
    for limit in LIMITS:
        console.print(Text(f"    · {limit}", style="dim"))


def access_text(access: Access, *, width: int = 100) -> str:
    """The same output as a plain string — for tests, pipes and files."""
    console = Console(
        file=io.StringIO(), width=width, no_color=True, highlight=False, record=True
    )
    render_access(access, console)
    return console.export_text()


def _item(console: Console, said: str, *, style: str = "", mark: str = "·") -> None:
    """One listed line. A long one — a policy with its condition — carries on
    under its own text, not under the mark."""
    lines = textwrap.wrap(
        said,
        max(console.width - 6, 20),
        break_long_words=False,
        break_on_hyphens=False,
    )
    for index, line in enumerate(lines):
        console.print(Text(f"    {mark if index == 0 else ' '} {line}", style=style))


def _through(level: str, on: str) -> str:
    if level == "table":
        return "the table's own"
    return f"inherited from {level} {on}".rstrip()


def _filter_line(row_filter: RowFilter) -> str:
    on = f" on {listed(row_filter.columns)}" if row_filter.columns else ""
    return f"row filter {row_filter.function}{on}"


def _mask_line(column: str, mask: Mask) -> str:
    using = f", using {listed(mask.using_columns)}" if mask.using_columns else ""
    return f"mask on {column} with {mask.function}{using}"


def _nothing(access: Access) -> str:
    if access.policies_unread:
        return "no row filter and no mask on the table"
    return "nothing: no row filter, no mask, no policy in scope"


# ---------------------------------------------------------------------------
# as data
# ---------------------------------------------------------------------------


def access_to_dict(access: Access) -> dict[str, Any]:
    return {
        "format_version": FORMAT_VERSION,
        "table": access.table,
        "owner": access.owner,
        "grants": [
            {
                "principal": held.principal,
                "privilege": held.privilege,
                "level": held.level,
                "on": held.on,
                "inherited": held.inherited,
            }
            for held in access.grants
        ],
        "row_filter": (
            None
            if access.row_filter is None
            else {
                "function": access.row_filter.function,
                "columns": list(access.row_filter.columns),
            }
        ),
        "masks": [
            {
                "column": column,
                "function": mask.function,
                "using_columns": list(mask.using_columns),
            }
            for column, mask in access.masks
        ],
        "policies": [_policy_to_dict(policy) for policy in access.policies],
        "policies_unread": access.policies_unread,
        # What the report is not, where the report goes.
        "does_not": list(LIMITS),
    }


def dumps(access: Access) -> str:
    """The report as JSON: what `stevin access --json` prints."""
    return json.dumps(access_to_dict(access), indent=2) + "\n"


def loads(text: str) -> Access:
    """A report back from its JSON. Raises `AccessError` for anything else."""
    try:
        data = json.loads(text)
        row_filter = data["row_filter"]
        return Access(
            table=data["table"],
            owner=data["owner"],
            grants=tuple(
                Held(g["principal"], g["privilege"], g["level"], g["on"])
                for g in data["grants"]
            ),
            row_filter=(
                None
                if row_filter is None
                else RowFilter(row_filter["function"], tuple(row_filter["columns"]))
            ),
            masks=tuple(
                (m["column"], Mask(m["function"], tuple(m["using_columns"])))
                for m in data["masks"]
            ),
            policies=tuple(_policy_from_dict(p) for p in data["policies"]),
            policies_unread=data["policies_unread"],
        )
    except (ValueError, KeyError, TypeError) as error:
        raise AccessError(f"not an access report: {error!r}") from error

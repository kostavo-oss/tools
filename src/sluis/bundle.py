"""The bundle's answers, read. Pure.

What the Databricks CLI prints is someone else's format, so it is read
leniently: only what sluis uses is looked at, and nothing else is validated.
The plan document itself is kept whole in sluis's plan (`BundlePlan.document`)
so apply can hand it back to `bundle deploy --plan` untouched.
"""

from __future__ import annotations

from collections.abc import Mapping

from sluis.errors import SluisError
from sluis.model import Action, Change, Json

#: The direct engine's plan format this was written against.
PLAN_VERSION = 2

#: The CLI's per-resource actions, as sluis's. `update_id` gives the resource
#: a new id — for whatever refers to it, that is a replacement.
_ACTIONS: dict[str, Action | None] = {
    "skip": None,
    "create": "create",
    "update": "update",
    "resize": "update",
    "update_id": "replace",
    "recreate": "replace",
    "delete": "delete",
}


def name(config: Mapping[str, Json]) -> str:
    return str(_section(config, "bundle").get("name", "bundle"))


def target(config: Mapping[str, Json]) -> str:
    bundle = _section(config, "bundle")
    chosen = bundle.get("target")
    if not isinstance(chosen, str):
        raise SluisError(
            "The bundle's resolved config names no target; pass one with --target."
        )
    return chosen


def host(config: Mapping[str, Json]) -> str | None:
    """The workspace the target deploys to."""
    value = _section(config, "workspace").get("host")
    return value if isinstance(value, str) else None


def resource_keys(config: Mapping[str, Json]) -> frozenset[str]:
    """Every resource the bundle declares, as `<type>.<key>`."""
    resources = config.get("resources")
    if not isinstance(resources, dict):
        return frozenset()
    return frozenset(
        f"{kind}.{key}"
        for kind, entries in resources.items()
        if isinstance(entries, dict)
        for key in entries
    )


def changes(document: Mapping[str, Json]) -> tuple[Change, ...]:
    """The plan's resources that change, as sluis changes.

    An action this doesn't know (a newer CLI's) is kept and marked destructive:
    sluis would rather ask than wave through what it can't read.
    """
    version = document.get("plan_version")
    if version != PLAN_VERSION:
        raise SluisError(
            f"The Databricks CLI wrote a plan of version {version}; sluis reads "
            f"version {PLAN_VERSION}. Check `sluis doctor` for a supported CLI."
        )
    plan = document.get("plan")
    if not isinstance(plan, dict):
        return ()
    result: list[Change] = []
    for key in sorted(plan):
        entry = plan[key]
        if not isinstance(entry, dict):
            continue
        raw = str(entry.get("action", ""))
        short = key.removeprefix("resources.")
        if raw not in _ACTIONS:
            result.append(
                Change(
                    key=key,
                    action="update",
                    summary=short,
                    destructive=True,
                    detail=(f"the CLI plans `{raw}`, which sluis doesn't know",),
                )
            )
            continue
        action = _ACTIONS[raw]
        if action is None:
            continue
        result.append(
            Change(key=key, action=action, summary=short, detail=_fields(entry))
        )
    return tuple(result)


def created(changes: tuple[Change, ...]) -> frozenset[str]:
    """Resources this deploy creates or replaces, as `<type>.<key>`: their ids
    aren't known until it has run."""
    return frozenset(
        change.key.removeprefix("resources.")
        for change in changes
        if change.action in ("create", "replace")
    )


def _fields(entry: Mapping[str, Json]) -> tuple[str, ...]:
    """Which fields change, and which of them force a replacement."""
    fields = entry.get("changes")
    if not isinstance(fields, dict):
        return ()
    causes: list[str] = []
    others: list[str] = []
    for field_name in sorted(fields):
        change = fields[field_name]
        if not isinstance(change, dict) or change.get("action") in (None, "skip"):
            continue
        if change.get("action") in ("recreate", "update_id"):
            reason = change.get("reason")
            causes.append(f"{field_name} ({reason})" if reason else field_name)
        else:
            others.append(field_name)
    lines = [f"replaced: {', '.join(causes)}"] if causes else []
    return tuple(lines + others)


def _section(config: Mapping[str, Json], key: str) -> Mapping[str, Json]:
    section = config.get(key)
    return section if isinstance(section, dict) else {}

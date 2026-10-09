"""Whose table is it — and so what stevin may do with it.

stevin's rule is that it only touches what it made. Next to that sits a
smaller one: some tables in the schemas it works in are *another tool's*. A
dbt model, a dlt landing table, a notebook team's output. stevin doesn't know
which is which unless it is told, and the consequences of not knowing are
quiet: `import` writes specs for forty dbt models, a plan claims a table a
pipeline will recreate tonight, a strict schema lists them all as *unmanaged*,
which is true and says nothing.

So `stevin.yml` can say who owns what, and a dbt manifest can say it for dbt:

```yaml
owned_elsewhere:
  ${catalog}.silver.*: dbt
  ${catalog}.science.*: the data-science team
dbt:
  manifest: ../analytics/target/manifest.json
```

A dlt pipeline needs no telling: a schema that holds dlt's own `_dlt_loads`
and `_dlt_version` tables is dlt's, every table in it — a heuristic, and
written down as one (`is_dlt_schema`).

What an owner means:

* **dbt's** tables are refused outright, shape and governance alike: dbt's own
  config carries grants and tags, and a `table` materialisation recreates the
  table and drops its masks, so two writers would fight every run. A
  schema-level policy is how PII in dbt's tables gets masked.
* **dlt's**, a team's, or an `unknown` owner's tables can be *governed*: a spec
  that says who may see them — tags, grants, masks, a row filter, an owner —
  and nothing about their shape. stevin never claims, reshapes or drops such a
  table.
* Everything else is as it always was: stevin's to shape, or unmanaged.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from stevin.errors import StevinError

#: The owner labels with a meaning of their own. Any other label is a name for
#: whoever it is — "the data-science team" — and means "not stevin's to shape".
DBT = "dbt"
DLT = "dlt"
UNKNOWN = "unknown"

#: dlt keeps its own bookkeeping in two tables beside the ones it loads. A schema
#: with both is a dlt dataset. https://dlthub.com/docs/general-usage/destination-tables
DLT_TABLES = frozenset({"_dlt_loads", "_dlt_version"})

#: dbt nodes that become tables or views in the catalog. Sources are not here:
#: they are the tables dbt *reads*, which is exactly what stevin is for.
DBT_RELATIONS = frozenset({"model", "seed", "snapshot"})


class OwnedError(StevinError):
    """What says who owns what can't be read."""


@dataclass(frozen=True, slots=True)
class Owners:
    """Who owns which names, as far as the project's files say.

    `names` are exact full names, in lower case, from a dbt manifest. `patterns`
    are `catalog.schema.table` with `*` for any part, from `stevin.yml` — with a
    target's variables already substituted. An exact name wins over a pattern.
    What a dlt pipeline owns isn't here: that is read off the live schema
    (`is_dlt_schema`), because only the workspace can say it.
    """

    names: tuple[tuple[str, str], ...] = ()
    patterns: tuple[tuple[str, str], ...] = ()
    #: What was passed over while reading, said once rather than per node.
    notes: tuple[str, ...] = ()

    def owner_of(self, name: str) -> str | None:
        """The owner label for a full name, or None when nothing claims it."""
        lowered = name.lower()
        for exact, owner in self.names:
            if exact == lowered:
                return owner
        for pattern, owner in self.patterns:
            if matches(pattern, lowered):
                return owner
        return None

    def __bool__(self) -> bool:
        return bool(self.names or self.patterns)


def matches(pattern: str, name: str) -> bool:
    """Does a `catalog.schema.table` pattern cover this name? `*` is any one part;
    the rest is compared the way the catalog compares names, ignoring case."""
    parts = pattern.lower().split(".")
    wanted = name.lower().split(".")
    if len(parts) != len(wanted):
        return False
    return all(part in ("*", want) for part, want in zip(parts, wanted, strict=True))


def is_dlt_schema(table_names: Iterable[str]) -> bool:
    """Is a schema with these tables a dlt dataset? Both bookkeeping tables, by
    their short or full name. A heuristic: a schema someone copied `_dlt_loads`
    into would pass, and a dlt dataset whose bookkeeping was dropped would not."""
    short = {name.rsplit(".", 1)[-1].lower() for name in table_names}
    return short >= DLT_TABLES


def read_manifest(path: Path) -> Owners:
    """What dbt's `target/manifest.json` says dbt builds.

    Read leniently, like a bundle file: a manifest from another dbt version is
    read for what it has, and a node that can't be read is passed over and
    counted in `notes`. A manifest that isn't there, or isn't JSON, is an
    `OwnedError` naming the path — dbt hasn't run yet, or the path is wrong,
    and either way stevin can't say what is dbt's.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise OwnedError(
            f"the dbt manifest {path} can't be read ({error.strerror or error}) — "
            "run dbt first, or point `dbt: manifest:` at the one it wrote"
        ) from error
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        raise OwnedError(f"the dbt manifest {path} isn't JSON: {error}") from error
    nodes = document.get("nodes") if isinstance(document, dict) else None
    if not isinstance(nodes, dict):
        raise OwnedError(f"the dbt manifest {path} has no `nodes`; is it a manifest?")
    names: list[tuple[str, str]] = []
    passed_over = 0
    for node in nodes.values():
        if not isinstance(node, dict):
            passed_over += 1
            continue
        if node.get("resource_type") not in DBT_RELATIONS:
            continue
        config = node.get("config")
        materialized = config.get("materialized") if isinstance(config, dict) else None
        if materialized == "ephemeral":
            continue  # never a relation in the catalog
        database, schema = node.get("database"), node.get("schema")
        relation = node.get("alias") or node.get("name")
        if not all(
            isinstance(part, str) and part for part in (database, schema, relation)
        ):
            passed_over += 1
            continue
        names.append((f"{database}.{schema}.{relation}".lower(), DBT))
    notes = ()
    if passed_over:
        notes = (
            f"{passed_over} node{'s' if passed_over != 1 else ''} in {path.name} "
            "could not be read as a relation and were passed over",
        )
    return Owners(names=tuple(sorted(set(names))), notes=notes)


def combined(*owners: Owners) -> Owners:
    """Several sources as one, the first winning where they disagree."""
    return Owners(
        names=tuple(n for o in owners for n in o.names),
        patterns=tuple(p for o in owners for p in o.patterns),
        notes=tuple(n for o in owners for n in o.notes),
    )


def possessive(owner: str) -> str:
    """`dbt` → `dbt's`; `the data-science team` → `the data-science team's`."""
    return f"{owner}'s"


def dbt_refusal(name: str) -> str:
    return (
        f"{name} is dbt's: put grants and tags in dbt's config, and use a "
        "schema-level policy for masks"
    )


def shape_refusal(name: str, owner: str) -> str:
    return (
        f"{name} is {possessive(owner)}: leave the columns' types out to govern it "
        "(tags, grants, masks, a row filter), or take it out of owned_elsewhere"
    )


def unowned_refusal(name: str) -> str:
    return (
        f"{name} has no columns' types, so it governs a table another tool makes — "
        "but nothing says whose it is: say the columns, or name the owner in "
        "owned_elsewhere"
    )

"""`stevin access`: who may see a table, and through what.

A reviewer asking that of a Unity Catalog table has three places to look — the
grants on the table and on its parents, the row filter and masks it carries,
and the ABAC policies defined somewhere above it. This reads the three for one
table and hands them back as one `Access`. It writes nothing.

`manage:` holds here as it does for a plan. A project that hands grants or
policies to another tool has said the workspace isn't asked about them
(docs/spec.md, What stevin manages), and a report is no exception: it reads the
rest, and says which of the two it did not read.
"""

from __future__ import annotations

from stevin.errors import StevinError
from stevin.introspect import Introspector
from stevin.model.access import Access


class AccessError(StevinError):
    """The table can't be reported on — it isn't there, or isn't a table — or a
    saved report can't be read back."""


def read(introspector: Introspector, name: str) -> Access:
    """What is granted on `catalog.schema.table`, what narrows a read, the owner.

    Raises `AccessError` for a name that isn't a table here, and
    `IntrospectionError` if the workspace can't be read.
    """
    parts = name.split(".")
    if len(parts) != 3 or not all(parts):
        raise AccessError(f"a table is named catalog.schema.table, not {name!r}")
    # Unity Catalog keeps names in lower case, and `information_schema` is
    # asked by literal.
    name = name.lower()
    catalog, schema, _ = name.split(".")
    found = introspector.schema(catalog, schema, full=[name])
    if not found.exists:
        raise AccessError(f"there is no schema {catalog}.{schema}, so no table {name}")
    live = found.get(name)
    if live is None:
        if found.get_view(name) is not None:
            raise AccessError(f"{name} is a view; `stevin access` reads tables")
        other = dict(found.skipped).get(name)
        if other is not None:
            raise AccessError(f"{name} is a {other}; `stevin access` reads Delta tables")
        raise AccessError(f"there is no table {name}")
    asked = introspector.manage.manages("policies")
    grants_asked = introspector.manage.manages("grants")
    return Access(
        table=name,
        owner=live.table.owner,
        grants=introspector.privileges(name),
        grants_asked=grants_asked,
        row_filter=live.table.row_filter,
        masks=tuple((c.name, c.mask) for c in live.table.columns if c.mask is not None),
        policies=live.policies,
        policies_asked=asked,
        policies_unread=live.policies_unread if asked else None,
    )

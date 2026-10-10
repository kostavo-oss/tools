"""`stevin access`: who may see a table, and through what.

A reviewer asking that of a Unity Catalog table has three places to look — the
grants on the table and on its parents, the row filter and masks it carries,
and the ABAC policies defined somewhere above it. This reads the three for one
table and hands them back as one `Access`. It writes nothing.

`manage:` doesn't reach it. That line says what a project hands to another
tool, so stevin doesn't plan or change it. This changes nothing, and a team
whose grants live in Terraform is exactly who needs to see them: grants and
policies are read whatever the project manages (`api.access` reads with
everything managed).
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
    return Access(
        table=name,
        owner=live.table.owner,
        grants=introspector.privileges(name),
        row_filter=live.table.row_filter,
        masks=tuple((c.name, c.mask) for c in live.table.columns if c.mask is not None),
        policies=live.policies,
        policies_unread=live.policies_unread,
    )

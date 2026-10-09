"""Authorization rules — a domain service.

The "what can this principal do" logic that used to live on the cache. It's a
business rule about scopes + ACLs + identity, so it belongs in the domain.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .models import Acl, Identity, Scope

_PERM_RANK = {"READ": 1, "WRITE": 2, "MANAGE": 3}


def perm_rank(permission: str) -> int:
    return _PERM_RANK.get(permission, 0)


@dataclass
class AuthSummary:
    """What the person may do in one scope: what the page shows as their access."""

    scope: str
    effective: str = "—"  # current user's effective permission


def authorization_summary(
    identity: Identity,
    scopes: list[Scope],
    acls_by_scope: Mapping[str, list[Acl]],
    readable: set[str] | None = None,
) -> list[AuthSummary]:
    """Compute the current user's effective permission on each scope.

    "Effective" is the highest permission granted to any principal that is *you*:
    your username, the `users` group (everyone), or any group you belong to — so
    group-based access (the common case) counts, not just direct user ACLs.

    `readable` is the set of scopes whose secrets we could actually list. Listing
    a scope's ACLs needs MANAGE, so for a scope where you only hold READ/WRITE the
    ACLs come back empty and no grant looks like *yours* — yet you clearly have
    access. So we floor the effective permission to READ for any readable scope
    with no visible self-grant, rather than reporting "none".
    """
    readable = readable or set()
    mine = {identity.user_name, "users"} | set(identity.groups)
    summaries: list[AuthSummary] = []
    for scope in scopes:
        acls = acls_by_scope.get(scope.name, [])
        effective = "—"
        best = 0
        for acl in acls:
            if acl.principal in mine and perm_rank(acl.permission) > best:
                best = perm_rank(acl.permission)
                effective = acl.permission
        if best == 0 and scope.name in readable:
            effective = "READ"
        summaries.append(AuthSummary(scope=scope.name, effective=effective))
    return summaries

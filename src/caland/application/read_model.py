"""WorkspaceCache — the in-memory read model the UI renders from.

A projection that the application service warms up front (US-14) and keeps in
sync on writes. Pure data + bookkeeping; it holds no business rules (those live
in the domain) and does no I/O.

Strategy (US-14/16):
  * On connect the service warms scopes -> secret metadata -> ACLs in the
    background.
  * Secret *values* are NOT bulk-loaded: one is read when it is asked for, and
    read again every time it is. What was read or written is held here until it
    is forgotten, and nothing is answered from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import Acl, Identity, Scope, Secret


@dataclass
class WorkspaceCache:
    label: str
    identity: Identity = field(default_factory=Identity)

    scopes: list[Scope] = field(default_factory=list)
    secrets: dict[str, list[Secret]] = field(default_factory=dict)
    acls: dict[str, list[Acl]] = field(default_factory=dict)
    # values as they are stored — bytes — by scope and key
    raw: dict[tuple[str, str], bytes] = field(default_factory=dict)
    # scopes whose secrets we could list ⇒ the user holds at least READ on them
    readable: set[str] = field(default_factory=set)

    # -- lookups ------------------------------------------------------------
    def secrets_for(self, scope: str) -> list[Secret]:
        return self.secrets.get(scope, [])

    def acls_for(self, scope: str) -> list[Acl]:
        return self.acls.get(scope, [])

    # -- mutation keeping the read model + UI consistent --------------------
    def upsert_secret(self, secret: Secret) -> None:
        rows = self.secrets.setdefault(secret.scope, [])
        for i, existing in enumerate(rows):
            if existing.key == secret.key:
                rows[i] = secret
                break
        else:
            rows.append(secret)
        rows.sort(key=lambda s: s.key.lower())

    def remove_secret(self, scope: str, key: str) -> None:
        self.secrets[scope] = [s for s in self.secrets.get(scope, []) if s.key != key]
        self.raw.pop((scope, key), None)

    def add_scope(self, scope: Scope) -> None:
        if not any(s.name == scope.name for s in self.scopes):
            self.scopes.append(scope)
            self.scopes.sort(key=lambda s: s.name.lower())
        self.secrets.setdefault(scope.name, [])
        self.acls.setdefault(scope.name, [])

    def remove_scope(self, name: str) -> None:
        self.scopes = [s for s in self.scopes if s.name != name]
        self.secrets.pop(name, None)
        self.acls.pop(name, None)
        self.readable.discard(name)
        self.forget_scope(name)

    def forget_scope(self, name: str) -> None:
        """Let go of the values held of one scope — in place, each by its own
        key. Scopes are read eight at a time while values are read and written:
        made anew from what was held a moment before, what is held would lose
        whatever came in between."""
        for key in [key for key in list(self.raw) if key[0] == name]:
            self.raw.pop(key, None)

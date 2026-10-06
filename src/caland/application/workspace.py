"""WorkspaceService — the application service / use-case layer.

Orchestrates a `SecretStore` (domain port) and the read model, exposing every
operation the UI needs as a plain, synchronous method. All store/cache
coordination lives here, so:

  * the UI just calls a method and renders the result (no business logic), and
  * the whole layer is unit-testable with a fake store and no event loop.

The UI runs these (blocking) methods in worker threads.
"""

from __future__ import annotations

from collections.abc import Iterator

from ..domain import (
    Acl,
    AuthSummary,
    Identity,
    Scope,
    Secret,
    SecretStore,
    StoreError,
    authorization_summary,
)
from .read_model import WorkspaceCache


class WorkspaceService:
    def __init__(
        self, store: SecretStore, label: str, cache: WorkspaceCache | None = None
    ) -> None:
        self._store = store
        # The read model is injectable (decoupled), defaulting to a fresh one.
        self.cache = cache or WorkspaceCache(label=label)
        # the one secret that can be put back: where it was, and what it held
        self._taken: tuple[str, str, bytes] | None = None

    @property
    def label(self) -> str:
        return self.cache.label

    @property
    def identity(self) -> Identity:
        return self.cache.identity

    @property
    def scopes(self) -> list[Scope]:
        return self.cache.scopes

    # -- connection / warming -------------------------------------------
    def authenticate(self) -> Identity:
        identity = self._store.whoami()
        self.cache.identity = identity
        return identity

    def load_scopes(self) -> list[Scope]:
        scopes = self._store.list_scopes()
        self.cache.scopes = scopes
        self.cache.scopes_loaded = True
        return scopes

    def warm_scope(self, scope: str) -> None:
        """Pull secret metadata + ACLs for one scope into the read model.

        The two reads are gated by different permissions (list_secrets needs
        READ, list_acls needs MANAGE), so they're tried independently: succeeding
        at list_secrets is what marks a scope readable — i.e. one the user can
        actually see — even when its ACLs are off-limits.
        """
        try:
            self.cache.secrets[scope] = self._store.list_secrets(scope)
            self.cache.readable.add(scope)
        except StoreError:
            self.cache.secrets.setdefault(scope, [])
            self.cache.readable.discard(scope)
        try:
            self.cache.acls[scope] = self._store.list_acls(scope)
        except StoreError:
            self.cache.acls.setdefault(scope, [])

    def warm_all(self) -> Iterator[tuple[int, int, Scope]]:
        """Warm every scope, yielding (index, total, scope) for progress."""
        total = len(self.cache.scopes)
        for i, scope in enumerate(self.cache.scopes, 1):
            self.warm_scope(scope.name)
            yield i, total, scope

    # -- reads ----------------------------------------------------------
    def secrets_for(self, scope: str) -> list[Secret]:
        return self.cache.secrets_for(scope)

    def acls_for(self, scope: str) -> list[Acl]:
        return self.cache.acls_for(scope)

    def is_readable(self, scope: str) -> bool:
        """Whether the user can list this scope's secrets (holds ≥ READ)."""
        return scope in self.cache.readable

    def scope(self, name: str) -> Scope | None:
        return next((s for s in self.cache.scopes if s.name == name), None)

    def secret(self, scope: str, key: str) -> Secret | None:
        return next((s for s in self.cache.secrets_for(scope) if s.key == key), None)

    def all_secrets(self) -> list[Secret]:
        """Every warmed secret across all scopes (the global-search projection)."""
        return [
            s for scope in self.cache.scopes for s in self.cache.secrets_for(scope.name)
        ]

    def acl_entries(self) -> list[tuple[str, Acl]]:
        """Every (scope, acl) pair in the workspace (the principal-lookup view)."""
        return [
            (scope.name, a)
            for scope in self.cache.scopes
            for a in self.cache.acls_for(scope.name)
        ]

    def cached_value(self, scope: str, key: str) -> str | None:
        return self.cache.cached_value(scope, key)

    def forget_values(self) -> None:
        """Purge every cached secret value; reveal will re-fetch on demand."""
        self.cache.values.clear()
        self.cache.raw.clear()
        self._taken = None

    def reveal(self, scope: str, key: str) -> str:
        """Return the secret value, fetching+caching it on first access."""
        cached = self.cache.cached_value(scope, key)
        if cached is not None:
            return cached
        value = self._store.get_secret_value(scope, key)
        self.cache.set_value(scope, key, value)
        return value

    # -- mutations ------------------------------------------------------
    def put_secret(self, scope: str, key: str, value: str) -> None:
        self._store.put_secret(scope, key, value)
        try:  # refresh metadata so the timestamp is accurate
            self.cache.secrets[scope] = self._store.list_secrets(scope)
        except StoreError:
            self.cache.upsert_secret(Secret(scope=scope, key=key))
        self.cache.set_value(scope, key, value)

    def delete_secret(self, scope: str, key: str) -> None:
        self._store.delete_secret(scope, key)
        self.cache.remove_secret(scope, key)

    def create_scope(self, name: str) -> None:
        self._store.create_scope(name)
        self.cache.add_scope(Scope(name=name))
        self.cache.readable.add(name)  # you just made it — you can read it

    def delete_scope(self, name: str) -> None:
        self._store.delete_scope(name)
        self.cache.remove_scope(name)

    def refresh_scope(self, scope: str) -> None:
        self.warm_scope(scope)

    # -- values as they are: bytes ---------------------------------------
    # What the page works with. A value is carried as the bytes it is stored
    # as, so that a file that is no text goes in, moves and comes back whole.
    def reveal_bytes(self, scope: str, key: str) -> bytes:
        """The value as stored, read once and kept for the session."""
        held = self.cache.raw.get((scope, key))
        if held is not None:
            return held
        value = self._store.get_secret_bytes(scope, key)
        self.cache.raw[(scope, key)] = value
        return value

    def put_secret_bytes(self, scope: str, key: str, value: bytes) -> None:
        self._store.put_secret_bytes(scope, key, value)
        try:  # refresh metadata so the timestamp is accurate
            self.cache.secrets[scope] = self._store.list_secrets(scope)
        except StoreError:
            self.cache.upsert_secret(Secret(scope=scope, key=key))
        self.cache.raw[(scope, key)] = value
        self.cache.values.pop((scope, key), None)  # the text of it is no longer this

    def move_secret(
        self, scope: str, key: str, to_scope: str, to_key: str, *, keep: bool = False
    ) -> None:
        """Move, rename or — with `keep` — copy a secret, in the safe order: read,
        write at the new place, and only then remove the old. A failure halfway
        leaves the secret in two places and never in none."""
        value = self.reveal_bytes(scope, key)
        self.put_secret_bytes(to_scope, to_key, value)
        if not keep:
            self.delete_secret(scope, key)
            self._taken = (scope, key, value)

    def delete_secret_kept(self, scope: str, key: str) -> bool:
        """Delete a secret, keeping what it held so that it can be put back.
        False when its value could not be read first: then it is gone for good."""
        try:
            value: bytes | None = self.reveal_bytes(scope, key)
        except StoreError:
            value = None
        self.delete_secret(scope, key)
        if value is not None:
            self._taken = (scope, key, value)
        return value is not None

    @property
    def taken(self) -> tuple[str, str] | None:
        """The secret that can be put back, as (scope, key)."""
        return self._taken[:2] if self._taken else None

    def put_back(self) -> tuple[str, str]:
        """Put back the secret last deleted or moved away. One deep."""
        if self._taken is None:
            raise StoreError("Nothing to put back.")
        scope, key, value = self._taken
        if self.scope(scope) is None:
            self._taken = None
            raise StoreError(f"Cannot put it back: scope “{scope}” is gone.")
        self.put_secret_bytes(scope, key, value)
        self._taken = None
        return scope, key

    # -- scope permissions / ACLs (US-11 update, US-12) -----------------
    def set_acl(self, scope: str, principal: str, permission: str) -> None:
        """Grant or change a principal's permission (put_acl is an upsert)."""
        self._store.put_acl(scope, principal, permission)
        self.cache.acls[scope] = self._store.list_acls(scope)

    def remove_acl(self, scope: str, principal: str) -> None:
        self._store.delete_acl(scope, principal)
        self.cache.acls[scope] = self._store.list_acls(scope)

    # -- authorization overview ----------------------------------------
    def auth_summary(self) -> list[AuthSummary]:
        return authorization_summary(
            self.cache.identity,
            self.cache.scopes,
            self.cache.acls,
            self.cache.readable,
        )

"""WorkspaceService — the application service / use-case layer.

Orchestrates a `SecretStore` (domain port) and the read model, exposing every
operation the UI needs as a plain, synchronous method. All store/cache
coordination lives here, so:

  * the UI just calls a method and renders the result (no business logic), and
  * the whole layer is unit-testable with a fake store and no event loop.

The UI runs these (blocking) methods in worker threads.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

from ..domain import (
    Acl,
    AuthSummary,
    Exists,
    Identity,
    Scope,
    Secret,
    SecretStore,
    StoreError,
    authorization_summary,
    same_name,
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
        # one change at a time. Two at once — a delete and a put-back, two moves —
        # could each leave the other's work undone, and a value with it.
        self._one_at_a_time = threading.RLock()
        #: Why the last import stopped, when it did.
        self.import_error = ""

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
        # what was read of it before is not what is there now
        self.cache.values = {k: v for k, v in self.cache.values.items() if k[0] != scope}
        self.cache.raw = {k: v for k, v in self.cache.raw.items() if k[0] != scope}
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
        with self._one_at_a_time:
            self._store.delete_secret(scope, key)
            self.cache.remove_secret(scope, key)

    def create_scope(self, name: str) -> None:
        with self._one_at_a_time:
            self._store.create_scope(name)
            self.cache.add_scope(Scope(name=name))
            self.cache.readable.add(name)  # you just made it — you can read it

    def delete_scope(self, name: str) -> None:
        with self._one_at_a_time:
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
        with self._one_at_a_time:
            self._store.put_secret_bytes(scope, key, value)
            try:  # refresh metadata so the timestamp is accurate
                self.cache.secrets[scope] = self._store.list_secrets(scope)
            except StoreError:
                self.cache.upsert_secret(Secret(scope=scope, key=key))
            self.cache.raw[(scope, key)] = value
            self.cache.values.pop((scope, key), None)  # its text is no longer this

    def create_secret_bytes(self, scope: str, key: str, value: bytes) -> None:
        """Put a secret that is not there yet. Raises `Exists` when one is."""
        with self._one_at_a_time:
            self._must_be_free(scope, key)
            self.put_secret_bytes(scope, key, value)

    def move_secret(
        self, scope: str, key: str, to_scope: str, to_key: str, *, keep: bool = False
    ) -> None:
        """Move, rename or — with `keep` — copy a secret, in the safe order: read,
        write at the new place, and only then remove the old. A failure halfway
        leaves the secret in two places and never in none.

        The value is read now, not taken from what was read earlier: a secret
        that was changed since must not be moved as it used to be. Raises
        `Exists` when the new place is taken — and when it *is* the old place
        but for the case of its name, which to Databricks is the same secret:
        writing it and then removing "the old" would remove it altogether."""
        with self._one_at_a_time:
            if same_name(scope, to_scope) and same_name(key, to_key):
                raise Exists(
                    "That is where it is: Databricks does not tell names apart by case."
                )
            self._must_be_free(to_scope, to_key)
            value = self._read_now(scope, key)
            self.put_secret_bytes(to_scope, to_key, value)
            if not keep:
                self.delete_secret(scope, key)
                self._taken = (scope, key, value)

    def delete_secret_kept(self, scope: str, key: str) -> bool:
        """Delete a secret, keeping what it held so that it can be put back.
        False when its value could not be read first: then it is gone for good."""
        with self._one_at_a_time:
            try:
                value: bytes | None = self._read_now(scope, key)
            except StoreError:
                value = None
            self.delete_secret(scope, key)
            if value is not None:
                self._taken = (scope, key, value)
            return value is not None

    def import_secrets(self, scope: str, pairs: dict[str, str]) -> tuple[list[str], str]:
        """Put every pair into a scope as a secret, in order, stopping at the
        first the workspace refuses. Returns the keys that went in and, when it
        stopped, the key it stopped at ("" otherwise) — raising nothing, so that
        who asked can say how far it got. An overwritten secret cannot be put
        back: this is not a delete."""
        done: list[str] = []
        with self._one_at_a_time:
            for key, value in pairs.items():
                try:
                    self.put_secret_bytes(scope, key, value.encode("utf-8"))
                except StoreError as exc:
                    self.import_error = str(exc)
                    return done, key
                done.append(key)
        self.import_error = ""
        return done, ""

    def export_secrets(self, scope: str) -> tuple[list[tuple[str, str]], list[str]]:
        """Every secret of a scope that is text, as (key, value) — and the keys
        of those that are not, which a line of text cannot carry. Reads every
        value: asked for, never done unasked."""
        pairs: list[tuple[str, str]] = []
        left_out: list[str] = []
        for secret in self.secrets_for(scope):
            data = self.reveal_bytes(scope, secret.key)
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                left_out.append(secret.key)
                continue
            if "\x00" in text:
                left_out.append(secret.key)
            else:
                pairs.append((secret.key, text))
        return pairs, left_out

    def taken_over(self, scope: str, keys: list[str]) -> list[str]:
        """Which of these keys are in the scope already — as the workspace says
        now, and whatever their case — under the names they have there."""
        self.cache.secrets[scope] = self._store.list_secrets(scope)
        there = {
            secret.key.casefold(): secret.key for secret in self.cache.secrets[scope]
        }
        return [there[key.casefold()] for key in keys if key.casefold() in there]

    @property
    def taken(self) -> tuple[str, str] | None:
        """The secret that can be put back, as (scope, key)."""
        taken = self._taken
        return taken[:2] if taken else None

    def put_back(self) -> tuple[str, str]:
        """Put back the secret last deleted or moved away. One deep.

        What is held is let go of only once it is back: when it cannot be put
        back now — its scope is gone, or is Azure's, or a secret of that name is
        there again — it is kept, for when it can."""
        with self._one_at_a_time:
            if self._taken is None:
                raise StoreError("There is nothing to put back.")
            scope, key, value = self._taken
            found = self.scope(scope)
            if found is None:
                raise StoreError(f"It cannot be put back: scope “{scope}” is gone.")
            if found.is_keyvault:
                raise StoreError(
                    f"It cannot be put back: “{scope}” is Azure Key Vault's."
                )
            self._must_be_free(scope, key, "putting the old one back would overwrite it")
            self.put_secret_bytes(scope, key, value)
            self._taken = None
            return scope, key

    def _read_now(self, scope: str, key: str) -> bytes:
        """The value as it is stored at this moment."""
        value = self._store.get_secret_bytes(scope, key)
        self.cache.raw[(scope, key)] = value
        return value

    def _must_be_free(self, scope: str, key: str, why: str = "") -> None:
        """Raise `Exists` when a secret of this name is in the scope — as the
        workspace says now, and whatever the case of the name."""
        self.cache.secrets[scope] = self._store.list_secrets(scope)
        for secret in self.cache.secrets[scope]:
            if same_name(secret.key, key):
                raise Exists(
                    f"There is a “{secret.key}” in “{scope}” already"
                    + (f": {why}." if why else ".")
                )

    # -- scope permissions / ACLs (US-11 update, US-12) -----------------
    def set_acl(self, scope: str, principal: str, permission: str) -> None:
        """Grant or change a principal's permission (put_acl is an upsert)."""
        with self._one_at_a_time:
            self._store.put_acl(scope, principal, permission)
            self.cache.acls[scope] = self._store.list_acls(scope)

    def remove_acl(self, scope: str, principal: str) -> None:
        with self._one_at_a_time:
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

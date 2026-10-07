"""In-memory test doubles for the domain ports — faithful stand-ins for
Databricks. They implement the `SecretStore`, `WorkspaceConnector`, and
`ProfileStore` protocols so the whole stack above infrastructure is testable
without a network.
"""

from __future__ import annotations

from caland.application import OnboardingService
from caland.domain import Acl, Identity, Scope, Secret
from caland.domain.errors import StoreError


class FakeSecretStore:
    def __init__(
        self,
        *,
        profile: str | None = "fake",
        scopes: list[Scope] | None = None,
        secrets: dict[str, list[Secret]] | None = None,
        acls: dict[str, list[Acl]] | None = None,
        values: dict[tuple[str, str], str | bytes] | None = None,
        identity: Identity | None = None,
        fail_on: set[str] | None = None,
        no_read: set[str] | None = None,
    ) -> None:
        self.profile = profile
        self._scopes = scopes or []
        self._secrets = secrets or {}
        self._acls = acls or {}
        self._values = values or {}
        self._identity = identity or Identity("me@corp.com", "Me", authenticated=True)
        self._fail_on = fail_on or set()
        # scopes listed by list_scopes but whose secrets/ACLs the user can't read
        # (models Databricks returning all scopes but denying per-scope access)
        self._no_read = no_read or set()
        self.calls: list[tuple] = []

    def _record(self, *call) -> None:
        self.calls.append(call)
        if call[0] in self._fail_on:
            raise StoreError(f"boom:{call[0]}")

    def _as_kept(self, scope: str, key: str) -> str:
        """The name a secret is kept under: Databricks keeps the case it was
        first given, and takes any other case for the same secret."""
        for secret in self._secrets.get(scope, []):
            if secret.key.casefold() == key.casefold():
                return secret.key
        return key

    def count(self, name: str) -> int:
        return sum(1 for c in self.calls if c[0] == name)

    def reads(self) -> int:
        """How many times a value was read."""
        return self.count("get_secret_bytes")

    # -- Gateway protocol ----------------------------------------------
    def whoami(self) -> Identity:
        self.calls.append(("whoami",))
        return self._identity

    def list_scopes(self) -> list[Scope]:
        self._record("list_scopes")
        # mirror DatabricksSecretStore's observable contract: sorted results
        return sorted(self._scopes, key=lambda s: s.name.lower())

    def create_scope(self, name: str) -> None:
        self._record("create_scope", name)
        self._scopes.append(Scope(name=name))
        self._secrets.setdefault(name, [])
        self._acls.setdefault(name, [])

    def delete_scope(self, name: str) -> None:
        self._record("delete_scope", name)
        self._scopes = [s for s in self._scopes if s.name != name]
        self._secrets.pop(name, None)

    def list_secrets(self, scope: str) -> list[Secret]:
        self._record("list_secrets", scope)
        if scope in self._no_read:
            raise StoreError(f"permission denied: {scope}")
        return sorted(self._secrets.get(scope, []), key=lambda s: s.key.lower())

    def get_secret_bytes(self, scope: str, key: str) -> bytes:
        self._record("get_secret_bytes", scope, key)
        key = self._as_kept(scope, key)
        held = self._values.get((scope, key), f"value::{scope}/{key}")
        return held if isinstance(held, bytes) else held.encode()

    def put_secret_bytes(self, scope: str, key: str, value: bytes) -> None:
        self._record("put_secret_bytes", scope, key, value)
        key = self._as_kept(scope, key)
        self._values[(scope, key)] = value
        rows = self._secrets.setdefault(scope, [])
        if not any(s.key == key for s in rows):
            rows.append(Secret(scope=scope, key=key))

    def delete_secret(self, scope: str, key: str) -> None:
        self._record("delete_secret", scope, key)
        key = self._as_kept(scope, key)
        self._secrets[scope] = [s for s in self._secrets.get(scope, []) if s.key != key]
        self._values.pop((scope, key), None)

    def list_acls(self, scope: str) -> list[Acl]:
        self._record("list_acls", scope)
        if scope in self._no_read:
            raise StoreError(f"permission denied: {scope}")
        return sorted(self._acls.get(scope, []), key=lambda a: a.principal.lower())

    def put_acl(self, scope: str, principal: str, permission: str) -> None:
        self._record("put_acl", scope, principal, permission)
        rows = [a for a in self._acls.get(scope, []) if a.principal != principal]
        rows.append(Acl(principal=principal, permission=permission))
        self._acls[scope] = rows

    def delete_acl(self, scope: str, principal: str) -> None:
        self._record("delete_acl", scope, principal)
        self._acls[scope] = [
            a for a in self._acls.get(scope, []) if a.principal != principal
        ]


def seeded_store() -> FakeSecretStore:
    """A standard two-scope dataset used across UI/session tests."""
    return FakeSecretStore(
        scopes=[Scope("prod", "DATABRICKS"), Scope("kv", "AZURE_KEYVAULT")],
        secrets={
            "prod": [
                Secret("prod", "api-key", 1_718_000_000_000),
                Secret("prod", "db-password", 1_718_500_000_000),
            ],
            "kv": [Secret("kv", "tenant-id", 1_717_000_000_000)],
        },
        acls={
            "prod": [Acl("me@corp.com", "MANAGE"), Acl("users", "READ")],
            "kv": [Acl("users", "READ")],
        },
    )


class StubProfiles:
    """A `ProfileStore` that holds profiles in memory."""

    def __init__(self, workspaces=None) -> None:
        self._workspaces = list(workspaces or [])
        self.saved: list[tuple] = []
        #: Profiles the file has that are no workspace to offer.
        self.others: list[str] = []

    def discover(self):
        return list(self._workspaces)

    def names(self):
        """Every profile there is: those offered, those kept since, and — as the
        real file has — any that are no workspace to offer (`self.others`)."""
        offered = [w.profile for w in self._workspaces if w.profile]
        return ["DEFAULT", *offered, *self.others, *[name for name, _, _ in self.saved]]

    def add(self, name, host) -> None:
        from caland.domain import Exists

        if any(name.casefold() == other.casefold() for other in self.names()):
            raise Exists(f"There is a profile “{name}” already.")
        self.saved.append((name, host, None))


class StubConnector:
    """A `WorkspaceConnector` that refuses to connect (login needs a network)."""

    def connect_profile(self, profile):
        raise NotImplementedError

    def connect_url(self, host):
        raise NotImplementedError


class ConnectingStubConnector:
    """A `WorkspaceConnector` that 'connects' any profile to a seeded fake store."""

    def __init__(self, store=None):
        self.store = store or seeded_store()

    def connect_profile(self, profile):
        from caland.domain import Connected

        return Connected(store=self.store, label=profile)

    def connect_url(self, host):
        from caland.domain import Connected

        return Connected(store=self.store, label=host, host=host)


class StubBundle:
    """A `BundleStore` that returns a preset bundle workspace (or none)."""

    def __init__(self, workspace=None) -> None:
        self._workspace = workspace

    def discover(self):
        return self._workspace


def stub_onboarding(profiles=None, bundle=None) -> OnboardingService:
    """An OnboardingService wired to stubs — listed workspaces, no live connect."""
    return OnboardingService(StubConnector(), StubProfiles(profiles), StubBundle(bundle))

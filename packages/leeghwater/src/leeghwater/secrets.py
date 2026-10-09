"""dlt's secrets, from Databricks secret scopes. `spec/003`.

Two config providers for dlt. Both are registered after dlt's own, so an environment
variable wins, then a `secrets.toml`, then these:
https://dlthub.com/docs/general-usage/credentials/setup#available-config-providers

This module imports dlt. On Databricks, import it after `leeghwater.prepare()`.
"""

import threading
from collections.abc import Mapping, Sequence
from typing import Any

from dlt.common.configuration.providers.provider import ConfigProvider, get_key_name
from dlt.common.configuration.providers.vault import VaultDocProvider, normalize_key
from dlt.common.configuration.specs.base_configuration import is_secret_hint

from leeghwater import _dlt
from leeghwater._errors import LeeghwaterError


def _default_client() -> Any:
    # The SDK's default sign-in: a profile on a laptop, the run's own identity on
    # Databricks. leeghwater reads no token and passes none. `spec/002`, R6.
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


class Scopes:
    """Secret scopes, read through the Databricks SDK. The client is made on first use."""

    def __init__(self, client: Any | None) -> None:
        self._client = client
        self._lock = threading.Lock()

    @property
    def client(self) -> Any:
        with self._lock:
            if self._client is None:
                self._client = _default_client()
            return self._client

    def names(self, scope: str) -> set[str]:
        """The names of the secrets in a scope. No values: a list never returns them."""
        from databricks.sdk.errors import NotFound, PermissionDenied

        try:
            return {secret.key for secret in self.client.secrets.list_secrets(scope)}
        except NotFound as error:
            raise LeeghwaterError(
                f"The secret scope '{scope}' does not exist in this workspace, so none of"
                " its secrets can be found. Check the scope's name where the run names it"
                " (--secret-scope, or the app's secret_scopes), or make it:"
                f" `databricks secrets create-scope {scope}`."
            ) from error
        except PermissionDenied as error:
            try:
                who = self.identity()
            except Exception:
                who = "this identity"
            raise LeeghwaterError(
                f"The secret scope '{scope}' can't be listed by {who}."
                " It needs READ on the scope:"
                f" `databricks secrets put-acl {scope} <principal> READ`."
            ) from error

    def read(self, scope: str, key: str) -> str | None:
        """One secret's value, or None when it isn't there for this identity."""
        from databricks.sdk.errors import NotFound, PermissionDenied

        # Through the client's dbutils, not its secrets API. Off Databricks they are the
        # same call. On Databricks this is the runtime's own dbutils, and a value read
        # through it is redacted wherever the run's output would show it; one read
        # through the API is printed as it is. Both were tried in a serverless wheel
        # task on 2026-10-07.
        # https://docs.databricks.com/aws/en/security/secrets/secrets-redaction
        try:
            value = self.client.dbutils.secrets.get(scope, key)
        except (NotFound, PermissionDenied):
            # dlt asks for many keys that don't exist, on purpose: "not here" is an
            # answer, and dlt looks on. Anything else is raised as it came.
            return None
        return value or None

    def identity(self) -> str:
        return str(self.client.current_user.me().user_name)


class DatabricksSecretsProvider(VaultDocProvider):
    """A dlt config provider that reads one Databricks secret scope.

    A secret is found by the path dlt has for it, joined with `-`: what dlt asks for as
    `sources.github.access_token` is the secret `sources-github-access_token`. A secret
    named `dlt_secrets_toml`, `sources`, `sources-<name>`, `destination` or
    `destination-<name>` is read as a piece of `secrets.toml`.

    The scope is listed once, on first use, and only what is there is fetched. Only values
    a source marks as secret are looked up.
    """

    def __init__(self, scope: str, *, workspace_client: Any | None = None):
        scope = (scope or "").strip()
        if not scope:
            raise LeeghwaterError("A secret scope needs a name; an empty one was given.")
        self.scope = scope
        self._reader = Scopes(workspace_client)
        # `VaultDocProvider` is not promised to stay as it is: it is why pyproject.toml
        # caps dlt below 2. With `list_secrets` the names are known up front, so single
        # values are looked up as well as fragments (`only_toml_fragments=False`).
        super().__init__(only_secrets=False, only_toml_fragments=False, list_secrets=True)
        # Set after the call: dlt warns when listing is combined with `only_secrets`,
        # about lookups that are skipped. Skipping what isn't a secret is what is wanted.
        self.only_secrets = True

    @staticmethod
    def get_key_name(key: str, *sections: str) -> str:
        """The name of a secret in the scope: the path, joined with `-`.

        The same as dlt's Google provider, `dlt/common/configuration/providers/
        google_secrets.py`: punctuation other than `-` and `_` is taken out of each part.
        """
        parts = [normalize_key(section) for section in sections if section]
        return get_key_name(normalize_key(key), "-", *parts)

    @property
    def name(self) -> str:
        return f"Databricks secret scope '{self.scope}'"

    @property
    def supports_sections(self) -> bool:
        return True

    @property
    def locations(self) -> Sequence[str]:
        return [f"secret scope {self.scope}"]

    def _list_vault(self) -> set[str]:
        return self._reader.names(self.scope)

    def _look_vault(self, full_key: str, hint: type) -> str | None:
        return self._reader.read(self.scope, full_key)


class PointedSecretsProvider(ConfigProvider):
    """Secrets that exist under another name, pointed at as `scope/key`.

    `{"sources.github.access_token": "platform-shared/github-token"}` answers dlt's
    question for `sources.github.access_token` with the secret `github-token` in the scope
    `platform-shared`. `spec/003`, R7.
    """

    NAME = "Databricks secrets, pointed at"

    def __init__(
        self,
        pointers: Mapping[str, str],
        *,
        workspace_client: Any | None = None,
    ) -> None:
        self.point_at(pointers, workspace_client=workspace_client)

    def point_at(
        self, pointers: Mapping[str, str], *, workspace_client: Any | None = None
    ) -> None:
        """Replace what is pointed at, and forget what was read."""
        self._pointers = {
            path: split_pointer(path, ref) for path, ref in pointers.items()
        }
        self._reader = Scopes(workspace_client)
        self._values: dict[str, str | None] = {}
        self._names: dict[str, set[str]] = {}

    @property
    def paths(self) -> list[str]:
        return sorted(self._pointers)

    def get_value(
        self, key: str, hint: type[Any], pipeline_name: str | None, *sections: str
    ) -> tuple[Any | None, str]:
        path = ".".join((*sections, key))
        if path not in self._pointers or not is_secret_hint(hint):
            return None, path
        if path not in self._values:
            scope, name = self._pointers[path]
            # Listed first: a pointer at nothing is a mistake to name, not a secret that
            # may be somewhere else. A missing scope is named by the listing itself.
            if scope not in self._names:
                self._names[scope] = self._reader.names(scope)
            if name not in self._names[scope]:
                there = ", ".join(sorted(self._names[scope])) or "none"
                raise LeeghwaterError(
                    f"'{path}' is pointed at {scope}/{name}, and the scope '{scope}' has"
                    f" no secret '{name}'. It has: {there}."
                )
            self._values[path] = self._reader.read(scope, name)
        return self._values[path], path

    @property
    def supports_secrets(self) -> bool:
        return True

    @property
    def supports_sections(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return self.NAME

    @property
    def locations(self) -> Sequence[str]:
        return [f"secret {scope}/{name}" for scope, name in self._pointers.values()]


def split_pointer(path: str, ref: str) -> tuple[str, str]:
    """Split `scope/key` at the first `/`."""
    scope, _, key = (ref or "").partition("/")
    if not path.strip() or not scope.strip() or not key:
        raise LeeghwaterError(
            f"A secret is pointed at as <dlt's name>=<scope>/<key>; got '{path}={ref}'."
            " For example: sources.github.access_token=platform-shared/github-token"
        )
    return scope.strip(), key


def _find(name: str) -> ConfigProvider | None:
    return next((p for p in _dlt.registered_providers() if p.name == name), None)


def register_secret_scope(
    scope: str, *, workspace_client: Any | None = None
) -> DatabricksSecretsProvider:
    """Add a scope to the places dlt looks for secrets, after the ones it has.

    Registering the same scope twice changes nothing: the provider that is there is
    returned.
    """
    provider = DatabricksSecretsProvider(scope, workspace_client=workspace_client)
    existing = _find(provider.name)
    if existing is not None:
        return existing  # type: ignore[return-value]
    _dlt.register_provider(provider)
    return provider


def register_pointed_secrets(
    pointers: Mapping[str, str], *, workspace_client: Any | None = None
) -> PointedSecretsProvider:
    """Add pointed-at secrets to the places dlt looks, after the ones dlt has.

    There is one such provider in a process, registered the first time; a later call
    replaces what it points at. Register it before any scope, so that it is asked first.
    """
    existing = _find(PointedSecretsProvider.NAME)
    if isinstance(existing, PointedSecretsProvider):
        existing.point_at(pointers, workspace_client=workspace_client)
        return existing
    provider = PointedSecretsProvider(pointers, workspace_client=workspace_client)
    _dlt.register_provider(provider)
    return provider

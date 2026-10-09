"""dlt's secrets, from an Azure Key Vault. `spec/003`, R12.

A second vault provider beside the secret-scope one, for a team whose secrets live in a
Key Vault and not in a Databricks scope. It is asked after the scopes, and like them after
dlt's own providers. Needs the `keyvault` extra: `uv add "leeghwater[keyvault]"`.

Who reads the vault is whoever `DefaultAzureCredential` finds: `az login` on a laptop, a
service principal's variables or a managed identity elsewhere. A Databricks job has no
identity in Azure by itself, so there a vault is reachable only with a service principal
whose secret comes from somewhere — in practice a Databricks scope — and only when the
compute's network reaches `vault.azure.net`. The README says so.

This module imports dlt. On Databricks, import it after `leeghwater.prepare()`.
"""

import re
import threading
from collections.abc import Sequence
from typing import Any

from dlt.common.configuration.providers.provider import get_key_name
from dlt.common.configuration.providers.vault import VaultDocProvider, normalize_key

from leeghwater import _dlt
from leeghwater._errors import LeeghwaterError

# A Key Vault secret's name: letters, digits and dashes, 1 to 127 of them.
# https://learn.microsoft.com/azure/key-vault/general/about-keys-secrets-certificates#vault-name-and-object-name
_NAME = re.compile(r"^[0-9A-Za-z-]{1,127}$")


def secret_name(key: str, *sections: str) -> str:
    """The name of a secret in the vault for dlt's path: joined with `-`, no underscores.

    `sources.github.access_token` is `sources-github-access-token`. A Key Vault allows
    no underscore, so each becomes a dash; dlt's `dlt_secrets_toml` is `dlt-secrets-toml`.
    """
    parts = [normalize_key(section) for section in sections if section]
    return get_key_name(normalize_key(key), "-", *parts).replace("_", "-")


def _default_client(vault_url: str) -> Any:
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
    except ImportError as error:
        raise LeeghwaterError(
            "Reading an Azure Key Vault needs the keyvault extra:"
            ' uv add "leeghwater[keyvault]"'
        ) from error
    return SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())


class Vault:
    """One Key Vault, read through Azure's SDK. The client is made on first use."""

    def __init__(self, url: str, client: Any | None) -> None:
        self.url = url
        self._client = client
        self._lock = threading.Lock()

    @property
    def client(self) -> Any:
        with self._lock:
            if self._client is None:
                self._client = _default_client(self.url)
            return self._client

    def names(self) -> set[str]:
        """The names of the secrets in the vault. No values: a listing never has them."""
        from azure.core.exceptions import ClientAuthenticationError, HttpResponseError

        try:
            return {secret.name for secret in self.client.list_properties_of_secrets()}
        except ClientAuthenticationError as error:
            raise LeeghwaterError(
                f"Nobody is signed in to Azure to read the Key Vault {self.url}: on a"
                " laptop, `az login`; elsewhere, a service principal's variables or a"
                " managed identity (DefaultAzureCredential)."
            ) from error
        except HttpResponseError as error:
            if error.status_code == 403:
                raise LeeghwaterError(
                    f"The Key Vault {self.url} can't be listed by this identity. It needs"
                    " the Key Vault Secrets User role, or a 'list' secret permission."
                ) from error
            if error.status_code == 404:
                raise LeeghwaterError(
                    f"There is no Key Vault at {self.url}: check the --key-vault address."
                ) from error
            raise

    def read(self, name: str) -> str | None:
        """One secret's value, or None when it isn't there for this identity."""
        from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

        try:
            secret = self.client.get_secret(name)
        except ResourceNotFoundError:
            return None
        except HttpResponseError as error:
            if error.status_code == 403:
                return None
            raise
        return secret.value or None


class KeyVaultSecretsProvider(VaultDocProvider):
    """A dlt config provider that reads one Azure Key Vault.

    A secret is found by dlt's path, joined with `-` and with no underscores: what dlt
    asks for as `sources.github.access_token` is the secret `sources-github-access-token`.
    A secret named `dlt-secrets-toml`, `sources`, `sources-<name>`, `destination` or
    `destination-<name>` is read as a piece of `secrets.toml`.

    The vault is listed once, on first use, and only what is there is fetched. Only values
    a source marks as secret are looked up.
    """

    def __init__(self, url: str, *, client: Any | None = None) -> None:
        url = (url or "").strip().rstrip("/")
        if not url.startswith("https://"):
            raise LeeghwaterError(
                "A Key Vault is named by its address, like"
                f" https://my-vault.vault.azure.net; got '{url}'."
            )
        self.url = url
        self._vault = Vault(url, client)
        # As the scope provider: list first, then single values too. The base class is
        # why pyproject.toml caps dlt below 2.
        super().__init__(only_secrets=False, only_toml_fragments=False, list_secrets=True)
        self.only_secrets = True

    @staticmethod
    def get_key_name(key: str, *sections: str) -> str:
        return secret_name(key, *sections)

    @property
    def name(self) -> str:
        return f"Azure Key Vault {self.url}"

    @property
    def supports_sections(self) -> bool:
        return True

    @property
    def locations(self) -> Sequence[str]:
        return [f"key vault {self.url}"]

    def _list_vault(self) -> set[str]:
        return self._vault.names()

    def _look_vault(self, full_key: str, hint: type) -> str | None:
        if not _NAME.match(full_key):
            return None
        return self._vault.read(full_key)


def register_key_vault(url: str, *, client: Any | None = None) -> KeyVaultSecretsProvider:
    """Add a Key Vault to the places dlt looks for secrets, after the ones it has.

    Registering the same vault twice changes nothing: the provider that is there is
    returned.
    """
    provider = KeyVaultSecretsProvider(url, client=client)
    for existing in _dlt.registered_providers():
        if existing.name == provider.name:
            return existing  # type: ignore[return-value]
    _dlt.register_provider(provider)
    return provider

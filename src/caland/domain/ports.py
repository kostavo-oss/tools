"""Ports — the domain's outbound contracts for all I/O.

Infrastructure implements these; the application depends only on them. Together
with `SecretStore` (in secret_store.py) they are every door out of the domain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .models import Settings, Workspace
from .secret_store import SecretStore


@dataclass
class Connected:
    """The result of establishing a connection: a store plus how to label and
    (optionally) persist it."""

    store: SecretStore
    label: str
    host: str = ""


@runtime_checkable
class WorkspaceConnector(Protocol):
    """Establishes a connection to a workspace's secret backend (login)."""

    def connect_profile(self, profile: str) -> Connected: ...
    def connect_url(self, host: str) -> Connected: ...


@runtime_checkable
class ProfileStore(Protocol):
    """Reads and writes saved connection profiles (~/.databrickscfg)."""

    def discover(self) -> list[Workspace]: ...

    # every profile there is, with an address or not — and one added under a
    # name that is none of them (raises `Exists` otherwise)
    def names(self) -> list[str]: ...
    def add(self, name: str, host: str) -> None: ...


@runtime_checkable
class BundleStore(Protocol):
    """Reads the workspace target from a Databricks Asset Bundle (databricks.yml)
    in the working directory, if one is present."""

    def discover(self) -> Workspace | None: ...


@runtime_checkable
class SettingsStore(Protocol):
    """Loads and saves persisted UI preferences (theme, toggles)."""

    def load(self) -> Settings: ...
    def save(self, settings: Settings) -> None: ...

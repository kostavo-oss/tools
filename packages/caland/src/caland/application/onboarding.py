"""OnboardingService — connection/login use-cases.

Depends only on domain ports (`WorkspaceConnector`, `ProfileStore`, `BundleStore`);
the composition root injects concrete infrastructure adapters. Produces
ready-to-use `WorkspaceService` instances so the UI never touches the store or
the SDK.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain import (
    SOURCE_PROFILE,
    AuthError,
    BundleStore,
    ProfileStore,
    Workspace,
    WorkspaceConnector,
)
from .workspace import WorkspaceService


@dataclass
class Connection:
    """A live workspace session plus the host needed to persist it as a profile."""

    service: WorkspaceService
    host: str = ""


def _on_offer(workspaces: list[Workspace]) -> str:
    names = ", ".join(workspace.name for workspace in workspaces)
    return f"There is: {names}." if names else "There is none to choose from."


class OnboardingService:
    def __init__(
        self,
        connector: WorkspaceConnector,
        profiles: ProfileStore,
        bundle: BundleStore | None = None,
    ) -> None:
        self._connector = connector
        self._profiles = profiles
        self._bundle = bundle

    # -- discovery ------------------------------------------------------
    def available_workspaces(self) -> list[Workspace]:
        """Every workspace we can offer, each tagged with where it came from: the
        bundle target (default) first, then every ~/.databrickscfg profile.

        A profile at the bundle's address, or at another profile's, is offered
        like any other: it has its own way of signing in — a token, a service
        principal — which the entry beside it has not."""
        bundle = self._bundle.discover() if self._bundle else None
        return [*([bundle] if bundle else []), *self._profiles.discover()]

    def choose(self, name: str | None = None) -> Workspace:
        """The workspace that was asked for by name — or, with no name, the one
        there is no doubt about: the bundle's default, or the only one there is.

        A profile comes before a bundle's target of the same name: the target
        needs no name, and the profile has no other way to be asked for.

        Raises `AuthError` saying what there is to choose from otherwise.
        """
        workspaces = self.available_workspaces()
        if name:
            named = [workspace for workspace in workspaces if workspace.name == name]
            if not named:
                raise AuthError(f"No workspace “{name}” found. {_on_offer(workspaces)}")
            return next((w for w in named if w.source == SOURCE_PROFILE), named[0])
        default = next((w for w in workspaces if w.default), None)
        if default:
            return default
        if len(workspaces) == 1:
            return workspaces[0]
        if not workspaces:
            raise AuthError(
                "No workspace found: there is no databricks.yml here and no profile "
                "in ~/.databrickscfg."
            )
        raise AuthError(f"Which workspace? {_on_offer(workspaces)}")

    def profile_names(self) -> list[str]:
        """Every profile there is — also those that are no workspace to offer."""
        return self._profiles.names()

    def add_profile(self, name: str, host: str) -> None:
        """Keep an address under a new name. Raises `Exists` for a name in use."""
        self._profiles.add(name, host)

    # -- connection use-cases -------------------------------------------
    def connect(self, workspace: Workspace) -> Connection:
        """Connect to a chosen workspace. A saved profile uses its stored auth; a
        bundle target or manual URL signs in through the browser (OAuth)."""
        if workspace.source == SOURCE_PROFILE and workspace.profile:
            return self.connect_profile(workspace.profile)
        return self.connect_url(workspace.host)

    def connect_profile(self, profile: str) -> Connection:
        c = self._connector.connect_profile(profile)
        return Connection(WorkspaceService(c.store, c.label))

    def connect_url(self, host: str) -> Connection:
        c = self._connector.connect_url(host)
        return Connection(WorkspaceService(c.store, c.label), host=c.host)

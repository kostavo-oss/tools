"""Domain model — the ubiquitous language of Caland as plain value objects.

No UI, no Databricks SDK, no I/O. These are the nouns the whole app speaks:
workspaces, scopes, secrets, ACLs, identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Rotation-policy default: a secret untouched this long counts as stale.
STALE_AFTER_DAYS = 90

# Where a connection target was discovered. Shown to the user so it's always
# clear where a workspace came from.
SOURCE_PROFILE = "profile"  # ~/.databrickscfg
SOURCE_BUNDLE = "bundle"  # ./databricks.yml (Databricks Asset Bundle)
SOURCE_URL = "url"  # typed in by hand

_SOURCE_LABELS = {
    SOURCE_PROFILE: "~/.databrickscfg",
    SOURCE_BUNDLE: "databricks.yml",
    SOURCE_URL: "manual",
}


def same_name(one: str, other: str) -> bool:
    """Whether two names are one name to Databricks, which does not tell a scope
    or a secret apart by its case: `Api-Key` and `api-key` are the same secret.
    (Tried on a workspace, 2026-10-06: the second put overwrote the first.)"""
    return one.casefold() == other.casefold()


@dataclass(frozen=True)
class Workspace:
    """A connection target the login can offer, plus where it came from."""

    profile: str = ""  # ~/.databrickscfg profile name (empty for bundle/url)
    host: str = ""
    source: str = SOURCE_PROFILE
    target: str = ""  # bundle target / display name when there's no profile
    default: bool = False  # pre-select this entry in the picker

    @property
    def host_label(self) -> str:
        return self.host.replace("https://", "").replace("http://", "").rstrip("/")

    @property
    def name(self) -> str:
        return self.profile or self.target or self.host_label or "(workspace)"

    @property
    def source_label(self) -> str:
        base = _SOURCE_LABELS.get(self.source, self.source)
        return f"{base}  ·  default" if self.default else base

    @property
    def label(self) -> str:
        return f"{self.name}  ·  {self.host_label}" if self.host_label else self.name


@dataclass
class Scope:
    name: str
    backend_type: str = "DATABRICKS"

    @property
    def is_keyvault(self) -> bool:
        return self.backend_type == "AZURE_KEYVAULT"


@dataclass
class Secret:
    scope: str
    key: str
    last_updated_ms: int | None = None


@dataclass
class Acl:
    principal: str
    permission: str  # READ | WRITE | MANAGE


@dataclass
class Settings:
    """Persisted preferences — how things are shown, never secret material."""

    show_all_scopes: bool = True
    audit_threshold: int = STALE_AFTER_DAYS


@dataclass
class Identity:
    """Who we are authenticated as in a workspace."""

    user_name: str = ""
    display_name: str = ""
    authenticated: bool = False
    error: str = ""
    groups: list[str] = field(default_factory=list)  # group memberships (SCIM)

"""What the page is told, as plain data.

Pure: a workspace as the application layer holds it goes in, dictionaries that
become JSON come out. No secret's value is in anything here — a value is only
ever the answer to the one request that asks for it (`server.py`).
"""

from __future__ import annotations

import base64
from typing import Any

from ...application import Progress, WorkspaceService
from ...domain import Settings, Workspace


def state(
    progress: Progress,
    service: WorkspaceService | None,
    *,
    workspace: Workspace,
    read_only: bool,
    settings: Settings,
    version: str,
) -> dict[str, Any]:
    """Everything the page draws its frame from: how far the loading is, who is
    connected to what, and the scopes with how many secrets each holds."""
    told: dict[str, Any] = {
        "caland": version,
        "phase": progress.phase,
        "done": progress.done,
        "total": progress.total,
        "error": progress.error,
        "version": progress.version,
        "workspace": {"name": workspace.name, "host": workspace.host_label},
        "identity": None,
        "read_only": read_only,
        "show_all": settings.show_all_scopes,
        "stale_after": settings.audit_threshold,
        "scopes": [],
        # the secret that can be put back — where it was, never what it held
        "taken": None,
    }
    if service is None:
        return told
    identity = service.identity
    if identity.authenticated:
        told["identity"] = {"user": identity.user_name, "name": identity.display_name}
    if service.taken:
        told["taken"] = {"scope": service.taken[0], "key": service.taken[1]}
    access = {summary.scope: summary.effective for summary in service.auth_summary()}
    told["scopes"] = [
        {
            "name": scope.name,
            "keyvault": scope.is_keyvault,
            "access": _access(access.get(scope.name)),
            "count": len(service.secrets_for(scope.name)),
            "loaded": scope.name in service.cache.secrets,
        }
        for scope in service.scopes
    ]
    return told


def scope(service: WorkspaceService, name: str) -> dict[str, Any] | None:
    """One scope: its secrets by name and date, and who has a grant on it."""
    found = service.scope(name)
    if found is None:
        return None
    access = {summary.scope: summary.effective for summary in service.auth_summary()}
    return {
        "name": found.name,
        "keyvault": found.is_keyvault,
        "access": _access(access.get(found.name)),
        "secrets": _secrets(service, found.name),
        "grants": [[acl.principal, acl.permission] for acl in service.acls_for(name)],
    }


def keys(service: WorkspaceService) -> dict[str, Any]:
    """Every secret's name and date, by scope — what the page filters over
    without asking again."""
    return {"scopes": {s.name: _secrets(service, s.name) for s in service.scopes}}


def grants(service: WorkspaceService) -> dict[str, Any]:
    """Every scope's grants — what "who has access" is answered from."""
    return {
        "scopes": {
            s.name: [[acl.principal, acl.permission] for acl in service.acls_for(s.name)]
            for s in service.scopes
        }
    }


def value(data: bytes) -> dict[str, Any]:
    """A value, for the one request that asks for it: as text when it is text,
    and otherwise as what it is — bytes, said in base64."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    if text is not None and not any(ord(c) < 32 and c not in "\t\n\r" for c in text):
        return {"value": text}
    return {"binary": True, "size": len(data), "base64": base64.b64encode(data).decode()}


def _secrets(service: WorkspaceService, name: str) -> list[list[Any]]:
    return [[secret.key, secret.last_updated_ms] for secret in service.secrets_for(name)]


def _access(effective: str | None) -> str:
    """READ, WRITE or MANAGE — or nothing, for a scope out of reach."""
    return effective if effective in ("READ", "WRITE", "MANAGE") else ""

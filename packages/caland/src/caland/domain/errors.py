"""Domain-level error types — abstractions the application catches without
knowing (or caring) that the backend is Databricks."""

from __future__ import annotations


class StoreError(Exception):
    """A secret-store operation failed; carries a UI-friendly message."""


class Exists(StoreError):
    """What was about to be written would land on something that is there."""


class AuthError(Exception):
    """Login / workspace-discovery failure; carries a UI-friendly message."""

"""One plan for your whole Databricks deploy.

The bundle and everything around it — the steps before, the steps after —
reviewed before anything runs, and taken down again when you say so. `spec/`
says what each piece must deliver; `docs/DESIGN.md` says how it is built.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lely")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0"

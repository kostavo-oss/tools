"""One plan for your whole Databricks deploy.

The bundle and everything around it — the steps before, the steps after —
reviewed before anything runs, and taken down again when you say so. `RULES.md`
says what must be true of it; `docs/how-it-works.md` says how it works.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lely")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0"

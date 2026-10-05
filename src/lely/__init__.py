"""One plan and one apply for a whole Databricks deploy.

Pre-deploy steps, the bundle, post-deploy steps — each planned before anything
changes, and each able to use what the ones before it produced. `docs/DESIGN.md`
is the source of truth.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lely")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0"

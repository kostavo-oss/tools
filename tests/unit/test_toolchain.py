"""The tools around the code agree with each other."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pre_commit_runs_the_ruff_that_ci_runs() -> None:
    """A commit is checked by pre-commit and a pull request by `uv run ruff`.
    Two versions of one formatter is a commit that passes one and fails the
    other — and Dependabot only moves the lock file."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    (locked,) = [p["version"] for p in lock["package"] if p["name"] == "ruff"]
    hooks = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    pinned = re.search(r"ruff-pre-commit\s+rev: v(\S+)", hooks)
    assert pinned and pinned.group(1) == locked

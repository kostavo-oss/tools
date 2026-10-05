"""Running another program: the Databricks CLI, stevin, a `command` step.

One place, so every step that shells out fails the same way: a missing program
says so, and a failing one is shown in its own words.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from lely.errors import LelyError


class ProcessError(LelyError):
    """Another program was missing, or failed."""


def run(
    args: Sequence[str],
    cwd: Path,
    *,
    env: Mapping[str, str] | None = None,
    hint: str = "",
) -> subprocess.CompletedProcess[str]:
    """Run `args`, capturing its output. A missing program raises; a failing
    one doesn't — the caller decides what its exit code means."""
    try:
        return subprocess.run(
            list(args),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise ProcessError(
            f"`{args[0]}` isn't installed or isn't on PATH."
            + (f" {hint}" if hint else "")
        ) from None


def failure(what: str, result: subprocess.CompletedProcess[str]) -> ProcessError:
    """A failed run, as an error that quotes what the program said."""
    said = result.stderr.strip() or result.stdout.strip() or "(no output)"
    return ProcessError(f"{what} failed (exit {result.returncode}):\n{said}")

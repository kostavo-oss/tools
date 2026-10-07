"""Offline tests stay offline.

A machine with the Databricks CLI or stevin installed would answer
differently from one without them — and from CI — so the unit suite hides
both from PATH; tests that want one pass a fake as the `executable`.

So would git under a developer's own config: `commit.gpgsign = true` there
failed every fixture that commits. git, as the tests run it and as lely does
in them, reads a repository's own config and nothing of the machine's.
"""

import os
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest


def path_without(*programs: str) -> str:
    kept = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if any(shutil.which(p, path=entry) for p in programs):
            continue
        kept.append(entry)
    return os.pathsep.join(kept)


@pytest.fixture(autouse=True)
def _without_real_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", path_without("databricks", "stevin"))


@pytest.fixture(scope="session")
def _no_git_config(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """An empty file to stand where git looks for a user's config."""
    empty = tmp_path_factory.mktemp("git") / "config"
    empty.touch()
    return empty


@pytest.fixture(autouse=True)
def _without_the_machines_git_config(
    _no_git_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No global and no system config, wherever a test makes a repository."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(_no_git_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def git_is_gone(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    """Call it, and from then on there is no `git` on PATH."""

    def gone() -> None:
        monkeypatch.setenv("PATH", path_without("git"))

    return gone


@pytest.fixture
def git_refuses(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Callable[[], None]:
    """Call it, and from then on `git` refuses every repository the way it
    refuses a checkout owned by someone else — common in containers.

    A stand-in, because whether the real git refuses is the machine's own
    business: a CI runner's `safe.directory` lets everything through.
    """

    def refuse() -> None:
        folder = tmp_path_factory.mktemp("refusing-git")
        script = folder / "git"
        script.write_text(
            "#!/bin/sh\n"
            "echo \"fatal: detected dubious ownership in repository at '$PWD'\" >&2\n"
            "exit 128\n"
        )
        script.chmod(0o755)
        monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ['PATH']}")

    return refuse

"""Offline tests stay offline.

A machine with the Databricks CLI or stevin installed would answer
differently from one without them — and from CI — so the unit suite hides
both from PATH; tests that want one pass a fake as the `executable`.
"""

import os
import shutil

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

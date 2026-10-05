"""Fakes for the edges: the Databricks CLI, in process.

`FakeDatabricks` is `fake_databricks.py` called as a function: the same
answers the program gives, without a process per call. Its world is a folder,
so a test can read back what lely asked (`calls`) and what the simulated
workspace remembers (`state`).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fake_databricks

FIXTURES = Path(__file__).parent / "fixtures"
HOST = fake_databricks.HOST
USER = fake_databricks.USER


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def bundle_config(
    *,
    name: str = "shop",
    target: str = "dev",
    variables: Mapping[str, Any] | None = None,
    resources: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """A resolved config shaped like `bundle validate -o json` prints one."""
    return {
        "bundle": {"name": name, "target": target, "environment": target},
        "variables": {
            key: {"default": value, "value": value}
            for key, value in (variables or {}).items()
        },
        "resources": dict(resources or {}),
        "workspace": {
            "host": HOST,
            "current_user": {"userName": USER, "short_name": "jane"},
            "root_path": f"/Workspace/Users/{USER}/.bundle/{name}/{target}",
        },
    }


@dataclass(frozen=True)
class FakeDatabricks:
    """The fake CLI over a world folder. `profile` is who is asking."""

    world: Path
    profile: str | None = None

    def run(self, args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        command = list(args)
        if self.profile is not None:
            at = command.index("--") if "--" in command else len(command)
            command[at:at] = ["--profile", self.profile]
        code, out, err = fake_databricks.answer(self.world, command, cwd)
        return subprocess.CompletedProcess(command, code, out, err)

    @property
    def calls(self) -> list[list[str]]:
        path = self.world / "calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    @property
    def verbs(self) -> list[str]:
        """What was asked, as `validate`, `plan`, `deploy`, …"""
        return [call[1] for call in self.calls if call[:1] == ["bundle"]]

    @property
    def state(self) -> dict[str, Any]:
        path = self.world / "state.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def deployed(
        self, name: str = "shop", target: str = "dev", user: str = USER
    ) -> dict[str, Any]:
        """What the workspace remembers of one bundle: `<type>.<key>` → record."""
        root = f"/Workspace/Users/{user}/.bundle/{name}/{target}"
        return self.state.get("bundles", {}).get(root, {}).get("deployed", {})

    def uploads(self, name: str = "shop", target: str = "dev") -> int:
        root = f"/Workspace/Users/{USER}/.bundle/{name}/{target}"
        return self.state.get("bundles", {}).get(root, {}).get("uploads", 0)

    @property
    def runs(self) -> list[dict[str, Any]]:
        return self.state.get("runs", [])

    def clear_calls(self) -> None:
        (self.world / "calls.jsonl").unlink(missing_ok=True)


def write_bundle(folder: Path, bundle: Mapping[str, Any]) -> None:
    """Put a simulated bundle where a `databricks.yml` would be."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / fake_databricks.BUNDLE_FILE).write_text(json.dumps(bundle, indent=1))


def deploy(
    world: Path,
    resources: Mapping[str, Mapping[str, Any]],
    *,
    name: str = "shop",
    target: str = "dev",
    user: str = USER,
) -> None:
    """Make the simulated workspace remember resources as deployed already:
    `{"jobs.backfill": {"id": "771", "config": {...}}}`."""
    world.mkdir(parents=True, exist_ok=True)
    path = world / "state.json"
    state = json.loads(path.read_text()) if path.exists() else {}
    root = f"/Workspace/Users/{user}/.bundle/{name}/{target}"
    state.setdefault("bundles", {})[root] = {
        "lineage": f"lineage-{name}",
        "serial": 1,
        "deployed": {key: dict(record) for key, record in resources.items()},
        "uploads": 1,
    }
    path.write_text(json.dumps(state, indent=1))

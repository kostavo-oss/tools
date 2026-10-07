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


#: The tasks every Kostavo tool has, under these names: the template gives them.
TASKS = {
    "dev",
    "test",
    "test:lowest",
    "lint",
    "fmt",
    "fix",
    "typecheck",
    "check",
    "build",
    "docs",
    "docs:build",
    "ci",
    "clean",
}


def test_the_tasks_every_kostavo_tool_has_are_here() -> None:
    config = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
    assert set(config["tasks"]) >= TASKS
    # Nothing under [env] is a secret, and no file of them is loaded: an
    # assistant that asks mise for the environment is shown all of this.
    assert set(config["env"]) == {"UV_PROJECT_ENVIRONMENT", "NO_MKDOCS_2_WARNING"}


def test_an_assistant_is_given_mises_server_and_nothing_else() -> None:
    import json

    given = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert given == {
        "mcpServers": {
            "mise": {
                "command": "mise",
                "args": ["mcp"],
                "env": {"MISE_EXPERIMENTAL": "1"},
            }
        }
    }


def test_the_tool_says_which_template_it_has_taken() -> None:
    answers = (ROOT / ".copier-answers.yml").read_text(encoding="utf-8")
    assert "_src_path: gh:kostavo-oss/template-python" in answers
    # its code is its own: an update writes no starter command beside it
    assert "starter_code: false" in answers

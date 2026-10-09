"""What holds across the packages: each is a tool of its own, and none needs another."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = sorted(p.name for p in (ROOT / "packages").iterdir() if p.is_dir())


def test_the_workspace_lists_every_package_and_nothing_else() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    members = config["tool"]["uv"]["workspace"]["members"]
    assert members == ["packages/*"]
    # the last deltaplan release is a package of its own, published by hand
    excluded = config["tool"]["uv"]["workspace"]["exclude"]
    assert excluded == ["packages/stevin/deltaplan-shim"]
    assert set(config["project"]["dependencies"]) == {
        "stevin",
        "lely",
        "leeghwater[keyvault]",
        "caland",
    }
    named = {name.split("[")[0] for name in config["project"]["dependencies"]}
    assert named == set(PACKAGES)


@pytest.mark.parametrize("package", PACKAGES)
def test_a_package_has_what_a_tool_of_its_own_has(package: str) -> None:
    here = ROOT / "packages" / package
    files = ("README.md", "CHANGELOG.md", "CLAUDE.md", "LICENSE", "pyproject.toml")
    files += ("mkdocs.yml",)
    for name in files:
        assert (here / name).is_file(), f"{package} has no {name}"
    assert (here / "docs" / "index.md").is_file()
    assert (here / "src" / package).is_dir()
    assert (here / "tests").is_dir()
    config = tomllib.loads((here / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["project"]["name"] == package
    # one LICENSE, byte for byte, in every package: hatchling packs it into the sdist
    assert (here / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()
    # the docs say where they are: one site, one section per tool
    urls = config["project"]["urls"]
    assert urls["Documentation"] == f"https://kostavo-oss.github.io/tools/{package}/"
    assert urls["Repository"] == "https://github.com/kostavo-oss/tools"


IMPORT = re.compile(r"^\s*(?:from|import)\s+([a-zA-Z_][\w]*)", re.MULTILINE)


@pytest.mark.parametrize("package", PACKAGES)
def test_no_package_imports_another(package: str) -> None:
    """Each tool does one job and none needs another. lely runs stevin as a
    command through uvx, which is not an import — and the only way allowed."""
    others = set(PACKAGES) - {package}
    here = ROOT / "packages" / package
    offending = []
    for folder in ("src", "tests"):
        for file in (here / folder).rglob("*.py"):
            for match in IMPORT.finditer(file.read_text(encoding="utf-8")):
                if match.group(1) in others:
                    where = file.relative_to(ROOT)
                    offending.append(f"{where}: {match.group(0).strip()}")
    assert offending == []


def test_the_site_has_a_section_per_package() -> None:
    # the root config carries plugin tags (!include, !!python/name) a plain loader refuses
    text = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    for package in PACKAGES:
        assert f"- {package}: '!include packages/{package}/mkdocs.yml'" in text, package
    site = yaml.safe_load(text.replace("!include ", "").replace("!!python/name:", ""))
    assert site["site_url"] == "https://kostavo-oss.github.io/tools/"
    assert "monorepo" in site["plugins"]


def test_the_tasks_every_tool_had_are_here() -> None:
    config = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
    assert set(config["tasks"]) >= {
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
    # Nothing under [env] is a secret, and no file of them is loaded: an
    # assistant that asks mise for the environment is shown all of this.
    assert set(config["env"]) == {"UV_PROJECT_ENVIRONMENT", "NO_MKDOCS_2_WARNING"}


def test_pre_commit_runs_the_ruff_that_ci_runs() -> None:
    """A commit is checked by pre-commit and a pull request by `uv run ruff`.
    Two versions of one formatter is a commit that passes one and fails the
    other — and Dependabot only moves the lock file."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    (locked,) = [p["version"] for p in lock["package"] if p["name"] == "ruff"]
    hooks = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    pinned = re.search(r"ruff-pre-commit\s+rev: v(\S+)", hooks)
    assert pinned and pinned.group(1) == locked


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

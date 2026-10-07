"""The repository itself: what stands in it, and what a release carries out of it."""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: What stands at the top of the repository. Anything else was put there by a
#: tool — a test report, a build — and a tool's report can hold the environment
#: of the machine it ran on. One did, in the source packages of 0.5.1 to 0.6.0.
TOP = {
    ".github",
    ".gitignore",
    ".pre-commit-config.yaml",
    ".zed",
    "CHANGELOG.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "docs",
    "mise.toml",
    "mkdocs.yml",
    "pyproject.toml",
    "spec",
    "src",
    "tests",
    "uv.lock",
}


def tracked() -> list[str]:
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [name for name in listed.stdout.split("\0") if name]


def test_nothing_stands_at_the_top_that_was_not_put_there_on_purpose() -> None:
    top = {name.split("/", 1)[0] for name in tracked()}
    assert top <= TOP, f"new at the top of the repository: {sorted(top - TOP)}"


def test_no_report_a_tool_wrote_is_in_the_repository() -> None:
    reports = [name for name in tracked() if name.endswith("_report.html")]
    assert reports == []


def test_a_source_package_is_made_from_a_list() -> None:
    """Without one a build packs whatever lies in the folder, ignored or not."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    listed = config["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert set(listed) == {
        "/src",
        "/tests",
        "/README.md",
        "/LICENSE",
        "/CHANGELOG.md",
        "/pyproject.toml",
    }


def test_what_a_user_reads_first_does_not_speak_of_the_terminal_app() -> None:
    """Caland is a page. The site's description, the form for a bug and the
    docs' stylesheet said "terminal UI", "the TUI" and `--iso-` for a release."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    site = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert f'site_description: "{config["project"]["description"]}"' in site
    for name in (
        "mkdocs.yml",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        "docs/stylesheets/extra.css",
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        for word in ("TUI", "terminal UI", "--iso-", "2>err.log"):
            assert word not in text, f"{word} in {name}"


def test_it_is_said_to_run_where_it_is_run() -> None:
    """macOS and Linux, which CI runs. Windows is untried, and is not promised:
    not by a classifier, not by the installation page."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    systems = [c for c in config["project"]["classifiers"] if "Operating System" in c]
    assert systems == ["Operating System :: MacOS", "Operating System :: POSIX :: Linux"]
    page = (ROOT / "docs" / "installation.md").read_text(encoding="utf-8")
    assert "Windows is\n  untried" in page

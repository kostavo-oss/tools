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
    ".copier-answers.yml",
    ".github",
    ".gitignore",
    ".mcp.json",
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


def test_the_security_policy_says_what_the_docs_say() -> None:
    """It was behind them: a value read "only when you explicitly reveal or
    copy", and not a word of the server that serves the page."""
    policy = " ".join((ROOT / "SECURITY.md").read_text(encoding="utf-8").split())
    for said in (
        "to move or copy its secret, to delete its secret",
        "a `.env` export with values",
        "`127.0.0.1` only",
        "never a cookie",
        "~/.config/databricks-sdk-py/oauth/",
    ):
        assert said in policy, said
    for gone in ("explicitly reveal or copy", "databricks auth login` does"):
        assert gone not in policy, gone


def test_the_changelogs_links_point_at_what_is_there() -> None:
    """A version's link compares two tags. 0.1.0 and 0.3.0 were never tagged, and
    the links that named `v0.1.0` and `v0.3.0` opened nothing; neither did the one
    to the repository under its first owner. Where there is no tag the link names
    the commit. The version in pyproject.toml may have none yet: releasing it is
    what makes its tag. Skipped in a checkout without tags, as CI's is."""
    import re

    tags = subprocess.run(
        ["git", "tag", "--list"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.split()
    if not tags:
        pytest.skip("no tags in this checkout")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    coming = f"v{project['project']['version']}"
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    links = re.findall(r"^\[[^\]]+\]: (\S+)$", text, flags=re.MULTILINE)
    assert len(links) > 15
    for link in links:
        assert link.startswith("https://github.com/kostavo-oss/caland/"), link
        for name in re.findall(r"(?:compare/|\.\.\.|tree/)([^./][^.]*(?:\.\d+)*)", link):
            there = (
                name in tags
                or name in ("HEAD", coming)
                or re.fullmatch(r"[0-9a-f]{40}", name)
            )
            assert there, f"{name} in {link}"


def test_the_package_says_of_itself_what_is_so() -> None:
    """A tool, not a library: it ships no `py.typed`, and does not say it is typed."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    assert "Typing :: Typed" not in project["classifiers"]
    assert not (ROOT / "src" / "caland" / "py.typed").exists()
    assert "Environment :: Console" in project["classifiers"]  # it is a command
    assert "cli" not in project["keywords"]


def test_the_readme_has_no_link_or_picture_that_only_works_on_github() -> None:
    """The README is the page on PyPI too, where `docs/img/…` is no picture and
    `LICENSE` no link: every address in it is a whole one."""
    import re

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)\s]+)", readme)
    targets += re.findall(r"(?:src|href)=[\"']([^\"']+)", readme)
    assert len(targets) > 10
    relative = [target for target in targets if not target.startswith("https://")]
    assert relative == []
    # and the pictures are ones that are in the repository
    for picture in re.findall(r"/caland/main/(docs/img/[\w.-]+)", readme):
        assert (ROOT / picture).is_file(), picture


def test_the_package_says_where_its_docs_are() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    docs = config["project"]["urls"]["Documentation"]
    assert docs == "https://kostavo-oss.github.io/caland/"
    assert f"site_url: {docs}\n" in (ROOT / "mkdocs.yml").read_text(encoding="utf-8")


def test_pre_commit_runs_the_ruff_that_ci_runs() -> None:
    """A commit is checked by pre-commit and a pull request by `uv run ruff`.
    Two versions of one formatter is a commit that passes one and fails the
    other — and Dependabot only moves the lock file."""
    import re

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

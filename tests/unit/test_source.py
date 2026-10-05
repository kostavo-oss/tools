"""Which version of the project a plan was made from: the git tree."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lely import source
from lely.model import Source


def git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    (tmp_path / "lely.yml").write_text("steps: []\n")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "notes.txt").write_text("one\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "first")
    return tmp_path


def test_outside_a_repository_nothing_is_recorded(tmp_path: Path) -> None:
    assert source.read(tmp_path) == Source()


def test_a_clean_checkout_is_its_tree(repo: Path) -> None:
    assert source.read(repo) == Source(git(repo, "rev-parse", "HEAD^{tree}"))


def test_a_commit_that_changes_nothing_keeps_the_tree(repo: Path) -> None:
    """The tree, not the commit: a merge with no other change keeps a plan valid."""
    before = source.read(repo)
    git(repo, "commit", "-q", "--allow-empty", "-m", "nothing")
    assert source.read(repo) == before


def test_a_changed_tracked_file_is_uncommitted(repo: Path) -> None:
    (repo / "lely.yml").write_text("steps: [x]\n")
    assert source.read(repo).dirty


def test_a_file_git_doesnt_track_is_not_seen(repo: Path) -> None:
    """The plan file itself is usually one."""
    (repo / "plan.json").write_text("{}")
    assert not source.read(repo).dirty


def test_the_whole_repository_counts_not_only_the_configs_folder(repo: Path) -> None:
    """A step can reach outside the folder its config is in — a bundle at
    `path: ../bundle` — so a change anywhere makes a plan stale."""
    project_dir = repo / "deploy"
    project_dir.mkdir()
    (project_dir / "lely.yml").write_text("steps: []\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "a project in a folder")
    before = source.read(project_dir)
    assert before == source.read(repo)
    (repo / "other" / "notes.txt").write_text("two\n")
    assert source.read(project_dir).dirty
    git(repo, "commit", "-q", "-am", "elsewhere")
    after = source.read(project_dir)
    assert after.tree != before.tree
    assert not after.dirty


def test_the_plan_file_itself_is_left_out(repo: Path) -> None:
    """A plan committed to be reviewed — a destroy going through a pull request
    — would otherwise change the tree it records, and refuse itself."""
    plan = repo / "plans" / "destroy.json"
    planned_on = source.read(repo, plan)
    assert planned_on == source.read(repo)  # it isn't there yet
    plan.parent.mkdir()
    plan.write_text("{}")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "a destroy, for review")
    assert source.read(repo) != planned_on  # the tree did change …
    assert source.read(repo, plan) == planned_on  # … by nothing but the plan
    # planning again over the tracked file doesn't count as an uncommitted change
    plan.write_text('{"again": true}')
    assert source.read(repo).dirty
    assert source.read(repo, plan) == planned_on
    # and git's own index was not touched to find that out
    assert git(repo, "status", "--porcelain") == "M plans/destroy.json"


def test_a_plan_file_somewhere_else_changes_nothing(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path.parent / "elsewhere-plan.json"
    assert source.read(repo, outside) == source.read(repo)

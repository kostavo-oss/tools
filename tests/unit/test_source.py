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


def test_only_the_projects_own_directory_counts(repo: Path) -> None:
    """Another project in the same repository doesn't make a plan stale."""
    project_dir = repo / "service"
    project_dir.mkdir()
    (project_dir / "lely.yml").write_text("steps: []\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "a project in a folder")
    before = source.read(project_dir)
    assert before.tree and before.tree != source.read(repo).tree
    (repo / "other" / "notes.txt").write_text("two\n")
    assert source.read(project_dir) == before
    git(repo, "commit", "-q", "-am", "elsewhere")
    assert source.read(project_dir) == before
    (project_dir / "lely.yml").write_text("steps: [y]\n")
    assert source.read(project_dir).dirty

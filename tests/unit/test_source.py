"""Which version of the project a plan was made from: git's word for it."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from lely import source
from lely.model import Source
from lely.source import SourceError


def git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip("\n")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    (root / "lely.yml").write_text("steps: []\n")
    (root / "other").mkdir()
    (root / "other" / "notes.txt").write_text("one\n")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "first")
    return root


def head_tree(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD^{tree}")


def test_outside_a_repository_nothing_is_recorded(tmp_path: Path) -> None:
    assert source.read(tmp_path) == Source()


def test_a_clean_checkout_is_heads_tree(repo: Path) -> None:
    assert source.read(repo) == Source(head_tree(repo), dirty=False, root=".")


def test_a_commit_that_changes_nothing_keeps_the_tree(repo: Path) -> None:
    """The tree, not the commit: a merge with no other change keeps a plan valid."""
    before = source.read(repo)
    git(repo, "commit", "-q", "--allow-empty", "-m", "nothing")
    assert source.read(repo) == before


def test_uncommitted_changes_are_in_the_tree_not_only_flagged(repo: Path) -> None:
    """A plan made on a changed checkout is held to exactly those changes: the
    tree is what committing them would make."""
    (repo / "lely.yml").write_text("steps: [x]\n")
    changed = source.read(repo)
    assert changed.dirty
    assert changed.tree != head_tree(repo)
    (repo / "lely.yml").write_text("steps: [y]\n")
    assert source.read(repo).tree != changed.tree  # other changes, another tree
    (repo / "lely.yml").write_text("steps: [x]\n")
    git(repo, "commit", "-q", "-am", "the same change, committed")
    assert source.read(repo) == Source(changed.tree, dirty=False, root=".")


def test_a_file_git_doesnt_track_is_not_seen(repo: Path) -> None:
    (repo / "new-notebook.py").write_text("# not added yet\n")
    assert source.read(repo) == Source(head_tree(repo), root=".")


def test_the_whole_repository_counts_and_the_project_is_named(repo: Path) -> None:
    """A step can reach outside the folder its config is in — a bundle at
    `path: ../bundle` — so a change anywhere makes a plan stale. Which project
    of the repository a plan is for is recorded beside the tree."""
    project_dir = repo / "deploy"
    project_dir.mkdir()
    (project_dir / "lely.yml").write_text("steps: []\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "a project in a folder")
    before = source.read(project_dir)
    assert before == Source(head_tree(repo), root="deploy")
    assert source.read(repo).root == "."
    (repo / "other" / "notes.txt").write_text("two\n")
    assert source.read(project_dir).dirty
    git(repo, "commit", "-q", "-am", "elsewhere")
    assert source.read(project_dir).tree != before.tree


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
    # planning again over the tracked file isn't an uncommitted change
    plan.write_text('{"again": true}')
    assert source.read(repo).dirty
    assert source.read(repo, plan) == planned_on
    relative = Path(os.path.relpath(plan, Path.cwd()))
    assert source.read(repo, relative) == planned_on


def test_only_the_one_plan_file_is_left_out(repo: Path) -> None:
    """A second plan file in the repository is a change like any other: it is
    in the tree, so a plan made beside it is held to it."""
    first, second = repo / "a.json", repo / "b.json"
    first.write_text("{}")
    second.write_text("{}")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "two plans")
    first.write_text('{"new": 1}')
    with_first_rewritten = source.read(repo, second)
    assert with_first_rewritten.dirty
    assert with_first_rewritten.tree != source.read(repo, first).tree
    git(repo, "commit", "-q", "-am", "the first, rewritten")
    assert source.read(repo, second).tree == with_first_rewritten.tree


def test_a_plan_file_somewhere_else_changes_nothing(repo: Path, tmp_path: Path) -> None:
    assert source.read(repo, tmp_path / "elsewhere.json") == source.read(repo)


def test_a_file_renamed_onto_the_plans_path_is_a_change(repo: Path) -> None:
    """With `-z`, git names what a file was renamed from in a field of its own."""
    (repo / "sql").write_text("select 1\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "a file with a short name")
    clean = source.read(repo, repo / "plan.json")
    git(repo, "mv", "sql", "plan.json")
    moved = source.read(repo, repo / "plan.json")
    assert moved.dirty  # `sql` is gone, and that isn't the plan file's doing
    assert moved.tree != clean.tree


def test_a_file_git_was_told_not_to_look_at_is_read_anyway(repo: Path) -> None:
    """`assume-unchanged` and `skip-worktree` hide a change from `git status`.
    What is deployed is what is on disk, so that is what is recorded."""
    for flag in ("--assume-unchanged", "--skip-worktree"):
        git(repo, "update-index", flag, "lely.yml")
        (repo / "lely.yml").write_text(f"steps: [hidden by {flag}]\n")
        assert git(repo, "status", "--porcelain", "--untracked-files=no") == ""
        assert source.read(repo).tree != head_tree(repo)
        git(repo, "update-index", flag.replace("--", "--no-"), "lely.yml")
        git(repo, "checkout", "-q", "--", "lely.yml")


def test_nothing_of_the_users_is_written(repo: Path) -> None:
    """The tree is made in an index and an object store of its own."""
    (repo / "lely.yml").write_text("steps: [uncommitted]\n")
    plan = repo / "other" / "notes.txt"  # tracked, so the scratch index is used
    index = (repo / ".git" / "index").read_bytes()
    objects = git(repo, "count-objects", "-v")
    assert source.read(repo, plan).tree
    assert (repo / ".git" / "index").read_bytes() == index
    assert git(repo, "count-objects", "-v") == objects
    assert git(repo, "status", "--porcelain") == " M lely.yml"


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes anywhere")
def test_a_checkout_that_cant_be_written_to_is_still_read(repo: Path) -> None:
    (repo / "lely.yml").write_text("steps: [uncommitted]\n")
    folders = [repo / ".git", repo / ".git" / "objects"]
    try:
        for folder in folders:
            folder.chmod(0o555)
        assert source.read(repo).tree not in (None, head_tree(repo))
    finally:
        for folder in folders:
            folder.chmod(0o755)


def test_git_refusing_is_not_the_same_as_no_repository(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only git's own "not a git repository" means that. Any other failure
    fails the plan: one that quietly recorded nothing would be held to nothing.
    Here, the refusal a container gives a checkout owned by someone else."""
    monkeypatch.setenv("GIT_TEST_ASSUME_DIFFERENT_OWNER", "1")
    with pytest.raises(SourceError) as caught:
        source.read(repo)
    assert "dubious ownership" in str(caught.value)
    assert "would be held to nothing" in str(caught.value)


def test_no_git_in_a_repository_is_an_error_and_outside_one_it_isnt(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "nothing-here"))
    with pytest.raises(SourceError, match="git couldn't be run"):
        source.read(repo)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert source.read(elsewhere) == Source()


def test_inside_a_git_hook(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A hook runs with `GIT_DIR=.git`, relative to the top; lely runs git in
    the project's folder."""
    project_dir = repo / "deploy"
    project_dir.mkdir()
    (project_dir / "lely.yml").write_text("steps: []\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "a project in a folder")
    expected = source.read(project_dir)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GIT_DIR", ".git")
    assert source.read(project_dir) == expected == Source(head_tree(repo), root="deploy")


def test_a_repository_with_no_commit_yet(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    (tmp_path / "lely.yml").write_text("steps: []\n")
    empty = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    assert source.read(tmp_path) == Source(empty, dirty=False, root=".")

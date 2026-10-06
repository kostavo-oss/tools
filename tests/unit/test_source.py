"""Which version of the project a plan was made from: git's word for it."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
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


def tree_without(repo: Path, *paths: str) -> str:
    """The tree `HEAD` would be without `paths`, as git itself makes it."""
    git(repo, "rm", "-q", "-r", "--cached", "--", *paths)
    tree = git(repo, "write-tree")
    git(repo, "reset", "-q")
    return tree


def test_outside_a_repository_nothing_is_recorded(tmp_path: Path) -> None:
    assert source.read(tmp_path) == Source()


def test_a_clean_checkout_is_heads_tree(repo: Path) -> None:
    assert source.read(repo) == Source(head_tree(repo), dirty=False, root=".")


def test_a_commit_that_changes_nothing_keeps_the_tree(repo: Path) -> None:
    """The tree, not the commit: a merge with no other change keeps a plan valid."""
    before = source.read(repo)
    git(repo, "commit", "-q", "--allow-empty", "-m", "nothing")
    assert source.read(repo) == before


def test_anything_that_differs_from_head_is_dirty(repo: Path) -> None:
    """A plan file is for a clean checkout. The tree is `HEAD`'s either way:
    what tells a changed checkout from a clean one is `dirty`, and a staged new
    file — which leaves every tracked file as it was — is one too."""
    (repo / "lely.yml").write_text("steps: [x]\n")
    assert source.read(repo) == Source(head_tree(repo), dirty=True, root=".")
    git(repo, "checkout", "-q", "--", "lely.yml")
    assert not source.read(repo).dirty
    (repo / "new.py").write_text("# staged, not committed\n")
    git(repo, "add", "new.py")
    assert source.read(repo) == Source(head_tree(repo), dirty=True, root=".")
    git(repo, "commit", "-q", "-m", "now it is in")
    assert source.read(repo) == Source(head_tree(repo), root=".")
    (repo / "new.py").unlink()
    assert source.read(repo).dirty  # a tracked file that is gone


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
    """A second plan file in the repository is a change like any other."""
    first, second = repo / "a.json", repo / "b.json"
    first.write_text("{}")
    second.write_text("{}")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "two plans")
    first.write_text('{"new": 1}')
    assert not source.read(repo, first).dirty  # its own rewriting doesn't count
    assert source.read(repo, second).dirty  # the other one's does
    assert source.read(repo, first).tree != source.read(repo, second).tree


def test_a_plan_file_somewhere_else_changes_nothing(repo: Path, tmp_path: Path) -> None:
    assert source.read(repo, tmp_path / "elsewhere.json") == source.read(repo)


def test_a_file_renamed_onto_the_plans_path_is_a_change(repo: Path) -> None:
    """With `-z`, git names what a file was renamed from in a field of its own."""
    (repo / "sql").write_text("select 1\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "a file with a short name")
    assert not source.read(repo, repo / "plan.json").dirty
    git(repo, "mv", "sql", "plan.json")
    # `sql` is gone, and that isn't the plan file's doing
    assert source.read(repo, repo / "plan.json").dirty


def test_a_file_git_was_told_not_to_look_at_cant_be_vouched_for(repo: Path) -> None:
    """`assume-unchanged` and `skip-worktree` hide a change from `git status`.
    lely doesn't call such a checkout clean."""
    for flag in ("--assume-unchanged", "--skip-worktree"):
        git(repo, "update-index", flag, "lely.yml")
        (repo / "lely.yml").write_text(f"steps: [hidden by {flag}]\n")
        assert git(repo, "status", "--porcelain", "--untracked-files=no") == ""
        assert source.read(repo).dirty
        git(repo, "update-index", flag.replace("--", "--no-"), "lely.yml")
        git(repo, "checkout", "-q", "--", "lely.yml")
    assert not source.read(repo).dirty


def test_a_sparse_checkout_is_the_tree_of_what_is_checked_out(repo: Path) -> None:
    """There `skip-worktree` marks a file that isn't on disk: nothing is hidden,
    so the checkout is clean — and it is not the whole one. A plan made where
    every file was there isn't run where a step would find some missing."""
    whole = source.read(repo)
    part = tree_without(repo, "other/notes.txt")
    assert part != whole.tree
    git(repo, "update-index", "--skip-worktree", "other/notes.txt")
    (repo / "other" / "notes.txt").unlink()
    sparse = source.read(repo)
    assert sparse == Source(part, root=".")
    # with the plan file left out as well
    (repo / "plan.json").write_text("{}")
    git(repo, "add", "plan.json")
    git(repo, "commit", "-q", "-m", "a plan to review")
    assert source.read(repo, repo / "plan.json") == sparse
    # back to the whole checkout
    git(repo, "update-index", "--no-skip-worktree", "other/notes.txt")
    git(repo, "checkout", "-q", "--", "other/notes.txt")
    assert source.read(repo, repo / "plan.json") == whole


def test_a_link_to_nowhere_where_a_file_was_is_not_nothing(repo: Path) -> None:
    git(repo, "update-index", "--skip-worktree", "other/notes.txt")
    (repo / "other" / "notes.txt").unlink()
    (repo / "other" / "notes.txt").symlink_to("/nonexistent/notes.txt")
    assert source.read(repo).dirty


def test_a_clone_without_all_its_files_is_read_without_fetching_them(
    tmp_path: Path,
) -> None:
    """A blobless, sparse clone — what a large repository is checked out as —
    with a committed plan file: the tree is made of names, and no file is
    fetched to make it. Here the remote is gone, so a fetch would fail."""
    origin = tmp_path / "origin"
    (origin / "deploy").mkdir(parents=True)
    (origin / "big").mkdir()
    git(origin, "init", "-q")
    (origin / "deploy" / "lely.yml").write_text("steps: []\n")
    (origin / "deploy" / "plan.json").write_text("{}")
    (origin / "big" / "f.bin").write_text("blob\n")
    git(origin, "add", ".")
    git(origin, "commit", "-q", "-m", "first")
    git(origin, "config", "uploadpack.allowFilter", "true")
    clone = tmp_path / "clone"
    git(
        tmp_path,
        "clone",
        "-q",
        "--filter=blob:none",
        "--sparse",
        f"file://{origin}",
        str(clone),
    )
    git(clone, "sparse-checkout", "set", "deploy")
    git(clone, "remote", "set-url", "origin", "file:///nonexistent/origin")
    found = source.read(clone / "deploy", clone / "deploy" / "plan.json")
    assert found == Source(tree_without(origin, "big", "deploy/plan.json"), root="deploy")


def test_a_submodule_counts_whatever_git_was_told_to_ignore(
    repo: Path, tmp_path: Path
) -> None:
    """`submodule.<name>.ignore = all` hides a submodule on another commit from
    `git status`. What it holds is deployed all the same."""
    library = tmp_path / "library"
    library.mkdir()
    git(library, "init", "-q")
    (library / "lib.py").write_text("v = 1\n")
    git(library, "add", ".")
    git(library, "commit", "-q", "-m", "one")
    git(
        repo,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(library),
        "lib",
    )
    git(repo, "commit", "-q", "-m", "a submodule")
    git(repo, "config", "submodule.lib.ignore", "all")
    assert not source.read(repo).dirty
    (repo / "lib" / "lib.py").write_text("v = 2\n")  # changes of its own
    assert git(repo, "status", "--porcelain", "--untracked-files=no") == ""
    assert source.read(repo).dirty
    git(repo / "lib", "commit", "-q", "-am", "two")  # … and on another commit
    assert git(repo, "status", "--porcelain", "--untracked-files=no") == ""
    assert source.read(repo).dirty


def test_a_file_a_submodule_doesnt_track_is_not_seen_either(
    repo: Path, tmp_path: Path
) -> None:
    """A build's leftovers in a submodule are no more a change than they are
    at the top."""
    library = tmp_path / "library"
    library.mkdir()
    git(library, "init", "-q")
    (library / "lib.py").write_text("v = 1\n")
    git(library, "add", ".")
    git(library, "commit", "-q", "-m", "one")
    git(
        repo,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(library),
        "lib",
    )
    git(repo, "commit", "-q", "-m", "a submodule")
    (repo / "lib" / "__pycache__").mkdir()
    (repo / "lib" / "__pycache__" / "lib.pyc").write_text("x")
    (repo / "left-over.txt").write_text("x")
    assert not source.read(repo).dirty


def test_nothing_of_the_users_is_written(repo: Path) -> None:
    """Not an index, not an object, not a shared index beside it — and the
    user's hooks are not run. The one tree lely has to make, `HEAD`'s without a
    tracked plan file, is made in an index and an object store of its own."""
    plan = repo / "plans.json"
    plan.write_text("{}")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "a plan, tracked")
    git(repo, "config", "core.splitIndex", "true")
    hook = repo / ".git" / "hooks" / "post-index-change"
    hook.write_text('#!/bin/sh\ntouch "$(git rev-parse --git-dir)/hook-ran"\n')
    hook.chmod(0o755)
    before = sorted(p.name for p in (repo / ".git").iterdir())
    index = (repo / ".git" / "index").read_bytes()
    objects = git(repo, "count-objects", "-v")
    assert source.read(repo, plan).tree != head_tree(repo)
    assert sorted(p.name for p in (repo / ".git").iterdir()) == before
    assert (repo / ".git" / "index").read_bytes() == index
    assert git(repo, "count-objects", "-v") == objects


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes anywhere")
def test_a_checkout_that_cant_be_written_to_is_still_read(repo: Path) -> None:
    plan = repo / "plans.json"
    plan.write_text("{}")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "a plan, tracked")
    expected = source.read(repo, plan)
    folders = [repo / ".git", repo / ".git" / "objects"]
    try:
        for folder in folders:
            folder.chmod(0o555)
        assert source.read(repo, plan) == expected
    finally:
        for folder in folders:
            folder.chmod(0o755)


def test_a_repository_whose_path_holds_a_colon(tmp_path: Path) -> None:
    """The repository's objects are named to git in a list that a colon
    separates."""
    repo = tmp_path / "re:po"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "plan.json").write_text("{}")
    (repo / "lely.yml").write_text("steps: []\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "first")
    assert source.read(repo, repo / "plan.json").tree != head_tree(repo)


def test_a_folder_spelled_in_another_case_is_the_same_project(repo: Path) -> None:
    """Where the file system doesn't tell `projA` from `PROJA`, lely doesn't
    either: git is asked what the folder is called."""
    project_dir = repo / "projA"
    project_dir.mkdir()
    (project_dir / "lely.yml").write_text("steps: []\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "a project")
    shouted = repo / "PROJA"
    if not shouted.exists():
        pytest.skip("this file system tells the two apart")
    plan = shouted / "plan.json"
    assert source.read(shouted, plan) == source.read(
        project_dir, project_dir / "plan.json"
    )
    assert source.read(shouted).root == "projA"


def test_git_refusing_is_not_the_same_as_no_repository(
    repo: Path, git_refuses: Callable[[], None]
) -> None:
    """Only git's own "not a git repository" means that. Any other failure
    fails the plan: one that quietly recorded nothing would be held to nothing.
    Here, the refusal a container gives a checkout owned by someone else."""
    git_refuses()
    with pytest.raises(SourceError) as caught:
        source.read(repo)
    assert "dubious ownership" in str(caught.value)
    assert "would be held to nothing" in str(caught.value)


def test_a_git_folder_git_cant_use_is_not_no_repository(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """git says "not a git repository" for these too. A plan made there would
    record nothing, and be run on any commit."""
    copied = tmp_path / "copied"  # a worktree, copied without what it points to
    copied.mkdir()
    (copied / ".git").write_text("gitdir: /nonexistent/.git/worktrees/x\n")
    with pytest.raises(SourceError, match="There is a `.git` here or above"):
        source.read(copied)

    project_dir = repo / "deploy"
    project_dir.mkdir()
    with monkeypatch.context() as patch:  # git told not to look above the folder
        patch.setenv("GIT_CEILING_DIRECTORIES", str(repo))
        with pytest.raises(SourceError, match="would be held to nothing"):
            source.read(project_dir)
    assert source.read(project_dir).root == "deploy"

    (repo / ".git" / "HEAD").write_text("garbage\n")
    with pytest.raises(SourceError, match="git says this is no repository"):
        source.read(repo)


def test_a_project_outside_the_checkout_git_names(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`GIT_DIR` and `GIT_WORK_TREE` naming another checkout: its tree says
    nothing about the files of this project."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("GIT_DIR", str(repo / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(repo))
    with pytest.raises(SourceError, match="is not in the checkout git names"):
        source.read(elsewhere)
    assert source.read(repo) == Source(head_tree(repo), root=".")


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
    """There is no tree to record, and the plan says so — whether or not
    anything is staged."""
    git(tmp_path, "init", "-q")
    (tmp_path / "lely.yml").write_text("steps: []\n")
    assert source.read(tmp_path) == Source(None, dirty=True, root=".")
    git(tmp_path, "add", ".")
    assert source.read(tmp_path) == Source(None, dirty=True, root=".")

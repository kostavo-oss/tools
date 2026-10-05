"""Which version of the project a plan was made from: the git tree.

An edge: it runs `git`. A plan file records the tree it was planned on, so that
what was reviewed is what is deployed — a plan approved for one commit is
refused on another. A bundle's notebooks and wheels are in no plan at all;
this is what ties them to the review.

What is recorded:

- **The tree of the whole repository at `HEAD`** — not the commit, so a merge
  that changes nothing keeps a plan valid. The whole repository and not only
  the folder the config is in, because a step can reach outside it: a bundle
  at `path: ../bundle`, or one that syncs files from next door. In a
  repository with several projects that makes a plan stale more often than it
  has to be; planning again is cheap, deploying what nobody reviewed is not.
- **Without the plan file itself.** A plan that is committed to be reviewed — a
  destroy going through a pull request — would otherwise change the tree it
  records, and refuse itself.
- **Whether a tracked file had uncommitted changes.** Files git doesn't track
  yet are not seen.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from lely.model import Source
from lely.process import ProcessError, run


def read(root: Path, plan_file: Path | None = None) -> Source:
    """The repository's tree, or an empty `Source` outside a git repository.

    `plan_file` is the plan being written or run: it is left out.
    """
    top = _git(root, "rev-parse", "--show-toplevel")
    if top is None or _git(root, "rev-parse", "--verify", "--quiet", "HEAD") is None:
        return Source()
    left_out = _inside(Path(top), plan_file)
    tree = _tree(Path(top), left_out)
    if tree is None:
        return Source()
    return Source(tree=tree, dirty=_dirty(Path(top), left_out))


def _inside(top: Path, path: Path | None) -> str | None:
    """`path` as git names it — relative to the top — or `None` if it is
    somewhere else."""
    if path is None:
        return None
    try:
        return path.resolve().relative_to(top.resolve()).as_posix()
    except ValueError:
        return None


def _tree(top: Path, left_out: str | None) -> str | None:
    if left_out is None:
        return _git(top, "rev-parse", "--verify", "--quiet", "HEAD^{tree}")
    # `HEAD`, read into an index of its own, minus one file: git's own index
    # and the working tree are not touched.
    with tempfile.TemporaryDirectory(prefix="lely-tree-") as scratch:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(scratch) / "index")}
        if _git(top, "read-tree", "HEAD", env=env) is None:
            return None
        removed = _git(top, "update-index", "--force-remove", "--", left_out, env=env)
        if removed is None:
            return None
        return _git(top, "write-tree", env=env)


def _dirty(top: Path, left_out: str | None) -> bool:
    changed = _git(top, "status", "--porcelain", "--untracked-files=no", "-z")
    for entry in (changed or "").split("\0"):
        # `XY <path>`; a rename's old name follows as an entry of its own
        if len(entry) > 3 and entry[3:] != left_out:
            return True
    return False


def _git(root: Path, *args: str, env: dict[str, str] | None = None) -> str | None:
    try:
        result = run(["git", *args], root, env=env)
    except (ProcessError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip("\n")

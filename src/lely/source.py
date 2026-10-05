"""Which version of the project a plan was made from: the git tree.

An edge: it runs `git`. A plan file records the tree it was planned on, so that
what was reviewed is what is deployed — a plan approved for one commit is
refused on another. A bundle's notebooks and wheels are in no plan at all;
this is what ties them to the review.

What is recorded is the tree of the project's directory at `HEAD` — not the
commit, so a merge that changes nothing keeps a plan valid, and not the whole
repository, so another project in it doesn't make one stale — and whether any
tracked file under it had uncommitted changes. Files git doesn't track yet are
not seen: the plan file itself is usually one of them.
"""

from __future__ import annotations

from pathlib import Path

from lely.model import Source
from lely.process import ProcessError, run


def read(root: Path) -> Source:
    """The project's tree, or an empty `Source` outside a git repository."""
    tree = _git(root, "rev-parse", "--verify", "--quiet", "HEAD:./")
    if tree is None:
        return Source()
    changed = _git(root, "status", "--porcelain", "--untracked-files=no", "--", ".")
    return Source(tree=tree, dirty=bool(changed))


def _git(root: Path, *args: str) -> str | None:
    try:
        result = run(["git", *args], root)
    except (ProcessError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()

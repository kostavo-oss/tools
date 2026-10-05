"""Which version of the project a plan was made from: git's word for it.

An edge: it runs `git`. A plan file records what it was planned on, so that
what was reviewed is what is deployed — a plan approved for one commit is
refused on another. A bundle's notebooks and wheels are in no plan at all;
this is what ties them to the review.

What is recorded:

- **`tree`: every tracked file as it is on disk**, as one git tree. On a clean
  checkout that is `HEAD`'s tree — not the commit, so a merge that changes
  nothing keeps a plan valid. With uncommitted changes it is the tree those
  changes would make, so a plan made on a changed checkout is held to exactly
  those changes instead of to nothing.
- **Of the whole repository**, not only the folder the config is in: a step can
  reach outside it — a bundle at `path: ../bundle`. In a repository with
  several projects that makes a plan stale more often than it has to be;
  planning again is cheap, deploying what nobody reviewed is not.
- **`root`: which project in that repository** — the config's folder, from the
  top. Two projects that share a tree are still two projects.
- **Without the plan file itself.** A plan committed to be reviewed — a destroy
  going through a pull request — would otherwise change the tree it records,
  and refuse itself. Only that one file: a second plan file in the repository
  is a change like any other.
- **`dirty`**: whether a tracked file had uncommitted changes. For the reader;
  the tree already holds them.

Files git doesn't track yet are not seen.

Nothing of the user's is written: the tree is made in an index and an object
store of its own, in a scratch folder. And only git's own "not a git
repository" means that — any other failure fails the plan, because a plan that
quietly recorded nothing would be held to nothing.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from lely.errors import LelyError
from lely.model import Source
from lely.process import ProcessError, run

#: Variables that name paths git resolves from its working directory. A git
#: hook sets them relative to the top; lely runs git somewhere else.
_PATHS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
)


class SourceError(LelyError):
    """git is there and couldn't say which version of the project this is."""


def read(root: Path, plan_file: Path | None = None) -> Source:
    """What the project at `root` is on, or an empty `Source` outside a git
    repository. `plan_file` is the plan being written or run: it is left out.
    """
    top = _top(root)
    if top is None:
        return Source()
    left_out = _inside(top, plan_file)
    changed = [path for path in _changed(top) if path != left_out]
    # A file git was told not to look at can't be vouched for by `git status`:
    # then everything is read again, whatever status says.
    reread = bool(changed) or _has_hidden(top)
    return Source(
        tree=_tree(top, left_out, reread),
        dirty=bool(changed),
        root=_inside(top, root) or ".",
    )


def _top(root: Path) -> Path | None:
    """The top of the repository `root` is in; `None` if it is in none."""
    try:
        result = run(["git", "rev-parse", "--show-toplevel"], root, env=_env())
    except ProcessError as error:
        if _looks_like_a_repository(root):
            raise SourceError(
                f"This is a git repository, and git couldn't be run: {error} A plan "
                "made here couldn't be held to the version it was made on."
            ) from None
        return None
    if result.returncode == 0:
        return Path(result.stdout.strip("\n"))
    said = result.stderr.strip()
    if "not a git repository" in said.lower():
        return None
    raise SourceError(_failed("`git rev-parse`", said))


def _looks_like_a_repository(root: Path) -> bool:
    return any((folder / ".git").exists() for folder in (root, *root.parents))


def _inside(top: Path, path: Path | None) -> str | None:
    """`path` as git names it — relative to the top — or `None` if it is
    somewhere else."""
    if path is None:
        return None
    try:
        return path.resolve().relative_to(top.resolve()).as_posix()
    except ValueError:
        return None


def _changed(top: Path) -> list[str]:
    """Every tracked path with an uncommitted change, both names of a rename."""
    said = _git(top, "status", "--porcelain", "--untracked-files=no", "-z")
    fields = said.split("\0")
    paths: list[str] = []
    at = 0
    while at < len(fields):
        entry = fields[at]
        at += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            # with `-z`, the name it was renamed or copied from follows
            if at < len(fields):
                paths.append(fields[at])
            at += 1
    return paths


def _has_hidden(top: Path) -> bool:
    """Whether any file is marked `assume-unchanged` or `skip-worktree`: git
    then reports it as it was, not as it is."""
    listed = _git(top, "ls-files", "-v", "-z")
    return any(
        entry[:1] == "S" or entry[:1].islower() for entry in listed.split("\0") if entry
    )


def _tree(top: Path, left_out: str | None, reread: bool) -> str:
    """The tree of every tracked file as it is on disk, without `left_out`.

    `reread` is false for a clean checkout: then it is `HEAD`'s tree, and no
    file has to be read.
    """
    has_head = _try(top, "rev-parse", "--verify", "--quiet", "HEAD") is not None
    in_head = (
        has_head
        and left_out is not None
        and bool(_git(top, "ls-tree", "HEAD", "--", left_out))
    )
    if has_head and not reread and not in_head:
        return _git(top, "rev-parse", "--verify", "HEAD^{tree}")
    objects = Path(_git(top, "rev-parse", "--git-path", "objects"))
    with tempfile.TemporaryDirectory(prefix="lely-tree-") as scratch:
        # An index and an object store of its own: git's index, the working
        # tree and the repository's objects are read and never written.
        store = Path(scratch) / "objects"
        store.mkdir()
        env = _env()
        shared = [str(objects if objects.is_absolute() else top / objects)]
        if env.get("GIT_ALTERNATE_OBJECT_DIRECTORIES"):
            shared.append(env["GIT_ALTERNATE_OBJECT_DIRECTORIES"])
        env |= {
            "GIT_INDEX_FILE": str(Path(scratch) / "index"),
            "GIT_OBJECT_DIRECTORY": str(store),
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": os.pathsep.join(shared),
        }
        if has_head:
            _git(top, "read-tree", "HEAD", env=env)
        if reread:
            _git(top, "add", "--update", "--", ".", env=env)
        if left_out is not None:
            _git(top, "update-index", "--force-remove", "--", left_out, env=env)
        return _git(top, "write-tree", env=env)


def _env() -> dict[str, str]:
    env = dict(os.environ)
    for name in _PATHS:
        if env.get(name) and not Path(env[name]).is_absolute():
            env[name] = str(Path.cwd() / env[name])
    if env.get("GIT_DIR") and not env.get("GIT_WORK_TREE"):
        # as in a hook: git then takes the working directory for the top, and
        # the one lely runs git in is the project's folder, not the top
        env["GIT_WORK_TREE"] = str(Path.cwd())
    # nothing lely asks of git may write to the repository, not even to
    # refresh its index; and git's words are read, so they are in English
    env |= {"GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"}
    return env


def _git(top: Path, *args: str, env: dict[str, str] | None = None) -> str:
    """What git prints, or a `SourceError` in git's own words."""
    try:
        result = run(["git", *args], top, env=env or _env())
    except ProcessError as error:
        raise SourceError(_failed(f"`git {args[0]}`", str(error))) from None
    if result.returncode != 0:
        raise SourceError(_failed(f"`git {args[0]}`", result.stderr.strip()))
    return result.stdout.strip("\n")


def _try(top: Path, *args: str) -> str | None:
    try:
        result = run(["git", *args], top, env=_env())
    except ProcessError:
        return None
    return result.stdout.strip("\n") if result.returncode == 0 else None


def _failed(command: str, said: str) -> str:
    return (
        f"git couldn't say which version of the project this is ({command} failed), "
        "and a plan that recorded nothing would be held to nothing:\n"
        f"{said or '(git said nothing)'}"
    )

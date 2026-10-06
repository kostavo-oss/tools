"""Which version of the project a plan was made from: git's word for it.

An edge: it runs `git`. A plan file records what it was planned on, so that
what was reviewed is what is deployed — a plan approved for one commit is
refused on another. A bundle's notebooks and wheels are in no plan at all;
this is what ties them to the review.

The rule is a plain one: **a plan file is for a clean checkout.** What is
recorded:

- **`tree`: `HEAD`'s tree, of the whole repository.** Not the commit, so a
  merge that changes nothing keeps a plan valid. The whole repository and not
  only the folder the config is in, because a step can reach outside it — a
  bundle at `path: ../bundle`. In a repository with several projects that
  makes a plan stale more often than it has to be; planning again is cheap,
  deploying what nobody reviewed is not.
- **`root`: which project in that repository** — the config's folder, from the
  top, as git names it. Two projects that share a tree are still two projects.
- **`dirty`: whether anything differs from `HEAD`** — a changed, staged, added
  or removed file, a submodule that moved or has changes of its own, a file
  git was told not to look at. A plan made on such a checkout says so and is
  not run from a file: lely could not say what it was made on. Neither is any
  plan run from a file on such a checkout.
- **Without the plan file itself**, in the tree and in what counts as a
  change. A plan committed to be reviewed — a destroy going through a pull
  request — would otherwise change the tree it records, and refuse itself.
  Only that one file.
- **Without what a sparse checkout leaves out.** The tree is the tree of what
  is checked out, so a plan made on a whole checkout isn't run on part of one:
  the files a step would read are not all there.

Files git doesn't track yet are not seen, in a submodule either. A repository
with no commit yet has no tree to record, and the plan says so.

Only git's own "not a git repository" means that, and only where nothing
looks like one — any other failure fails the plan, because a plan that quietly
recorded nothing would be held to nothing. And lely writes nothing to the
repository: no index, no ref, no object; nor does it fetch one. (A tree it has
to make — `HEAD`'s without a tracked plan file, or without what isn't checked
out — is made in an index and an object store of its own.)
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence
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

#: Settings under which git would write beside the index it is given.
_QUIET = ("-c", "core.splitIndex=false", "-c", "core.fsmonitor=false")


class SourceError(LelyError):
    """git is there and couldn't say which version of the project this is."""


def read(root: Path, plan_file: Path | None = None) -> Source:
    """What the project at `root` is on, or an empty `Source` outside a git
    repository. `plan_file` is the plan being written or run: it is left out.
    """
    top = _top(root)
    if top is None:
        return Source()
    if _git(root, "rev-parse", "--is-inside-work-tree") != "true":
        # `GIT_DIR` naming a checkout somewhere else, or a folder inside `.git`
        raise SourceError(
            f"git couldn't say which version of the project this is: {root} is not "
            f"in the checkout git names ({top}), and a plan held to another "
            "project's files would be held to nothing."
        )
    # as git names it, so a path spelled another way is still the same folder
    project = _git(root, "rev-parse", "--show-prefix").rstrip("/") or "."
    left_out = _named(top, plan_file)
    changed = [path for path in _changed(top) if path != left_out]
    hidden, absent = _unseen(top)
    dirty = bool(changed) or hidden
    if _try(top, "rev-parse", "--verify", "--quiet", "HEAD") is None:
        return Source(tree=None, dirty=True, root=project)  # no commit yet
    return Source(tree=_tree(top, left_out, absent), dirty=dirty, root=project)


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
    if "not a git repository" not in said.lower():
        raise SourceError(_failed("`git rev-parse`", said))
    if _looks_like_a_repository(root):
        # a worktree or a submodule copied without what it points to, a broken
        # `HEAD`, a `GIT_CEILING_DIRECTORIES` in the way
        raise SourceError(
            "There is a `.git` here or above, and git says this is no repository. "
            + _failed("`git rev-parse`", said)
        )
    return None


def _looks_like_a_repository(root: Path) -> bool:
    root = root.absolute()
    return any(os.path.lexists(folder / ".git") for folder in (root, *root.parents))


def _named(top: Path, path: Path | None) -> str | None:
    """`path` as git names it — from the top — or `None` if it isn't in this
    repository. git is asked, so a folder spelled in another case is still the
    same folder."""
    if path is None:
        return None
    folder = path.resolve().parent
    if not folder.is_dir():
        return None
    its_top = _try(folder, "rev-parse", "--show-toplevel")
    # as paths: on Windows git writes `C:/…` for what Python writes `C:\…`
    if its_top is None or Path(its_top) != top:
        return None
    prefix = _try(folder, "rev-parse", "--show-prefix")
    return None if prefix is None else prefix + path.name


def _changed(top: Path) -> list[str]:
    """Every tracked path that differs from `HEAD`, both names of a rename. A
    submodule counts whatever the repository was told to ignore about it —
    but for files it doesn't track, which are seen there as little as here."""
    said = _git(
        top,
        "status",
        "--porcelain",
        "--untracked-files=no",
        "--ignore-submodules=untracked",
        "-z",
    )
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


def _unseen(top: Path) -> tuple[bool, list[str]]:
    """What `git status` doesn't speak of: whether git was told not to look at
    a file that is there — it then reports the file as it was, not as it is,
    and lely can't vouch for it — and which files are not checked out at all.

    `assume-unchanged` always hides. `skip-worktree` hides a file that is on
    disk, a link to nowhere included; in a sparse checkout the file isn't, and
    is one the tree is made without.
    """
    hidden = False
    absent: list[str] = []
    for entry in _git(top, "ls-files", "-v", "-z").split("\0"):
        tag, path = entry[:1], entry[2:]
        if not path:
            continue
        if tag.islower() or (tag == "S" and os.path.lexists(top / path)):
            hidden = True
        elif tag == "S":
            absent.append(path)
    return hidden, absent


def _tree(top: Path, plan_file: str | None, absent: Sequence[str]) -> str:
    """`HEAD`'s tree, without the plan file if that is tracked and without the
    files that aren't checked out."""
    without = list(absent)
    if plan_file is not None and _git(top, "ls-tree", "HEAD", "--", plan_file):
        without.append(plan_file)
    if not without:
        return _git(top, "rev-parse", "--verify", "HEAD^{tree}")
    objects = Path(_git(top, "rev-parse", "--git-path", "objects"))
    with tempfile.TemporaryDirectory(prefix="lely-tree-") as scratch:
        # An index and an object store of its own: the repository's are read
        # through an alternate and never written; its hooks are not run.
        store = Path(scratch) / "objects"
        store.mkdir()
        hooks = Path(scratch) / "no-hooks"
        hooks.mkdir()
        env = _env()
        shared = [_listed(objects if objects.is_absolute() else top / objects)]
        if env.get("GIT_ALTERNATE_OBJECT_DIRECTORIES"):
            shared.append(env["GIT_ALTERNATE_OBJECT_DIRECTORIES"])
        env |= {
            "GIT_INDEX_FILE": str(Path(scratch) / "index"),
            "GIT_OBJECT_DIRECTORY": str(store),
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": os.pathsep.join(shared),
        }
        quiet = ("-c", f"core.hooksPath={hooks}", "-c", "index.sparse=false")
        _git(top, *quiet, "read-tree", "HEAD", env=env)
        _git(
            top,
            *quiet,
            "update-index",
            "--force-remove",
            "-z",
            "--stdin",
            env=env,
            given="".join(f"{path}\0" for path in without),
        )
        # `--missing-ok`: a tree is made of names. In a clone without all of
        # its files, git has no need to go and fetch one to look at it.
        return _git(top, *quiet, "write-tree", "--missing-ok", env=env)


def _listed(path: Path) -> str:
    """A path as an entry of `GIT_ALTERNATE_OBJECT_DIRECTORIES`: quoted the way
    git reads it when it holds the character that separates the entries."""
    text = str(path)
    if os.pathsep not in text and not text.startswith('"'):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


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


def _git(
    folder: Path,
    *args: str,
    env: dict[str, str] | None = None,
    given: str | None = None,
) -> str:
    """What git prints, or a `SourceError` in git's own words."""
    try:
        result = run(["git", *_QUIET, *args], folder, env=env or _env(), given=given)
    except ProcessError as error:
        raise SourceError(_failed(_verb(args), str(error))) from None
    if result.returncode != 0:
        raise SourceError(_failed(_verb(args), result.stderr.strip()))
    return result.stdout.strip("\n")


def _try(folder: Path, *args: str) -> str | None:
    try:
        result = run(["git", *_QUIET, *args], folder, env=_env())
    except ProcessError:
        return None
    return result.stdout.strip("\n") if result.returncode == 0 else None


def _verb(args: tuple[str, ...]) -> str:
    """`git status`, from a command line that may start with `-c` settings."""
    words = list(args)
    while words[:1] == ["-c"]:
        words = words[2:]
    return f"`git {words[0] if words else ''}`"


def _failed(command: str, said: str) -> str:
    return (
        f"git couldn't say which version of the project this is ({command} failed), "
        "and a plan that recorded nothing would be held to nothing:\n"
        f"{said or '(git said nothing)'}"
    )

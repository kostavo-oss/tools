"""Finding the plugin a `uses:` names.

Three spellings:

1. A registered name — `bundle`, `bundle.run` — from the entry-point group
   `lely.steps`. The plugins lely ships register exactly as anyone's would.
2. `package.module:Class`, importable from the environment lely runs in.
3. `./path/to/file.py:Class`, a file in the repo, relative to the config.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import importlib.util
import inspect
import re
import sys
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path

from lely.errors import LelyError

GROUP = "lely.steps"


class StepNotFound(LelyError):
    """A `uses:` that names no plugin, or something that isn't one."""


@dataclass(frozen=True, slots=True)
class Found:
    uses: str
    cls: type
    source: str
    #: The plugin's `Options` dataclass; set once `find` has checked there is one.
    options: type = object


def installed() -> dict[str, EntryPoint]:
    return {ep.name: ep for ep in entry_points(group=GROUP)}


def find(uses: str, root: Path) -> Found:
    if uses.startswith(("./", "../")):
        found = _from_file(uses, root)
    elif ":" in uses:
        found = _from_module(uses)
    else:
        found = _from_entry_point(uses)
    return _check(found)


def _from_entry_point(uses: str) -> Found:
    points = installed()
    if uses not in points:
        known = ", ".join(sorted(points)) or "none"
        raise StepNotFound(
            f"No plugin named `{uses}` is installed (installed: {known}). One in the "
            "repo is `./path/file.py:Class`; one in a package is `module:Class`."
        )
    point = points[uses]
    try:
        cls = point.load()
    except Exception as error:  # a plugin's import error is its own
        raise StepNotFound(f"Plugin `{uses}` failed to load: {error}") from error
    dist = point.dist.name if point.dist else "?"
    source = "built-in" if dist == "lely" else f"from {dist}"
    return Found(uses, cls, source)


def _from_module(uses: str) -> Found:
    module_name, _, attr = uses.partition(":")
    if not module_name or not attr or module_name.startswith("."):
        raise StepNotFound(
            f"`{uses}`: a plugin in a package is `package.module:Class`; one in the "
            "repo is `./path/file.py:Class`"
        )
    try:
        module = importlib.import_module(module_name)
    except Exception as error:  # a plugin's import error is its own
        raise StepNotFound(f"`{uses}`: can't import `{module_name}`: {error}") from error
    return Found(uses, _attr(module, attr, uses), f"module {module_name}")


def _from_file(uses: str, root: Path) -> Found:
    relative, _, attr = uses.rpartition(":")
    if not relative or not attr:
        raise StepNotFound(f"`{uses}`: a plugin in a file is `./path/file.py:Class`")
    path = (root / relative).resolve()
    if not path.is_file():
        raise StepNotFound(f"`{uses}`: there is no file {path}")
    # One module per file, named after its path, so type hints resolve and a
    # file two plugins share is imported once.
    name = "lely_local_" + hashlib.sha256(str(path).encode()).hexdigest()[:12]
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:  # pragma: no cover
            raise StepNotFound(f"`{uses}`: can't load {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as error:
            del sys.modules[name]
            raise StepNotFound(f"`{uses}`: {path} failed to load: {error}") from error
    return Found(uses, _attr(module, attr, uses), f"file {relative}")


def _attr(module: object, attr: str, uses: str) -> type:
    cls = getattr(module, attr, None)
    if not isinstance(cls, type):
        raise StepNotFound(f"`{uses}`: there is no class `{attr}` there")
    return cls


def _check(found: Found) -> Found:
    cls = found.cls
    options = getattr(cls, "Options", None)
    problems = []
    if not (isinstance(options, type) and dataclasses.is_dataclass(options)):
        problems.append("an `Options` dataclass")
    for method in ("plan", "apply"):
        if not callable(getattr(cls, method, None)):
            problems.append(f"a `{method}` method")
    # destroying is planned first, like everything else: one without the other
    # is a plugin half written
    halves = [callable(getattr(cls, m, None)) for m in ("plan_destroy", "destroy")]
    if halves == [True, False]:
        problems.append("a `destroy` method to go with `plan_destroy`")
    if halves == [False, True]:
        problems.append("a `plan_destroy` method to go with `destroy`")
    if problems:
        raise StepNotFound(
            f"`{found.uses}` ({cls.__qualname__}) isn't a plugin: it needs "
            + " and ".join(problems)
        )
    assert isinstance(options, type)
    return dataclasses.replace(found, options=options)


def option_docs(options: type) -> dict[str, str]:
    """What a plugin's author wrote above each option, as `#:` comments.

        #: The directory holding `databricks.yml`, relative to the config.
        path: str = "."

    Read from the plugin's source, for the editors' schema. A plugin whose
    source isn't there to read has none.
    """
    try:
        source = inspect.getsource(options)
    except (OSError, TypeError):
        return {}
    docs: dict[str, str] = {}
    above: list[str] = []
    for line in source.splitlines():
        text = line.strip()
        if text.startswith("#:"):
            above.append(text[2:].strip())
            continue
        named = re.match(r"(\w+)\s*:", text)
        if named and above:
            docs[named.group(1)] = " ".join(above)
        above = []
    return docs

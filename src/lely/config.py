"""The project's config in, one list of steps out.

`lely.yml`, or `[tool.lely]` in `pyproject.toml`, with the same keys and the
same meaning. This is the only place that reads either. Both become the same
tree of located nodes (`Scalar`, `Seq`, `Map`), so every error can point at the
file, line and column it came from, and a step's `with:` block stays located
until its plugin's `Options` class is known (`options.py`).

YAML is read through its node tree, which keeps every position. TOML is read
with `tomllib`, which keeps none: `_TomlPositions` finds each key again by
scanning the text in the order the keys were read — exact for a file written
the usual way, a best effort otherwise.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

import yaml
from yaml.constructor import SafeConstructor
from yaml.nodes import MappingNode, ScalarNode, SequenceNode
from yaml.nodes import Node as YamlNode

from lely.errors import LelyError
from lely.model import Json

CONFIG_FILE = "lely.yml"
PYPROJECT = "pyproject.toml"

#: Every key the config accepts at the top, and in a step. Anything else is an
#: error where it was written.
TOP_KEYS = ("steps",)
STEP_KEYS = ("name", "uses", "with", "targets")

#: A step's name is what `${steps.<name>.…}` says, so it is one path part.
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")


@dataclass(frozen=True, slots=True)
class Loc:
    file: str
    line: int
    column: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.column}"


@dataclass(frozen=True, slots=True)
class Scalar:
    value: str | int | float | bool | None
    loc: Loc


@dataclass(frozen=True, slots=True)
class Seq:
    items: tuple[Node, ...]
    loc: Loc


@dataclass(frozen=True, slots=True)
class Entry:
    key: str
    key_loc: Loc
    value: Node


@dataclass(frozen=True, slots=True)
class Map:
    entries: tuple[Entry, ...]
    loc: Loc

    def get(self, key: str) -> Node | None:
        for entry in self.entries:
            if entry.key == key:
                return entry.value
        return None


Node: TypeAlias = Scalar | Seq | Map


class ConfigError(LelyError):
    """The config can't be read; every problem found, one per line."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(problems))


@dataclass(frozen=True, slots=True)
class StepConfig:
    name: str
    uses: str
    options: Map | None
    targets: tuple[str, ...] | None
    loc: Loc

    def runs_for(self, target: str) -> bool:
        return self.targets is None or target in self.targets


@dataclass(frozen=True, slots=True)
class Config:
    path: Path
    steps: tuple[StepConfig, ...]

    @property
    def root(self) -> Path:
        """The project's directory: a step's paths are relative to it."""
        return self.path.parent

    def step(self, name: str) -> StepConfig | None:
        for step in self.steps:
            if step.name == name:
                return step
        return None


def written(node: Node | None) -> Json:
    """A `with:` block as plain values, references as they were written."""
    if node is None:
        return None
    if isinstance(node, Seq):
        return [written(child) for child in node.items]
    if isinstance(node, Map):
        return {entry.key: written(entry.value) for entry in node.entries}
    return node.value


def find(start: Path) -> Path:
    """The config for a command run in `start`: the nearest one, looking up."""
    for folder in (start, *start.parents):
        own = folder / CONFIG_FILE
        shared = folder / PYPROJECT
        in_pyproject = shared.is_file() and _has_section(shared)
        if own.is_file() and in_pyproject:
            raise ConfigError(
                [
                    f"{own} and the `[tool.lely]` section of {shared} both configure "
                    "lely. Keep one of the two: lely doesn't merge them and doesn't pick."
                ]
            )
        if own.is_file():
            return own
        if in_pyproject:
            return shared
        misnamed = folder / "lely.yaml"
        if misnamed.is_file():
            raise ConfigError(
                [
                    f"{misnamed}: lely reads `{CONFIG_FILE}`. Rename it, or name "
                    "it with -c."
                ]
            )
    raise ConfigError(
        [
            f"No `{CONFIG_FILE}`, and no `{PYPROJECT}` with a `[tool.lely]` section, in "
            f"{start} or any folder above it."
        ]
    )


def load(path: Path) -> Config:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(
            [
                f"{path}: not found. lely reads `{CONFIG_FILE}`, or `[tool.lely]` in "
                f"`{PYPROJECT}`."
            ]
        ) from None
    except OSError as error:
        raise ConfigError([f"{path}: {error.strerror or error}"]) from None
    except UnicodeDecodeError:
        raise ConfigError([f"{path}: not a text file lely can read (UTF-8)."]) from None
    return load_text(text, path)


def load_text(text: str, path: Path) -> Config:
    reader = _Reader(str(path))
    if path.name == PYPROJECT:
        root, what = _toml(text, path), "[tool.lely]"
    else:
        root, what = _yaml(text, path, reader), "lely.yml"
    config = reader.config(root, path, what)
    if reader.problems:
        raise ConfigError(reader.problems)
    return config


# -- YAML -----------------------------------------------------------------------


def _yaml(text: str, path: Path, reader: _Reader) -> Node:
    try:
        node = yaml.compose(text, Loader=yaml.SafeLoader)
        if node is None:
            raise ConfigError([f"{path}: empty; it needs a `steps:` list."])
        return reader.node(node)
    except yaml.MarkedYAMLError as error:
        mark = error.problem_mark
        where = f"{path}:{mark.line + 1}:{mark.column + 1}" if mark else str(path)
        raise ConfigError([f"{where}: not valid YAML: {error.problem}"]) from None
    except yaml.YAMLError as error:  # a character YAML can't hold, and the like
        raise ConfigError([f"{path}: not valid YAML: {error}"]) from None
    except ValueError as error:  # a date that isn't one, a number too long to read
        raise ConfigError([f"{path}: a value lely can't read: {error}"]) from None
    except RecursionError:
        raise ConfigError(
            [f"{path}: an anchor refers to itself, or the file is nested too deep."]
        ) from None


# -- TOML -----------------------------------------------------------------------


def _has_section(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        tool = tomllib.loads(text).get("tool")
    except tomllib.TOMLDecodeError:
        # Broken, but about lely: `load` will say where.
        return _SECTION.search(text) is not None
    return isinstance(tool, dict) and "lely" in tool


_SECTION = re.compile(r"^[ \t]*(?:\[\[?[ \t]*)?tool[ \t]*\.[ \t]*lely\b", re.MULTILINE)


def _toml(text: str, path: Path) -> Node:
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError([f"{path}: not valid TOML: {error}"]) from None
    tool = document.get("tool")
    section = tool.get("lely") if isinstance(tool, dict) else None
    if section is None:
        raise ConfigError([f"{path}: it has no `[tool.lely]` section."])
    positions = _TomlPositions(text, str(path))
    return positions.node(section, positions.start())


_VALUE = re.compile(r"""["']|[-+0-9]|true|false|inf|nan""")
_WORD = re.compile(r"[\w.+:-]+")


class _TomlPositions:
    """Where each key and value of `[tool.lely]` was written.

    `tomllib` keeps keys in the order they appear, so one cursor moving forward
    through the text finds them again.
    """

    def __init__(self, text: str, file: str) -> None:
        self.text = text
        self.file = file
        self.cursor = 0
        self._starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def start(self) -> int:
        match = _SECTION.search(self.text)
        self.cursor = match.start() if match else 0
        return self.cursor

    def loc(self, offset: int) -> Loc:
        line = max(i for i, start in enumerate(self._starts) if start <= offset)
        return Loc(self.file, line + 1, offset - self._starts[line] + 1)

    def node(self, value: Any, at: int) -> Node:
        if isinstance(value, dict):
            inline = self.text.startswith("{", at)
            if inline:
                self.cursor = max(self.cursor, at + 1)
            entries = []
            for key, child in value.items():
                found = self._key(str(key))
                key_at = at if found is None else found
                entries.append(
                    Entry(
                        str(key), self.loc(key_at), self.node(child, self._value(key_at))
                    )
                )
            if inline:
                self._close("}")
            return Map(tuple(entries), self.loc(at))
        if isinstance(value, list):
            inline = self.text.startswith("[", at)
            if inline:
                self.cursor = max(self.cursor, at + 1)
            items = tuple(self._element(child, at) for child in value)
            if inline:
                self._close("]")
            return Seq(items, self.loc(at))
        if not isinstance(value, str | int | float | bool):
            value = str(value)  # dates and times: keep what was written
        self._skip_scalar(at)
        return Scalar(value, self.loc(at))

    def _close(self, bracket: str) -> None:
        """Move past the end of an inline table or array, so the next thing
        looked for isn't found inside it."""
        end = self.text.find(bracket, self.cursor)
        if end >= 0:
            self.cursor = end + 1

    def _key(self, key: str) -> int | None:
        """The next place `key` is written as a key, and the cursor past it."""
        name = re.escape(key)
        pattern = re.compile(
            rf"""(?<![\w-])(?:{name}|"{name}"|'{name}')(?=[ \t]*[=.\]])"""
        )
        match = pattern.search(self.text, self.cursor)
        if match is None:
            return None
        self.cursor = match.end()
        return match.start()

    def _value(self, key_at: int) -> int:
        """Where the value of the key at `key_at` starts: after its `=`."""
        match = re.compile(r"[^=\n]*=[ \t]*").match(self.text, key_at)
        if match is None or self.text[key_at:].lstrip().startswith("["):
            return key_at
        end = match.end()
        # `steps = [ … ]` and `[[…steps]]`: the elements are looked for from the key
        if not self.text.startswith("[", end):
            self.cursor = max(self.cursor, end)
        return end

    def _element(self, value: Any, at: int) -> Node:
        if isinstance(value, dict):
            # a table of an array: its `[[…]]` header, or an inline `{`
            match = re.compile(r"\]\]|\{").search(self.text, self.cursor)
            if match is None:
                return self.node(value, at)
            self.cursor = match.end()
            line_start = self.text.rfind("\n", 0, match.start()) + 1
            header = self.text.find("[[", line_start, match.start())
            return self.node(
                value, header if match.group() == "]]" and header >= 0 else match.start()
            )
        if isinstance(value, list):
            match = re.compile(r"\[").search(self.text, self.cursor)
            if match is not None:
                self.cursor = match.end()
            return self.node(value, match.start() if match else at)
        match = _VALUE.search(self.text, self.cursor)
        if match is None:
            return self.node(value, at)
        return self.node(value, match.start())

    def _skip_scalar(self, at: int) -> None:
        """Move the cursor past the scalar written at `at`, so nothing inside a
        string is taken for a key."""
        if at < self.cursor and not _VALUE.match(self.text, at):
            return
        quote = self.text[at : at + 1]
        if quote in ('"', "'"):
            triple = quote * 3
            if self.text.startswith(triple, at):
                end = self.text.find(triple, at + 3)
                self.cursor = max(self.cursor, len(self.text) if end < 0 else end + 3)
                return
            end = at + 1
            while end < len(self.text) and self.text[end] not in (quote, "\n"):
                end += 2 if self.text[end] == "\\" and quote == '"' else 1
            self.cursor = max(self.cursor, end + 1)
            return
        match = _WORD.match(self.text, at)
        if match is not None:
            self.cursor = max(self.cursor, match.end())


# -- the shape of a config ------------------------------------------------------


class _Reader:
    def __init__(self, file: str) -> None:
        self.file = file
        self.problems: list[str] = []
        self._constructor = SafeConstructor()

    def problem(self, loc: Loc, message: str) -> None:
        self.problems.append(f"{loc}: {message}")

    def loc(self, node: YamlNode) -> Loc:
        mark = node.start_mark
        return Loc(self.file, mark.line + 1, mark.column + 1)

    def node(self, node: YamlNode) -> Node:
        loc = self.loc(node)
        if isinstance(node, ScalarNode):
            value = self._constructor.construct_object(node)
            if not isinstance(value, str | int | float | bool) and value is not None:
                # Timestamps and the like: keep what was written.
                value = str(node.value)
            return Scalar(value, loc)
        if isinstance(node, SequenceNode):
            return Seq(tuple(self.node(child) for child in node.value), loc)
        if isinstance(node, MappingNode):
            entries: list[Entry] = []
            seen: set[str] = set()
            for key_node, value_node in node.value:
                key_loc = self.loc(key_node)
                if not isinstance(key_node, ScalarNode) or not isinstance(
                    self._constructor.construct_object(key_node), str
                ):
                    self.problem(key_loc, "keys must be plain strings")
                    continue
                key = str(key_node.value)
                if key in seen:
                    self.problem(key_loc, f"`{key}` appears twice")
                    continue
                seen.add(key)
                entries.append(Entry(key, key_loc, self.node(value_node)))
            return Map(tuple(entries), loc)
        raise AssertionError(f"unexpected YAML node {node!r}")  # pragma: no cover

    def mapping(self, node: Node, what: str, known: tuple[str, ...]) -> Map | None:
        if not isinstance(node, Map):
            self.problem(node.loc, f"{what} must be a mapping")
            return None
        for entry in node.entries:
            if entry.key not in known:
                self.problem(
                    entry.key_loc,
                    f"unknown key `{entry.key}` in {what}; expected "
                    + ("one of " if len(known) > 1 else "")
                    + ", ".join(known),
                )
        return node

    def string(self, node: Node | None, what: str, loc: Loc) -> str | None:
        if node is None:
            self.problem(loc, f"{what} is required")
            return None
        if not isinstance(node, Scalar) or not isinstance(node.value, str):
            self.problem(node.loc, f"{what} must be a string")
            return None
        return node.value

    def config(self, root: Node, path: Path, what: str) -> Config:
        top = self.mapping(root, what, TOP_KEYS)
        steps: tuple[StepConfig, ...] = ()
        if top is not None:
            steps = self.steps(top.get("steps"))
            if not steps and not self.problems:
                self.problem(top.loc, "no steps: add at least one under `steps`")
        self.unique_names(steps)
        return Config(path=path, steps=steps)

    def steps(self, node: Node | None) -> tuple[StepConfig, ...]:
        if node is None:
            return ()
        if not isinstance(node, Seq):
            self.problem(node.loc, "`steps` must be a list of steps")
            return ()
        steps = (self.step(child) for child in node.items)
        return tuple(step for step in steps if step is not None)

    def step(self, node: Node) -> StepConfig | None:
        block = self.mapping(node, "a step", STEP_KEYS)
        if block is None:
            return None
        uses = self.string(block.get("uses"), "`uses`", block.loc)
        if uses is None:
            return None
        name_node = block.get("name")
        if name_node is None:
            if not _NAME.match(uses):
                self.problem(
                    block.loc,
                    f"step `{uses}` needs a `name`: only a plain plugin name like "
                    "`bundle` doubles as one",
                )
                return None
            name = uses
        else:
            name = self.string(name_node, "`name`", block.loc)
            if name is None:
                return None
            if not _NAME.match(name):
                self.problem(
                    name_node.loc,
                    f"step name `{name}` must be letters, digits, `_` or `-` — it "
                    "is what `${steps.<name>.…}` says",
                )
                return None
        options = block.get("with")
        if options is not None and not isinstance(options, Map):
            self.problem(options.loc, f"`with` of step `{name}` must be a mapping")
            options = None
        return StepConfig(
            name=name,
            uses=uses,
            options=options if isinstance(options, Map) else None,
            targets=self.targets(block.get("targets"), name),
            loc=block.loc,
        )

    def targets(self, node: Node | None, name: str) -> tuple[str, ...] | None:
        if node is None:
            return None
        if not isinstance(node, Seq) or not all(
            isinstance(child, Scalar) and isinstance(child.value, str)
            for child in node.items
        ):
            self.problem(node.loc, f"`targets` of step `{name}` must be a list of names")
            return None
        return tuple(
            str(child.value) for child in node.items if isinstance(child, Scalar)
        )

    def unique_names(self, steps: tuple[StepConfig, ...]) -> None:
        seen: dict[str, StepConfig] = {}
        for step in steps:
            if step.name in seen:
                self.problem(
                    step.loc,
                    f"two steps are named `{step.name}` (the other is at "
                    f"{seen[step.name].loc}); give one a `name`",
                )
            seen.setdefault(step.name, step)

"""`lely.yml` in, config out.

This is the only place that reads YAML. The file is read through the YAML
*node* tree rather than `safe_load`, so every error can point at the line and
column it came from. A step's `with:` block is kept as located items (`Scalar`,
`Seq`, `Map`) rather than plain values: which keys it may hold is the step's
business, decided once its `Options` class is known (`options.py`), and that
check wants locations too.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

import yaml
from yaml.constructor import SafeConstructor
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from lely.errors import LelyError
from lely.model import Phase

CONFIG_FILE = "lely.yml"

#: Every key the file accepts at the top, and in a step. Anything else is an
#: error where it was written.
TOP_KEYS = ("bundle", "pre", "bundle_vars", "post")
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
    items: tuple[Item, ...]
    loc: Loc


@dataclass(frozen=True, slots=True)
class Entry:
    key: str
    key_loc: Loc
    value: Item


@dataclass(frozen=True, slots=True)
class Map:
    entries: tuple[Entry, ...]
    loc: Loc

    def get(self, key: str) -> Item | None:
        for entry in self.entries:
            if entry.key == key:
                return entry.value
        return None


Item: TypeAlias = Scalar | Seq | Map


class ConfigError(LelyError):
    """`lely.yml` can't be read; every problem found, one per line."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(problems))


@dataclass(frozen=True, slots=True)
class StepConfig:
    name: str
    uses: str
    phase: Phase
    options: Map | None
    targets: tuple[str, ...] | None
    loc: Loc

    def runs_for(self, target: str) -> bool:
        return self.targets is None or target in self.targets


@dataclass(frozen=True, slots=True)
class Config:
    path: Path
    bundle_dir: Path
    pre: tuple[StepConfig, ...]
    bundle_vars: Map | None
    post: tuple[StepConfig, ...]
    digest: str = field(repr=False)

    @property
    def root(self) -> Path:
        return self.path.parent

    @property
    def steps(self) -> tuple[StepConfig, ...]:
        return self.pre + self.post


def load(path: Path) -> Config:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(
            [f"{path}: not found. lely reads `{CONFIG_FILE}` next to `databricks.yml`."]
        ) from None
    return load_text(text, path)


def load_text(text: str, path: Path) -> Config:
    reader = _Reader(str(path))
    try:
        node = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.MarkedYAMLError as error:
        mark = error.problem_mark
        where = f"{path}:{mark.line + 1}:{mark.column + 1}" if mark else str(path)
        raise ConfigError([f"{where}: not valid YAML: {error.problem}"]) from None
    if node is None:
        raise ConfigError(
            [f"{path}: empty; it needs at least one step under pre or post."]
        )
    config = reader.config(reader.item(node), path, text)
    if reader.problems:
        raise ConfigError(reader.problems)
    return config


class _Reader:
    def __init__(self, file: str) -> None:
        self.file = file
        self.problems: list[str] = []
        self._constructor = SafeConstructor()

    def problem(self, loc: Loc, message: str) -> None:
        self.problems.append(f"{loc}: {message}")

    def loc(self, node: Node) -> Loc:
        mark = node.start_mark
        return Loc(self.file, mark.line + 1, mark.column + 1)

    def item(self, node: Node) -> Item:
        loc = self.loc(node)
        if isinstance(node, ScalarNode):
            value = self._constructor.construct_object(node)
            if not isinstance(value, str | int | float | bool) and value is not None:
                # Timestamps and the like: keep what was written.
                value = str(node.value)
            return Scalar(value, loc)
        if isinstance(node, SequenceNode):
            return Seq(tuple(self.item(child) for child in node.value), loc)
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
                entries.append(Entry(key, key_loc, self.item(value_node)))
            return Map(tuple(entries), loc)
        raise AssertionError(f"unexpected YAML node {node!r}")  # pragma: no cover

    def mapping(self, item: Item, what: str, known: tuple[str, ...]) -> Map | None:
        if not isinstance(item, Map):
            self.problem(item.loc, f"{what} must be a mapping")
            return None
        for entry in item.entries:
            if entry.key not in known:
                self.problem(
                    entry.key_loc,
                    f"unknown key `{entry.key}` in {what}; expected one of "
                    f"{', '.join(known)}",
                )
        return item

    def string(self, item: Item | None, what: str, loc: Loc) -> str | None:
        if item is None:
            self.problem(loc, f"{what} is required")
            return None
        if not isinstance(item, Scalar) or not isinstance(item.value, str):
            self.problem(item.loc, f"{what} must be a string")
            return None
        return item.value

    def config(self, root: Item, path: Path, text: str) -> Config:
        top = self.mapping(root, "lely.yml", TOP_KEYS)
        bundle_dir = path.parent
        pre: tuple[StepConfig, ...] = ()
        post: tuple[StepConfig, ...] = ()
        bundle_vars: Map | None = None
        if top is not None:
            bundle = top.get("bundle")
            if bundle is not None:
                where = self.string(bundle, "`bundle`", top.loc)
                if where is not None:
                    bundle_dir = path.parent / where
            pre = self.steps(top.get("pre"), "pre")
            post = self.steps(top.get("post"), "post")
            bundle_vars = self.bundle_vars(top.get("bundle_vars"))
            if not pre and not post and not self.problems:
                self.problem(top.loc, "no steps: add at least one under pre or post")
        self.unique_names(pre + post)
        return Config(
            path=path,
            bundle_dir=bundle_dir,
            pre=pre,
            bundle_vars=bundle_vars,
            post=post,
            digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )

    def steps(self, item: Item | None, phase: Phase) -> tuple[StepConfig, ...]:
        if item is None:
            return ()
        if not isinstance(item, Seq):
            self.problem(item.loc, f"`{phase}` must be a list of steps")
            return ()
        steps = (self.step(child, phase) for child in item.items)
        return tuple(step for step in steps if step is not None)

    def step(self, item: Item, phase: Phase) -> StepConfig | None:
        block = self.mapping(item, f"a {phase} step", STEP_KEYS)
        if block is None:
            return None
        uses = self.string(block.get("uses"), "`uses`", block.loc)
        if uses is None:
            return None
        name_item = block.get("name")
        if name_item is None:
            if not _NAME.match(uses):
                self.problem(
                    block.loc,
                    f"step `{uses}` needs a `name`: only a plain step name like "
                    "`stevin` doubles as one",
                )
                return None
            name = uses
        else:
            name = self.string(name_item, "`name`", block.loc)
            if name is None:
                return None
            if not _NAME.match(name):
                self.problem(
                    name_item.loc,
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
            phase=phase,
            options=options if isinstance(options, Map) else None,
            targets=self.targets(block.get("targets"), name),
            loc=block.loc,
        )

    def targets(self, item: Item | None, name: str) -> tuple[str, ...] | None:
        if item is None:
            return None
        if not isinstance(item, Seq) or not all(
            isinstance(child, Scalar) and isinstance(child.value, str)
            for child in item.items
        ):
            self.problem(item.loc, f"`targets` of step `{name}` must be a list of names")
            return None
        return tuple(
            str(child.value) for child in item.items if isinstance(child, Scalar)
        )

    def bundle_vars(self, item: Item | None) -> Map | None:
        if item is None:
            return None
        if not isinstance(item, Map):
            self.problem(item.loc, "`bundle_vars` must be a mapping of variable to value")
            return None
        for entry in item.entries:
            if not isinstance(entry.value, Scalar) or entry.value.value is None:
                self.problem(
                    entry.value.loc,
                    f"bundle variable `{entry.key}` must be a single value; complex "
                    "variables aren't passed by lely yet",
                )
        return item

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

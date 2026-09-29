"""A step's `with:` block, into the step's own `Options` dataclass.

A step declares its options as a frozen dataclass; this reads the located YAML
into it, strictly: an unknown key, a missing required one or a wrong type is an
error at the line and column it was written. References in string values are
resolved on the way in (by a callback, so this module stays pure), and a value
decided at apply makes the whole block `Unresolved` — the core then plans the
step as deferred rather than calling it with half its options.

The field types a step may use: `str`, `int`, `float`, `bool`, `Secret`,
`Literal[...]`, `tuple[T, ...]`, `Mapping[str, T]` (or `dict`), `T | None`, and
`object` for anything JSON.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from sluis.config import Item, Map, Scalar, Seq
from sluis.errors import SluisError
from sluis.model import Secret, Value
from sluis.refs import Unknown

Resolver = Callable[[Scalar], Value | Unknown]


class OptionsError(SluisError):
    """A step's `with:` block doesn't fit its options; every problem, one per line."""


@dataclass(frozen=True, slots=True)
class Unresolved:
    """Options that hold a value decided at apply; why, per value."""

    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OptionField:
    name: str
    type: str
    required: bool
    default: str | None


def fields_of(cls: type) -> tuple[OptionField, ...]:
    """What a step's options are, for `sluis steps` and the editors' schema."""
    hints = typing.get_type_hints(cls)
    result: list[OptionField] = []
    for f in dataclasses.fields(cast(Any, cls)):
        required = (
            f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
        )
        default = None
        if f.default is not dataclasses.MISSING:
            default = repr(f.default)
        elif f.default_factory is not dataclasses.MISSING:
            default = repr(f.default_factory())
        result.append(OptionField(f.name, _describe(hints[f.name]), required, default))
    return tuple(result)


def build(cls: type, block: Map | None, resolve: Resolver, where: str) -> Any:
    """`block` as an instance of `cls`, or `Unresolved`. Raises `OptionsError`."""
    if not dataclasses.is_dataclass(cls):
        raise OptionsError(f"{where}: its `Options` is not a dataclass")
    hints = typing.get_type_hints(cls)
    fields = {f.name: f for f in dataclasses.fields(cast(Any, cls))}
    reader = _Reader(resolve)
    values: dict[str, Any] = {}
    given = {entry.key: entry for entry in block.entries} if block else {}
    for key, entry in given.items():
        if key not in fields:
            known = ", ".join(fields) or "none"
            reader.problem(entry.key_loc, f"unknown option `{key}`; known: {known}")
            continue
        values[key] = reader.convert(hints[key], entry.value, key)
    for name, f in fields.items():
        required = (
            f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
        )
        if required and name not in given:
            loc = block.loc if block else None
            reader.problems.append(
                f"{loc}: missing option `{name}`" if loc else f"missing option `{name}`"
            )
    if reader.problems:
        raise OptionsError(
            "\n".join(f"{problem} ({where})" for problem in reader.problems)
        )
    if reader.unknowns:
        return Unresolved(tuple(reader.unknowns))
    return cls(**values)


class _Pending:
    """Stands in for a value decided at apply, so conversion can go on."""


_PENDING = _Pending()


class _Reader:
    def __init__(self, resolve: Resolver) -> None:
        self.resolve = resolve
        self.problems: list[str] = []
        self.unknowns: list[str] = []

    def problem(self, loc: object, message: str) -> None:
        self.problems.append(f"{loc}: {message}")

    def value(self, item: Scalar) -> Any:
        if isinstance(item.value, str):
            resolved = self.resolve(item)
            if isinstance(resolved, Unknown):
                self.unknowns.append(resolved.reason)
                return _PENDING
            return resolved
        return item.value

    def convert(self, tp: Any, item: Item, name: str) -> Any:
        origin = typing.get_origin(tp)
        args = typing.get_args(tp)
        if origin in (types.UnionType, typing.Union):
            members = [a for a in args if a is not type(None)]
            if isinstance(item, Scalar) and item.value is None:
                return None
            if len(members) != 1:  # pragma: no cover - a step's own mistake
                raise OptionsError(
                    f"option `{name}`: only `T | None` unions are supported"
                )
            return self.convert(members[0], item, name)
        if tp is object or tp is Any:
            return self.plain(item)
        if origin in (tuple, list):
            if not isinstance(item, Seq):
                self.problem(item.loc, f"`{name}` must be a list")
                return None
            element = args[0] if args else object
            return tuple(self.convert(element, child, name) for child in item.items)
        if origin in (dict, Mapping) or tp in (dict, Mapping):
            if not isinstance(item, Map):
                self.problem(item.loc, f"`{name}` must be a mapping")
                return None
            element = args[1] if len(args) == 2 else object
            return {e.key: self.convert(element, e.value, name) for e in item.entries}
        if not isinstance(item, Scalar):
            self.problem(
                item.loc, f"`{name}` must be a single value, not a list or mapping"
            )
            return None
        value = self.value(item)
        if value is _PENDING:
            return value
        return self.scalar(tp, origin, args, value, item, name)

    def scalar(
        self,
        tp: Any,
        origin: Any,
        args: tuple[Any, ...],
        value: Any,
        item: Scalar,
        name: str,
    ) -> Any:
        if origin is Literal:
            if value not in args:
                allowed = ", ".join(repr(a) for a in args)
                self.problem(
                    item.loc, f"`{name}` must be one of {allowed}, not {value!r}"
                )
            return value
        if tp is Secret:
            if isinstance(value, Secret):
                return value
            if isinstance(value, str):
                return Secret(value)
        elif isinstance(value, Secret):
            self.problem(
                item.loc, f"`{name}` would hold a secret; only a `Secret` option may"
            )
            return None
        if (
            tp is str
            and isinstance(value, str | int | float)
            and not isinstance(value, bool)
        ):
            return str(value)
        if tp is bool and isinstance(value, bool):
            return value
        if tp is int and isinstance(value, int) and not isinstance(value, bool):
            return value
        if tp is float and isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        self.problem(item.loc, f"`{name}` must be {_describe(tp)}, not {value!r}")
        return None

    def plain(self, item: Item) -> Any:
        if isinstance(item, Seq):
            return [self.plain(child) for child in item.items]
        if isinstance(item, Map):
            return {e.key: self.plain(e.value) for e in item.entries}
        return self.value(item)


def _plural(tp: Any) -> str:
    names = {str: "strings", int: "integers", float: "numbers", bool: "booleans"}
    return names.get(tp, _describe(tp))


def _describe(tp: Any) -> str:
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin in (types.UnionType, typing.Union):
        return " | ".join(_describe(a) for a in args)
    if origin is Literal:
        return " | ".join(repr(a) for a in args)
    if origin in (tuple, list):
        return f"list of {_plural(args[0]) if args else 'anything'}"
    if origin in (dict, Mapping):
        return f"mapping to {_plural(args[1]) if len(args) == 2 else 'anything'}"
    if tp is type(None):
        return "null"
    if tp is object or tp is Any:
        return "anything"
    return {
        str: "a string",
        int: "an integer",
        float: "a number",
        bool: "true or false",
    }.get(tp, getattr(tp, "__name__", str(tp)))

"""A step's `with:` block, into its plugin's own `Options` dataclass.

A plugin declares its options as a frozen dataclass; this reads the located
config into it, strictly: an unknown key, a missing required one or a wrong
type is an error at the line and column it was written. References in string
values are resolved on the way in (by a callback, so this module stays pure),
and a value that isn't known yet makes the whole block `Unresolved` — the step
is then waiting, rather than planned with half its options.

The field types a plugin may use: `str`, `int`, `float`, `bool`, `Secret`,
`Literal[...]`, `tuple[T, ...]`, `Mapping[str, T]` (or `dict`), `T | None`,
`object` for anything JSON, and `Linked` for the name of another step.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from lely.config import Map, Node, Scalar, Seq
from lely.errors import LelyError
from lely.model import Linked, Secret, Value
from lely.refs import Unknown
from lely.step import quietly

Resolver = Callable[[Scalar], Value | Unknown]
#: Answers an option that names a step: the step, or what it is waiting for.
Linker = Callable[[Scalar], Linked | Unknown]


class OptionsError(LelyError):
    """A step's `with:` block doesn't fit its options; every problem, one per line."""


@dataclass(frozen=True, slots=True)
class Unresolved:
    """Options that hold a value that isn't known yet: the outputs waited for."""

    waits_for: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OptionField:
    name: str
    type: str
    required: bool
    default: str | None


def option_fields(cls: type) -> tuple[dataclasses.Field[Any], ...]:
    """The fields of an `Options` class a config can set: the ones its
    constructor takes. A field the class fills in itself (`init=False`) is not
    an option."""
    return tuple(f for f in dataclasses.fields(cast(Any, cls)) if f.init)


def fields_of(cls: type) -> tuple[OptionField, ...]:
    """What a plugin's options are, for `lely steps` and the editors' schema."""
    hints = typing.get_type_hints(cls)
    result: list[OptionField] = []
    for f in option_fields(cls):
        made = default_of(cls, f)
        required = made is dataclasses.MISSING
        default = None if required else repr(made)
        result.append(OptionField(f.name, _describe(hints[f.name]), required, default))
    return tuple(result)


def default_of(cls: type, f: dataclasses.Field[Any]) -> Any:
    """An option's default, or `MISSING` for an option that has to be given.
    A default made by a function is the plugin's own code: what it prints is
    not lely's output, and what it raises is said, not a traceback."""
    if f.default is not dataclasses.MISSING:
        return f.default
    if f.default_factory is dataclasses.MISSING:
        return dataclasses.MISSING
    try:
        with quietly(f"`{cls.__qualname__}`"):
            return f.default_factory()
    except LelyError:
        raise
    except Exception as error:
        raise OptionsError(
            f"`{cls.__qualname__}`: the default of its option `{f.name}` can't be "
            f"made: {type(error).__name__}: {error}"
        ) from error


def build(
    cls: type,
    block: Map | None,
    resolve: Resolver,
    where: str,
    link: Linker | None = None,
) -> Any:
    """`block` as an instance of `cls`, or `Unresolved`. Raises `OptionsError`."""
    if not dataclasses.is_dataclass(cls):
        raise OptionsError(f"{where}: its `Options` is not a dataclass")
    hints = typing.get_type_hints(cls)
    fields = {f.name: f for f in option_fields(cls)}
    reader = _Reader(resolve, link)
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
        return Unresolved(tuple(dict.fromkeys(reader.unknowns)))
    try:
        with quietly():
            return cls(**values)
    except LelyError as error:
        raise OptionsError(f"{where}: {error}") from error
    except Exception as error:  # a plugin's `__post_init__` is its own
        raise OptionsError(
            f"{where}: its options can't be built: {type(error).__name__}: {error}"
        ) from error


def _by_reference(item: Scalar) -> bool:
    return isinstance(item.value, str) and "${" in item.value


class _Pending:
    """Stands in for a value that isn't known yet, so conversion can go on."""


_PENDING = _Pending()
#: … and for one that isn't known yet but is known to be a secret.
_PENDING_SECRET = _Pending()


class _Reader:
    def __init__(self, resolve: Resolver, link: Linker | None) -> None:
        self.resolve = resolve
        self.link = link
        self.problems: list[str] = []
        self.unknowns: list[str] = []

    def problem(self, loc: object, message: str) -> None:
        self.problems.append(f"{loc}: {message}")

    def value(self, item: Scalar) -> Any:
        if isinstance(item.value, str):
            resolved = self.resolve(item)
            if isinstance(resolved, Unknown):
                self.unknowns.append(resolved.waits_for)
                return _PENDING_SECRET if resolved.secret else _PENDING
            return resolved
        return item.value

    def convert(self, tp: Any, item: Node, name: str, optional: bool = False) -> Any:
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
            return self.convert(members[0], item, name, optional=True)
        if tp is object or tp is Any:
            return self.plain(item)
        if tp is Linked:
            return self.linked(item, name)
        if origin in (tuple, list):
            element = args[0] if args else object
            if isinstance(item, Scalar) and _by_reference(item):
                return self.whole(item, name, "list", element, optional)
            if not isinstance(item, Seq):
                self.problem(item.loc, f"`{name}` must be a list")
                return None
            return tuple(self.convert(element, child, name) for child in item.items)
        if origin in (dict, Mapping) or tp in (dict, Mapping):
            element = args[1] if len(args) == 2 else object
            if isinstance(item, Scalar) and _by_reference(item):
                return self.whole(item, name, "mapping", element, optional)
            if not isinstance(item, Map):
                self.problem(item.loc, f"`{name}` must be a mapping")
                return None
            return {e.key: self.convert(element, e.value, name) for e in item.entries}
        if not isinstance(item, Scalar):
            self.problem(
                item.loc, f"`{name}` must be a single value, not a list or mapping"
            )
            return None
        value = self.value(item)
        if value is _PENDING:
            return value
        if value is None and optional:
            return None  # a null that came by reference is a null all the same
        return self.scalar(tp, origin, args, value, item, name)

    def whole(
        self, item: Scalar, name: str, kind: str, element: Any, optional: bool
    ) -> Any:
        """A list or a mapping given whole, by reference: `tags: ${steps.x.tags}`.
        The reference is looked at like any other — so one that names no step
        is said — and what it answers has to be what the option takes."""
        value = self.value(item)
        if value is _PENDING or value is _PENDING_SECRET:
            return _PENDING
        if value is None and optional:
            return None
        items: Any = None
        if kind == "list" and isinstance(value, list | tuple):
            items = tuple(value)
        elif kind == "mapping" and isinstance(value, Mapping):
            items = dict(value)
        held = items.values() if isinstance(items, dict) else items
        if items is None or (
            element is str and not all(isinstance(one, str) for one in held)
        ):
            of = " of text" if element is str else ""
            self.problem(
                item.loc, f"`{name}` must be a {kind}{of}; {item.value} gives {value!r}"
            )
            return None
        return items

    def scalar(
        self,
        tp: Any,
        origin: Any,
        args: tuple[Any, ...],
        value: Any,
        item: Scalar,
        name: str,
    ) -> Any:
        if value is _PENDING_SECRET:
            # not known yet, and a secret whatever it is: the same rule as below
            if tp is not Secret:
                self.problem(
                    item.loc, f"`{name}` would hold a secret; only a `Secret` option may"
                )
            return _PENDING
        if origin is Literal:
            # one of them, and of its kind: `true` is not the `1` of `Literal[1, 2]`
            if not any(type(arg) is type(value) and arg == value for arg in args):
                allowed = ", ".join(repr(a) for a in args)
                self.problem(
                    item.loc, f"`{name}` must be one of {allowed}, not {value!r}"
                )
            return value
        if tp is Secret:
            if isinstance(value, Secret):
                return value
            if isinstance(value, str | int | float | bool):
                return Secret(_text(value, item))
        elif isinstance(value, Secret):
            self.problem(
                item.loc, f"`{name}` would hold a secret; only a `Secret` option may"
            )
            return None
        if tp is str and isinstance(value, str | int | float | bool):
            return _text(value, item)
        if tp is bool and isinstance(value, bool):
            return value
        if tp is int and isinstance(value, int) and not isinstance(value, bool):
            return value
        if tp is float and isinstance(value, int | float) and not isinstance(value, bool):
            try:
                return float(value)
            except OverflowError:  # a whole number of hundreds of digits
                self.problem(item.loc, f"`{name}` is a number too large to hold")
                return None
        self.problem(item.loc, f"`{name}` must be {_describe(tp)}, not {value!r}")
        return None

    def linked(self, item: Node, name: str) -> Any:
        if not isinstance(item, Scalar) or not isinstance(item.value, str):
            self.problem(item.loc, f"`{name}` must be the name of a step")
            return None
        if self.link is None:  # pragma: no cover - the core always gives one
            raise OptionsError(f"option `{name}`: nothing here can name a step")
        found = self.link(item)
        if isinstance(found, Unknown):
            self.unknowns.append(found.waits_for)
            return _PENDING
        return found

    def plain(self, item: Node) -> Any:
        if isinstance(item, Seq):
            return [self.plain(child) for child in item.items]
        if isinstance(item, Map):
            return {e.key: self.plain(e.value) for e in item.entries}
        return self.value(item)


def _text(value: str | int | float | bool, item: Scalar) -> str:
    """A value for an option that wants text.

    A number or a boolean written in the config is passed on as it was written
    — `1.10` stays `1.10` and not `1.1`, `0123` isn't read as octal, `yes` stays
    `yes`. One that came from a reference is written the way JSON would.
    """
    if isinstance(value, str):
        return value
    if not isinstance(item.value, str) and item.raw is not None:
        return item.raw
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


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
    if tp is Linked:
        return "the name of a step"
    return {
        str: "a string",
        int: "an integer",
        float: "a number",
        bool: "true or false",
    }.get(tp, getattr(tp, "__name__", str(tp)))

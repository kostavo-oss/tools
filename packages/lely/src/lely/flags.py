"""A step's `Options` as the flags of its own command line, and back into a
config block — for a step run on its own (`spec/011`, R5).

Each field of the `Options` dataclass is `--<name>`, with the field's type, its
default and the `#:` comment above it as its help. What a flag gives is then
written into the same config nodes a `lely.yml` would hold, so the step's
options are read by `lely.options` exactly as under lely: one reader, one set
of errors, one `made_from` hash.

The types a flag can carry: `str`, `int`, `float`, `bool` (as a word: `true`,
`yes`, `no`…, so a bundle variable can set it), `Secret` (text), `Literal[…]`
(one of them), `tuple[T, …]` (the flag more than once), `Mapping[str, T]`
(`--name key=value`, more than once), and `T | None`. Anything else is refused
when the step starts, with this list.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from typer.core import TyperOption

from lely.config import Entry, Loc, Map, Scalar, Seq
from lely.errors import LelyError, Refused
from lely.model import Linked, Secret
from lely.options import default_of, option_fields
from lely.registry import option_docs

if TYPE_CHECKING:
    from typer._click.types import ParamType
else:  # typer carries its own click since 0.21
    try:
        from typer._click.types import ParamType
    except ImportError:  # pragma: no cover - typer before its own click
        from click import ParamType

#: Where an option given as a flag "was written".
COMMAND_LINE = Loc("command line", 0, 0)

_SCALARS = (str, int, float, bool)


class _YesNo(ParamType):
    """A yes or a no as a job's parameter can give it: a word, not a flag."""

    name = "true|false"

    def convert(self, value: Any, param: Any, ctx: Any) -> bool:
        if isinstance(value, bool):
            return value
        word = str(value).strip().lower()
        if word in ("true", "1", "yes", "y"):
            return True
        if word in ("false", "0", "no", "n"):
            return False
        self.fail(f"'{value}' is not one of true, 1, yes, y, false, 0, no, n", param, ctx)


class _OneOf(ParamType):
    """One of a `Literal`'s values, of its own kind."""

    def __init__(self, allowed: tuple[Any, ...]) -> None:
        self.allowed = allowed
        self.name = "|".join(str(a) for a in allowed)

    def convert(self, value: Any, param: Any, ctx: Any) -> Any:
        for allowed in self.allowed:
            if value == allowed or (isinstance(value, str) and str(allowed) == value):
                return allowed
        self.fail(f"'{value}' is not one of {self.name}", param, ctx)


class _Pair(ParamType):
    """`key=value`, for a mapping option."""

    name = "key=value"

    def convert(self, value: Any, param: Any, ctx: Any) -> tuple[str, str]:
        if isinstance(value, tuple):
            return value
        key, separator, rest = str(value).partition("=")
        if not separator or not key.strip():
            self.fail(f"'{value}' is not key=value", param, ctx)
        return key.strip(), rest


@dataclass(frozen=True, slots=True)
class Flag:
    """One option of the step, as its flag takes it."""

    field: str
    name: str
    kind: Any
    many: bool
    required: bool
    default: Any
    help: str

    @property
    def option(self) -> str:
        return "--" + self.field.replace("_", "-")


def flags_of(options: type) -> tuple[Flag, ...]:
    """The flags for an `Options` class. Raises `LelyError` for a field no
    flag can carry."""
    hints = typing.get_type_hints(options)
    docs = option_docs(options)
    result: list[Flag] = []
    for f in option_fields(options):
        made = default_of(options, f)
        required = made is dataclasses.MISSING
        kind, many = _kind(hints[f.name], f.name, options)
        result.append(
            Flag(
                field=f.name,
                name=f.name.replace("_", "-"),
                kind=kind,
                many=many,
                required=required,
                default=None if required else made,
                help=docs.get(f.name, ""),
            )
        )
    return tuple(result)


def _kind(tp: Any, name: str, options: type) -> tuple[Any, bool]:
    """What a flag for a field of type `tp` takes, and whether more than once."""
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin in (types.UnionType, typing.Union):
        members = [a for a in args if a is not type(None)]
        if len(members) == 1:
            return _kind(members[0], name, options)
    elif origin is Literal:
        return _OneOf(args), False
    elif origin in (tuple, list):
        element = args[0] if args else str
        if element is Ellipsis or element in _SCALARS or element is Secret:
            inner, _ = _kind(str if element is Ellipsis else element, name, options)
            return inner, True
    elif origin in (dict, Mapping) or tp in (dict, Mapping):
        element = args[1] if len(args) == 2 else str
        if element in _SCALARS or element is Secret:
            return _Pair(), True
    elif tp is bool:
        return _YesNo(), False
    elif tp in (str, int, float):
        return tp, False
    elif tp is Secret:
        return str, False
    which = "the name of a step" if tp is Linked else _said(tp)
    raise LelyError(
        f"`{options.__qualname__}.{name}` is {which}: a flag can't carry it. On its "
        "own, a step takes text, whole and decimal numbers, true or false, a secret, "
        "one of a few values, a list or a mapping of those, and `T | None`. Run it "
        "under lely for the rest."
    )


def _said(tp: Any) -> str:
    return getattr(tp, "__name__", None) or str(tp)


def options_of(flags: Sequence[Flag]) -> list[TyperOption]:
    """The step's own flags, as typer builds a command from."""
    made = []
    for flag in flags:
        kind: Any = flag.kind
        # No default here: a flag not given is left out of the block, so the
        # option's own default applies and the step is "made from" the same
        # thing as a config that doesn't write it. The default is said in the help.
        help_ = flag.help
        if not flag.required and not flag.many and flag.default is not None:
            help_ = f"{help_} [default: {flag.default}]".strip()
        made.append(
            TyperOption(
                param_decls=[flag.option, flag.field],
                type=kind,
                required=flag.required,
                multiple=flag.many,
                default=None,
                show_default=False,
                help=help_ or None,
            )
        )
    return made


def block_from(flags: Sequence[Flag], values: Mapping[str, Any]) -> Map:
    """What the flags gave, as the `with:` block a config would hold.

    A flag not given is left out, so the option's own default applies. A value
    that looks like a reference is refused: on its own, a step has no step
    above to take it from (`spec/011`, R8).
    """
    entries: list[Entry] = []
    for flag in flags:
        value = values.get(flag.field)
        if value is None or (flag.many and not value):
            continue
        _no_reference(flag, value)
        entries.append(Entry(flag.field, COMMAND_LINE, _node(value, flag)))
    return Map(tuple(entries), COMMAND_LINE)


def _node(value: Any, flag: Flag) -> Scalar | Seq | Map:
    if flag.many and isinstance(flag.kind, _Pair):
        pairs = [
            v if isinstance(v, tuple) else _Pair().convert(v, None, None) for v in value
        ]
        return Map(
            tuple(Entry(k, COMMAND_LINE, Scalar(v, COMMAND_LINE)) for k, v in pairs),
            COMMAND_LINE,
        )
    if flag.many:
        return Seq(tuple(Scalar(v, COMMAND_LINE) for v in value), COMMAND_LINE)
    return Scalar(value, COMMAND_LINE)


def _no_reference(flag: Flag, value: Any) -> None:
    texts = [value] if not isinstance(value, list | tuple) else list(value)
    for text in texts:
        if isinstance(text, tuple):
            text = text[1]
        if isinstance(text, str) and "${" in text:
            raise Refused(
                f"{flag.option} is `{text}`: on its own, a step has no step above to "
                "take a `${…}` reference from. Run it under lely, or pass the value."
            )

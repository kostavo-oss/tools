"""References: `${…}` in a step's options, checked offline and resolved at plan.

Pure. There is one spelling for a value from another step —
`${steps.<name>.<output>}` — and one for the environment, `${env.<NAME>}`,
which is not a step. Three jobs, kept apart:

- `match` finds the output a reference names among the ones a plugin declares.
  A declared name can be a shape (`resources.<type>.<key>.id`); the most literal
  one wins, and whatever is left of the reference walks into the value.
- `check` asks whether a reference *may* stand where it was written: the step it
  names is there, is listed above, runs for the same targets, and declares that
  output. `validate` runs it with no workspace at all.
- `resolve` answers one, against a `Scope` — what the steps above give so far.

A value that isn't known yet — the `id` of a job this deploy creates — resolves
to `Unknown`, naming the output, never to an empty string. A step whose options
hold one is *waiting* instead of being planned wrong.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from lely.config import Loc
from lely.errors import LelyError
from lely.model import KNOWN, Json, Output, Outputs, Secret, Value

NAMESPACES = ("steps", "env")

_REF = re.compile(r"\$\{([^}]*)\}")
_PART = re.compile(r"[A-Za-z0-9_-]+\Z")

#: The spellings from when the bundle was built in. Each now names its step.
_FORMER = ("var", "bundle", "workspace", "resources")


class RefError(LelyError):
    """A reference that can't stand where it was written, or can't be answered."""


@dataclass(frozen=True, slots=True)
class Ref:
    path: tuple[str, ...]

    @property
    def namespace(self) -> str:
        return self.path[0]

    @property
    def text(self) -> str:
        return "${" + ".".join(self.path) + "}"

    @property
    def step(self) -> str:
        return self.path[1]

    @property
    def output(self) -> tuple[str, ...]:
        return self.path[2:]


@dataclass(frozen=True, slots=True)
class Unknown:
    """A value that isn't known yet: the output a step is waiting for."""

    waits_for: str


def parse(text: str, loc: Loc) -> tuple[Ref, ...]:
    """Every reference in a string, each checked for shape."""
    refs: list[Ref] = []
    for found in _REF.finditer(text):
        body = found.group(1)
        parts = tuple(body.split("."))
        if not all(_PART.match(part) for part in parts):
            raise RefError(
                f"{loc}: `${{{body}}}` is not a reference: expected dotted names"
            )
        namespace = parts[0]
        if namespace in _FORMER:
            now = ".".join(parts[1:]) if namespace == "bundle" else body
            raise RefError(
                f"{loc}: `${{{body}}}`: every reference names the step its value "
                f"comes from — write `${{steps.<bundle step>.{now}}}`"
            )
        if namespace not in NAMESPACES:
            raise RefError(
                f"{loc}: `${{{body}}}`: unknown namespace `{namespace}`; expected one of "
                f"{', '.join(NAMESPACES)}"
            )
        if namespace == "env" and len(parts) != 2:
            raise RefError(
                f"{loc}: `${{{body}}}`: an environment variable is `${{env.<NAME>}}`"
            )
        if namespace == "steps" and len(parts) < 3:
            raise RefError(
                f"{loc}: `${{{body}}}`: a step's output is `${{steps.<name>.<output>}}`"
            )
        refs.append(Ref(parts))
    return tuple(refs)


# -- which declared output a reference names ---------------------------------


@dataclass(frozen=True, slots=True)
class Match:
    """`output` is the declaration; `name` the concrete name it stands for here;
    `rest` walks into the value."""

    output: Output
    name: str
    rest: tuple[str, ...]


def match(declared: tuple[Output, ...], path: tuple[str, ...]) -> Match | None:
    """The declared output `path` starts with: the most literal, then the longest."""
    best: tuple[int, int, Output] | None = None
    for output in declared:
        parts = output.parts
        if len(parts) > len(path):
            continue
        literal = 0
        for part, given in zip(parts, path, strict=False):
            if part.startswith("<"):
                continue
            if part != given:
                break
            literal += 1
        else:
            rank = (literal, len(parts))
            if best is None or rank > best[:2]:
                best = (*rank, output)
    if best is None:
        return None
    output = best[2]
    size = len(output.parts)
    return Match(output, ".".join(path[:size]), path[size:])


def gives(declared: tuple[Output, ...]) -> str:
    """What a plugin declares, for a message."""
    if not declared:
        return "it gives nothing"
    return "it gives: " + ", ".join(output.name for output in declared)


# -- where a reference may stand ---------------------------------------------


@dataclass(frozen=True, slots=True)
class Above:
    """A step listed above: what it declares (`None` when its plugin couldn't be
    found, which is reported on its own), and the targets it runs for."""

    declared: tuple[Output, ...] | None
    targets: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class Position:
    """Where a reference is written, and so what it may name."""

    this: str
    above: Mapping[str, Above]
    below: tuple[str, ...] = ()
    targets: tuple[str, ...] | None = None


def check(ref: Ref, position: Position, loc: Loc) -> Output | None:
    """Raise if `ref` can't stand at `position`. Needs no workspace.

    Returns the declared output a step reference names, where that is known.
    """
    if ref.namespace != "steps":
        return None
    above = check_step(ref.step, position, f"{loc}: {ref.text}")
    if above.declared is None:
        return None
    found = match(above.declared, ref.output)
    if found is None:
        raise RefError(
            f"{loc}: {ref.text}: step `{ref.step}` gives no output "
            f"`{'.'.join(ref.output)}`; {gives(above.declared)}"
        )
    return found.output


def check_step(name: str, position: Position, where: str) -> Above:
    """Raise unless step `name` stands above `position` and runs whenever it does."""
    if name == position.this:
        raise RefError(f"{where}: a step can't use its own outputs")
    if name in position.below:
        raise RefError(
            f"{where}: step `{name}` is listed below step `{position.this}`, and a "
            f"step can only use what is above it; move `{name}` up, or "
            f"`{position.this}` down"
        )
    if name not in position.above:
        raise RefError(f"{where}: there is no step `{name}`")
    above = position.above[name]
    if above.targets is not None:
        missing = (
            ["every other target"]
            if position.targets is None
            else [t for t in position.targets if t not in above.targets]
        )
        if missing:
            raise RefError(
                f"{where}: step `{name}` runs only for {', '.join(above.targets)}, and "
                f"step `{position.this}` also runs for {', '.join(missing)}; give both "
                "the same `targets`"
            )
    return above


# -- answering one ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Given:
    """What one step gives, as far as it is known now.

    `planned` is false for a step that couldn't be planned — it is waiting
    itself — so nothing it gives is known. `applied` is true once the step has
    run in this very run: what is missing then will not come.
    """

    declared: tuple[Output, ...]
    outputs: Outputs = field(default_factory=dict)
    later: frozenset[str] = frozenset()
    planned: bool = True
    applied: bool = False


@dataclass(frozen=True, slots=True)
class Scope:
    """What references resolve against at one point of the list."""

    steps: Mapping[str, Given] = field(default_factory=dict)
    env: Mapping[str, str] = field(default_factory=dict)


def resolve(text: str, scope: Scope, loc: Loc) -> Value | Unknown:
    """A string with references in it, answered.

    A string that is exactly one reference keeps the value's type (a version
    stays an int); references inside a longer string are formatted into it. A
    secret anywhere makes the whole result one — and a value from the
    environment is a secret.
    """
    refs = parse(text, loc)
    if not refs:
        return text
    if len(refs) == 1 and text.strip() == refs[0].text:
        return lookup(refs[0], scope, loc)
    secret = False
    unknown: Unknown | None = None

    def substitute(found: re.Match[str]) -> str:
        nonlocal secret, unknown
        ref = Ref(tuple(found.group(1).split(".")))
        value = lookup(ref, scope, loc)
        if isinstance(value, Unknown):
            unknown = unknown or value
            return ""
        if isinstance(value, Secret):
            secret = True
            return value.reveal()
        if isinstance(value, dict | list):
            raise RefError(
                f"{loc}: {ref.text} is a {type(value).__name__}, which can't be part "
                "of a longer string"
            )
        return _format(value)

    joined = _REF.sub(substitute, text)
    if unknown is not None:
        return unknown
    return Secret(joined) if secret else joined


def lookup(ref: Ref, scope: Scope, loc: Loc) -> Value | Unknown:
    """What one reference answers now, or the output it is waiting for."""
    if ref.namespace == "env":
        name = ref.path[1]
        if name not in scope.env:
            raise RefError(f"{loc}: {ref.text}: `{name}` isn't set in the environment")
        return Secret(scope.env[name])
    given = scope.steps.get(ref.step)
    if given is None:
        raise RefError(f"{loc}: {ref.text}: there is no step `{ref.step}` above")
    found = match(given.declared, ref.output)
    if found is None:
        raise RefError(
            f"{loc}: {ref.text}: step `{ref.step}` gives no output "
            f"`{'.'.join(ref.output)}`; {gives(given.declared)}"
        )
    waits_for = f"{ref.step}.{found.name}"
    if not given.planned:
        return Unknown(waits_for)
    if found.name in given.outputs:
        value = given.outputs[found.name]
        if isinstance(value, Secret):
            if found.rest:
                raise RefError(f"{loc}: {ref.text}: a secret has no fields")
            return value
        return _walk(value, found.rest, ref, loc)
    if given.applied:
        raise RefError(
            f"{loc}: {ref.text}: step `{ref.step}` has run and still gives no "
            f"`{found.name}`"
        )
    known = found.output.known
    if known == "run" or (
        known == "exists" and (not found.output.shape or found.name in given.later)
    ):
        return Unknown(waits_for)
    if not found.output.shape:
        raise RefError(
            f"{loc}: {ref.text}: step `{ref.step}` declares `{found.name}` as known "
            f"{KNOWN[known]}, and its plan gave none"
        )
    raise RefError(
        f"{loc}: {ref.text}: step `{ref.step}` has no `{found.name}`"
        + _alike(given, found.output)
    )


def _alike(given: Given, output: Output) -> str:
    """The names a step does have of one shape, for a message."""
    names = sorted(
        name
        for name in {*given.outputs, *given.later}
        if (found := match(given.declared, tuple(name.split("."))))
        and found.output == output
    )
    if not names:
        return ""
    shown = ", ".join(names[:8]) + (", …" if len(names) > 8 else "")
    return f" (it has: {shown})"


def _format(value: Json) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _walk(value: Json, parts: tuple[str, ...], ref: Ref, loc: Loc) -> Json:
    """Follow the rest of a reference into a JSON value."""
    for depth, part in enumerate(parts):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            walked = ".".join(ref.path[: len(ref.path) - len(parts) + depth + 1])
            raise RefError(f"{loc}: {ref.text}: there is no `{walked}`")
    return value

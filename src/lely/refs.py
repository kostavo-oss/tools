"""References: `${…}` in `lely.yml`, checked offline and resolved at plan.

Pure. Two jobs, kept apart:

- `check` asks whether a reference *may* stand where it was written: a pre step
  can't use a deployed resource's `id`, a step can't use a later step's
  outputs. `validate` runs it with no workspace at all.
- `resolve` answers one, against a `Scope` — the bundle's resolved config, its
  deployment summary, the outputs so far, the environment.

A value that isn't known yet — the `id` of a job this deploy creates — resolves
to `Unknown`, with the reason, never to an empty string. A step whose options
hold one is planned as *decided at apply* instead of being planned wrong.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from lely.config import Loc
from lely.errors import LelyError
from lely.model import Json, Outputs, Secret, Value

NAMESPACES = ("var", "bundle", "workspace", "resources", "steps", "env")

#: Fields of a bundle resource that only a deployment has; the resolved config
#: doesn't. `bundle summary -o json` carries them. TODO(verify): read from the
#: CLI's source (acceptance test `bundle/summary/modified_status`), not its docs.
DEPLOYED_FIELDS = frozenset({"id", "url", "modified_status"})

_REF = re.compile(r"\$\{([^}]*)\}")
_PART = re.compile(r"[A-Za-z0-9_-]+\Z")

#: The fewest parts a reference in each namespace has, and the most (`None`:
#: any number, the rest walks into the value).
_ARITY: dict[str, tuple[int, int | None]] = {
    "var": (2, 2),
    "env": (2, 2),
    "bundle": (2, None),
    "workspace": (2, None),
    "resources": (4, None),
    "steps": (3, None),
}


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


@dataclass(frozen=True, slots=True)
class Unknown:
    """A value decided at apply, and why."""

    reason: str


def parse(text: str, loc: Loc) -> tuple[Ref, ...]:
    """Every reference in a string, each checked for shape."""
    refs: list[Ref] = []
    for match in _REF.finditer(text):
        body = match.group(1)
        parts = tuple(body.split("."))
        if not all(_PART.match(part) for part in parts):
            raise RefError(
                f"{loc}: `${{{body}}}` is not a reference: expected dotted names"
            )
        namespace = parts[0]
        if namespace not in _ARITY:
            raise RefError(
                f"{loc}: `${{{body}}}`: unknown namespace `{namespace}`; expected one of "
                f"{', '.join(NAMESPACES)}"
            )
        least, most = _ARITY[namespace]
        if len(parts) < least or (most is not None and len(parts) > most):
            raise RefError(f"{loc}: `${{{body}}}`: {_SHAPE[namespace]}")
        refs.append(Ref(parts))
    return tuple(refs)


_SHAPE = {
    "var": "a variable is `${var.<name>}`",
    "env": "an environment variable is `${env.<NAME>}`",
    "bundle": "expected `${bundle.<field>}`",
    "workspace": "expected `${workspace.<field>}`",
    "resources": "a resource field is `${resources.<type>.<key>.<field>}`",
    "steps": "a step's output is `${steps.<name>.<output>}`",
}


# -- where a reference may stand ---------------------------------------------


@dataclass(frozen=True, slots=True)
class Position:
    """Where a reference is written, and so what it may name.

    `phase` is `bundle` for `bundle_vars`, which sits between the phases.
    `earlier` are the steps that run before this point; `later` the ones that
    don't (this step included). `fed` are the bundle variables lely sets.
    """

    where: str
    phase: Literal["pre", "bundle", "post"]
    earlier: tuple[str, ...]
    later: tuple[str, ...]
    fed: frozenset[str] = frozenset()
    this: str | None = None


def check(ref: Ref, position: Position, loc: Loc) -> None:
    """Raise if `ref` can't stand at `position`. Needs no workspace."""
    match ref.path:
        case ("steps", name, *_):
            if name == position.this:
                raise RefError(f"{loc}: {ref.text}: a step can't use its own outputs")
            if name in position.later:
                raise RefError(
                    f"{loc}: {ref.text}: step `{name}` runs after {position.where}"
                )
            if name not in position.earlier:
                raise RefError(f"{loc}: {ref.text}: there is no step `{name}`")
        case ("resources", _, _, field_name, *_) if field_name in DEPLOYED_FIELDS:
            if position.phase != "post":
                raise RefError(
                    f"{loc}: {ref.text}: a resource's `{field_name}` is known only "
                    "once the bundle has deployed; use it in a post step"
                )
        case ("var", name) if name in position.fed and position.phase != "post":
            raise RefError(
                f"{loc}: {ref.text}: `{name}` is set by bundle_vars from the pre "
                f"steps' outputs, so {position.where} can't read it"
            )
        case _:
            pass


# -- answering one ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Scope:
    """What references resolve against at one point of a plan.

    `config` is `bundle validate -o json`; `deployed` is `bundle summary -o json`
    (or `None` when nothing asked for it). `created` holds the resources this
    deploy creates or replaces — their `id` isn't known until it has. `pending`
    are bundle variables whose value is decided at apply.
    """

    config: Mapping[str, Json]
    deployed: Mapping[str, Json] | None = None
    created: frozenset[str] = frozenset()
    outputs: Mapping[str, Outputs] = field(default_factory=dict)
    deferred: Mapping[str, str] = field(default_factory=dict)
    env: Mapping[str, str] = field(default_factory=dict)
    pending: Mapping[str, str] = field(default_factory=dict)


def resolve(
    text: str, scope: Scope, loc: Loc, *, redact_env: bool = False
) -> Value | Unknown:
    """A string with references in it, answered.

    A string that is exactly one reference keeps the value's type (a version
    stays an int); references inside a longer string are formatted into it. A
    secret anywhere makes the whole result one. With `redact_env`, environment
    references stay as written — what an options hash wants.
    """
    refs = parse(text, loc)
    if not refs:
        return text
    if len(refs) == 1 and text.strip() == refs[0].text:
        return _lookup(refs[0], scope, loc, redact_env=redact_env)
    secret = False
    unknown: Unknown | None = None

    def substitute(match: re.Match[str]) -> str:
        nonlocal secret, unknown
        ref = Ref(tuple(match.group(1).split(".")))
        value = _lookup(ref, scope, loc, redact_env=redact_env)
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


def _format(value: Json) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _lookup(ref: Ref, scope: Scope, loc: Loc, *, redact_env: bool) -> Value | Unknown:
    match ref.path:
        case ("var", name):
            if name in scope.pending:
                return Unknown(scope.pending[name])
            variables = scope.config.get("variables")
            entry = variables.get(name) if isinstance(variables, dict) else None
            if not isinstance(entry, dict):
                raise RefError(f"{loc}: {ref.text}: the bundle has no variable `{name}`")
            if "value" not in entry:
                raise RefError(f"{loc}: {ref.text}: the bundle gives `{name}` no value")
            return entry["value"]
        case ("env", name):
            if redact_env:
                return ref.text
            if name not in scope.env:
                raise RefError(
                    f"{loc}: {ref.text}: `{name}` isn't set in the environment"
                )
            return scope.env[name]
        case ("bundle" | "workspace" as section, *rest):
            return _walk(scope.config.get(section), rest, ref, loc)
        case ("resources", kind, key, field_name, *rest) if field_name in DEPLOYED_FIELDS:
            if f"{kind}.{key}" in scope.created:
                return Unknown(f"resources.{kind}.{key} is created by this deploy")
            resources = (scope.deployed or {}).get("resources")
            entry = _walk(resources, [kind, key], None, loc) if resources else None
            if not isinstance(entry, dict) or field_name not in entry:
                return Unknown(f"resources.{kind}.{key} hasn't been deployed yet")
            return _walk(entry[field_name], rest, ref, loc)
        case ("resources", *rest):
            return _walk(scope.config.get("resources"), rest, ref, loc)
        case ("steps", name, output, *rest):
            outputs = scope.outputs.get(name, {})
            if output not in outputs:
                if name in scope.deferred:
                    return Unknown(f"step `{name}` is decided at apply")
                known = ", ".join(sorted(outputs)) or "none"
                raise RefError(
                    f"{loc}: {ref.text}: step `{name}` has no output `{output}` "
                    f"(its outputs: {known})"
                )
            value = outputs[output]
            if isinstance(value, Secret):
                if rest:
                    raise RefError(f"{loc}: {ref.text}: a secret has no fields")
                return value
            return _walk(value, rest, ref, loc)
        case _:  # pragma: no cover - `parse` admits nothing else
            raise RefError(f"{loc}: {ref.text}: not a reference")


def _walk(value: Json, parts: list[str], ref: Ref | None, loc: Loc) -> Json:
    """Follow the rest of a reference into a JSON value."""
    for depth, part in enumerate(parts):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            if ref is None:
                return None
            walked = ".".join(ref.path[: len(ref.path) - len(parts) + depth + 1])
            raise RefError(f"{loc}: {ref.text}: there is no `{walked}`")
    return value

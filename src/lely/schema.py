"""A schema for editors: the config, as JSON Schema, built from the plugins.

    lely schema -o lely.schema.json

and, as the first line of `lely.yml`:

    # yaml-language-server: $schema=lely.schema.json

An editor then completes `uses:` with the plugins installed here and the ones
this project names, and completes and checks a step's `with:` against that
plugin's own options while it is typed.

Pure: plugin classes in, a JSON document out. It says what `lely validate`
says about the *shape* of a config, and no more: that a reference names a step
that exists, stands above, and gives that output is `validate`'s to check — a
schema can't see one step from another. Anywhere a value may be a reference, a
`${…}` string is let through.

Draft-07, which is what editors' YAML support reads best.
"""

from __future__ import annotations

import dataclasses
import json
import re
import types
import typing
from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

from lely import step as contract
from lely.model import KNOWN, Linked, Secret
from lely.registry import Found

DRAFT = "http://json-schema.org/draft-07/schema#"

#: A step's name, as `config.py` reads one.
NAME = "^[A-Za-z_][A-Za-z0-9_-]*$"

#: A string holding a reference. Where an option wants a number, a reference
#: that will answer one is written as a string.
_REFERENCE = {"type": "string", "pattern": r"\$\{[^}]+\}"}


def build(
    plugins: Sequence[Found], docs: Mapping[str, Mapping[str, str]] | None = None
) -> dict[str, Any]:
    """The schema for a config that may use `plugins`.

    `docs` are the plugins' own words for their options, by `uses` and then by
    option — what a plugin's author wrote above each field.
    """
    docs = docs or {}
    return {
        "$schema": DRAFT,
        "title": "lely",
        "description": (
            "One plan for a whole Databricks deploy: an ordered list of steps, each "
            "done by a plugin. What stands above the bundle runs before the deploy, "
            "what stands below runs after."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": ["steps"],
        "properties": {
            "steps": {
                "type": "array",
                "minItems": 1,
                "description": (
                    "The steps, in the order they run. A step can use what the "
                    "steps above it give: ${steps.<name>.<output>}."
                ),
                "items": {"$ref": "#/definitions/step"},
            }
        },
        "definitions": {"step": _step(plugins, docs)},
    }


def dumps(schema: Mapping[str, Any]) -> str:
    return json.dumps(schema, indent=2) + "\n"


def _step(
    plugins: Sequence[Found], docs: Mapping[str, Mapping[str, str]]
) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["uses"],
        "properties": {
            "name": {
                "type": "string",
                "pattern": NAME,
                "description": (
                    "What other steps call this one: ${steps.<name>.<output>}. A "
                    "plain plugin name like `bundle` doubles as one."
                ),
            },
            "uses": {
                "description": "The plugin that does this step.",
                "anyOf": [
                    *(
                        {"const": found.uses, "description": _about(found)}
                        for found in plugins
                    ),
                    {
                        "type": "string",
                        "description": (
                            "A class in the repo (`./path/file.py:Class`), or in an "
                            "installed package (`package.module:Class`)."
                        ),
                    },
                ],
            },
            "with": {
                "type": "object",
                "description": "The step's options: what its plugin declares.",
            },
            "targets": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "The targets this step runs for, compared with `-t` as written. "
                    "For any other target the step is skipped."
                ),
            },
        },
        # one plugin's options at a time: an `if` on `uses`, so a mistake is
        # reported against the plugin that was named, not against all of them
        "allOf": [_when(found, docs.get(found.uses, {})) for found in plugins],
    }


def _when(found: Found, docs: Mapping[str, str]) -> dict[str, Any]:
    """What must hold for a step that uses one plugin."""
    options = _options(found.options, docs)
    required = []
    if options["required"]:
        required.append("with")
    if not _plain(found.uses):
        required.append("name")
    then: dict[str, Any] = {"properties": {"with": options}}
    if required:
        then["required"] = required
    return {
        "if": {"properties": {"uses": {"const": found.uses}}, "required": ["uses"]},
        "then": then,
    }


def _plain(uses: str) -> bool:
    """Whether `uses` can double as the step's name."""
    return re.match(NAME, uses) is not None


def _about(found: Found) -> str:
    """A plugin in a few lines: what it does, what a step of it gives."""
    doc = (found.cls.__doc__ or "").strip().splitlines()
    lines = [doc[0]] if doc else []
    if callable(getattr(found.cls, "outputs", None)):
        lines.append("Gives: what the step lists, by its options.")
    else:
        declared = contract.declared(found.cls, {})
        for known, words in KNOWN.items():
            names = [output.name for output in declared if output.known == known]
            if names:
                lines.append(f"Gives {words}: {', '.join(names)}.")
    return "\n".join(lines)


def _options(cls: type, docs: Mapping[str, str]) -> dict[str, Any]:
    """A plugin's `Options` dataclass, as the schema of a `with:` block."""
    hints = typing.get_type_hints(cls)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for field in dataclasses.fields(cast(Any, cls)):
        schema = dict(_of(hints[field.name]))
        if field.name in docs:
            schema["description"] = docs[field.name]
        if field.default is not dataclasses.MISSING:
            default = _plain_value(field.default)
            if default is not _NOT_JSON and default is not None:
                schema["default"] = default
        elif field.default_factory is dataclasses.MISSING:
            required.append(field.name)
        properties[field.name] = schema
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _of(tp: Any) -> dict[str, Any]:
    """One option's type, as the values a config may write for it."""
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin in (types.UnionType, typing.Union):
        members = [_of(arg) for arg in args if arg is not type(None)]
        return {"anyOf": [*members, {"type": "null"}]}
    if tp is object or tp is Any:
        return {}
    if tp is Linked:
        return {
            "type": "string",
            "pattern": NAME,
            "description": "The name of a step above this one.",
        }
    if origin in (tuple, list):
        return {"type": "array", "items": _of(args[0]) if args else {}}
    if origin in (dict, Mapping) or tp in (dict, Mapping):
        return {
            "type": "object",
            "additionalProperties": _of(args[1]) if len(args) == 2 else {},
        }
    if origin is Literal:
        return {"anyOf": [{"enum": list(args)}, _REFERENCE]}
    if tp is str or tp is Secret:
        # a number is taken as text, as `options.py` takes it
        return {"type": ["string", "number"]}
    if tp is bool:
        return {"anyOf": [{"type": "boolean"}, _REFERENCE]}
    if tp is int:
        return {"anyOf": [{"type": "integer"}, _REFERENCE]}
    if tp is float:
        return {"anyOf": [{"type": "number"}, _REFERENCE]}
    return {}  # a type `options.py` doesn't read either: it will say so


class _NotJson:
    pass


_NOT_JSON = _NotJson()


def _plain_value(value: Any) -> Any:
    """A default as JSON, or `_NOT_JSON` for one a config couldn't write."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, tuple | list):
        items = [_plain_value(item) for item in value]
        return _NOT_JSON if _NOT_JSON in items else items
    return _NOT_JSON

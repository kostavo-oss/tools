"""The plan file: what `plan -o` writes and `show` (and later `apply`) reads.

Both directions live here, so the writer and the reader can't drift apart; a
round-trip test holds them together. A secret never reaches the file: a secret
output is written as `{"$secret": true}` and read back as a `Secret` with no
value, and a payload holding one is refused outright.

A step's plan has the same shape here as a `command` step's plan command
prints, so `step_plan_from_json` reads both.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from lely.errors import LelyError
from lely.model import (
    ACTIONS,
    Action,
    BundlePlan,
    Change,
    Json,
    Outputs,
    Phase,
    Plan,
    PlannedStep,
    Secret,
    StepPlan,
    Value,
)

#: Bumped when the shape changes in a way a reader has to know about.
FORMAT_VERSION = 1

_SECRET = "$secret"


class PlanFileError(LelyError):
    """A plan file (or a plan command's output) that can't be read."""


def dumps(plan: Plan) -> str:
    return json.dumps(plan_to_json(plan), indent=2) + "\n"


def loads(text: str) -> Plan:
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        raise PlanFileError(f"Not a plan file: {error}") from None
    return plan_from_json(document)


def plan_to_json(plan: Plan) -> dict[str, Any]:
    return {
        "format_version": FORMAT_VERSION,
        "tool_version": plan.tool_version,
        "target": plan.target,
        "bundle": plan.bundle,
        "config_hash": plan.config_hash,
        "pre": [_step_to_json(step) for step in plan.pre],
        "deploy": {
            "changes": [_change_to_json(c) for c in plan.deploy.changes],
            "variables": dict(plan.deploy.variables),
            "document": plan.deploy.document,
            "deferred": plan.deploy.deferred,
        },
        "post": [_step_to_json(step) for step in plan.post],
    }


def plan_from_json(document: Json) -> Plan:
    doc = _object(document, "the plan file")
    version = doc.get("format_version")
    if version != FORMAT_VERSION:
        raise PlanFileError(
            f"This plan file is format {version}; this lely reads format "
            f"{FORMAT_VERSION}. Run `lely plan` again."
        )
    deploy = _object(doc.get("deploy"), "the plan file's `deploy`")
    variables = _object(deploy.get("variables", {}), "`deploy.variables`")
    return Plan(
        tool_version=_str(doc, "tool_version", "the plan file"),
        target=_str(doc, "target", "the plan file"),
        bundle=_str(doc, "bundle", "the plan file"),
        config_hash=_str(doc, "config_hash", "the plan file"),
        pre=tuple(_step_from_json(s) for s in _array(doc.get("pre"), "`pre`")),
        deploy=BundlePlan(
            changes=tuple(
                _change_from_json(c, "`deploy`")
                for c in _array(deploy.get("changes"), "`deploy.changes`")
            ),
            variables=tuple((str(k), str(v)) for k, v in variables.items()),
            document=deploy.get("document"),
            deferred=_optional_str(deploy, "deferred", "`deploy`"),
        ),
        post=tuple(_step_from_json(s) for s in _array(doc.get("post"), "`post`")),
    )


def step_plan_to_json(plan: StepPlan, where: str = "a step's plan") -> dict[str, Any]:
    _no_secrets(plan.payload, f"{where}: its payload")
    return {
        "changes": [_change_to_json(c) for c in plan.changes],
        "outputs": {name: _output_to_json(v, where) for name, v in plan.outputs.items()},
        "deferred": plan.deferred,
        "payload": plan.payload,
    }


def step_plan_from_json(document: Json, where: str = "a step's plan") -> StepPlan:
    doc = _object(document, where)
    unknown = set(doc) - {"changes", "outputs", "deferred", "payload"}
    if unknown:
        raise PlanFileError(f"{where}: unknown keys {', '.join(sorted(unknown))}")
    outputs = _object(doc.get("outputs", {}), f"{where}: `outputs`")
    changes = tuple(
        _change_from_json(c, where)
        for c in _array(doc.get("changes", []), f"{where}: `changes`")
    )
    keys = [c.key for c in changes]
    if len(set(keys)) != len(keys):
        raise PlanFileError(f"{where}: two changes share a key; each key must be unique")
    return StepPlan(
        changes=changes,
        outputs={name: _output_from_json(value) for name, value in outputs.items()},
        deferred=_optional_str(doc, "deferred", where),
        payload=doc.get("payload"),
    )


# -----------------------------------------------------------------------------


def _step_to_json(step: PlannedStep) -> dict[str, Any]:
    return {
        "name": step.name,
        "uses": step.uses,
        "phase": step.phase,
        "options_hash": step.options_hash,
        "plan": step_plan_to_json(step.plan, f"step `{step.name}`"),
    }


def _step_from_json(document: Json) -> PlannedStep:
    doc = _object(document, "a planned step")
    name = _str(doc, "name", "a planned step")
    phase = doc.get("phase")
    if phase not in ("pre", "post"):
        raise PlanFileError(f"step `{name}`: phase must be pre or post, not {phase!r}")
    return PlannedStep(
        name=name,
        uses=_str(doc, "uses", f"step `{name}`"),
        phase=cast(Phase, phase),
        options_hash=_str(doc, "options_hash", f"step `{name}`"),
        plan=step_plan_from_json(doc.get("plan"), f"step `{name}`"),
    )


def _change_to_json(change: Change) -> dict[str, Any]:
    return {
        "key": change.key,
        "action": change.action,
        "summary": change.summary,
        "destructive": change.destructive,
        "detail": list(change.detail),
    }


def _change_from_json(document: Json, where: str) -> Change:
    doc = _object(document, f"{where}: a change")
    key = _str(doc, "key", f"{where}: a change")
    action = doc.get("action")
    if action not in ACTIONS:
        raise PlanFileError(
            f"{where}: change {key!r}: action must be one of {', '.join(ACTIONS)}, "
            f"not {action!r}"
        )
    detail = _array(doc.get("detail", []), f"{where}: change {key!r} detail")
    return Change(
        key=key,
        action=cast(Action, action),
        summary=str(doc.get("summary") or key),
        destructive=bool(doc.get("destructive", False)),
        detail=tuple(str(line) for line in detail),
    )


def _output_to_json(value: Value, where: str) -> Json:
    if isinstance(value, Secret):
        return {_SECRET: True}
    _no_secrets(value, f"{where}: an output")
    return value


def _output_from_json(value: Json) -> Value:
    if isinstance(value, dict) and value.get(_SECRET) is True:
        return Secret()
    return value


def _no_secrets(value: Any, where: str) -> None:
    if isinstance(value, Secret):
        raise PlanFileError(
            f"{where} holds a secret; a plan file never does. Make it an output of "
            "its own (a `Secret`), or fetch it at apply."
        )
    if isinstance(value, dict):
        for item in value.values():
            _no_secrets(item, where)
    elif isinstance(value, list | tuple):
        for item in value:
            _no_secrets(item, where)
    elif value is not None and not isinstance(value, str | int | float | bool):
        raise PlanFileError(f"{where} holds a {type(value).__name__}, which isn't JSON")


def _object(value: Json, where: str) -> Mapping[str, Json]:
    if not isinstance(value, dict):
        raise PlanFileError(f"{where} must be a JSON object")
    return value


def _array(value: Json, where: str) -> list[Json]:
    if not isinstance(value, list):
        raise PlanFileError(f"{where} must be a JSON array")
    return value


def _str(doc: Mapping[str, Json], key: str, where: str) -> str:
    value = doc.get(key)
    if not isinstance(value, str):
        raise PlanFileError(f"{where}: `{key}` must be a string")
    return value


def _optional_str(doc: Mapping[str, Json], key: str, where: str) -> str | None:
    value = doc.get(key)
    if value is not None and not isinstance(value, str):
        raise PlanFileError(f"{where}: `{key}` must be a string or null")
    return value


def outputs_json(outputs: Outputs) -> dict[str, Json]:
    """Outputs as they are shown: secrets as `***`."""
    return {k: ("***" if isinstance(v, Secret) else v) for k, v in outputs.items()}

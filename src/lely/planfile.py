"""The plan file: what `plan -o` writes, and `show`, `apply` and `destroy` read.

Both directions live here, so the writer and the reader can't drift apart; a
round-trip test holds them together. At the top it says what it is: its format,
lely's version, whether it is a plan to apply or to destroy, the target, the
workspace and the identity it was planned as, and the git tree it was made on.
Then every step, in order.

A secret never reaches the file: a secret output is written as
`{"$secret": true}` and read back as a `Secret` with no value, and a payload
holding one is refused outright. Nothing in the file is kept for apply — every
step is planned again, and gives its values again.

A step's plan has the same shape here as a `command` step's plan command
prints, so `step_plan_from_json` reads both. What a run leaves behind — a
`Result`, a `Status` — is written here too, and never read back.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from lely.errors import LelyError
from lely.model import (
    ACTIONS,
    Action,
    Change,
    Input,
    Json,
    Outputs,
    Overview,
    Plan,
    PlanKind,
    PlannedStep,
    Result,
    Secret,
    Source,
    Status,
    StepPlan,
    Value,
    Workspace,
)

#: Bumped when the shape changes in a way a reader has to know about.
#: 2: one list of steps, the bundle among them; the workspace; the git tree.
FORMAT_VERSION = 2

_SECRET = "$secret"
_STEP_PLAN_KEYS = {"changes", "outputs", "later", "waiting", "notes", "payload"}


class PlanFileError(LelyError):
    """A plan file (or a plan command's output) that can't be read."""


def dumps(plan: Plan) -> str:
    return json.dumps(plan_to_json(plan), indent=2) + "\n"


def loads(text: str) -> Plan:
    try:
        document = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as error:
        raise PlanFileError(f"Not a plan file: {error}") from None
    return plan_from_json(document)


def plan_to_json(plan: Plan) -> dict[str, Any]:
    return {
        "format_version": FORMAT_VERSION,
        "tool_version": plan.tool_version,
        "kind": plan.kind,
        "target": plan.target,
        "workspace": _workspace_to_json(plan.workspace),
        "source": {"tree": plan.source.tree, "dirty": plan.source.dirty},
        "steps": [_step_to_json(step) for step in plan.steps],
    }


def plan_from_json(document: Json) -> Plan:
    doc = _object(document, "the plan file")
    version = doc.get("format_version")
    if version != FORMAT_VERSION:
        raise PlanFileError(
            f"This plan file is format {version}; this lely reads format "
            f"{FORMAT_VERSION}. Run `lely plan` again."
        )
    kind = doc.get("kind")
    if kind not in ("apply", "destroy"):
        raise PlanFileError(
            f"the plan file: `kind` must be apply or destroy, not {kind!r}"
        )
    workspace = _object(doc.get("workspace"), "the plan file's `workspace`")
    source = _object(doc.get("source"), "the plan file's `source`")
    return Plan(
        tool_version=_str(doc, "tool_version", "the plan file"),
        kind=cast(PlanKind, kind),
        target=_str(doc, "target", "the plan file"),
        workspace=Workspace(
            host=_str(workspace, "host", "the plan file's `workspace`"),
            identity=_str(workspace, "identity", "the plan file's `workspace`"),
        ),
        source=Source(
            tree=_optional_str(source, "tree", "the plan file's `source`"),
            dirty=bool(source.get("dirty", False)),
        ),
        steps=tuple(_step_from_json(s) for s in _array(doc.get("steps"), "`steps`")),
    )


def step_plan_to_json(plan: StepPlan, where: str = "a step's plan") -> dict[str, Any]:
    _no_secrets(plan.payload, f"{where}: its payload")
    return {
        "changes": [_change_to_json(c) for c in plan.changes],
        "outputs": {name: _value_to_json(v, where) for name, v in plan.outputs.items()},
        "later": list(plan.later),
        "waiting": plan.waiting,
        "notes": list(plan.notes),
        "payload": plan.payload,
    }


def step_plan_from_json(document: Json, where: str = "a step's plan") -> StepPlan:
    doc = _object(document, where)
    unknown = set(doc) - _STEP_PLAN_KEYS
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
        outputs={name: _value_from_json(value) for name, value in outputs.items()},
        later=_strings(doc.get("later", []), f"{where}: `later`"),
        waiting=_optional_str(doc, "waiting", where),
        notes=_strings(doc.get("notes", []), f"{where}: `notes`"),
        payload=doc.get("payload"),
    )


# -- what a run leaves behind ---------------------------------------------------


def result_to_json(result: Result) -> dict[str, Any]:
    """A run, with its three lists: what ran, what failed, what never started."""
    return {
        "kind": result.kind,
        "target": result.target,
        "workspace": _workspace_to_json(result.workspace),
        "outcome": result.outcome,
        "message": result.message,
        "ran": [step.name for step in result.ran],
        "failed": [step.name for step in result.failed],
        "refused": [step.name for step in result.refused],
        "not_started": [step.name for step in result.not_started],
        "rolled_back": [],
        "steps": [
            {
                "name": step.name,
                "uses": step.uses,
                "outcome": step.outcome,
                "detail": step.detail,
                "changes": [_change_to_json(c) for c in step.changes],
                "overview": overview_to_json(step.overview, step.happened),
            }
            for step in result.steps
        ],
    }


def status_to_json(status: Status) -> dict[str, Any]:
    return {
        "target": status.target,
        "workspace": _workspace_to_json(status.workspace),
        "steps": [
            {
                "name": step.name,
                "uses": step.uses,
                "note": step.note,
                "overview": overview_to_json(step.overview),
            }
            for step in status.steps
        ],
    }


def overview_to_json(
    overview: Overview | None, happened: Mapping[str, str] | None = None
) -> dict[str, Any] | None:
    if overview is None:
        return None
    return {
        "items": [
            {
                "kind": item.kind,
                "key": item.key,
                "name": item.name,
                "deployed": item.deployed,
                "id": item.id,
                "url": item.url,
                **(
                    {}
                    if happened is None
                    else {"happened": happened.get(item.key, "unchanged")}
                ),
            }
            for item in overview.items
        ],
        "notes": list(overview.notes),
    }


# -----------------------------------------------------------------------------


def _workspace_to_json(workspace: Workspace) -> dict[str, Any]:
    return {"host": workspace.host, "identity": workspace.identity}


def _step_to_json(step: PlannedStep) -> dict[str, Any]:
    where = f"step `{step.name}`"
    return {
        "name": step.name,
        "uses": step.uses,
        "state": step.state,
        "made_from": step.made_from,
        "waits_for": list(step.waits_for),
        "every_deploy": step.every_deploy,
        "skipped": step.skipped,
        "inputs": [
            {
                "label": i.label,
                "from": i.source,
                "known": i.known,
                "value": _value_to_json(i.value, where) if i.known else None,
            }
            for i in step.inputs
        ],
        "plan": step_plan_to_json(step.plan, where),
    }


def _step_from_json(document: Json) -> PlannedStep:
    doc = _object(document, "a planned step")
    name = _str(doc, "name", "a planned step")
    where = f"step `{name}`"
    inputs = []
    for raw in _array(doc.get("inputs", []), f"{where}: `inputs`"):
        entry = _object(raw, f"{where}: an input")
        inputs.append(
            Input(
                label=_str(entry, "label", f"{where}: an input"),
                source=_str(entry, "from", f"{where}: an input"),
                value=_value_from_json(entry.get("value")),
                known=bool(entry.get("known", True)),
            )
        )
    step = PlannedStep(
        name=name,
        uses=_str(doc, "uses", where),
        made_from=_str(doc, "made_from", where),
        plan=step_plan_from_json(doc.get("plan"), where),
        inputs=tuple(inputs),
        waits_for=_strings(doc.get("waits_for", []), f"{where}: `waits_for`"),
        skipped=_optional_str(doc, "skipped", where),
        every_deploy=bool(doc.get("every_deploy", False)),
    )
    # A step that isn't ready shows no changes, so it can't hold any: a file
    # that says both would hide what it then lets through.
    if step.plan.changes and (step.skipped is not None or step.waits_for):
        raise PlanFileError(
            f"{where} is {step.state} and holds changes; lely writes no such plan. "
            "Run `lely plan` again."
        )
    return step


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


def _value_to_json(value: Value, where: str) -> Json:
    if isinstance(value, Secret):
        return {_SECRET: True}
    _no_secrets(value, f"{where}: an output")
    return value


def _value_from_json(value: Json) -> Value:
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


def _strings(value: Json, where: str) -> tuple[str, ...]:
    return tuple(str(item) for item in _array(value, where))


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

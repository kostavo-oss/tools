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

import dataclasses
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
_PLAN_KEYS = frozenset(
    {"format_version", "tool_version", "kind", "target", "workspace", "source", "steps"}
)
_STEP_KEYS = frozenset(
    {
        "name",
        "uses",
        "state",
        "made_from",
        "waits_for",
        "every_deploy",
        "skipped",
        "inputs",
        "plan",
    }
)
_INPUT_KEYS = frozenset({"label", "from", "known", "value"})
_CHANGE_KEYS = frozenset({"key", "action", "summary", "destructive", "detail"})


class PlanFileError(LelyError):
    """A plan file (or a plan command's output) that can't be read."""


def dumps(plan: Plan) -> str:
    return json.dumps(plan_to_json(plan), indent=2) + "\n"


def loads(text: str) -> Plan:
    try:
        document = json.loads(text)
    except (ValueError, RecursionError) as error:  # not JSON, or a number too long
        raise PlanFileError(f"Not a plan file: {error}") from None
    return plan_from_json(document)


def plan_to_json(plan: Plan) -> dict[str, Any]:
    return {
        "format_version": FORMAT_VERSION,
        "tool_version": plan.tool_version,
        "kind": plan.kind,
        "target": plan.target,
        "workspace": _workspace_to_json(plan.workspace),
        "source": {
            "tree": plan.source.tree,
            "dirty": plan.source.dirty,
            "root": plan.source.root,
        },
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
    _only(doc, _PLAN_KEYS, "the plan file")
    workspace = _object(doc.get("workspace"), "the plan file's `workspace`")
    source = _object(doc.get("source"), "the plan file's `source`")
    target = _str(doc, "target", "the plan file")
    if not target.strip():
        # the Databricks CLI would read an empty target as "the default one"
        raise PlanFileError("the plan file: `target` is empty; a plan names its target")
    steps = tuple(_step_from_json(s) for s in _array(doc.get("steps"), "`steps`"))
    names = [step.name for step in steps]
    if len(set(names)) != len(names):
        raise PlanFileError("the plan file: two steps share a name")
    return Plan(
        tool_version=_str(doc, "tool_version", "the plan file"),
        kind=cast(PlanKind, kind),
        target=target,
        workspace=Workspace(
            host=_str(workspace, "host", "the plan file's `workspace`"),
            identity=_str(workspace, "identity", "the plan file's `workspace`"),
        ),
        source=Source(
            tree=_optional_str(source, "tree", "the plan file's `source`"),
            dirty=_bool(source, "dirty", "the plan file's `source`"),
            root=_optional_str(source, "root", "the plan file's `source`"),
        ),
        steps=steps,
    )


def step_plan_to_json(plan: StepPlan, where: str = "a step's plan") -> dict[str, Any]:
    return {
        "changes": [_change_to_json(c) for c in plan.changes],
        "outputs": {name: _value_to_json(v, where) for name, v in plan.outputs.items()},
        "later": list(plan.later),
        "waiting": plan.waiting,
        "notes": list(plan.notes),
        "payload": plain(plan.payload, f"{where}: its payload"),
    }


def normalised(plan: StepPlan, where: str = "a step's plan") -> StepPlan:
    """A plugin's plan as it reads back from a plan file: a tuple in an output
    is a list, and so on. Planning hands on this one, so a plan is the same
    whether it went through a file or not — and what was approved can be
    compared with what is planned again."""
    return dataclasses.replace(
        plan,
        outputs=normalised_outputs(plan.outputs, where),
        later=tuple(plan.later),
        notes=tuple(plan.notes),
        payload=plain(plan.payload, f"{where}: its payload"),
    )


def normalised_outputs(outputs: Outputs, where: str) -> dict[str, Value]:
    return {
        name: value if isinstance(value, Secret) else plain(value, f"{where}: an output")
        for name, value in outputs.items()
    }


def plain(value: Any, where: str) -> Json:
    """`value` as JSON holds it, or a `PlanFileError` saying why it can't.

    No secret, at any depth; no key that isn't text; nothing JSON has no word
    for — a date, a set, a number that isn't one.
    """
    if isinstance(value, Secret):
        raise PlanFileError(
            f"{where} holds a secret; a plan file never does. Make it an output of "
            "its own (a `Secret`), or fetch it at apply."
        )
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise PlanFileError(f"{where} holds {value}, which isn't JSON")
        return value
    if isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                raise PlanFileError(
                    f"{where} holds a key that isn't text ({key!r}), which isn't JSON"
                )
        return {key: plain(item, where) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [plain(item, where) for item in value]
    raise PlanFileError(f"{where} holds a {type(value).__name__}, which isn't JSON")


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
    _only(doc, _STEP_KEYS, where)
    inputs = []
    for raw in _array(doc.get("inputs", []), f"{where}: `inputs`"):
        entry = _object(raw, f"{where}: an input")
        _only(entry, _INPUT_KEYS, f"{where}: an input")
        inputs.append(
            Input(
                label=_str(entry, "label", f"{where}: an input"),
                source=_str(entry, "from", f"{where}: an input"),
                value=_value_from_json(entry.get("value")),
                known=_bool(entry, "known", f"{where}: an input", default=True),
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
        every_deploy=_bool(doc, "every_deploy", where),
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
    _only(doc, _CHANGE_KEYS, f"{where}: change {key!r}")
    action = doc.get("action")
    if action not in ACTIONS:
        raise PlanFileError(
            f"{where}: change {key!r}: action must be one of {', '.join(ACTIONS)}, "
            f"not {action!r}"
        )
    detail = _array(doc.get("detail", []), f"{where}: change {key!r} detail")
    if not all(isinstance(line, str) for line in detail):
        raise PlanFileError(f"{where}: change {key!r}: `detail` must be lines of text")
    return Change(
        key=key,
        action=cast(Action, action),
        summary=_optional_str(doc, "summary", f"{where}: change {key!r}") or key,
        destructive=_bool(doc, "destructive", f"{where}: change {key!r}"),
        detail=tuple(str(line) for line in detail),
    )


def _value_to_json(value: Value, where: str) -> Json:
    if isinstance(value, Secret):
        return {_SECRET: True}
    return plain(value, f"{where}: an output")


def _value_from_json(value: Json) -> Value:
    if isinstance(value, dict) and value.get(_SECRET) is True:
        return Secret()
    return value


def _only(doc: Mapping[str, Json], known: frozenset[str], where: str) -> None:
    """A plan file is read strictly: a key lely doesn't write is a file lely
    didn't write, or one that was edited."""
    unknown = set(doc) - known
    if unknown:
        raise PlanFileError(f"{where}: unknown keys {', '.join(sorted(unknown))}")


def _bool(
    doc: Mapping[str, Json], key: str, where: str, *, default: bool = False
) -> bool:
    value = doc.get(key, default)
    if not isinstance(value, bool):
        raise PlanFileError(f"{where}: `{key}` must be true or false")
    return value


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

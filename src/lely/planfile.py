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

A step's plan is written by `step_plan_to_json` and read back by
`step_plan_from_json`; `lely.testing` holds a plugin's plan to that round trip.
What a run leaves behind — a `Result`, a `Status` — is written here too, and
never read back.
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
    Item,
    Json,
    Outcome,
    Outputs,
    Overview,
    Plan,
    PlanKind,
    PlannedStep,
    Result,
    RunOutcome,
    Secret,
    Source,
    Status,
    StepPlan,
    StepResult,
    Value,
    Workspace,
)

#: Bumped when the shape changes in a way a reader has to know about.
#: 2: one list of steps, the bundle among them; the workspace; the git tree.
#: 3: which project of the repository; read strictly.
#: 4: a step's plan may carry its plugin's own view.
FORMAT_VERSION = 4

_SECRET = "$secret"
_STEP_PLAN_KEYS = {"changes", "outputs", "later", "waiting", "notes", "payload", "view"}
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
_WORKSPACE_KEYS = frozenset({"host", "identity"})
_SOURCE_KEYS = frozenset({"tree", "dirty", "root"})
_CHANGE_KEYS = frozenset({"key", "action", "summary", "destructive", "detail"})


class PlanFileError(LelyError):
    """A plan file that can't be read."""


#: The longest view a step's plan keeps, in characters: a view is a picture of
#: the plan, not a copy of the data. Held where a plugin hands one over and
#: where one is read from a file.
VIEW_LIMIT = 1_000_000


def dumps(plan: Plan) -> str:
    try:
        return json.dumps(plan_to_json(plan), indent=2) + "\n"
    except RecursionError:
        raise PlanFileError("The plan is nested too deep to write down.") from None


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
    _only(workspace, _WORKSPACE_KEYS, "the plan file's `workspace`")
    source = _object(doc.get("source"), "the plan file's `source`")
    _only(source, _SOURCE_KEYS, "the plan file's `source`")
    if "dirty" not in source:
        # left out, it would read as a clean checkout
        raise PlanFileError("the plan file's `source`: `dirty` must be true or false")
    target = _str(doc, "target", "the plan file")
    if not target.strip():
        # the Databricks CLI would read an empty target as "the default one"
        raise PlanFileError("the plan file: `target` is empty; a plan names its target")
    if source.get("tree") is not None and not isinstance(source.get("root"), str):
        # in a repository a plan says which project it is for; a file that
        # names a tree and no project couldn't be held to one
        raise PlanFileError("the plan file's `source`: a `tree` needs a `root`")
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
        "view": plan.view,
    }


def normalised(plan: StepPlan, where: str = "a step's plan") -> StepPlan:
    """A plugin's plan as it reads back from a plan file: a tuple in an output
    is a list, and so on. Planning hands on this one, so a plan is the same
    whether it went through a file or not — and what was approved can be
    compared with what is planned again."""
    try:
        return dataclasses.replace(
            plan,
            outputs=normalised_outputs(plan.outputs, where),
            later=tuple(plan.later),
            notes=tuple(plan.notes),
            payload=plain(plan.payload, f"{where}: its payload"),
        )
    except RecursionError:
        raise PlanFileError(f"{where} is nested too deep to write down") from None


def normalised_outputs(outputs: Outputs, where: str) -> dict[str, Value]:
    try:
        return {
            name: value
            if isinstance(value, Secret)
            else plain(value, f"{where}: an output")
            for name, value in outputs.items()
        }
    except RecursionError:
        raise PlanFileError(
            f"{where}: an output is nested too deep to write down"
        ) from None


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
    if value is None or isinstance(value, bool):
        return value
    # A kind of text or of number — a member of an enum, a `numpy.float64` — is
    # written as the text or the number it is, and is that from here on: what
    # a plan file reads back is then what a run in one go holds.
    if isinstance(value, str):
        return value if type(value) is str else str.__str__(value)
    if isinstance(value, int):
        value = value if type(value) is int else int(value)
        try:
            str(value)
        except ValueError:  # Python won't write an integer of thousands of digits
            raise PlanFileError(f"{where} holds a number too long to write") from None
        return value
    if isinstance(value, float):
        value = value if type(value) is float else float(value)
        if value != value or value in (float("inf"), float("-inf")):
            raise PlanFileError(f"{where} holds {value}, which isn't JSON")
        return value
    if isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                raise PlanFileError(
                    f"{where} holds a key that isn't text ({key!r}), which isn't JSON"
                )
            if key == _SECRET:
                # it would read back as a secret, and a secret is never compared
                raise PlanFileError(
                    f"{where} holds a key `{_SECRET}`, which is how a plan file "
                    "marks a secret"
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
        view=_view(doc, where),
    )


def _view(doc: Mapping[str, Json], where: str) -> str | None:
    view = _optional_str(doc, "view", where)
    if view is not None and len(view) > VIEW_LIMIT:
        raise PlanFileError(
            f"{where}: its view is {len(view)} characters, and a plan keeps at most "
            f"{VIEW_LIMIT}"
        )
    return view


# -- what a run leaves behind ---------------------------------------------------


#: The format of a run's record. A record is for reading: lely never takes
#: one back to decide anything.
RESULT_FORMAT = 1

_RESULT_KEYS = frozenset(
    {"result_format", "kind", "target", "workspace", "outcome", "message", "steps"}
    | {"ran", "failed", "refused", "not_started", "rolled_back"}
)
_RESULT_STEP_KEYS = frozenset(
    {"name", "uses", "outcome", "detail", "changes", "overview"}
)
_OVERVIEW_KEYS = frozenset({"items", "notes"})
_ITEM_KEYS = frozenset({"kind", "key", "name", "deployed", "id", "url", "happened"})
_OUTCOMES = ("done", "nothing", "skipped", "passed", "failed", "refused", "not started")


def result_to_json(result: Result) -> dict[str, Any]:
    """A run, with its three lists: what ran, what failed, what never started."""
    return {
        "result_format": RESULT_FORMAT,
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


def is_result(document: Json) -> bool:
    """Whether a JSON document says it is a run's record, and not a plan."""
    return isinstance(document, dict) and "result_format" in document


def result_from_json(document: Json) -> Result:
    """A run's record, read back to be shown — as strictly as a plan is read.

    A run that ended before its first step named no steps, and may not have
    known its target or its workspace: those read back as `?`.
    """
    where = "the result file"
    doc = _object(document, where)
    version = doc.get("result_format")
    if version != RESULT_FORMAT:
        raise PlanFileError(
            f"This result file is format {version}; this lely reads format "
            f"{RESULT_FORMAT}."
        )
    _only(doc, _RESULT_KEYS, where)
    kind, outcome = doc.get("kind"), doc.get("outcome")
    if kind not in ("apply", "destroy"):
        raise PlanFileError(f"{where}: `kind` must be apply or destroy, not {kind!r}")
    if outcome not in ("done", "failed", "refused"):
        raise PlanFileError(f"{where}: `outcome` must be done, failed or refused")
    host = identity = "?"
    if doc.get("workspace") is not None:
        workspace = _object(doc.get("workspace"), f"{where}'s `workspace`")
        _only(workspace, _WORKSPACE_KEYS, f"{where}'s `workspace`")
        host = _str(workspace, "host", f"{where}'s `workspace`")
        identity = _str(workspace, "identity", f"{where}'s `workspace`")
    result = Result(
        kind=cast(PlanKind, kind),
        target=_optional_str(doc, "target", where) or "?",
        workspace=Workspace(host, identity),
        steps=tuple(
            _step_result_from_json(step)
            for step in _array(doc.get("steps", []), f"{where}: `steps`")
        ),
        outcome=cast(RunOutcome, outcome),
        message=_optional_str(doc, "message", where) or "",
    )
    _one_story(result, doc, where)
    return result


def _one_story(result: Result, doc: Mapping[str, Json], where: str) -> None:
    """A record says how the run ended in three places: its `outcome`, each
    step's own, and the lists of names. lely writes them from one result, so
    they agree; a file where they don't was edited, and would show a run that
    failed as one that was applied."""
    names = [step.name for step in result.steps]
    if len(set(names)) != len(names):
        raise PlanFileError(f"{where}: two steps share a name")
    if len(result.failed) + len(result.refused) > 1:
        # the first step that fails or is refused stops the run
        raise PlanFileError(
            f"{where}: more than one step failed or was refused; lely writes no "
            "such record."
        )
    if result.outcome == "done" and result.message:
        raise PlanFileError(
            f"{where}: `outcome` says done, and its `message` says what went wrong; "
            "lely writes no such record."
        )
    if result.steps:
        ended = "refused" if result.refused else "failed" if result.failed else "done"
        unfinished = bool(result.not_started) and ended == "done"
        if result.outcome != ended or unfinished:
            raise PlanFileError(
                f"{where}: `outcome` says {result.outcome}, and its steps say "
                f"otherwise; lely writes no such record."
            )
    lists = {
        "ran": result.ran,
        "failed": result.failed,
        "refused": result.refused,
        "not_started": result.not_started,
    }
    for key, steps in lists.items():
        if doc.get(key) != [step.name for step in steps]:
            raise PlanFileError(
                f"{where}: `{key}` doesn't name the steps that its `steps` say "
                f"{key.replace('_', ' ')}; lely writes no such record."
            )
    if doc.get("rolled_back") != []:
        raise PlanFileError(
            f"{where}: `rolled_back` is never anything: lely rolls nothing back"
        )


def _step_result_from_json(document: Json) -> StepResult:
    doc = _object(document, "a step of the result")
    name = _str(doc, "name", "a step of the result")
    where = f"step `{name}`"
    _only(doc, _RESULT_STEP_KEYS, where)
    outcome = doc.get("outcome")
    if outcome not in _OUTCOMES:
        raise PlanFileError(f"{where}: `outcome` must be one of {', '.join(_OUTCOMES)}")
    overview, happened = None, {}
    if doc.get("overview") is not None:
        overview, happened = _overview_from_json(doc.get("overview"), where)
    return StepResult(
        name=name,
        uses=_str(doc, "uses", where),
        outcome=cast(Outcome, outcome),
        detail=_optional_str(doc, "detail", where) or "",
        changes=tuple(
            _change_from_json(change, where)
            for change in _array(doc.get("changes", []), f"{where}: `changes`")
        ),
        overview=overview,
        happened=happened,
    )


def _overview_from_json(document: Json, where: str) -> tuple[Overview, dict[str, str]]:
    """What exists, and what the run did to each thing. What the run removed
    is listed by its key alone: it is no longer a thing that exists."""
    doc = _object(document, f"{where}: its overview")
    _only(doc, _OVERVIEW_KEYS, f"{where}: its overview")
    items: list[Item] = []
    happened: dict[str, str] = {}
    for raw in _array(doc.get("items", []), f"{where}: its overview's `items`"):
        entry = _object(raw, f"{where}: a line of its overview")
        _only(entry, _ITEM_KEYS, f"{where}: a line of its overview")
        key = _str(entry, "key", f"{where}: a line of its overview")
        line = f"{where}: `{key}` of its overview"
        did = _optional_str(entry, "happened", line)
        if did is not None and did != "unchanged":
            happened[key] = did
        kind = _str(entry, "kind", line)
        if not kind:
            continue  # removed by the run: there is nothing left to list
        items.append(
            Item(
                kind=kind,
                key=key,
                name=_str(entry, "name", line),
                deployed=_bool(entry, "deployed", line),
                id=_optional_str(entry, "id", line),
                url=_optional_str(entry, "url", line),
            )
        )
    notes = _strings(doc.get("notes", []), f"{where}: its overview's `notes`")
    return Overview(tuple(items), notes), happened


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
    """An overview as JSON — and, right after a run (`happened` is not `None`),
    what the run did to each thing. What the run removed is no longer in the
    overview: it is listed after what is left, by its key, as the terminal
    lists it."""
    if overview is None:
        return None
    did = happened or {}
    listed = {item.key for item in overview.items}
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
                    else {"happened": did.get(item.key, "unchanged")}
                ),
            }
            for item in overview.items
        ]
        + [
            {
                "kind": "",
                "key": key,
                "name": "",
                "deployed": False,
                "id": None,
                "url": None,
                "happened": word,
            }
            for key, word in did.items()
            if key not in listed
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
    # `state` is written for whoever reads the file, and worked out again from
    # the rest by lely. A file where the two differ tells its reader one thing
    # and lely another.
    said = doc.get("state", step.state)
    if said != step.state:
        raise PlanFileError(
            f"{where}: `state` says {said!r}, and the rest of the step says it is "
            f"{step.state}; lely writes no such plan. Run `lely plan` again."
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
    if value == {_SECRET: True}:  # exactly the marker, and nothing beside it
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

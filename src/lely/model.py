"""What lely talks in: changes, plans, outputs, overviews, results.

A plugin answers `plan` with a `StepPlan` of `Change`s; the core puts every
step's into one `Plan`. That is what `plan -o` writes, what `show` renders, and
what `apply` and `destroy` check a fresh plan against before they let a step
run. A `Result` is what a run leaves behind.

Frozen, slotted dataclasses. `outputs` is a mapping rather than a tuple of
pairs because plugin authors read it by name; nothing hashes a plan.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from lely.errors import LelyError

Json: TypeAlias = None | bool | int | float | str | list["Json"] | dict[str, "Json"]

#: What a change does. `run` is the odd one: it isn't a difference between two
#: states but something that happens on every apply — a job run, a script, a
#: bundle's files uploaded — so a plan that holds one is never empty.
Action: TypeAlias = Literal["create", "update", "delete", "replace", "run"]
ACTIONS: tuple[Action, ...] = ("create", "update", "delete", "replace", "run")

#: Actions that lose something by definition. A plugin may mark any other change
#: destructive too (an update that drops a column); it can't unmark these.
DESTRUCTIVE_ACTIONS: frozenset[str] = frozenset({"delete", "replace"})

#: When an output is known: always when planning; when planning if the thing is
#: there already, otherwise after apply; or never when planning, because it is
#: produced by running.
Known: TypeAlias = Literal["plan", "exists", "run"]
KNOWN: dict[str, str] = {
    "plan": "at plan",
    "exists": "once it exists",
    "run": "after every run",
}

PlanKind: TypeAlias = Literal["apply", "destroy"]
StepState: TypeAlias = Literal["ready", "waiting", "skipped"]


@dataclass(frozen=True, slots=True)
class Secret:
    """A value a step needs, but no plan may show or keep.

    It renders as `***` and is never written to a plan file. One read back from
    a plan file has no value: `apply` plans every step again before it runs
    one, so what a step needs at apply is fetched fresh.
    """

    _value: str | None = field(default=None, repr=False, compare=False)

    def reveal(self) -> str:
        if self._value is None:
            raise LelyError(
                "This secret was read back from a plan file, which never keeps one; "
                "it is fetched again when the step is planned at apply."
            )
        return self._value

    def __str__(self) -> str:
        return "***"


Value: TypeAlias = Json | Secret
Outputs: TypeAlias = Mapping[str, Value]


@dataclass(frozen=True, slots=True)
class Output:
    """Something a step gives, and when it is known.

    `name` is a plain name (`version`) or a shape, for a name that depends on
    the project: `resources.<type>.<key>.id`, where each `<…>` stands for
    exactly one part.
    """

    name: str
    known: Known = "plan"
    doc: str = ""

    def __post_init__(self) -> None:
        if self.known not in KNOWN:
            raise LelyError(
                f"Output `{self.name}`: `known` must be one of {', '.join(KNOWN)}, "
                f"not {self.known!r}."
            )
        if not self.name or not all(self.parts):
            raise LelyError(f"`{self.name}` is not an output's name: dotted parts.")

    @property
    def parts(self) -> tuple[str, ...]:
        return tuple(self.name.split("."))

    @property
    def shape(self) -> bool:
        return any(part.startswith("<") for part in self.parts)


@dataclass(frozen=True, slots=True)
class Change:
    """One thing a step would do.

    `key` is the change's identity across plans — a table name, a resource key
    — so the plan made at apply can be matched against the one that was
    approved. It must be unique within a step's plan.
    """

    key: str
    action: Action
    summary: str
    destructive: bool = False
    detail: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.action not in ACTIONS:
            raise LelyError(
                f"A change's action must be one of {', '.join(ACTIONS)}, "
                f"not {self.action!r} (change {self.key!r})."
            )
        if self.action in DESTRUCTIVE_ACTIONS and not self.destructive:
            object.__setattr__(self, "destructive", True)
        # One spelling, so a change reads the same before and after a plan
        # file: a change with no summary is named by its key, and its detail
        # is a tuple whatever it was handed.
        if not self.summary:
            object.__setattr__(self, "summary", self.key)
        if not isinstance(self.detail, tuple):
            object.__setattr__(self, "detail", tuple(self.detail))


@dataclass(frozen=True, slots=True)
class StepPlan:
    """A plugin's answer to `plan`, and to `plan_destroy`.

    `outputs` are what the step knows now, by declared name. `later` names the
    declared outputs that will exist only once the step has been applied — the
    id of a job this deploy creates. `waiting` says why part of the plan can't
    be made yet. `notes` are lines shown with the plan that are not changes.
    `payload` is the plugin's own data, carried through the plan file.
    """

    changes: tuple[Change, ...] = ()
    outputs: Outputs = field(default_factory=dict)
    later: tuple[str, ...] = ()
    waiting: str | None = None
    notes: tuple[str, ...] = ()
    payload: Json = None

    @property
    def empty(self) -> bool:
        return not self.changes and self.waiting is None

    @property
    def destructive(self) -> bool:
        return any(change.destructive for change in self.changes)


@dataclass(frozen=True, slots=True)
class Skip:
    """A plugin's answer when there is nothing to destroy, or nothing to list."""

    reason: str


@dataclass(frozen=True, slots=True)
class Item:
    """One line of an overview: a thing that exists because of a step."""

    kind: str
    key: str
    name: str
    deployed: bool
    id: str | None = None
    url: str | None = None


@dataclass(frozen=True, slots=True)
class Overview:
    """What exists because of a step. `notes` say whose view it is."""

    items: tuple[Item, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Linked:
    """An option that names a whole step: `bundle: app`.

    The plugin is given that step's own options, resolved, and what it gives.
    The named step stands above the one that names it, like any reference.
    """

    name: str
    uses: str
    options: object
    outputs: Outputs = field(default_factory=dict)
    later: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Input:
    """One thing a step takes: where it goes, where it comes from, its value.

    `label` is the option it fills (`model_version`), empty for an item of a
    list. `source` is `<step>.<output>`, or `<step>` for a linked step. `value`
    is there only when `known`; a secret is shown as `***` and never written.
    """

    label: str
    source: str
    value: Value = None
    known: bool = True


@dataclass(frozen=True, slots=True)
class Workspace:
    """Which workspace a run talks to, and as whom."""

    host: str
    identity: str

    def __str__(self) -> str:
        return f"{self.host} as {self.identity}"


@dataclass(frozen=True, slots=True)
class Source:
    """The version of the project a plan was made from.

    `tree` is every tracked file as it was on disk, as one git tree; `None`
    outside a repository. `dirty` says some of that was uncommitted. `root` is
    the project's folder in the repository, from its top: two projects that
    share a tree are still two projects.
    """

    tree: str | None = None
    dirty: bool = False
    root: str | None = None


@dataclass(frozen=True, slots=True)
class PlannedStep:
    """A step as planned.

    `made_from` is a hash of the step's plugin and its options as written, so a
    plan whose step was reconfigured since is refused rather than applied.
    `waits_for` names the outputs it takes that aren't known yet; `every_deploy`
    says one of them is only ever produced by a run, so the step waits not just
    the first time. `skipped` says why the step isn't part of this run.
    """

    name: str
    uses: str
    made_from: str
    plan: StepPlan = field(default_factory=StepPlan)
    inputs: tuple[Input, ...] = ()
    waits_for: tuple[str, ...] = ()
    skipped: str | None = None
    every_deploy: bool = False

    @property
    def state(self) -> StepState:
        if self.skipped is not None:
            return "skipped"
        if self.waits_for or self.plan.waiting is not None:
            return "waiting"
        return "ready"

    @property
    def waiting(self) -> str | None:
        """What a waiting step waits for, in words."""
        if self.waits_for:
            words = "waiting for " + ", ".join(self.waits_for)
            return words + (" — on every deploy" if self.every_deploy else "")
        if self.plan.waiting is not None:
            return f"waiting: {self.plan.waiting}"
        return None


@dataclass(frozen=True, slots=True)
class Summary:
    changes: int
    runs: int
    destructive: int
    waiting: int

    @property
    def empty(self) -> bool:
        return not (self.changes or self.runs or self.waiting)


@dataclass(frozen=True, slots=True)
class Plan:
    """A whole deploy, or a whole teardown: every step, in the order written."""

    tool_version: str
    kind: PlanKind
    target: str
    workspace: Workspace
    source: Source
    steps: tuple[PlannedStep, ...]

    @property
    def summary(self) -> Summary:
        active = [step for step in self.steps if step.state != "skipped"]
        changes = [change for step in active for change in step.plan.changes]
        return Summary(
            changes=sum(1 for c in changes if c.action != "run"),
            runs=sum(1 for c in changes if c.action == "run"),
            destructive=sum(1 for c in changes if c.destructive),
            waiting=sum(1 for step in active if step.state == "waiting"),
        )

    @property
    def waiting(self) -> tuple[PlannedStep, ...]:
        return tuple(step for step in self.steps if step.state == "waiting")

    def step(self, name: str) -> PlannedStep | None:
        for step in self.steps:
            if step.name == name:
                return step
        return None


#: What a run did to a thing an overview lists, by the action that was applied.
HAPPENED: dict[str, str] = {
    "create": "created",
    "update": "changed",
    "replace": "replaced",
    "delete": "deleted",
}

#: How a step ended. `passed` is a step `--from` went past: planned for what it
#: gives the others, not applied.
Outcome: TypeAlias = Literal[
    "done", "nothing", "skipped", "passed", "failed", "refused", "not started"
]
RunOutcome: TypeAlias = Literal["done", "failed", "refused"]


@dataclass(frozen=True, slots=True)
class StepResult:
    """What became of one step in an apply or a destroy.

    `happened` says, per overview key, what this run did to it: created,
    changed, replaced, deleted. It comes from the plan that was just applied,
    in the same run; nothing is remembered.
    """

    name: str
    uses: str
    outcome: Outcome
    detail: str = ""
    changes: tuple[Change, ...] = ()
    overview: Overview | None = None
    happened: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Result:
    """A run: every step, in the order it was taken."""

    kind: PlanKind
    target: str
    workspace: Workspace
    steps: tuple[StepResult, ...]
    outcome: RunOutcome = "done"
    message: str = ""

    @property
    def ran(self) -> tuple[StepResult, ...]:
        """The steps that did something. One with nothing to do didn't run."""
        return tuple(s for s in self.steps if s.outcome == "done")

    @property
    def failed(self) -> tuple[StepResult, ...]:
        return tuple(s for s in self.steps if s.outcome == "failed")

    @property
    def refused(self) -> tuple[StepResult, ...]:
        """A refusal isn't a failure: running again won't help, a new plan will."""
        return tuple(s for s in self.steps if s.outcome == "refused")

    @property
    def not_started(self) -> tuple[StepResult, ...]:
        return tuple(s for s in self.steps if s.outcome == "not started")


@dataclass(frozen=True, slots=True)
class StepStatus:
    """One step in `lely status`: what exists because of it, or why not shown."""

    name: str
    uses: str
    overview: Overview | None = None
    note: str = ""


@dataclass(frozen=True, slots=True)
class Status:
    target: str
    workspace: Workspace
    steps: tuple[StepStatus, ...]

"""The plan: what every step, and the bundle, would change.

A step answers `plan` with a `StepPlan` of `Change`s; the core puts those, and
the bundle's own plan, into one `Plan`. That is what `plan -o` writes, what
`show` renders, and — from milestone 2 — what `apply` checks a fresh plan
against before it lets a step run.

Frozen, slotted dataclasses. `outputs` is a mapping rather than a tuple of
pairs because step authors read it by name; nothing hashes a plan.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from lely.errors import LelyError

Json: TypeAlias = None | bool | int | float | str | list["Json"] | dict[str, "Json"]

#: What a change does. `run` is the odd one: it isn't a difference between two
#: states but an action, so a plan that holds one is never empty.
Action: TypeAlias = Literal["create", "update", "delete", "replace", "run"]
ACTIONS: tuple[Action, ...] = ("create", "update", "delete", "replace", "run")

#: Actions that lose something by definition. A step may mark any other change
#: destructive too (an update that drops a column); it can't unmark these.
DESTRUCTIVE_ACTIONS: frozenset[str] = frozenset({"delete", "replace"})

Phase: TypeAlias = Literal["pre", "post"]


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
class Change:
    """One thing a step (or the bundle) would do.

    `key` is the change's identity across plans — a table name, a resource key,
    a revision — so the plan made at apply can be matched against the one that
    was approved. It must be unique within a step's plan.
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


@dataclass(frozen=True, slots=True)
class StepPlan:
    """A step's answer to `plan`.

    `outputs` are what the step knows now, for the steps after it (and the
    bundle's variables). `deferred` says why part of the plan can only be
    decided at apply — something this deploy creates. `payload` is the step's
    own data, carried through the plan file to its `apply` untouched.
    """

    changes: tuple[Change, ...] = ()
    outputs: Outputs = field(default_factory=dict)
    deferred: str | None = None
    payload: Json = None

    @property
    def empty(self) -> bool:
        return not self.changes and self.deferred is None

    @property
    def destructive(self) -> bool:
        return any(change.destructive for change in self.changes)


@dataclass(frozen=True, slots=True)
class PlannedStep:
    """A step as planned: which one, where it runs, and its plan.

    `options_hash` covers the step's resolved options, so a plan whose step was
    reconfigured since is refused rather than applied. Values read from the
    environment count by name, not by value: a rotated token isn't a new plan.
    """

    name: str
    uses: str
    phase: Phase
    options_hash: str
    plan: StepPlan


@dataclass(frozen=True, slots=True)
class BundlePlan:
    """The bundle's part: its changes, and the variables lely passes it.

    `document` is the Databricks CLI's own plan, kept whole so apply can hand it
    back to `bundle deploy --plan`. It is `None` when the bundle couldn't be
    planned yet (`deferred` says why).
    """

    changes: tuple[Change, ...] = ()
    variables: tuple[tuple[str, str], ...] = ()
    document: Json = None
    deferred: str | None = None


@dataclass(frozen=True, slots=True)
class Summary:
    changes: int
    runs: int
    destructive: int
    deferred: int

    @property
    def empty(self) -> bool:
        return not (self.changes or self.runs or self.deferred)


@dataclass(frozen=True, slots=True)
class Plan:
    """A whole deploy: the pre steps, the bundle, the post steps, in order."""

    tool_version: str
    target: str
    bundle: str
    config_hash: str
    pre: tuple[PlannedStep, ...]
    deploy: BundlePlan
    post: tuple[PlannedStep, ...]

    @property
    def steps(self) -> tuple[PlannedStep, ...]:
        return self.pre + self.post

    @property
    def summary(self) -> Summary:
        changes = [c for s in self.steps for c in s.plan.changes] + list(
            self.deploy.changes
        )
        deferred = sum(1 for s in self.steps if s.plan.deferred) + (
            1 if self.deploy.deferred else 0
        )
        return Summary(
            changes=sum(1 for c in changes if c.action != "run"),
            runs=sum(1 for c in changes if c.action == "run"),
            destructive=sum(1 for c in changes if c.destructive),
            deferred=deferred,
        )

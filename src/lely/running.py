"""Apply, destroy, status: the half of lely that changes a workspace, and the
command that shows what is there.

**Apply** goes down the list. Each step is planned again immediately before it
runs, and may run only if every change in that fresh plan is one that was shown
and approved (`approval.py`). A step that was *waiting* when the plan was made
was never shown: a reviewed file stops there; a run at a terminal asks again;
`--yes` without a file runs it. Never out of order, and never past
`--allow-destructive`.

**Destroy** resolves every step's options from the top down, by planning each
as usual — a step that only looks something up still does its lookup — and then
removes from the bottom up, so a step below the bundle is destroyed while the
bundle, and the id it needed, still exist.

The first failing step stops a run; nothing after it starts, and nothing is
rolled back. A failure is finished by running again; a refusal takes a new plan.

Nothing is remembered between runs. Every plugin is asked again.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from lely import approval
from lely import step as contract
from lely.config import Config, StepConfig
from lely.errors import LelyError, Refused
from lely.model import (
    HAPPENED,
    Outcome,
    Overview,
    Plan,
    PlannedStep,
    Result,
    RunOutcome,
    Skip,
    Status,
    StepPlan,
    StepResult,
    StepStatus,
    Workspace,
)
from lely.planning import Prepared, Session, made_from, missing
from lely.registry import find
from lely.step import Cli, Log

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient

#: Asked at a step that was waiting when the plan was made, with the step as it
#: is planned now. `True` runs it.
AtWaiting = Callable[[PlannedStep], bool]


def apply(
    config: Config,
    approved: Plan,
    *,
    workspace: Workspace,
    env: Mapping[str, str],
    databricks: Cli,
    log: Log,
    connect: Callable[[], WorkspaceClient],
    allow_destructive: bool = False,
    from_step: str | None = None,
    at_waiting: AtWaiting | None = None,
) -> Result:
    """Run `approved`, a plan to apply.

    `at_waiting` is `None` for a plan that was reviewed as a file: it stops at
    a waiting step. Raises `Refused` when nothing may start at all.
    """
    if approved.kind != "apply":
        raise Refused(
            "This is a plan to destroy, and `lely apply` only applies. Run it with "
            f"`lely destroy <file> -t {approved.target}`."
        )
    target = approved.target
    active = [step for step in config.steps if step.runs_for(target)]
    _known_step(from_step, active)
    for step in active:
        found = find(step.uses, config.root)
        if not contract.applies(found.cls):
            raise Refused(
                f"Step `{step.name}` uses `{step.uses}`, which can plan and can't "
                "apply yet. Nothing was run."
            )
    approval.destructive_allowed(approved.steps, allow_destructive)

    session = Session(config, target, workspace, env, databricks, log, connect)
    run = _Run("apply", target, workspace)
    started = from_step is None
    for index, step in enumerate(config.steps):
        if not step.runs_for(target):
            run.add(step, "skipped", f"not for target `{target}`")
            continue
        started = started or step.name == from_step
        was = approved.step(step.name)
        try:
            prepared = session.prepare(step)
            if prepared.waits_for:
                if not started:
                    session.unplanned(prepared)
                    run.add(step, "passed", "before `--from`; couldn't be planned")
                    continue
                raise LelyError(
                    f"Step `{step.name}`: {missing(prepared.waits_for)}, now that "
                    "the steps above it have run."
                )
            fresh = session.plan(prepared)
            if not started:
                run.add(step, "passed", "before `--from`; planned, not applied")
                continue
            _may_apply(step, prepared, fresh, was, at_waiting, allow_destructive)
            if not fresh.changes:
                run.add(step, "nothing", "nothing to do")
                continue
            session.apply(prepared, fresh)
            run.add(step, "done", plan=fresh)
        except Refused as error:
            return run.stopped(step, "refused", error, config.steps[index + 1 :])
        except LelyError as error:
            return run.stopped(step, "failed", error, config.steps[index + 1 :])
    return run.done(session)


def _may_apply(
    step: StepConfig,
    prepared: Prepared,
    fresh: StepPlan,
    was: PlannedStep | None,
    at_waiting: AtWaiting | None,
    allow_destructive: bool,
) -> None:
    """Whether a freshly planned step may run. Raises `Refused` if not."""
    if fresh.waiting is not None:
        raise Refused(
            f"Step `{step.name}` still can't be planned in full: {fresh.waiting}. "
            f"{approval.AGAIN}"
        )
    if was is None or was.state == "skipped":
        raise Refused(f"Step `{step.name}` isn't in the approved plan. {approval.AGAIN}")
    if was.state == "waiting":
        if at_waiting is None:
            raise Refused(
                f"Step `{step.name}` was {was.waiting} when this plan was made, so "
                "nobody has seen what it will do. Plan again: the next plan shows it."
            )
        now = PlannedStep(
            step.name, step.uses, made_from(step), plan=fresh, inputs=prepared.inputs
        )
        if not at_waiting(now):
            raise Refused(f"Step `{step.name}` wasn't approved. Nothing more was run.")
    else:
        approval.same_inputs(was, prepared.inputs)
        approval.approved_changes(was.plan, fresh, step.name)
    if fresh.destructive and not allow_destructive:
        found = "; ".join(c.summary for c in fresh.changes if c.destructive)
        raise Refused(
            f"Step `{step.name}` holds destructive changes — {found}. Pass "
            "--allow-destructive to apply them."
        )


def destroy(
    config: Config,
    approved: Plan,
    *,
    workspace: Workspace,
    env: Mapping[str, str],
    databricks: Cli,
    log: Log,
    connect: Callable[[], WorkspaceClient],
    from_step: str | None = None,
) -> Result:
    """Run `approved`, a plan to destroy: from the bottom of the list up."""
    if approved.kind != "destroy":
        raise Refused(
            "This is a plan to apply, and `lely destroy` only destroys. Run it with "
            "`lely apply <file>`."
        )
    target = approved.target
    active = [step for step in config.steps if step.runs_for(target)]
    _known_step(from_step, active)

    # From the top down: what each step gives the ones below. Nothing is removed
    # until every step's options are resolved.
    session = Session(config, target, workspace, env, databricks, log, connect)
    resolved: dict[str, Prepared] = {}
    for step in active:
        prepared = session.prepare(step)
        resolved[step.name] = prepared
        if prepared.waits_for:
            session.unplanned(prepared)
        else:
            session.plan(prepared)

    run = _Run("destroy", target, workspace)
    order = tuple(reversed(config.steps))
    started = from_step is None
    for index, step in enumerate(order):
        if not step.runs_for(target):
            run.add(step, "skipped", f"not for target `{target}`")
            continue
        started = started or step.name == from_step
        if not started:
            run.add(step, "passed", "below `--from`; not destroyed")
            continue
        was = approved.step(step.name)
        prepared = resolved[step.name]
        try:
            if prepared.waits_for:
                run.add(step, "skipped", missing(prepared.waits_for))
                continue
            fresh = session.plan_destroy(prepared)
            if isinstance(fresh, Skip):
                run.add(step, "skipped", fresh.reason)
                continue
            if was is None:
                raise Refused(
                    f"Step `{step.name}` isn't in the approved plan. {approval.AGAIN}"
                )
            approval.approved_changes(was.plan, fresh, step.name)
            if not fresh.changes:
                run.add(step, "nothing", "nothing to destroy")
                continue
            session.destroy(prepared, fresh)
            run.add(step, "done", plan=fresh)
        except Refused as error:
            return run.stopped(step, "refused", error, order[index + 1 :])
        except LelyError as error:
            return run.stopped(step, "failed", error, order[index + 1 :])
    return run.done(None)


def status(
    config: Config,
    *,
    target: str,
    workspace: Workspace,
    env: Mapping[str, str],
    databricks: Cli,
    log: Log,
    connect: Callable[[], WorkspaceClient],
) -> Status:
    """What is deployed right now, per step. Changes nothing.

    To find it, each step's inputs are resolved from the top down, the way a
    plan does.
    """
    session = Session(config, target, workspace, env, databricks, log, connect)
    steps: list[StepStatus] = []
    for step in config.steps:
        if not step.runs_for(target):
            steps.append(
                StepStatus(
                    step.name, step.uses, note=f"skipped: not for target `{target}`"
                )
            )
            continue
        prepared = session.prepare(step)
        if prepared.waits_for:
            session.unplanned(prepared)
            note = f"can't be listed: {missing(prepared.waits_for)}"
            steps.append(StepStatus(step.name, step.uses, note=note))
            continue
        session.plan(prepared)
        found = session.overview(prepared)
        if isinstance(found, Skip):
            steps.append(StepStatus(step.name, step.uses, note=found.reason))
        else:
            steps.append(StepStatus(step.name, step.uses, overview=found))
    return Status(target, workspace, tuple(steps))


# -----------------------------------------------------------------------------


def _known_step(name: str | None, active: list[StepConfig]) -> None:
    if name is not None and name not in [step.name for step in active]:
        known = ", ".join(step.name for step in active) or "none"
        raise Refused(
            f"`--from {name}`: no step `{name}` runs for this target ({known})."
        )


@dataclasses.dataclass
class _Run:
    kind: str
    target: str
    workspace: Workspace
    steps: list[StepResult] = dataclasses.field(default_factory=list)
    applied: dict[str, StepPlan] = dataclasses.field(default_factory=dict)

    def add(
        self,
        step: StepConfig,
        outcome: Outcome,
        detail: str = "",
        *,
        plan: StepPlan | None = None,
    ) -> None:
        if plan is not None:
            self.applied[step.name] = plan
        self.steps.append(
            StepResult(
                step.name,
                step.uses,
                outcome,
                detail,
                changes=plan.changes if plan is not None else (),
            )
        )

    def stopped(
        self,
        step: StepConfig,
        outcome: RunOutcome,
        error: LelyError,
        rest: tuple[StepConfig, ...],
    ) -> Result:
        """The first step that fails stops the run: nothing after it starts."""
        assert outcome != "done"
        self.steps.append(StepResult(step.name, step.uses, outcome, str(error)))
        for later in rest:
            if later.runs_for(self.target):
                self.steps.append(StepResult(later.name, later.uses, "not started"))
            else:
                self.add(later, "skipped", f"not for target `{self.target}`")
        return self._result(outcome, str(error))

    def done(self, session: Session | None) -> Result:
        """A finished run. After an apply, every plugin that can says what now
        exists — and each line says what this run did to it."""
        if session is not None:
            self.steps = [self._with_overview(step, session) for step in self.steps]
        return self._result("done", "")

    def _with_overview(self, step: StepResult, session: Session) -> StepResult:
        prepared = session.resolved.get(step.name)
        if prepared is None or step.outcome == "skipped":
            return step
        try:
            found = session.overview(prepared)
        except LelyError as error:
            # the step ran; that it can't be listed doesn't undo that
            return dataclasses.replace(step, detail=f"couldn't be listed: {error}")
        if not isinstance(found, Overview):
            return step
        plan = self.applied.get(step.name)
        happened = {
            change.key: HAPPENED[change.action]
            for change in (plan.changes if plan is not None else ())
            if change.action in HAPPENED
        }
        return dataclasses.replace(step, overview=found, happened=happened)

    def _result(self, outcome: RunOutcome, message: str) -> Result:
        kind = "apply" if self.kind == "apply" else "destroy"
        return Result(
            kind, self.target, self.workspace, tuple(self.steps), outcome, message
        )

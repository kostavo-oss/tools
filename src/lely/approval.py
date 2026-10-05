"""What may run: the approval check, and the checks on a plan file.

Pure. Two sentences carry it: a plan reaches as far as lely can see, and
consent covers what was shown.

Every refusal here is a `Refused`: running the same thing again won't help, it
takes a new plan.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from lely.errors import Refused
from lely.model import (
    Change,
    Input,
    Plan,
    PlannedStep,
    Secret,
    Source,
    StepPlan,
    Workspace,
)

AGAIN = "Plan again."


def same_project(approved: Plan, steps: Sequence[tuple[str, str, str]]) -> None:
    """Refuse a plan file whose steps, or any step's options as written, differ
    from the project's now. `steps` are (name, uses, made-from hash), in order.

    What is compared is the config as lely reads it, not the file's text — an
    unrelated edit doesn't make a plan stale — with environment values by name.
    """
    planned = [step.name for step in approved.steps]
    current = [name for name, _, _ in steps]
    if planned != current:
        raise Refused(
            f"The plan was made for the steps {', '.join(planned) or 'none'}; the "
            f"project now has {', '.join(current) or 'none'}. {AGAIN}"
        )
    for step, (name, uses, made_from) in zip(approved.steps, steps, strict=True):
        if step.uses != uses or step.made_from != made_from:
            raise Refused(
                f"Step `{name}` is configured differently than when the plan was "
                f"made. {AGAIN}"
            )


def same_workspace(approved: Plan, workspace: Workspace) -> None:
    """A plan made against one workspace is refused on another. Consent is
    given to a target *on a workspace*, not to a name that could mean anything.

    The identity may differ: a plan is made with credentials that can only
    read, and applied with ones that can write.
    """
    if _host(approved.workspace.host) != _host(workspace.host):
        raise Refused(
            f"The plan was made for {approved.workspace.host}, and this run talks to "
            f"{workspace.host}. {AGAIN}"
        )


def same_source(approved: Plan, source: Source) -> None:
    """What was reviewed is what is deployed: refuse the file for another
    project of the repository, and on another tree.

    A plan made outside a git repository recorded nothing it can be held to —
    it said so when it was made.
    """
    planned = approved.source
    if planned.tree is None:
        return
    if source.tree is None:
        raise Refused(
            "The plan was made in a git repository, and this isn't one: lely can't "
            f"check that the project is as it was planned. {AGAIN}"
        )
    if planned.root != source.root:
        raise Refused(
            f"The plan was made for the project in {_folder(planned.root)}, and this "
            f"is the one in {_folder(source.root)}. {AGAIN}"
        )
    if source.tree == planned.tree:
        return
    if source.dirty and not planned.dirty:
        raise Refused(
            f"The project has uncommitted changes that the plan was made without. {AGAIN}"
        )
    if planned.dirty and not source.dirty:
        raise Refused(
            "The plan was made with uncommitted changes that this checkout doesn't "
            f"have. {AGAIN}"
        )
    raise Refused(
        f"The plan was made on git tree {planned.tree[:12]}, and the project is "
        f"now on {source.tree[:12]}. {AGAIN}"
    )


def _folder(root: str | None) -> str:
    return "the top of the repository" if root in (None, ".") else f"`{root}`"


def same_inputs(approved: PlannedStep, inputs: Sequence[Input]) -> None:
    """Every value a step took when it was planned must be the value it takes
    now: the plan showed `model_version = 14`, and 15 was never approved.

    The same value means the same as it would be written: `1` is not `true`,
    `14` is not `14.0` and not `"14"`.
    """
    known = {
        (taken.label, taken.source): taken.value
        for taken in approved.inputs
        if taken.known and not isinstance(taken.value, Secret)
    }
    for taken in inputs:
        key = (taken.label, taken.source)
        if key not in known or isinstance(taken.value, Secret) or not taken.known:
            continue
        if _written(known[key]) != _written(taken.value):
            raise Refused(
                f"Step `{approved.name}` takes {taken.source} = {taken.value!r} now; "
                f"the plan was approved with {known[key]!r}. {AGAIN}"
            )


def _written(value: object) -> str:
    """A value as JSON writes it: what tells `1` from `true` and from `1.0`,
    and makes a tuple and a list of the same things the same."""
    return json.dumps(value, sort_keys=True, default=repr)


def approved_changes(approved: StepPlan, fresh: StepPlan, step: str) -> None:
    """The approval check: every change in the fresh plan must be one that was
    shown — the same thing, the same kind of change, the same lines.

    Fewer changes is fine: someone else did part of the work, or an earlier run
    did. Anything new, or anything that reads differently, stops the run.
    """
    shown = {change.key: change for change in approved.changes}
    for change in fresh.changes:
        was = shown.get(change.key)
        if was is None:
            raise Refused(
                f"Step `{step}` would now also {_says(change)}, which the approved "
                f"plan didn't show. {AGAIN}"
            )
        if was != change:
            raise Refused(
                f"Step `{step}` would now {_says(change)}; the approved plan showed "
                f"it would {_says(was)}. {AGAIN}"
            )


def destructive_allowed(steps: Sequence[PlannedStep], allow: bool) -> None:
    """A destructive change needs `--allow-destructive`. Where the plan already
    shows one, this refuses before anything runs."""
    if allow:
        return
    found = [
        f"{step.name}: {change.summary}"
        for step in steps
        if step.state != "skipped"
        for change in step.plan.changes
        if change.destructive
    ]
    if found:
        raise Refused(
            "The plan holds destructive changes — " + "; ".join(found) + ". "
            "Pass --allow-destructive to apply them."
        )


def _says(change: Change) -> str:
    words = f"{change.action} {change.summary}"
    if change.destructive and change.action not in ("delete", "replace"):
        words += " (destructive)"
    if change.detail:
        words += f" [{'; '.join(change.detail)}]"
    return words


def _host(host: str) -> str:
    return host.rstrip("/").lower()

"""What may run: the approval check, and the checks on a plan file.

Pure. Two sentences carry it: a plan reaches as far as lely can see, and
consent covers what was shown.

Every refusal here is a `Refused`: running the same thing again won't help, it
takes a new plan.
"""

from __future__ import annotations

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
    Value,
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
    """What was reviewed is what is deployed. A plan file is for a clean
    checkout: refuse it for another project of the repository, on another
    tree, and whenever something differs from `HEAD` — now, or when the plan
    was made, since lely then can't say what it was made on.

    A plan made outside a git repository, or in one with no commit yet,
    recorded nothing it can be held to — it said so when it was made.
    """
    planned = approved.source
    if planned.tree is None:
        return
    if source.tree is None:
        raise Refused(
            "The plan was made on a commit of a git repository, and there is none "
            f"here: lely can't check that the project is as it was planned. {AGAIN}"
        )
    if planned.root != source.root:
        raise Refused(
            f"The plan was made for the project in {_folder(planned.root)}, and this "
            f"is the one in {_folder(source.root)}. {AGAIN}"
        )
    if planned.dirty:
        raise Refused(
            "The plan was made with uncommitted changes, so lely can't say what it "
            "was made on. Plan again on a clean checkout — or run it without a file."
        )
    if source.dirty:
        raise Refused(
            f"The project has uncommitted changes that the plan was made without. {AGAIN}"
        )
    if source.tree != planned.tree:
        raise Refused(
            f"The plan was made on git tree {planned.tree[:12]}, and the project is "
            f"now on {source.tree[:12]}. {AGAIN}"
        )


def _folder(root: str | None) -> str:
    return "the top of the repository" if root in (None, ".") else f"`{root}`"


def same_inputs(approved: PlannedStep, inputs: Sequence[Input]) -> None:
    """Every value a step took when it was planned must be the value it takes
    now: the plan showed `model_version = 14`, and 15 was never approved.

    The same value means the same kind of value: `1` is not `true`, `14` is
    not `14.0` and not `"14"`. A secret can't be compared, and stays one: a
    value the plan showed is not replaced by one nobody can see, nor the other
    way round.
    """
    known = {(one.label, one.source): one.value for one in approved.inputs if one.known}
    for taken in inputs:
        key = (taken.label, taken.source)
        if key not in known or not taken.known:
            continue
        if not _unchanged(known[key], taken.value):
            raise Refused(
                f"Step `{approved.name}` takes {taken.source} = {_said(taken.value)} "
                f"now; the plan was approved with {_said(known[key])}. {AGAIN}"
            )


def _unchanged(was: Value, now: Value) -> bool:
    if isinstance(was, Secret) or isinstance(now, Secret):
        return isinstance(was, Secret) and isinstance(now, Secret)
    return _same(was, now)


def _said(value: Value) -> str:
    return "a secret" if isinstance(value, Secret) else repr(value)


def _same(one: object, other: object) -> bool:
    """Equal, and of one kind. Python calls `1 == True` and `14 == 14.0` true;
    a reviewer who was shown one was not shown the other. A tuple and a list
    of the same things are the same: one is what a plugin gave, the other what
    a plan file read back."""
    if isinstance(one, list | tuple) and isinstance(other, list | tuple):
        return len(one) == len(other) and all(
            _same(a, b) for a, b in zip(one, other, strict=True)
        )
    if isinstance(one, dict) and isinstance(other, dict):
        return one.keys() == other.keys() and all(
            _same(value, other[key]) for key, value in one.items()
        )
    return type(one) is type(other) and one == other


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

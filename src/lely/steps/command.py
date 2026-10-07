"""`command`: a step as commands, for steps that don't need Python.

    - name: seed
      uses: command
      with:
        plan: [./ops/seed.sh, --plan]      # optional
        apply: [./ops/seed.sh]
        destroy: [./ops/seed.sh, --drop]   # optional
        outputs: [count]                   # optional: what the step gives

Each command is a list — a program and its arguments — and is never passed
through a shell. All run in the project's directory, with the environment lely
was run in, the step's `env`, and `LELY_TARGET` and `LELY_STEP`.

**Plan.** The `plan` command prints the step's plan as JSON on stdout — the same
shape a plan file holds for a step:

    {"changes": [{"key": "…", "action": "update", "summary": "…"}],
     "outputs": {"count": 14}}

Without one, the step's plan is a single `run`: it runs on every apply. lely
can't show what a script it has never run will do.

**Apply.** The `apply` command also gets `LELY_PLAN`, a file holding the plan
that was approved for this step, and `LELY_OUTPUTS`, a file it writes its
outputs to, one `name=value` to a line.

**Outputs.** The step lists them. One the plan command prints is known at plan;
one the apply command writes is known only after the run. So without a plan
command they are all *after every run*, and a step that takes one waits on
every deploy. With a plan command lely can't know before running it which ones
it prints: they are *once it exists*. A name the step lists and gives in
neither way is a failed step.

**Destroy.** With a `destroy` command, the destroy plan shows that command line
in full, marked destructive: lely can't vouch for what it removes. Without one
the step is skipped, visibly.

**No secrets in arguments**: they would be visible to every process on the
machine. `env` may hold one. A step that has to give a secret is a Python class.
"""

from __future__ import annotations

import dataclasses
import json
import re
import shlex
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from lely import process
from lely.errors import LelyError
from lely.model import Change, Json, Output, Outputs, Secret, Skip, StepPlan
from lely.planfile import step_plan_from_json, step_plan_to_json
from lely.step import Context

_NAME = re.compile(r"[A-Za-z0-9_-]+\Z")

#: The key of the run a plan command's plan is given when the apply command
#: has an output still to give. Not the step's bare name: a plan command is
#: handed that as `LELY_STEP`, and may well key a change of its own with it.
_RUN = "{step} (apply)"


class Command:
    """Runs commands you give it: apply, and optionally plan and destroy."""

    @dataclass(frozen=True, slots=True)
    class Options:
        #: Run at apply, as a list: `[./ops/seed.sh, --fast]`.
        apply: tuple[str, ...]
        #: Prints the step's plan as JSON; without it the step always runs.
        plan: tuple[str, ...] | None = None
        #: Run at destroy; without it the step is skipped there.
        destroy: tuple[str, ...] | None = None
        #: The names of what the step gives.
        outputs: tuple[str, ...] = ()
        #: Extra environment for every command. May hold a secret.
        env: Mapping[str, Secret] = field(default_factory=dict)

    #: A command has nothing lely can list; `lely status` says so in these words.
    nothing_to_list = "runs a command; nothing to list"

    @staticmethod
    def outputs(written: Mapping[str, Json]) -> tuple[Output, ...]:
        """What a step lists under `outputs`, and when each can be known."""
        listed = written.get("outputs")
        names = listed if isinstance(listed, list) else []
        for name in names:
            if not isinstance(name, str) or not _NAME.match(name):
                raise LelyError(
                    f"`outputs` must list plain names (letters, digits, `_`, `-`), "
                    f"not {name!r}"
                )
        twice = sorted({str(name) for name in names if names.count(name) > 1})
        if twice:
            raise LelyError(f"`outputs` lists {', '.join(twice)} more than once")
        known = "exists" if written.get("plan") else "run"
        return tuple(Output(str(name), known) for name in names)

    @staticmethod
    def programs(written: Mapping[str, Json]) -> tuple[str, ...]:
        """The program each of the step's commands starts with."""
        commands = (written.get(key) for key in ("plan", "apply", "destroy"))
        return tuple(
            str(command[0])
            for command in commands
            if isinstance(command, list) and command
        )

    def plan(self, ctx: Context[Command.Options]) -> StepPlan:
        options = ctx.options
        if not options.apply:
            raise LelyError(f"step `{ctx.name}`: `apply` needs a command to run")
        if options.plan is not None and not options.plan:
            raise LelyError(f"step `{ctx.name}`: `plan` needs a command to run")
        if options.plan is None:
            shown = shlex.join(options.apply)
            return StepPlan(
                changes=(Change(key=ctx.name, action="run", summary=f"runs {shown}"),),
                later=options.outputs,
            )
        result = process.run(options.plan, ctx.root, env=_env(ctx))
        if result.returncode != 0:
            raise process.failure(f"step `{ctx.name}`'s plan command", result)
        try:
            document = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise LelyError(
                f"step `{ctx.name}`'s plan command must print JSON on stdout: {error}"
            ) from None
        where = f"step `{ctx.name}`'s plan command"
        plan = step_plan_from_json(document, where=where)
        _only_listed(plan.outputs, options, where)
        if any(isinstance(value, Secret) for value in plan.outputs.values()):
            raise LelyError(f"{where}: a `command` step can't give a secret")
        later = tuple(name for name in options.outputs if name not in plan.outputs)
        changes = plan.changes
        if later:
            # Something to give that the plan command didn't: only the apply
            # command can give it, so the step runs — and its plan says so,
            # every time, beside whatever else it changes, and in the same
            # words whichever outputs are still to come. A run that failed
            # further down can then be finished from the same plan: what is
            # left to do is something it showed.
            run = Change(
                key=_RUN.format(step=ctx.name),
                action="run",
                summary=f"runs {shlex.join(options.apply)}",
                detail=("to give its outputs",),
            )
            if any(change.key == run.key for change in changes):
                raise LelyError(
                    f"{where} prints a change keyed `{run.key}`, which is the key "
                    "of the step's own run; give that change another key"
                )
            changes = (*changes, run)
        return dataclasses.replace(plan, changes=changes, later=later)

    def apply(self, ctx: Context[Command.Options], plan: StepPlan) -> Outputs:
        options = ctx.options
        with tempfile.TemporaryDirectory(prefix="lely-command-") as scratch:
            plan_file = Path(scratch) / "plan.json"
            plan_file.write_text(json.dumps(step_plan_to_json(plan)), encoding="utf-8")
            outputs_file = Path(scratch) / "outputs"
            outputs_file.touch()
            env = {
                **_env(ctx),
                "LELY_PLAN": str(plan_file),
                "LELY_OUTPUTS": str(outputs_file),
            }
            _run(ctx, options.apply, env, "apply")
            written = _read_outputs(outputs_file.read_text(encoding="utf-8"), ctx.name)
        _only_listed(written, options, f"step `{ctx.name}`'s apply command")
        missing = [
            name
            for name in options.outputs
            if name not in written and name not in plan.outputs
        ]
        if missing:
            raise LelyError(
                f"step `{ctx.name}` lists {', '.join(f'`{m}`' for m in missing)} under "
                "`outputs`, and neither its plan command printed it nor its apply "
                "command wrote it to the file `LELY_OUTPUTS` names"
            )
        # What the apply command writes is text; what the plan command printed
        # is JSON. The same value written both ways is the one the plan gave —
        # `14`, not `"14"` — so a step below that took it still takes it.
        same = {
            name: plan.outputs[name]
            for name, value in written.items()
            if name in plan.outputs and _says(str(value), plan.outputs[name])
        }
        return {**plan.outputs, **written, **same}

    def plan_destroy(self, ctx: Context[Command.Options]) -> StepPlan | Skip:
        command = ctx.options.destroy
        if command is None:
            return Skip("it has no `destroy` command")
        if not command:
            raise LelyError(f"step `{ctx.name}`: `destroy` needs a command to run")
        return StepPlan(
            changes=(
                Change(
                    key=ctx.name,
                    action="run",
                    summary=f"runs {shlex.join(command)}",
                    destructive=True,
                ),
            ),
            notes=("lely can't vouch for what this command removes",),
        )

    def destroy(self, ctx: Context[Command.Options], plan: StepPlan) -> None:
        command = ctx.options.destroy
        if not command:  # pragma: no cover - `plan_destroy` skipped the step
            return
        _run(ctx, command, _env(ctx), "destroy")


def _run(
    ctx: Context[Command.Options],
    command: tuple[str, ...],
    env: Mapping[str, str],
    which: str,
) -> None:
    """Run a step's apply or destroy command. What it writes, on either
    stream, goes to the step's log a line at a time, as it comes."""
    ctx.log.info(f"{ctx.name}: {shlex.join(command)}")
    result = process.run(
        command,
        ctx.root,
        env=env,
        said=lambda line: ctx.log.info(f"{ctx.name}: {line}"),
    )
    if result.returncode != 0:
        raise process.failure(f"step `{ctx.name}`'s {which} command", result)


def _env(ctx: Context[Command.Options]) -> dict[str, str]:
    own = {
        name: value.reveal() if isinstance(value, Secret) else str(value)
        for name, value in ctx.options.env.items()
    }
    return {**ctx.env, **own, "LELY_TARGET": ctx.target, "LELY_STEP": ctx.name}


def _says(written: str, planned: object) -> bool:
    """Whether `written` — text, as an apply command writes it — is the value
    `planned` that the plan command printed as JSON. A script writes `True`
    for `true` and `3.0` for `3` without meaning another value."""
    if isinstance(planned, str):
        return written == planned
    if isinstance(planned, bool):
        return written.lower() == ("true" if planned else "false")
    if planned is None:
        return written in ("", "null")
    try:
        parsed = json.loads(written)
    except ValueError:
        return False
    if isinstance(planned, int | float):
        return (
            isinstance(parsed, int | float)
            and not isinstance(parsed, bool)
            and parsed == planned
        )
    return bool(parsed == planned)


def _only_listed(outputs: Outputs, options: Command.Options, where: str) -> None:
    extra = [name for name in outputs if name not in options.outputs]
    if extra:
        listed = ", ".join(options.outputs) or "none"
        raise LelyError(
            f"{where} gives {', '.join(f'`{e}`' for e in extra)}, which the step "
            f"doesn't list under `outputs` (listed: {listed})"
        )


def _read_outputs(text: str, step: str) -> dict[str, Json]:
    """The file `LELY_OUTPUTS` names: one `name=value` to a line."""
    outputs: dict[str, Json] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        name, equals, value = line.partition("=")
        if not equals or not _NAME.match(name.strip()):
            raise LelyError(
                f"step `{step}`'s apply command wrote line {number} to the file "
                f"`LELY_OUTPUTS` names, which isn't `name=value`: {line!r}"
            )
        # the spaces round a value are how it was written, not part of it
        outputs[name.strip()] = value.strip()
    return outputs

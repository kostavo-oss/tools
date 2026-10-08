"""The plugin contract: what a plugin is, and what a step of it is given.

A plugin is a class with an `Options` dataclass, the outputs it gives, and two
methods — and up to three more:

    class WarmCache:
        @dataclass(frozen=True, slots=True)
        class Options:
            table: str

        outputs = (Output("rows"),)

        def plan(self, ctx: Context[WarmCache.Options]) -> StepPlan: ...
        def apply(self, ctx: Context[WarmCache.Options], plan: StepPlan) -> Outputs: ...

        # optional: a plugin without one says so by not having it
        def overview(self, ctx) -> Overview | Skip: ...
        def plan_destroy(self, ctx) -> StepPlan | Skip: ...
        def destroy(self, ctx, plan: StepPlan) -> None: ...

A plugin with nothing to list may say why, for `lely status`, in
`nothing_to_list`; one that can plan and can't apply yet sets `plan_only`; one
that runs programs names them for `lely doctor` in `programs(written)`.

The rules a plugin follows, which `lely.testing` checks:

- **No state.** `plan` and `apply` may run on different machines, days apart;
  only the `StepPlan` passes between them, through the plan file.
- **`plan` changes nothing**, and neither does `overview`.
- **`apply` does what the plan says and no more.** Planning again right after
  it gives no changes, unless they are `run`s.
- **Only what the options name.** Anything else is not its own, never changed.
- **It destroys only what it can show is its own.**
- **Destructive is declared** on the change.
- **Outputs are as declared**: nothing undeclared, nothing *at plan* missing.
- **No secrets in plans**: a secret output is a `Secret`, a payload holds none.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, Literal, Protocol, TextIO, TypeVar

from lely.errors import LelyError
from lely.model import Change, Json, Output, Outputs, Secret, StepPlan

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient

OptionsT = TypeVar("OptionsT")
OptionsT_contra = TypeVar("OptionsT_contra", contravariant=True)


class Log(Protocol):
    def info(self, message: str) -> None: ...


class NullLog:
    def info(self, message: str) -> None:
        pass


class Cli(Protocol):
    """The Databricks CLI, with this run's credentials."""

    def run(self, args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        """Run `databricks <args>` in `cwd`. A failing run doesn't raise."""
        ...


#: What a step is being planned for.
Purpose = Literal["apply", "destroy", "status"]


@dataclass(frozen=True, slots=True)
class Context(Generic[OptionsT]):
    """Everything a step is given, and nothing else.

    Not the other steps' outputs, and not the bundle: what a step depends on is
    in its options, as `${steps.<name>.<output>}` or as a `Linked` step.

    `target` is `-t` as it was typed; each plugin reads it its own way. `root`
    is the project's directory, where the config file is. `host` is the
    workspace this run talks to. `env` is the environment for a program the step
    runs: lely's own, plus `DATABRICKS_CONFIG_PROFILE` when a profile was chosen.
    `databricks` runs the Databricks CLI with the same credentials.

    `purpose` is what the step is planned for. For a destroy and a status,
    `plan` is asked only for what the step gives the ones below it — and there
    what exists now is what counts, not what a deploy would make of it: the id
    of a pipeline the next deploy would replace is the id to give.
    """

    target: str
    name: str
    options: OptionsT
    root: Path
    host: str
    env: Mapping[str, str]
    databricks: Cli
    log: Log
    connect: Callable[[], WorkspaceClient]
    purpose: Purpose = "apply"

    @property
    def workspace(self) -> WorkspaceClient:
        """The workspace, through the SDK. Connects on first use."""
        return self.connect()


class Plugin(Protocol[OptionsT_contra]):
    """What `uses:` names. See the module docstring for the rules."""

    Options: type[Any]

    def plan(self, ctx: Context[OptionsT_contra]) -> StepPlan: ...

    def apply(self, ctx: Context[OptionsT_contra], plan: StepPlan) -> Outputs: ...


@contextlib.contextmanager
def quietly(whose: str = "its plugin") -> Iterator[None]:
    """Run a plugin's own code — its module, its options, its methods — with
    what it prints sent to stderr. `whose` names the plugin in an error.

    stdout is lely's: a plan or a result as JSON, a schema. A `print` left in a
    plugin would otherwise land in the middle of it. So would what goes round
    `sys.stdout` — a program the plugin starts without taking its output,
    `os.write(1, …)` — so the stream under it is pointed at stderr as well.

    What the plugin prints to is a stream of its own, not `sys.stderr` itself:
    a plugin that wraps or detaches "its" stdout to set an encoding would
    otherwise take lely's stderr with it when it is done.

    And a plugin doesn't end the program: `sys.exit` in one is an error like
    any other, not lely ending with whatever the plugin said.
    """
    with contextlib.ExitStack() as stack:
        stack.enter_context(_under_stdout())
        stream = _for_prints()
        stack.enter_context(contextlib.redirect_stdout(stream))
        try:
            yield
        except SystemExit as error:
            raise LelyError(
                f"{whose} ended the program (`sys.exit({error.code!r})`). A plugin "
                "returns, or raises an error."
            ) from None
        finally:
            # closed or detached by the plugin: it was the plugin's to break
            with contextlib.suppress(OSError, ValueError):
                stream.flush()


def _for_prints() -> TextIO:
    """A stream to stderr that isn't `sys.stderr`: closing it closes nothing."""
    try:
        sys.stderr.flush()
        return open(  # noqa: SIM115 — the plugin may keep it: a logging handler
            sys.stderr.fileno(),
            "w",
            buffering=1,
            encoding=getattr(sys.stderr, "encoding", None) or "utf-8",
            errors="backslashreplace",
            closefd=False,
        )
    except (AttributeError, OSError, ValueError):
        return sys.stderr  # not a file — a test's capture: nothing to protect


@contextlib.contextmanager
def _under_stdout() -> Iterator[None]:
    """Point file descriptor 1 at stderr, and back."""
    try:
        if sys.__stdout__ is not None:
            sys.__stdout__.flush()  # lely's own, written before: it goes first
        saved = os.dup(1)
    except (OSError, ValueError):
        yield  # no stdout at all
        return
    try:
        os.dup2(2, 1)
        yield
    finally:
        with contextlib.suppress(OSError, ValueError):
            if sys.__stdout__ is not None:
                sys.__stdout__.flush()  # the plugin's, written round `sys.stdout`
        os.dup2(saved, 1)
        os.close(saved)


class Step:
    """A base for a step that runs on its own as well as under lely.

    Inheriting it changes nothing about the contract: a step is still its
    `Options`, its `outputs`, `plan` and `apply`. What it adds is a command
    line, from one line at the bottom of the file (`spec/011`):

        if __name__ == "__main__":
            SecretScope.main()

    `uv run ops/scope.py plan -t dev --name x` then plans the step and shows
    the plan; `apply`, `destroy`, `status` and `check` go with it. The flags
    are the fields of `Options`. Under lely the same file is
    `uses: ./ops/scope.py:SecretScope`, unchanged.
    """

    @dataclass(frozen=True, slots=True)
    class Options:
        pass

    outputs: tuple[Output, ...] = ()

    @classmethod
    def main(cls, argv: Sequence[str] | None = None) -> None:
        """The step's own command line: `plan`, `apply`, `destroy`, `status`, `check`."""
        from lely.solo import main

        main(cls, argv)


class Program(Step):
    """A program as a step: one `run`, every apply.

        class Notify(Program):
            \"\"\"Tells the channel the deploy is done.\"\"\"

            command = ["./ops/notify.sh", "deployed"]
            destructive = False
            outputs = (Output("sent", known="run"),)

    Its plan is one `run` change, destructive if it says so; `apply` runs the
    program in the project's directory, with the environment lely was given
    and `LELY_TARGET` and `LELY_STEP`, and fails the step when the program
    fails. Outputs, when it declares any, are what the program prints as JSON
    on the last line of its output. A run has nothing to take down, so a
    `Program` has no destroy and `lely destroy` skips it visibly.

    A program may not be given a secret in its arguments: every process on the
    machine can see them. An option of type `Secret` goes in `env`.
    """

    #: The program and its arguments, never passed through a shell.
    command: Sequence[str] = ()
    #: Whether the run loses something: shown so in a plan.
    destructive: bool = False
    #: Extra environment for the program; may hold a secret.
    env: Mapping[str, str] = {}

    def plan(self, ctx: Context[Any]) -> StepPlan:
        command = self._command(ctx)
        return StepPlan(
            changes=(
                Change(
                    key=ctx.name,
                    action="run",
                    summary=f"runs {shlex.join(command)}",
                    destructive=self.destructive,
                ),
            ),
        )

    def apply(self, ctx: Context[Any], plan: StepPlan) -> Outputs:
        from lely import process

        command = self._command(ctx)
        env = {
            **ctx.env,
            **{k: _plain_env(v) for k, v in self.env.items()},
            "LELY_TARGET": ctx.target,
            "LELY_STEP": ctx.name,
        }
        result = process.run(command, ctx.root, env=env, said=ctx.log.info)
        if result.returncode != 0:
            raise process.failure(f"`{shlex.join(command)}`", result)
        return self._outputs(result.stdout)

    def programs(self, written: Mapping[str, Json]) -> tuple[str, ...]:
        """For `lely doctor`: the program this step runs."""
        return (self.command[0],) if self.command else ()

    def _command(self, ctx: Context[Any]) -> list[str]:
        command = [str(part) for part in self.command]
        if not command:
            raise LelyError(f"{type(self).__qualname__}: `command` is empty.")
        return command

    def _outputs(self, stdout: str) -> Outputs:
        declared_names = [output.name for output in declared(type(self), {})]
        if not declared_names:
            return {}
        lines = [line for line in stdout.splitlines() if line.strip()]
        try:
            document = json.loads(lines[-1]) if lines else None
        except json.JSONDecodeError:
            document = None
        if not isinstance(document, dict):
            raise LelyError(
                f"{type(self).__qualname__} declares outputs "
                f"({', '.join(declared_names)}), and the program's last line isn't "
                "a JSON object holding them."
            )
        missing = [name for name in declared_names if name not in document]
        if missing:
            raise LelyError(
                f"{type(self).__qualname__}: the program gave no `{missing[0]}`."
            )
        return {name: document[name] for name in declared_names}


def _plain_env(value: Any) -> str:
    return value.reveal() if isinstance(value, Secret) else str(value)


def declared(cls: type, written: Mapping[str, Json]) -> tuple[Output, ...]:
    """The outputs a step of plugin `cls` gives.

    A plugin lists them as `outputs`, or — when they depend on how the step is
    configured — as a function of its options *as written*, references still
    unresolved. A plugin that says nothing gives nothing.
    """
    listed: Any = getattr(cls, "outputs", ())
    if callable(listed):
        with quietly():
            listed = listed(written)
    try:
        outputs = tuple(listed)
    except TypeError:
        raise LelyError(
            f"{cls.__qualname__}: `outputs` must be a tuple of `Output`s, "
            f"not {type(listed).__name__}"
        ) from None
    for output in outputs:
        if not isinstance(output, Output):
            raise LelyError(
                f"{cls.__qualname__}: `outputs` must hold `Output`s, "
                f"not {type(output).__name__}"
            )
    return outputs


def lists(cls: type) -> bool:
    """Whether the plugin can say what exists because of a step."""
    return callable(getattr(cls, "overview", None))


def destroys(cls: type) -> bool:
    """Whether the plugin can take down what a step made."""
    return callable(getattr(cls, "plan_destroy", None)) and callable(
        getattr(cls, "destroy", None)
    )


def applies(cls: type) -> bool:
    """False for a plugin that can plan but not apply yet (`plan_only = True`)."""
    return not getattr(cls, "plan_only", False)

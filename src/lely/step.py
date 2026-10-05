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
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

from lely.errors import LelyError
from lely.model import Json, Output, Outputs, StepPlan

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient

OptionsT = TypeVar("OptionsT")
OptionsT_contra = TypeVar("OptionsT_contra", contravariant=True)


class Log(Protocol):
    def info(self, message: str) -> None: ...


class NullLog:
    def info(self, message: str) -> None:
        pass


class StderrLog:
    def info(self, message: str) -> None:
        print(message, file=sys.stderr)


class Cli(Protocol):
    """The Databricks CLI, with this run's credentials."""

    def run(self, args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        """Run `databricks <args>` in `cwd`. A failing run doesn't raise."""
        ...


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
def quietly() -> Iterator[None]:
    """Run a plugin's own code with what it prints sent to stderr.

    stdout is lely's: a plan or a result as JSON, a schema. A `print` left in a
    plugin — on import, in `plan` — would otherwise land in the middle of it.
    """
    with contextlib.redirect_stdout(sys.stderr):
        yield


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

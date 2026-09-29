"""The step interface: what a step is, and what it is given.

A step is a class with an `Options` dataclass and two methods:

    class WarmCache:
        @dataclass(frozen=True, slots=True)
        class Options:
            table: str

        def plan(self, ctx: Context[WarmCache.Options]) -> StepPlan: ...
        def apply(self, ctx: Context[WarmCache.Options], plan: StepPlan) -> Outputs: ...

The rules a step follows, which `sluis.testing` checks:

- **Stateless.** `plan` and `apply` may run on different machines, days apart;
  only the `StepPlan` passes between them, through the plan file.
- **`plan` changes nothing.** It runs on every pull request.
- **`apply` does what the plan says and no more.** Planning again right after
  it gives an empty plan, unless the step's changes are `run`s.
- **Only what the options name.** Anything else is unmanaged, never removed.
- **Destructive is declared** on the change, and never applied without
  `--allow-destructive`.
- **No secrets in plans**: a secret output is a `Secret`, and a payload holds
  none.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

from sluis.model import Json, Outputs, Phase, StepPlan

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient

    from sluis.databricks import Databricks

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


@dataclass(frozen=True, slots=True)
class Context(Generic[OptionsT]):
    """Everything a step gets.

    `bundle` is the bundle's resolved config (`bundle validate -o json`) and
    `deployed` its deployment summary (`bundle summary -o json`), when anything
    asked for one. `outputs` are the earlier steps', by name. `root` is where
    `sluis.yml` is. `env` is the environment for a program the step runs: sluis's
    own, plus `DATABRICKS_CONFIG_PROFILE` when a profile was chosen. `databricks`
    runs the Databricks CLI in the bundle's directory.
    """

    target: str
    phase: Phase
    name: str
    options: OptionsT
    bundle: Mapping[str, Json]
    deployed: Mapping[str, Json] | None
    outputs: Mapping[str, Outputs]
    root: Path
    bundle_root: Path
    env: Mapping[str, str]
    databricks: Databricks
    log: Log
    connect: Callable[[], WorkspaceClient]

    @property
    def workspace(self) -> WorkspaceClient:
        """The target's workspace, with the CLI's auth. Connects on first use."""
        return self.connect()


class Step(Protocol[OptionsT_contra]):
    """What `uses:` names. See the module docstring for the rules."""

    Options: type[Any]

    def plan(self, ctx: Context[OptionsT_contra]) -> StepPlan: ...

    def apply(self, ctx: Context[OptionsT_contra], plan: StepPlan) -> Outputs: ...

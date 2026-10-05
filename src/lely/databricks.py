"""The Databricks CLI, run with this run's credentials.

`DatabricksCli` is the edge: a subprocess. What a plugin asks it for is the
plugin's business — the bundle plugin asks for `bundle validate`, `plan` and
the rest — so nothing here knows a verb. Tests put a fake in its place.

The workspace comes from `--profile` or from the variables the CLI and the SDK
already read; one run talks to one workspace.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from lely.errors import LelyError
from lely.model import Json
from lely.process import failure, run
from lely.step import Cli

INSTALL = (
    "Install the Databricks CLI: https://docs.databricks.com/aws/en/dev-tools/cli/install"
)


class CliError(LelyError):
    """The Databricks CLI failed, or isn't there; its own words are in the message."""


@dataclass(frozen=True, slots=True)
class DatabricksCli:
    executable: tuple[str, ...] = ("databricks",)
    profile: str | None = None
    env: Mapping[str, str] | None = None

    def run(self, args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        command = [*self.executable, *args]
        if self.profile is not None:
            # before a `--`: what follows one is the job's, not the CLI's
            at = command.index("--") if "--" in command else len(command)
            command[at:at] = ["--profile", self.profile]
        return run(command, cwd, env=self.env, hint=INSTALL)


def answer(cli: Cli, args: Sequence[str], cwd: Path) -> dict[str, Json]:
    """What `databricks <args> --output json` prints, as a JSON object.

    The exit code decides success, not the output: a failed `bundle validate`
    still prints JSON.
    """
    what = f"`databricks {' '.join(args[:2])}`"
    result = cli.run([*args, "--output", "json"], cwd)
    if result.returncode != 0:
        raise CliError(str(failure(what, result)))
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise CliError(f"{what} with `-o json` didn't print JSON: {error}") from None
    if not isinstance(document, dict):
        raise CliError(f"{what} with `-o json` printed no JSON object")
    return document

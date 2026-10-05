"""The Databricks CLI: the only way lely learns what the bundle is.

lely never reads `databricks.yml` itself. The CLI resolves variables, runs
lookups, applies presets and target overrides, and names everything as a
deploy would; lely asks it, with `-o json`, and reimplements none of it.

`Databricks` is the edge the rest of lely talks to, so tests can answer it
from recordings; `DatabricksCli` is the real one, a subprocess in the bundle's
directory.

- `bundle validate -o json`: the resolved config. A failed validate still
  prints JSON, so the exit code, not the output, decides success.
- `bundle plan -o json`: the direct engine's plan. `--var` is a persistent flag
  of `bundle`, so plan takes it like deploy does.
- `bundle summary -o json`: the resolved config plus each deployed resource's
  `id` and `url`; before a first deploy, `modified_status: created` instead.

Source for all three: the CLI's acceptance tests and `cmd/bundle/` at
https://github.com/databricks/cli/tree/e41a5c87436a5b8fa81ce192e2aac77675d4b4c2
(see `tests/fixtures/cli/README.md`).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from lely.errors import LelyError
from lely.model import Json
from lely.process import failure, run

INSTALL = (
    "Install the Databricks CLI: https://docs.databricks.com/aws/en/dev-tools/cli/install"
)


class CliError(LelyError):
    """The Databricks CLI failed, or isn't there; its own words are in the message."""


class Databricks(Protocol):
    def validate(
        self, target: str | None, variables: Mapping[str, str]
    ) -> dict[str, Json]:
        """The bundle's resolved config for `target` (its default when `None`)."""
        ...

    def plan(self, target: str, variables: Mapping[str, str]) -> dict[str, Json]:
        """What `bundle deploy` would do, as the CLI's plan document."""
        ...

    def summary(self, target: str) -> dict[str, Json]:
        """The resolved config with what is deployed: ids and urls."""
        ...


@dataclass(frozen=True, slots=True)
class DatabricksCli:
    root: Path
    executable: tuple[str, ...] = ("databricks",)
    profile: str | None = None

    def validate(
        self, target: str | None, variables: Mapping[str, str]
    ) -> dict[str, Json]:
        return self._json("validate", target, variables)

    def plan(self, target: str, variables: Mapping[str, str]) -> dict[str, Json]:
        return self._json("plan", target, variables)

    def summary(self, target: str) -> dict[str, Json]:
        return self._json("summary", target, {})

    def command(
        self, verb: str, target: str | None, variables: Mapping[str, str], *extra: str
    ) -> list[str]:
        args = [*self.executable, "bundle", verb, *extra]
        if target is not None:
            args += ["--target", target]
        args += [f"--var={name}={value}" for name, value in variables.items()]
        if self.profile is not None:
            args += ["--profile", self.profile]
        return args

    def _json(
        self, verb: str, target: str | None, variables: Mapping[str, str]
    ) -> dict[str, Json]:
        args = self.command(verb, target, variables, "--output", "json")
        result = run(args, self.root, hint=INSTALL)
        if result.returncode != 0:
            raise CliError(str(failure(f"`databricks bundle {verb}`", result)))
        try:
            document = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise CliError(
                f"`databricks bundle {verb} -o json` didn't print JSON: {error}"
            ) from None
        if not isinstance(document, dict):
            raise CliError(f"`databricks bundle {verb} -o json` printed no JSON object")
        return document

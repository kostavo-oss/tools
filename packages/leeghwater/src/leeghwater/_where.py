"""Where the process runs: on a laptop or on Databricks. `spec/002`, R1."""

import os
from collections.abc import Mapping
from dataclasses import dataclass

# The Databricks SDK decides the same way: `databricks/sdk/credentials_provider.py`
# looks for this variable to tell that it runs on Databricks.
RUNTIME_VARIABLE = "DATABRICKS_RUNTIME_VERSION"


@dataclass(frozen=True)
class Where:
    """Where the process runs."""

    on_databricks: bool
    runtime: str | None
    """What `DATABRICKS_RUNTIME_VERSION` holds, e.g. `16.4` or `client.2.5`."""

    @property
    def serverless(self) -> bool:
        # In a serverless wheel task the variable held `client.2.5` (run on 2026-10-07).
        # TODO(verify): a classic cluster, where it should be a version such as `16.4`.
        return self.runtime is not None and self.runtime.startswith("client.")

    def describe(self) -> str:
        if not self.on_databricks:
            return "a laptop (not on Databricks)"
        kind = "serverless" if self.serverless else "a cluster"
        return f"Databricks, {kind}, runtime {self.runtime}"


def where(environ: Mapping[str, str] | None = None) -> Where:
    """Say where the process runs. Reads one environment variable and nothing else."""
    runtime = (os.environ if environ is None else environ).get(RUNTIME_VARIABLE)
    return Where(on_databricks=bool(runtime), runtime=runtime or None)

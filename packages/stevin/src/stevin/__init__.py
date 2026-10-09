"""stevin: safe plan/apply migrations for Unity Catalog tables and schemas.

Two ways in, the same code underneath. The command line is the one most people
meet:

```sh
stevin plan
stevin apply
```

And this package is the other, for a program that runs stevin as part of
something larger — a deployment task that plans, shows the plan its own way,
and applies it:

```python
import stevin

project = stevin.Project.find()
target = project.resolve(project.target("prod"))
```

Everything a host needs is exported here, and only what is exported here is
meant to be relied on. Names from `stevin.<module>` that this list doesn't
mention are the implementation, and move without notice.

Errors all descend from `StevinError`, so one `except` reports any failure
and a subclass reacts to a particular one. Rendering a plan is separate from
making one: `render_plan` for a terminal, `render_markdown` for a pull request,
`plan_to_json` for a file or a queue.
"""

from __future__ import annotations

from stevin.adopt import Adoption, CannotAdopt
from stevin.api import (
    ImportedSchema,
    ImportedSpec,
    adopt,
    apply,
    drift,
    history_for,
    import_schema,
    is_stale,
    plan,
    validate,
    verify,
)
from stevin.bundle import Bundle, BundleError, BundleTarget, find_cli
from stevin.connect import Connection, NotConnected
from stevin.errors import StevinError
from stevin.executor import (
    DestructiveRefused,
    ExecutionError,
    ExecutionResult,
    Executor,
    StalePlan,
)
from stevin.history import DeltaHistory, HistoryStore, MemoryHistory, NoHistory
from stevin.introspect import IntrospectionError, Introspector, WarehouseRunner
from stevin.loader import (
    Diagnostic,
    LoadedSpec,
    Project,
    SpecError,
    SpecErrors,
    Specs,
    Target,
    dump_spec,
    load_project,
    load_spec,
    load_specs,
    spec_files,
    validate_spec,
)
from stevin.manage import MANAGEABLE, Manage
from stevin.model.function import Function
from stevin.model.plan import Plan, Risk, Step, Summary, TableDiff, TableFacts
from stevin.model.schema import Schema
from stevin.model.table import (
    Check,
    ForeignKey,
    Grant,
    PrimaryKey,
    RowFilter,
    Table,
)
from stevin.model.types import Column, Field, Mask
from stevin.model.view import Relation, View
from stevin.model.volume import Volume
from stevin.planning import PlanningError, plan_tables
from stevin.probes import PROBES, Bench, Disagrees, Probe, Result
from stevin.render.html import render_html
from stevin.render.json import PlanFileError
from stevin.render.json import dumps as plan_to_json
from stevin.render.json import loads as plan_from_json
from stevin.render.markdown import render_markdown
from stevin.render.rich import plan_text, render_plan

__all__ = [
    "__version__",
    "adopt",
    "Adoption",
    "apply",
    "Bench",
    "Bundle",
    "BundleError",
    "BundleTarget",
    "CannotAdopt",
    "Check",
    "Column",
    "Connection",
    "DeltaHistory",
    "DestructiveRefused",
    "Diagnostic",
    "Disagrees",
    "drift",
    "dump_spec",
    "ExecutionError",
    "ExecutionResult",
    "Executor",
    "Field",
    "find_cli",
    "ForeignKey",
    "Function",
    "Grant",
    "history_for",
    "HistoryStore",
    "import_schema",
    "ImportedSchema",
    "ImportedSpec",
    "IntrospectionError",
    "Introspector",
    "is_stale",
    "load_project",
    "load_spec",
    "load_specs",
    "LoadedSpec",
    "Manage",
    "MANAGEABLE",
    "Mask",
    "MemoryHistory",
    "NoHistory",
    "NotConnected",
    "Plan",
    "plan",
    "plan_from_json",
    "plan_tables",
    "plan_text",
    "plan_to_json",
    "PlanFileError",
    "PlanningError",
    "PrimaryKey",
    "Probe",
    "PROBES",
    "Project",
    "Relation",
    "render_html",
    "render_markdown",
    "render_plan",
    "Result",
    "Risk",
    "RowFilter",
    "Schema",
    "spec_files",
    "SpecError",
    "SpecErrors",
    "Specs",
    "StalePlan",
    "Step",
    "StevinError",
    "Summary",
    "Table",
    "TableDiff",
    "TableFacts",
    "Target",
    "validate",
    "validate_spec",
    "verify",
    "View",
    "Volume",
    "WarehouseRunner",
]


def __getattr__(name: str) -> str:
    """`stevin.__version__`, read from the installed distribution."""
    if name == "__version__":
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("stevin")
        except PackageNotFoundError:  # pragma: no cover - running from a checkout
            return "0.0.0"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

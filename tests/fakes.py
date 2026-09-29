"""Fakes for the edges: the Databricks CLI, in process.

`FakeDatabricks` answers `validate`, `plan` and `summary` from JSON documents,
the way the CLI would: a `--var` overrides the variable's `value` in what
validate returns. It keeps every call, so a test can assert what sluis asked.
Anything it has no answer for fails loudly.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def bundle_config(
    *,
    name: str = "shop",
    target: str = "dev",
    variables: Mapping[str, Any] | None = None,
    resources: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """A resolved config shaped like `bundle validate -o json` prints one."""
    return {
        "bundle": {"name": name, "target": target, "environment": target},
        "variables": {
            key: {"default": value, "value": value}
            for key, value in (variables or {}).items()
        },
        "resources": dict(resources or {}),
        "workspace": {
            "host": "https://dbc-example.cloud.databricks.com",
            "current_user": {"userName": "jane@example.com", "short_name": "jane"},
        },
    }


@dataclass
class FakeDatabricks:
    config: dict[str, Any]
    plan_document: dict[str, Any] | None = None
    summary_document: dict[str, Any] | None = None
    calls: list[tuple[str, str | None, dict[str, str]]] = field(default_factory=list)

    def validate(
        self, target: str | None, variables: Mapping[str, str]
    ) -> dict[str, Any]:
        self.calls.append(("validate", target, dict(variables)))
        return self._with(variables)

    def plan(self, target: str, variables: Mapping[str, str]) -> dict[str, Any]:
        self.calls.append(("plan", target, dict(variables)))
        if self.plan_document is None:
            raise AssertionError("the fake has no plan document")
        return copy.deepcopy(self.plan_document)

    def summary(self, target: str) -> dict[str, Any]:
        self.calls.append(("summary", target, {}))
        if self.summary_document is None:
            raise AssertionError("the fake has no summary document")
        return copy.deepcopy(self.summary_document)

    def _with(self, variables: Mapping[str, str]) -> dict[str, Any]:
        document = copy.deepcopy(self.config)
        declared = document.setdefault("variables", {})
        for key, value in variables.items():
            if key not in declared:
                raise AssertionError(f"--var {key}: the bundle declares no such variable")
            declared[key]["value"] = value
        return document

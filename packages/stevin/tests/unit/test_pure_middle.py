"""The middle of the pipeline reaches nothing outside itself.

The differ and the planner are pure, the model is values, and a plan is made from
specs and live objects alone. These read the source and hold it to that: what a
module imports, and how the model's classes are declared.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import stevin

SRC = Path(stevin.__file__).parent

#: What a pure module may import: the standard library's own pure parts, the model,
#: the quoting helpers and the names written onto tables.
PURE_STDLIB = {"__future__", "collections.abc", "dataclasses", "typing"}
PURE_STEVIN = {"stevin.differ", "stevin.formerly", "stevin.sql"}
#: A field that could be changed in place: the model holds tuples.
MUTABLE = re.compile(r"\b(list|dict|set)\[")


def imported(path: Path) -> set[str]:
    """Every module a file imports, wherever in the file it does so."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
    return found


def test_the_differ_and_the_planner_import_nothing_that_reaches_outside() -> None:
    # RULES.md: PLAN-1.
    for name in ("differ.py", "planner.py"):
        reaching = sorted(
            module
            for module in imported(SRC / name)
            if module not in PURE_STDLIB | PURE_STEVIN
            and not module.startswith("stevin.model.")
        )
        assert reaching == [], f"{name} imports {reaching}"
        calls = {
            node.func.id
            for node in ast.walk(ast.parse((SRC / name).read_text(encoding="utf-8")))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not calls & {"open", "print", "input"}, name


def test_the_model_is_frozen_slotted_and_holds_tuples() -> None:
    # RULES.md: PLAN-1.
    classes = 0
    for path in sorted((SRC / "model").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ClassDef):
                continue
            marks = [ast.unparse(mark) for mark in node.decorator_list]
            if not any(mark.startswith("dataclass") for mark in marks):
                continue
            classes += 1
            where = f"{path.name}::{node.name}"
            assert marks == ["dataclass(frozen=True, slots=True)"], where
            for field in node.body:
                if isinstance(field, ast.AnnAssign):
                    held = ast.unparse(field.annotation)
                    assert not MUTABLE.search(held), f"{where} holds {held}"
    assert classes > 20, "the model's classes were not found"
    for path in sorted(SRC.rglob("*.py")):
        validators = {m.split(".")[0] for m in imported(path)} & {"pydantic", "msgspec"}
        assert not validators, f"{path.name} imports {validators}"


def test_planning_reads_nothing_of_what_a_workspace_accepts() -> None:
    # RULES.md: PLAN-2.
    for name in ("planning.py", "differ.py", "planner.py"):
        asking = imported(SRC / name) & {"stevin.probes", "stevin.doctor", "stevin.api"}
        assert not asking, f"{name} imports {sorted(asking)}"

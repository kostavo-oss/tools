"""How caland is layered, read from its own source.

The Databricks SDK is behind one door, a workspace is asked only what the SDK's secrets
API answers, and the layers point inward. Each is a rule of `RULES.md`; none had a test
until the rules were written down.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "caland"
LAYERS = ("domain", "application", "infrastructure", "interface")

#: The layers of caland a layer may import from.
MAY_IMPORT = {
    "domain": {"domain"},
    "application": {"domain", "application"},
    "infrastructure": {"domain", "infrastructure"},
    "interface": {"domain", "application", "interface"},
}

#: The libraries caland depends on, and the one layer that may import each.
LIBRARIES = {"databricks": "infrastructure", "yaml": "infrastructure"}


def imported(file: Path) -> tuple[set[str], set[str]]:
    """What a file imports: the layers of caland, and the libraries by their first
    name. An import inside a function counts like one at the top."""
    here = file.relative_to(SRC).parts[:-1]
    layers, libraries = set(), set()
    for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            libraries |= {name.name.split(".")[0] for name in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            libraries.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            base = here[: len(here) - (node.level - 1)]
            target = (*base, *(node.module or "").split("."))
            names = [target[0]] if target[0] else [name.name for name in node.names]
            layers |= {name for name in names if name in LAYERS}
    return layers, libraries


def files(layer: str) -> list[Path]:
    found = sorted((SRC / layer).rglob("*.py"))
    assert found, layer
    return found


def test_only_infrastructure_imports_the_databricks_sdk() -> None:
    """CODE-1.

    CODE-1. CODE-1. And only it reads YAML: the two libraries that reach outward.
    """
    for layer in LAYERS:
        for file in files(layer):
            _, libraries = imported(file)
            for library, home in LIBRARIES.items():
                if layer != home:
                    assert library not in libraries, f"{file.name} imports {library}"
    assert "databricks" not in imported(SRC / "app.py")[1]
    assert any("databricks" in imported(file)[1] for file in files("infrastructure"))


def test_a_workspace_is_asked_only_for_secrets_and_who_is_signed_in() -> None:
    """CODE-2.

    CODE-2. CODE-2. No query, no warehouse, no system table: of a workspace client only
    `secrets` and `current_user` are used."""
    source = "\n".join(f.read_text(encoding="utf-8") for f in files("infrastructure"))
    assert set(re.findall(r"\bclient\.(\w+)\.", source)) == {"secrets", "current_user"}
    everything = "\n".join(f.read_text(encoding="utf-8") for f in SRC.rglob("*.py"))
    for word in ("statement_execution", "warehouses", "system.access", "AccountClient("):
        assert word not in everything, word


def test_the_layers_point_inward() -> None:
    """CODE-3.

    CODE-3. CODE-3. The domain imports no other layer and no library; the application
    imports the domain, and one library in one file."""
    for layer in LAYERS:
        for file in files(layer):
            layers, _ = imported(file)
            assert layers <= MAY_IMPORT[layer], f"{file.name} imports {layers}"
    for file in files("domain") + files("application") + files("interface"):
        _, libraries = imported(file)
        reaching = libraries & {"cryptography", "databricks", "yaml"}
        allowed = {"cryptography"} if file.name == "files.py" else set()
        assert reaching <= allowed, f"{file.name} imports {reaching}"

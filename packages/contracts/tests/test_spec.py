"""The spec is all there is, so the spec is what is tested.

Not run by CI or by `mise run test` yet: this package joins both with its first
code. Run it from this folder with `uv run pytest`.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import contracts

HERE = Path(__file__).resolve().parent.parent
SPEC = HERE / "spec"
SPECS = sorted(p for p in SPEC.glob("[0-9][0-9][0-9]-*.md"))


def test_the_index_names_every_spec_and_nothing_that_is_not_there() -> None:
    index = (SPEC / "README.md").read_text(encoding="utf-8")
    linked = set(re.findall(r"\]\(((?:\d{3})-[a-z0-9-]+\.md)(?:#[^)]*)?\)", index))
    assert linked == {p.name for p in SPECS}
    assert len(SPECS) == 5


def test_every_spec_says_where_it_stands() -> None:
    for spec in SPECS:
        text = spec.read_text(encoding="utf-8")
        assert re.search(r"^\*\*Status:\*\* draft", text, flags=re.MULTILINE), spec.name
        assert "## Not in this spec" in text, spec.name
        assert "## Done when" in text, spec.name


def test_nothing_is_built_and_nothing_can_be_published() -> None:
    config = tomllib.loads((HERE / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    assert contracts.__version__ == project["version"] == "0.0.0"
    # the working name is taken on PyPI; this classifier makes PyPI refuse an upload
    assert "Private :: Do Not Upload" in project["classifiers"]
    assert project["dependencies"] == []
    assert "scripts" not in project

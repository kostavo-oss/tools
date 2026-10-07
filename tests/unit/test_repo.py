"""The repository's own text: what a reader sees is what is there."""

from __future__ import annotations

import ast
import re
import subprocess
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: What is no text: a picture is looked at, not read.
PICTURES = (".png",)

#: Folders a tool makes, for where git can't say what is the repository's.
MADE = ("site", "dist", "build", "__pycache__")


def files() -> list[Path]:
    """Every file of the repository that is text: all git tracks — the
    changelog, the workflows and the tests' snapshots as much as the code —
    or, where git can't say (an unpacked source package), every file that is
    in no folder a tool made and isn't hidden."""
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split("\0")
        paths = [ROOT / name for name in listed if name]
    except (OSError, subprocess.CalledProcessError):
        paths = [
            path
            for path in ROOT.rglob("*")
            if not any(
                part.startswith(".") or part in MADE or part.endswith(".egg-info")
                for part in path.relative_to(ROOT).parts
            )
        ]
    return [path for path in paths if path.is_file() and path.suffix not in PICTURES]


#: The characters `lely.render.words.clean` makes visible, by number — spelled
#: out here so that this file holds none of them either.
INVISIBLE = {0x061C, 0x200B, 0x200E, 0x200F, 0x2060, 0xFEFF, *range(0x202A, 0x202F)} | {
    *range(0x2066, 0x206A)
}


def test_no_file_holds_a_character_a_reader_cant_see() -> None:
    """A character that reorders or hides text belongs in source as its
    escape. Written raw, the line reads as something it isn't — and an editor,
    a diff and a reviewer all show the wrong thing. (Found on 2026-10-06: the
    very list of these characters had been written raw.)"""
    read = files()
    assert len(read) > 50
    names = {path.relative_to(ROOT).as_posix() for path in read}
    assert {"CHANGELOG.md", "pyproject.toml", "src/lely/cli.py"} <= names
    found = []
    for path in read:
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.split("\n"), start=1):
            odd = sorted(
                {
                    f"U+{ord(char):04X}"
                    for char in line
                    if ord(char) in INVISIBLE
                    or (unicodedata.category(char) == "Cc" and char != "\t")
                }
            )
            if odd:
                found.append(f"{path.relative_to(ROOT)}:{number}: {', '.join(odd)}")
    assert found == []


def test_every_text_file_is_read_with_git_or_without(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The check above skipped the changelog, the workflows and the tests'
    snapshots: it listed folders and suffixes of its own."""
    wanted = {
        "CHANGELOG.md",
        "pyproject.toml",
        "tests/unit/__snapshots__/test_render_html.ambr",
        "tests/fixtures/stevin-create.json",
    }
    tracked = {path.relative_to(ROOT).as_posix() for path in files()}
    if (ROOT / ".git").exists():
        # a checkout: what a source package leaves out is read too
        assert wanted | {"CONTRIBUTING.md", ".github/workflows/ci.yml"} <= tracked
        assert not any(name.endswith(PICTURES) for name in tracked)
    monkeypatch.setenv("PATH", "")  # no git: as in an unpacked source package
    walked = {path.relative_to(ROOT).as_posix() for path in files()}
    assert wanted <= walked
    assert not any(name.startswith((".venv/", "site/", ".git/")) for name in walked)


def imports_a_plugin(source: str) -> bool:
    """Whether a module's text imports `lely.steps`, or anything in it."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names = [node.module or ""]
            if node.module == "lely":
                names = [f"lely.{alias.name}" for alias in node.names]
        else:
            continue
        if any(name == "lely.steps" or name.startswith("lely.steps.") for name in names):
            return True
    return False


def test_no_module_outside_steps_imports_a_plugin() -> None:
    """CLAUDE.md: plugins are found through the registry, the bundle included.
    The plugins lely ships are in `src/lely/steps/`, and only they import one
    another."""
    assert imports_a_plugin("from lely.steps.bundle import Bundle")
    assert imports_a_plugin("def f():\n    from lely import steps")
    assert imports_a_plugin("import lely.steps.command as c")
    assert not imports_a_plugin("from lely import step as contract\nimport lely.step")
    package = ROOT / "src" / "lely"
    core = [path for path in package.rglob("*.py") if path.parent.name != "steps"]
    assert len(core) > 15
    found = [
        path.relative_to(package).as_posix()
        for path in core
        if imports_a_plugin(path.read_text(encoding="utf-8"))
    ]
    assert found == []


# -- what a document shows can be followed ---------------------------------------------

#: The documents a reader follows, and the plugins each may name: the README
#: stands alone, so a class its config names is shown in it; a page of the
#: docs may name one that the README or another page shows.
README = ROOT / "README.md"
PAGES = (README, *sorted((ROOT / "docs").glob("*.md")))

_FENCED = re.compile(r"^```(\w+)\n(.*?)^```$", re.DOTALL | re.MULTILINE)
_IN_THE_REPO = re.compile(r"""uses\s*[:=]\s*["']?\./([\w./-]+\.py):(\w+)""")


def fenced(document: Path, language: str) -> list[str]:
    text = document.read_text(encoding="utf-8")
    return [body for said, body in _FENCED.findall(text) if said == language]


def configs() -> list[tuple[str, str, str]]:
    """Every whole config a document shows: where, the file it would be, its text."""
    found = []
    for document in PAGES:
        name = document.relative_to(ROOT).as_posix()
        whole = [
            ("lely.yml", b) for b in fenced(document, "yaml") if b.startswith("steps:")
        ]
        whole += [
            ("pyproject.toml", b)
            for b in fenced(document, "toml")
            if b.startswith("[[tool.lely.steps]]")
        ]
        found += [(f"{name} #{n}", file, body) for n, (file, body) in enumerate(whole, 1)]
    return found


@pytest.mark.parametrize(
    ("where", "file", "text"), configs(), ids=[where for where, _, _ in configs()]
)
def test_a_config_a_document_shows_is_one_lely_takes(
    where: str, file: str, text: str, tmp_path: Path
) -> None:
    """The README's quickstart named `./ops/steps.py:LatestModel` and never
    showed it: followed as written, `lely validate` failed on its first step.
    Every whole config in the README and the docs is checked offline here, as
    `lely validate` checks it, with the plugin files the documents show."""
    from lely import planning
    from lely.config import load

    shows = [README] if where.startswith("README.md") else list(PAGES)
    classes = [body for page in shows for body in fenced(page, "python")]
    for path, name in _IN_THE_REPO.findall(text):
        shown = [body for body in classes if re.search(rf"^class {name}\b", body, re.M)]
        assert shown, f"{where} names ./{path}:{name}, and no document shows that class"
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(shown[0], encoding="utf-8")
    (tmp_path / file).write_text(text, encoding="utf-8")
    wires = planning.check(load(tmp_path / file))
    assert len(wires) >= 1


def test_the_documents_show_whole_configs_to_check() -> None:
    expected = {"README.md"}
    if (ROOT / "docs").is_dir():  # a source package has the README only
        expected |= {
            "docs/config.md",
            "docs/getting-started.md",
            "docs/writing-a-plugin.md",
        }
    assert {where.split(" #")[0] for where, _, _ in configs()} >= expected

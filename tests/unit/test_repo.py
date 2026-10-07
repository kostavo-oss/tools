"""The repository's own text: what a reader sees is what is there."""

from __future__ import annotations

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
        "CONTRIBUTING.md",
        "pyproject.toml",
        "tests/unit/__snapshots__/test_render_html.ambr",
        "tests/fixtures/stevin-create.json",
    }
    tracked = {path.relative_to(ROOT).as_posix() for path in files()}
    if (ROOT / ".git").exists():
        assert wanted | {".github/workflows/ci.yml", ".gitignore"} <= tracked
        assert not any(name.endswith(PICTURES) for name in tracked)
    monkeypatch.setenv("PATH", "")  # no git: as in an unpacked source package
    walked = {path.relative_to(ROOT).as_posix() for path in files()}
    assert wanted <= walked
    assert not any(name.startswith((".venv/", "site/", ".git/")) for name in walked)

"""The repository's own text: what a reader sees is what is there."""

from __future__ import annotations

import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

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
    files = [ROOT / "README.md", ROOT / "CLAUDE.md"]
    for folder in ("src", "tests", "docs", "spec"):
        files += [
            path
            for path in (ROOT / folder).rglob("*")
            if path.suffix in (".py", ".md", ".yml", ".toml")
        ]
    assert len(files) > 50
    found = []
    for path in files:
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

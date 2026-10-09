"""Parse and format .env content for bulk secret import/export.

Pure text transforms — no I/O. Values with newlines or other awkward characters
are written JSON-quoted and read back the same way, so multiline secrets
(PEM keys etc.) round-trip.

A value may also be quoted over several lines, as people write a key into such a
file by hand. It is read whole — every line of it — or the file is refused: read
line by line, a key's own lines would be taken for secrets of their own.
"""

from __future__ import annotations

import json
import re

# values that can be written bare, without quoting
_BARE = re.compile(r"[A-Za-z0-9_@%+=:,./-]*")
# in a value that is not quoted, a # after a space starts a comment
_COMMENT = re.compile(r"\s+#.*$")


class DotenvError(ValueError):
    """The text cannot be read as a .env file without guessing."""


def parse_dotenv(text: str) -> dict[str, str]:
    """KEY=VALUE lines. Blank lines and #-comments are ignored, an `export `
    prefix is dropped, and single/double/JSON-style quotes are stripped. A quoted
    value may run over several lines. Raises `DotenvError` for a quote that is
    opened and never closed."""
    entries: dict[str, str] = {}
    lines = text.removeprefix("﻿").splitlines()
    at = 0
    while at < len(lines):
        number, line = at + 1, lines[at].strip()
        at += 1
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        value = value.strip()
        quote = value[:1]
        if quote in ('"', "'"):
            body = value[1:]
            end = _closing(body, quote)
            while end < 0:  # the value goes on: take the next line as it is
                if at >= len(lines):
                    raise DotenvError(
                        f"line {number}: the quote that opens the value of {key} "
                        "is never closed"
                    )
                body += "\n" + lines[at]
                at += 1
                end = _closing(body, quote)
            after = body[end + 1 :].strip()
            if after and not after.startswith("#"):
                if "\n" in body or not value.endswith(quote):
                    raise DotenvError(
                        f"line {number}: something follows the quote that closes "
                        f"the value of {key}"
                    )
                end = len(body) - 1  # a quote inside the quotes: the last one closes
            inner = body[:end]
            value = _unescaped(inner) if quote == '"' else inner
        else:
            value = _COMMENT.sub("", value).strip()
        if key:
            entries[key] = value
    return entries


def _closing(body: str, quote: str) -> int:
    """Where the quote that closes a value is, or -1. In double quotes a quote
    after a backslash is part of the value."""
    at = 0
    while True:
        at = body.find(quote, at)
        if at < 0:
            return -1
        if quote == "'":
            return at
        slashes = len(body[:at]) - len(body[:at].rstrip("\\"))
        if slashes % 2 == 0:
            return at
        at += 1


def _unescaped(inner: str) -> str:
    """What is between double quotes, with its \\n and the like made real —
    when it is written that way; taken as it is otherwise."""
    try:
        return json.loads(f'"{inner}"')
    except ValueError:
        return inner


def format_dotenv(pairs: list[tuple[str, str]]) -> str:
    """Render pairs as .env lines."""
    lines = []
    for key, value in pairs:
        if _BARE.fullmatch(value):  # the whole of it: `$` would let a last newline by
            lines.append(f"{key}={value}")
        else:
            lines.append(f"{key}={json.dumps(value)}")
    return "\n".join(lines) + "\n"

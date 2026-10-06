"""parse_dotenv / format_dotenv — the .env import/export text transforms."""

from __future__ import annotations

from caland.application import format_dotenv, parse_dotenv


def test_parse_ignores_noise_and_strips_quotes():
    text = """
# a comment
export API_KEY=abc123
DB_URL="postgres://u:p@h/db"
EMPTY=
QUOTED='single quoted'
not a kv line
=no key
"""
    assert parse_dotenv(text) == {
        "API_KEY": "abc123",
        "DB_URL": "postgres://u:p@h/db",
        "EMPTY": "",
        "QUOTED": "single quoted",
    }


def test_multiline_values_round_trip():
    pem = "-----BEGIN KEY-----\nline1\nline2\n-----END KEY-----\n"
    text = format_dotenv([("TLS_KEY", pem), ("PLAIN", "abc")])
    assert parse_dotenv(text) == {"TLS_KEY": pem, "PLAIN": "abc"}


def test_format_redacted_writes_keys_only():
    assert format_dotenv([("A", "x"), ("B", "y")], redact=True) == "A=\nB=\n"


# ── what a second pair of eyes found ─────────────────────────────────
PEM = (
    "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkq=\n"
    "c2VjcmV0IGtleSBtYXRlcmlhbCBQQ==\n-----END PRIVATE KEY-----"
)


def test_a_value_quoted_over_several_lines_is_one_value():
    """Read line by line, the key's own lines — some end in `=` — would be taken
    for secrets of their own, named after pieces of the key."""
    text = f'BEFORE=1\nTLS_KEY="{PEM}"\nAFTER=2\n'
    assert parse_dotenv(text) == {"BEFORE": "1", "TLS_KEY": PEM, "AFTER": "2"}
    assert parse_dotenv(f"TLS_KEY='{PEM}'\nAFTER=2\n") == {"TLS_KEY": PEM, "AFTER": "2"}


def test_a_quote_that_is_never_closed_is_refused_not_guessed_at():
    import pytest

    from caland.application.dotenv import DotenvError

    with pytest.raises(
        DotenvError, match="line 2: the quote that opens the value of TLS_KEY"
    ):
        parse_dotenv('A=1\nTLS_KEY="-----BEGIN\nMIIE=\n')
    with pytest.raises(DotenvError, match="something follows the quote"):
        parse_dotenv('A="one\ntwo" three\n')


def test_a_comment_after_a_value_is_no_part_of_it():
    assert parse_dotenv('A=v # c\nB="v" # c\nC=v#notacomment\nD="a # b"\n') == {
        "A": "v",
        "B": "v",
        "C": "v#notacomment",
        "D": "a # b",
    }


def test_a_mark_at_the_start_of_the_file_is_no_part_of_the_first_key():
    assert parse_dotenv("﻿KEY=value\n") == {"KEY": "value"}


def test_quotes_inside_quotes_on_one_line_are_as_they_were():
    assert parse_dotenv('A=\'it\'s\'\nB="say \\"hi\\""\n') == {
        "A": "it's",
        "B": 'say "hi"',
    }


def test_what_is_written_is_read_back_the_same():
    import random

    values = [
        "plain",
        "ends with a newline\n",
        "\n",
        " leading and trailing ",
        "",
        "a=b=c",
        "with # hash",
        "#starts with one",
        'double " quote',
        "single ' quote",
        "back\\slash",
        "tab\there",
        "two\nlines",
        "crlf\r\nlines",
        "unicode ünïcödé ✓",
        "x" * 5000,
        PEM,
        PEM + "\n",
        '"quoted"',
        "'quoted'",
        "ends with backslash\\",
        "export NOT=a key",
    ]
    letters = "ab \n\t\"'\\#=${}-_.é"
    rng = random.Random(7)
    values += [
        "".join(rng.choice(letters) for _ in range(rng.randint(0, 12)))
        for _ in range(3000)
    ]
    pairs = [(f"K{n}", value) for n, value in enumerate(values)]
    assert parse_dotenv(format_dotenv(pairs)) == dict(pairs)

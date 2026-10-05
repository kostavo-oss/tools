"""Running another program: a missing one says so, and so does a missing folder."""

import sys
from pathlib import Path

import pytest

from lely.process import ProcessError, failure, run


def test_a_missing_program_says_so_with_the_hint(tmp_path: Path) -> None:
    with pytest.raises(ProcessError, match="`no-such-tool` isn't installed.*Get it."):
        run(["no-such-tool"], tmp_path, hint="Get it.")


def test_a_missing_directory_isnt_taken_for_a_missing_program(tmp_path: Path) -> None:
    with pytest.raises(ProcessError) as caught:
        run([sys.executable, "-c", "pass"], tmp_path / "nope")
    assert "There is no directory" in str(caught.value)
    assert "isn't installed" not in str(caught.value)


def test_a_failing_program_is_quoted(tmp_path: Path) -> None:
    result = run([sys.executable, "-c", "import sys; sys.exit('boom')"], tmp_path)
    assert str(failure("the tool", result)) == "the tool failed (exit 1):\nboom"

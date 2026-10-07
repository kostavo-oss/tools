"""Running another program: a missing one says so, and so does a missing folder;
what one writes is quoted when it fails, and heard while it runs when asked."""

import sys
from pathlib import Path

import pytest

from lely.process import ProcessError, failure, run

PYTHON = sys.executable


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


def test_a_failing_program_is_quoted_on_both_streams(tmp_path: Path) -> None:
    """Its reason may be on either: a program that says why on stdout and adds
    a notice on stderr used to be quoted for the notice alone."""
    script = (
        "import sys\n"
        "print('ERROR: table `orders` does not exist')\n"
        "print('notice: a new version is out', file=sys.stderr)\n"
        "sys.exit(3)\n"
    )
    result = run([PYTHON, "-c", script], tmp_path)
    assert str(failure("the tool", result)) == (
        "the tool failed (exit 3):\n"
        "stdout:\nERROR: table `orders` does not exist\n"
        "stderr:\nnotice: a new version is out"
    )
    quiet = run([PYTHON, "-c", "import sys; sys.exit(4)"], tmp_path)
    assert str(failure("the tool", quiet)) == "the tool failed (exit 4):\n(no output)"


#: Writes a line, and goes on only once somebody has heard it: a program whose
#: lines are passed on when it is done would wait here until it gave up.
WAITS_TO_BE_HEARD = (
    "import pathlib, sys, time\n"
    "print('first', flush=True)\n"
    "for _ in range(400):\n"
    "    if pathlib.Path('heard').exists():\n"
    "        break\n"
    "    time.sleep(0.05)\n"
    "else:\n"
    "    sys.exit('nobody heard the first line while this ran')\n"
    "print('WARNING: 3 rows were rejected', file=sys.stderr, flush=True)\n"
    "print('last, with no line break', end='')\n"
)


def test_a_program_is_heard_while_it_runs_and_what_it_wrote_is_kept(
    tmp_path: Path,
) -> None:
    heard: list[str] = []

    def said(line: str) -> None:
        heard.append(line)
        (tmp_path / "heard").touch()

    result = run([PYTHON, "-c", WAITS_TO_BE_HEARD], tmp_path, said=said)
    assert result.returncode == 0, result.stderr
    assert heard[0] == "first"
    # both streams, a line each, without the line break
    assert sorted(heard[1:]) == [
        "WARNING: 3 rows were rejected",
        "last, with no line break",
    ]
    assert result.stdout == "first\nlast, with no line break"
    assert result.stderr == "WARNING: 3 rows were rejected\n"


def test_a_program_that_is_heard_fails_as_any_other(tmp_path: Path) -> None:
    heard: list[str] = []
    script = "import sys; print('half done'); sys.exit('boom')"
    result = run([PYTHON, "-c", script], tmp_path, said=heard.append)
    assert sorted(heard) == ["boom", "half done"]
    assert str(failure("the tool", result)) == (
        "the tool failed (exit 1):\nstdout:\nhalf done\nstderr:\nboom"
    )
    with pytest.raises(ProcessError, match="`no-such-tool` isn't installed"):
        run(["no-such-tool"], tmp_path, said=heard.append)


def test_a_listener_that_fails_doesnt_cut_the_program_short(tmp_path: Path) -> None:
    """A deploy is not ended halfway because a line of it couldn't be shown:
    the program runs to its end, and the error is raised then."""
    script = (
        "import pathlib, sys, time\n"
        "print('one', flush=True)\n"
        "print('two', flush=True)\n"
        "time.sleep(0.2)\n"
        "pathlib.Path('finished').touch()\n"
    )
    heard: list[str] = []

    def said(line: str) -> None:
        heard.append(line)
        raise BrokenPipeError("nobody is listening")

    with pytest.raises(BrokenPipeError):
        run([PYTHON, "-c", script], tmp_path, said=said)
    assert heard == ["one"]
    assert (tmp_path / "finished").exists()


def test_what_a_program_is_given_reaches_it_when_it_is_heard_too(
    tmp_path: Path,
) -> None:
    heard: list[str] = []
    script = "import sys; print(sys.stdin.read().upper())"
    result = run([PYTHON, "-c", script], tmp_path, given="abc", said=heard.append)
    assert (result.returncode, heard) == (0, ["ABC"])

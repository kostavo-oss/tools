"""stdout is lely's: what a plugin's own code prints goes to stderr — and a
plugin can't take lely's streams, or lely itself, down with it.

Each case is a real process: the streams under `sys.stdout` and `sys.stderr`
are what is being tested, and a test runner puts its own in their place.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from lely.errors import LelyError
from lely.step import quietly


def run(body: str) -> subprocess.CompletedProcess[str]:
    script = (
        "import io, os, subprocess, sys\n"
        "from lely.step import quietly\n"
        "print('before')\n"
        "with quietly():\n"
        f"{textwrap.indent(textwrap.dedent(body), '    ')}\n"
        "print('after')\n"
        "print('still there', file=sys.stderr)\n"
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )


@pytest.mark.parametrize(
    "body",
    [
        "print('loud')",
        "sys.__stdout__.write('loud\\n')",  # round `sys.stdout`
        "os.write(1, b'loud\\n')",  # under it
        # a program it starts without taking its output
        "subprocess.run([sys.executable, '-c', 'print(\"loud\")'], check=True)",
        "with quietly():\n    print('loud')",
    ],
)
def test_what_a_plugin_writes_goes_to_stderr_however_it_writes(body: str) -> None:
    done = run(body)
    assert done.returncode == 0, done.stderr
    assert done.stdout == "before\nafter\n"
    assert done.stderr == "loud\nstill there\n"


@pytest.mark.parametrize(
    "body",
    [
        # the ways to "make stdout UTF-8" — found in the fourth review: each
        # closed lely's stderr, and the run ended in a traceback nobody saw
        "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')\n"
        "print('loud')",
        "sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')\n"
        "print('loud')",
        "sys.stdout.reconfigure(encoding='utf-8')\nprint('loud')",
        "print('loud')\nsys.stdout.close()",
    ],
)
def test_a_plugin_that_takes_its_stdout_apart_leaves_lelys_alone(body: str) -> None:
    done = run(body)
    assert done.returncode == 0, done.stderr
    assert done.stdout == "before\nafter\n"
    assert done.stderr == "loud\nstill there\n"


def test_a_stream_a_plugin_kept_still_writes() -> None:
    """A logging handler set up when the module was imported writes to the
    stream it was given then, long after."""
    script = (
        "import logging, sys\n"
        "from lely.step import quietly\n"
        "with quietly():\n"
        "    logging.basicConfig(stream=sys.stdout, format='%(message)s')\n"
        "with quietly():\n"
        "    logging.warning('later')\n"
        "print('after')\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert (done.returncode, done.stdout, done.stderr) == (0, "after\n", "later\n")


def test_a_plugin_doesnt_end_the_program() -> None:
    """`sys.exit(0)` in a plugin's `apply` ended lely with 0, nothing on
    stdout, and the steps below it never run."""
    with pytest.raises(LelyError) as caught, quietly():
        sys.exit(0)
    assert str(caught.value) == (
        "its plugin ended the program (`sys.exit(0)`). A plugin returns, or raises "
        "an error."
    )
    named = pytest.raises(LelyError, match=r"`./ops/p.py:P` ended the program")
    with named, quietly("`./ops/p.py:P`"):
        raise SystemExit("bye")
    with pytest.raises(KeyboardInterrupt), quietly():  # the user's, not the plugin's
        raise KeyboardInterrupt


def test_under_a_test_runner_there_is_nothing_to_protect(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with quietly():
        print("loud")
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "loud\n")

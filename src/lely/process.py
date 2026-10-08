"""Running another program: the Databricks CLI, stevin, a step's program.

One place, so every step that shells out fails the same way: a missing program
says so, and a failing one is shown in its own words — what it wrote on both of
its streams.

A program that only answers a question is run to its end and its output taken.
One that changes something — a deploy, a job run, a step's program — can
take minutes, so its caller may ask to hear it (`said`): each line is passed on
as it comes, and still kept for whoever reads the result.
"""

from __future__ import annotations

import contextlib
import queue
import subprocess
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TextIO

from lely.errors import LelyError

#: Given each line a program writes, without its line break.
Said = Callable[[str], None]


class ProcessError(LelyError):
    """Another program was missing, or failed."""


def run(
    args: Sequence[str],
    cwd: Path,
    *,
    env: Mapping[str, str] | None = None,
    hint: str = "",
    given: str | None = None,
    said: Said | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run `args`, capturing its output. A missing program raises; a failing
    one doesn't — the caller decides what its exit code means. `given` is what
    the program reads on its standard input.

    With `said`, every line the program writes — on either stream — is also
    passed to it as it comes, on the thread that called. Nothing here prints:
    what `said` does with a line is its caller's to decide, and to keep safe.
    """
    if not args:
        raise ProcessError("There is no command to run: it is empty.")
    if not cwd.is_dir():
        # the same error a missing program gives: say which of the two it is
        raise ProcessError(f"There is no directory {cwd} to run `{args[0]}` in.")
    try:
        if said is None:
            return subprocess.run(
                list(args),
                cwd=cwd,
                env=dict(env) if env is not None else None,
                capture_output=True,
                text=True,
                check=False,
                input=given,
            )
        child = subprocess.Popen(
            list(args),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdin=subprocess.PIPE if given is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # what a program wrote is shown, whatever bytes it holds
            errors="replace",
        )
    except FileNotFoundError:
        raise ProcessError(
            f"`{args[0]}` isn't installed or isn't on PATH."
            + (f" {hint}" if hint else "")
        ) from None
    return _heard(child, given, said)


def _heard(
    child: subprocess.Popen[str], given: str | None, said: Said
) -> subprocess.CompletedProcess[str]:
    """Wait for `child`, passing on each line as it is written. Two threads
    read the two streams, so neither fills up while the other is read; the
    lines reach `said` here, in the order they came.

    A `said` that fails doesn't end the program: it may be halfway through a
    deploy. It is heard out in silence, and the error is raised when it is done.
    """
    lines: queue.SimpleQueue[tuple[list[str], str] | None] = queue.SimpleQueue()
    kept: tuple[list[str], list[str]] = ([], [])

    def read(stream: TextIO, into: list[str]) -> None:
        try:
            for line in stream:
                lines.put((into, line))
        except (OSError, ValueError):
            pass  # closed under it: the run is being ended
        finally:
            lines.put(None)

    assert child.stdout is not None and child.stderr is not None
    readers = [
        threading.Thread(target=read, args=(stream, into), daemon=True)
        for stream, into in zip((child.stdout, child.stderr), kept, strict=True)
    ]
    failed: Exception | None = None
    try:
        for reader in readers:
            reader.start()
        if child.stdin is not None:
            # it may have ended, or stopped reading: its exit code says how
            with contextlib.suppress(OSError):
                child.stdin.write(given or "")
                child.stdin.close()
        reading = len(readers)
        while reading:
            item = lines.get()
            if item is None:
                reading -= 1
                continue
            into, line = item
            into.append(line)
            if failed is None:
                try:
                    said(line.rstrip("\n"))
                except Exception as error:
                    failed = error
        code = child.wait()
    except BaseException:
        # as `subprocess.run` does: nothing is left running behind an error
        child.kill()
        child.wait()
        raise
    finally:
        for reader in readers:
            if reader.ident is not None:
                reader.join(timeout=1)
        if not any(reader.is_alive() for reader in readers):
            for stream in (child.stdin, child.stdout, child.stderr):
                if stream is not None:
                    with contextlib.suppress(OSError):
                        stream.close()
    if failed is not None:
        raise failed
    return subprocess.CompletedProcess(
        child.args, code, "".join(kept[0]), "".join(kept[1])
    )


def wrote(result: subprocess.CompletedProcess[str]) -> str:
    """What a program wrote, for a message: both streams, each under its name
    when both were written to. Its reason for failing may be on either."""
    out, err = result.stdout.strip(), result.stderr.strip()
    if out and err:
        return f"stdout:\n{out}\nstderr:\n{err}"
    return out or err


def failure(what: str, result: subprocess.CompletedProcess[str]) -> ProcessError:
    """A failed run, as an error that quotes what the program said."""
    said = wrote(result) or "(no output)"
    return ProcessError(f"{what} failed (exit {result.returncode}):\n{said}")

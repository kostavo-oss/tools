"""caland as a page: a server on this machine, and a browser tab.

`run` is the whole of it — choose the workspace, start loading it, serve the page
until it is stopped. What the server will and will not answer is in `gate.py`. The
rules are `CMD` and `GATE` in `RULES.md`, and `DECISIONS.md` says why.

Stopping (CMD-7, CMD-9) is asked for and never thrown: ctrl+c, a signal to terminate and
being left alone each leave a note (`_Stop`), the loop that serves reads the note
between two requests, and the tidying that follows cannot be cut short by a second
signal, because a signal does nothing here but leave the note again.
"""

from __future__ import annotations

import contextlib
import signal
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from typing import TextIO

from ...application import OnboardingService
from ...application.loading import CONNECTING
from ...domain import AuthError, Settings, SettingsStore
from .opening import Opener
from .server import Page, Server

__all__ = ["IDLE", "Page", "Server", "run"]

#: Left alone this long, caland stops and forgets what it held. CMD-8.
IDLE = 30 * 60

#: How long the server waits for a request before it looks whether it was asked to
#: stop, in seconds: the longest a stop can take to be noticed.
TURN = 0.2


def run(
    onboarding: OnboardingService,
    name: str | None = None,
    *,
    read_only: bool = False,
    settings_store: SettingsStore | None = None,
    version: str = "",
    open_browser: bool = True,
    browser: Callable[[str], bool] = webbrowser.open,
    idle: float = IDLE,
    out: TextIO | None = None,
    stdin: TextIO | None = None,
    signals_back: bool = True,
) -> int:
    """Serve one workspace as a page until stopped. The exit code.

    `signals_back` puts the handlers for ctrl+c and a signal to terminate back as
    they were once everything is tidied. The command says False: it ends with this,
    and a signal that comes after the last line must find nothing to break."""
    out = out or sys.stderr
    stdin = stdin or sys.stdin
    try:
        workspace = onboarding.choose(name)
    except AuthError as exc:
        if name:  # asked for by name, and not there: said, and nothing started
            print(f"caland: {exc}", file=out)
            return 2
        workspace = None  # several, or none: the page asks which

    page = Page(
        onboarding=onboarding,
        read_only=read_only,
        settings=settings_store.load() if settings_store else Settings(),
        keep=settings_store.save if settings_store else lambda settings: None,
        version=version,
    )
    server = Server(page)
    server.out = out  # where a failure inside is said: the terminal, by a line
    server.timeout = TURN
    opener = Opener(browser)
    page.entered = opener.clean
    stop = _Stop()

    def show() -> None:
        if stop.asked:  # enter, pressed while it stops: no new key and no new file
            return
        link = f"{server.address}#{page.new_key()}"
        if open_browser and opener.open(link):
            print(f"caland is at {server.address} — opened in your browser.", file=out)
        elif not stop.asked:
            # asked for, or no browser could be started: the person is told the
            # link. A terminal is theirs alone; a command line is not.
            print(f"caland is waiting at:\n  {link}\nThe link works once.", file=out)

    def forget() -> None:
        loader = page.current()[2]
        if loader is not None and loader.service is not None:
            loader.service.forget_values()

    def goodbye() -> None:
        reason = f" {stop.why}" if stop.why else ""
        print(f"\ncaland stopped.{reason} Every value it held is forgotten.", file=out)

    # from here until the tidying is done a signal is a note and never an exception:
    # before the file with the key is made, so that nothing can come between making
    # it and being sure it is removed
    as_it_was = _listen(stop)
    try:
        if workspace is not None:
            page.connect(workspace)
        show()
        print("enter: a new link · ctrl+c: stop", file=out)
        _watch(page, idle, stop)
        if stdin.isatty():
            _again(stdin, show)
        while not stop.asked:
            server.handle_request()  # one request, or TURN seconds with none
    finally:
        stop()  # whatever ended the serving, nothing new is started from here on
        _tidy(
            out,
            ("closing the server", server.server_close),
            ("removing the file with the key", opener.close),
            ("forgetting the values", forget),
            ("saying so", goodbye),
        )
        if signals_back:
            as_it_was()
    return 0


class _Stop:
    """Whether caland was asked to stop, and why if it has a reason to give.

    Two plain attributes and no lock, on purpose. A signal's handler runs on the
    main thread between two of its instructions, wherever it is: a handler that
    waited for a lock the main thread held would wait for ever, and one that raised
    would cut short whatever was running, the tidying included (CMD-9).
    """

    def __init__(self) -> None:
        self.asked = False
        self.why = ""

    def __call__(self, why: str = "") -> None:
        if not self.asked:
            self.why = why
            self.asked = True


def _tidy(out: TextIO, *steps: tuple[str, Callable[[], None]]) -> None:
    """Every step, in order, each whatever became of the one before it. CMD-9.
    A step that fails is one line: what it was and the kind of failure, never the
    failure's own words, which can quote a value (VAL-1)."""
    for what, step in steps:
        try:
            step()
        except Exception as exc:  # noqa: BLE001 — the steps after it still have to run
            with contextlib.suppress(Exception):
                print(f"caland: {what} failed ({type(exc).__name__}).", file=out)


def _watch(page: Page, idle: float, stop: _Stop) -> None:
    """Ask caland to stop when nothing has been asked of it for `idle` seconds,
    and say that as the reason. CMD-8."""

    def watch() -> None:
        while page.idle() < idle:
            if stop.asked:
                return
            time.sleep(min(5.0, max(0.05, idle / 10)))
        why = f"Nothing was asked of it for {round(idle / 60)} minutes"
        loader = page.current()[2]
        if loader is not None and loader.progress().phase == CONNECTING:
            # a sign-in in the browser that was never finished, as a rule: the SDK
            # waits for it without end, and the page that waits with it is not asking
            why += ", and it was still waiting to be signed in to the workspace"
        stop(f"{why}.")

    threading.Thread(target=watch, name="caland-idle", daemon=True).start()


def _listen(stop: _Stop) -> Callable[[], None]:
    """ctrl+c (SIGINT) and being told to stop (SIGTERM) are the same thing: a note
    that caland is to stop. Neither raises, so a second one, and a third, changes
    nothing, whenever it comes. Returns what puts the handlers back as they were.
    Only the main thread may listen: on another, nothing is listened for."""
    if threading.current_thread() is not threading.main_thread():
        return lambda: None

    def note(signum: int, frame: object) -> None:
        stop()

    before = {sig: signal.signal(sig, note) for sig in (signal.SIGINT, signal.SIGTERM)}

    def as_it_was() -> None:
        for sig, handler in before.items():
            signal.signal(sig, handler)

    return as_it_was


def _again(stdin: TextIO, show: Callable[[], None]) -> None:
    """A new link whenever enter is pressed: a tab that was closed is not the end."""

    def listen() -> None:
        for _ in stdin:
            show()

    threading.Thread(target=listen, name="caland-enter", daemon=True).start()

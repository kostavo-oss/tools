"""caland as a page: a server on this machine, and a browser tab.

`run` is the whole of it — choose the workspace, start loading it, serve the page
until it is stopped. What the server will and will not answer is in `gate.py`;
spec/008-the-page.md says why.
"""

from __future__ import annotations

import signal
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from typing import TextIO

from ...application import OnboardingService
from ...domain import AuthError, Settings, SettingsStore
from .opening import Opener
from .server import Page, Server

__all__ = ["IDLE", "Page", "Server", "run"]

#: Left alone this long, caland stops and forgets what it held.
IDLE = 30 * 60


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
) -> int:
    """Serve one workspace as a page until stopped. The exit code."""
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
    opener = Opener(browser)
    page.entered = opener.clean
    if workspace is not None:
        page.connect(workspace)

    def show() -> None:
        link = f"{server.address}#{page.new_key()}"
        if open_browser and opener.open(link):
            print(f"caland is at {server.address} — opened in your browser.", file=out)
        else:
            # asked for, or no browser could be started: the person is told the
            # link. A terminal is theirs alone; a command line is not.
            print(f"caland is waiting at:\n  {link}\nThe link works once.", file=out)

    show()
    print("enter: a new link · ctrl+c: stop", file=out)

    why = _watch(server, page, idle)
    if stdin.isatty():
        _again(stdin, show)
    told_to_stop = _on_terminate()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        told_to_stop()
        server.server_close()
        opener.clean()
        if page.loader is not None and page.loader.service is not None:
            page.loader.service.forget_values()
    reason = f" {why[0]}" if why else ""
    print(f"\ncaland stopped.{reason} Every value it held is forgotten.", file=out)
    return 0


def _watch(server: Server, page: Page, idle: float) -> list[str]:
    """Stop the server when nothing has been asked of it for `idle` seconds.
    The list is given the reason when that happens."""
    why: list[str] = []

    def watch() -> None:
        while page.idle() < idle:
            time.sleep(min(5.0, max(0.05, idle / 10)))
        why.append(f"Nothing was asked of it for {round(idle / 60)} minutes.")
        server.shutdown()

    threading.Thread(target=watch, name="caland-idle", daemon=True).start()
    return why


def _on_terminate() -> Callable[[], None]:
    """Being told to stop (SIGTERM) is ctrl+c: the same tidying, the same goodbye.
    Returns what puts things back as they were. Only the main thread may listen."""
    if threading.current_thread() is not threading.main_thread():
        return lambda: None

    def stop(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    before = signal.signal(signal.SIGTERM, stop)

    def as_it_was() -> None:
        signal.signal(signal.SIGTERM, before)

    return as_it_was


def _again(stdin: TextIO, show: Callable[[], None]) -> None:
    """A new link whenever enter is pressed: a tab that was closed is not the end."""

    def listen() -> None:
        for _ in stdin:
            show()

    threading.Thread(target=listen, name="caland-enter", daemon=True).start()

"""caland as a page: a server on this machine, and a browser tab.

`run` is the whole of it — choose the workspace, start loading it, serve the page
until it is stopped. What the server will and will not answer is in `gate.py`;
spec/008-the-page.md says why.
"""

from __future__ import annotations

import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from typing import TextIO

from ...application import Loader, OnboardingService
from ...domain import AuthError, Settings
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
    settings: Settings | None = None,
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
        print(f"caland: {exc}", file=out)
        return 2

    loader = Loader(lambda: onboarding.connect(workspace).service)
    page = Page(
        loader,
        workspace=workspace,
        read_only=read_only,
        show_all=(settings or Settings()).show_all_scopes,
        version=version,
    )
    server = Server(page)
    opener = Opener(browser)
    page.entered = opener.clean
    loader.start()

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
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        opener.clean()
        if loader.service is not None:
            loader.service.forget_values()
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


def _again(stdin: TextIO, show: Callable[[], None]) -> None:
    """A new link whenever enter is pressed: a tab that was closed is not the end."""

    def listen() -> None:
        for _ in stdin:
            show()

    threading.Thread(target=listen, name="caland-enter", daemon=True).start()

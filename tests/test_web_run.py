"""`caland --page` from start to stop, with a browser that is not one."""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from caland.application import OnboardingService
from caland.domain import Workspace
from caland.interface import web
from fakes import ConnectingStubConnector, StubBundle, StubProfiles, seeded_store

DEV = Workspace(profile="dev", host="https://dev.example")
PROD = Workspace(profile="prod", host="https://prod.example")


def onboarding(store=None, workspaces=(DEV,)) -> OnboardingService:
    return OnboardingService(
        ConnectingStubConnector(store), StubProfiles(list(workspaces)), StubBundle()
    )


def run(**kwargs: Any) -> tuple[int, str]:
    """Run until it stops by itself: nothing asks it anything."""
    out = io.StringIO()
    settings: dict[str, Any] = {
        "idle": 0.2,
        "out": out,
        "stdin": io.StringIO(),
        "open_browser": False,
        **kwargs,
    }
    code = web.run(settings.pop("onboarding", None) or onboarding(), **settings)
    return code, out.getvalue()


def test_it_says_where_it_is_and_stops_when_left_alone():
    code, said = run()
    assert code == 0
    assert re.search(r"http://127\.0\.0\.1:\d+/#[\w-]{40,}", said)
    assert "The link works once." in said
    assert "caland stopped. Nothing was asked of it" in said
    assert "Every value it held is forgotten." in said


def test_with_a_browser_the_key_is_not_printed():
    opened: list[str] = []

    def browser(address: str) -> bool:
        opened.append(address)
        return True

    code, said = run(open_browser=True, browser=browser)
    assert code == 0 and len(opened) == 1 and opened[0].startswith("file://")
    assert "opened in your browser" in said and "#" not in said


def test_when_no_browser_starts_the_link_is_said_instead():
    code, said = run(open_browser=True, browser=lambda address: False)
    assert code == 0 and re.search(r"http://127\.0\.0\.1:\d+/#[\w-]{40,}", said)


def test_the_file_with_the_key_is_gone_when_it_stops():
    opened: list[str] = []
    run(open_browser=True, browser=lambda address: bool(opened.append(address)) or True)
    assert not Path(unquote(urlsplit(opened[0]).path)).exists()


def test_being_told_to_stop_is_tidied_like_ctrl_c():
    import os
    import signal
    import threading

    opened: list[str] = []
    threading.Timer(0.3, os.kill, (os.getpid(), signal.SIGTERM)).start()
    before = signal.getsignal(signal.SIGTERM)
    code, said = run(
        idle=30,
        open_browser=True,
        browser=lambda address: bool(opened.append(address)) or True,
    )
    assert code == 0 and "caland stopped. Every value it held is forgotten." in said
    assert not Path(unquote(urlsplit(opened[0]).path)).exists()
    assert signal.getsignal(signal.SIGTERM) is before


def test_a_workspace_that_is_not_there_ends_it_before_it_starts():
    code, said = run(name="nope")
    assert code == 2 and "No workspace “nope” found. There is: dev." in said
    assert "http://" not in said


def test_several_workspaces_and_no_name_starts_and_lets_the_page_ask_which():
    code, said = run(onboarding=onboarding(workspaces=(DEV, PROD)))
    assert code == 0 and re.search(r"http://127\.0\.0\.1:\d+/#[\w-]{40,}", said)
    assert "Which workspace?" not in said


def test_no_workspace_at_all_starts_too_for_one_can_be_signed_in_to_by_address():
    code, said = run(onboarding=onboarding(workspaces=()))
    assert code == 0 and "caland stopped." in said


def test_every_value_is_forgotten_when_it_stops():
    held = []

    class Remembering(OnboardingService):
        def connect(self, workspace):
            connection = super().connect(workspace)
            connection.service.reveal("prod", "api-key")
            held.append(connection.service)
            return connection

    board = Remembering(
        ConnectingStubConnector(seeded_store()), StubProfiles([DEV]), StubBundle()
    )
    run(onboarding=board)
    assert held and held[0].cached_value("prod", "api-key") is None

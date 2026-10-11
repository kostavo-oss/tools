"""`caland --page` from start to stop, with a browser that is not one."""

from __future__ import annotations

import http.client
import io
import os
import re
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import pytest

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
    out = kwargs.pop("out", None) or io.StringIO()
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
    """CMD-6, CMD-8."""
    code, said = run()
    assert code == 0
    assert re.search(r"http://127\.0\.0\.1:\d+/#[\w-]{40,}", said)
    assert "The link works once." in said
    assert "caland stopped. Nothing was asked of it" in said
    assert "Every value it held is forgotten." in said


def test_with_a_browser_the_key_is_not_printed():
    """CMD-6."""
    opened: list[str] = []

    def browser(address: str) -> bool:
        opened.append(address)
        return True

    code, said = run(open_browser=True, browser=browser)
    assert code == 0 and len(opened) == 1 and opened[0].startswith("file://")
    assert "opened in your browser" in said and "#" not in said


def test_when_no_browser_starts_the_link_is_said_instead():
    """CMD-6."""
    code, said = run(open_browser=True, browser=lambda address: False)
    assert code == 0 and re.search(r"http://127\.0\.0\.1:\d+/#[\w-]{40,}", said)


def test_the_file_with_the_key_is_gone_when_it_stops():
    """CMD-7."""
    opened: list[str] = []
    run(open_browser=True, browser=lambda address: bool(opened.append(address)) or True)
    assert not Path(unquote(urlsplit(opened[0]).path)).exists()


class Said(io.StringIO):
    """What caland prints, and the moment it has said that it is there."""

    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()

    def write(self, text: str) -> int:
        written = super().write(text)
        if "ctrl+c: stop" in self.getvalue():
            self.started.set()
        return written


def once_it_serves(out: Said, do, *args) -> threading.Thread:
    """Do something to a caland that is serving: it has said where it is, and it has
    answered a request. Nothing here waits for a length of time."""

    def wait() -> None:
        assert out.started.wait(10)
        port = int(re.findall(r"127\.0\.0\.1:(\d+)", out.getvalue())[0])
        asking = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            asking.request("GET", "/")
            assert asking.getresponse().status == 200
        finally:
            asking.close()
        do(*args)

    thread = threading.Thread(target=wait)
    thread.start()
    return thread


def handed_a_file() -> tuple[list[Path], Any]:
    """A browser that is none, and the files it was handed."""
    files: list[Path] = []

    def browser(address: str) -> bool:
        files.append(Path(unquote(urlsplit(address).path)))
        return True

    return files, browser


@pytest.mark.parametrize("sign", [signal.SIGINT, signal.SIGTERM])
def test_being_told_to_stop_is_tidied_like_ctrl_c(sign):
    """CMD-7."""
    files, browser = handed_a_file()
    out = Said()
    before = signal.getsignal(sign)
    sending = once_it_serves(out, os.kill, os.getpid(), sign)
    code, said = run(idle=30, out=out, open_browser=True, browser=browser)
    sending.join(10)
    assert code == 0 and "caland stopped. Every value it held is forgotten." in said
    assert "#" not in said and len(files) == 1 and not files[0].exists()
    assert signal.getsignal(sign) is before


@pytest.mark.parametrize(
    "first, then",
    [
        (signal.SIGINT, [signal.SIGINT]),
        (signal.SIGTERM, [signal.SIGTERM]),
        (signal.SIGTERM, [signal.SIGINT]),
        (signal.SIGINT, [signal.SIGTERM]),
        (signal.SIGTERM, [signal.SIGINT, signal.SIGTERM, signal.SIGINT]),
    ],
)
def test_a_signal_that_comes_while_it_tidies_up_changes_nothing(first, then, monkeypatch):
    """CMD-9. The signals after the first arrive inside the first step of the
    tidying: the steps after it are still to come, and all of them have to."""
    files, browser = handed_a_file()
    held, board, read = remembering()
    close = web.Server.server_close
    arrived: list[int] = []

    def closing(server) -> None:
        for sign in then:
            signal.raise_signal(sign)  # to this thread, which is the one tidying
            arrived.append(sign)
        close(server)
        assert server.socket.fileno() == -1  # closed, signals or no signals

    monkeypatch.setattr(web.Server, "server_close", closing)
    out = Said()

    def send() -> None:
        assert read.wait(10)  # there is a value to forget
        os.kill(os.getpid(), first)

    sending = once_it_serves(out, send)
    code, said = run(
        onboarding=board, idle=30, out=out, open_browser=True, browser=browser
    )
    sending.join(10)
    assert arrived == then
    assert code == 0 and "Traceback" not in said
    assert said.count("caland stopped. Every value it held is forgotten.") == 1
    assert len(files) == 1 and not files[0].exists() and not files[0].parent.exists()
    assert held and held[0].cache.raw == {}


def test_each_step_of_the_tidying_runs_whatever_became_of_the_one_before(monkeypatch):
    """CMD-9. A step that fails is said in a line, without the failure's words."""
    files, browser = handed_a_file()
    held, board, _ = remembering()

    def closing(server) -> None:
        raise OSError("value::prod/api-key")

    monkeypatch.setattr(web.Server, "server_close", closing)
    code, said = run(onboarding=board, open_browser=True, browser=browser)
    assert code == 0 and "caland: closing the server failed (OSError)." in said
    assert "value::" not in said and "Traceback" not in said
    assert not files[0].exists() and held[0].cache.raw == {}
    assert "caland stopped." in said


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no such signals")
@pytest.mark.parametrize(
    "signs",
    [
        (signal.SIGINT,),
        (signal.SIGTERM,),
        (signal.SIGTERM, signal.SIGINT),
        (signal.SIGINT, signal.SIGTERM, signal.SIGTERM, signal.SIGINT, signal.SIGINT),
    ],
)
def test_the_command_itself_stops_tidily_whatever_signals_it_is_sent(signs, tmp_path):
    """CMD-9. The real command, as a process of its own: the signals are sent one
    straight after the other, and land where they land. No workspace: nothing is
    found on this machine, and the browser is a command that does nothing."""
    home, temporary = tmp_path / "home", tmp_path / "tmp"
    home.mkdir()
    temporary.mkdir()
    kept = {k: v for k, v in os.environ.items() if not k.startswith("DATABRICKS_")}
    caland = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "caland"],
        cwd=home,
        env={
            **kept,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home),
            "DATABRICKS_CONFIG_FILE": str(home / "none"),
            "TMPDIR": str(temporary),
            "BROWSER": "true",
        },
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert caland.stderr is not None
    try:
        said = ""
        while "ctrl+c: stop" not in said:  # it listens for signals before it says so
            line = caland.stderr.readline()
            assert line, f"caland ended before it started: {said}"
            said += line
        files = list(temporary.glob("caland-*/open.html"))
        assert "opened in your browser" in said and len(files) == 1
        for sign in signs:
            caland.send_signal(sign)
        said += caland.communicate(timeout=20)[1]
    finally:
        caland.kill()
        caland.wait()
    assert caland.returncode == 0, said
    assert "Traceback" not in said and "KeyboardInterrupt" not in said
    assert said.count("caland stopped. Every value it held is forgotten.") == 1
    assert list(temporary.iterdir()) == []


def test_a_workspace_that_is_not_there_ends_it_before_it_starts():
    """CMD-4."""
    code, said = run(name="nope")
    assert code == 2 and "No workspace “nope” found. There is: dev." in said
    assert "http://" not in said


def test_several_workspaces_and_no_name_starts_and_lets_the_page_ask_which():
    code, said = run(onboarding=onboarding(workspaces=(DEV, PROD)))
    assert code == 0 and re.search(r"http://127\.0\.0\.1:\d+/#[\w-]{40,}", said)
    assert "Which workspace?" not in said


def test_no_workspace_at_all_starts_too_for_one_can_be_signed_in_to_by_address():
    """CMD-5."""
    code, said = run(onboarding=onboarding(workspaces=()))
    assert code == 0 and "caland stopped." in said


def remembering() -> tuple[list, OnboardingService, threading.Event]:
    """A workspace of which a value was read, what holds that value, and the moment
    it was read."""
    held: list = []
    read = threading.Event()

    class Remembering(OnboardingService):
        def connect(self, workspace):
            connection = super().connect(workspace)
            connection.service.reveal_bytes("prod", "api-key")
            held.append(connection.service)
            read.set()
            return connection

    board = Remembering(
        ConnectingStubConnector(seeded_store()), StubProfiles([DEV]), StubBundle()
    )
    return held, board, read


def test_every_value_is_forgotten_when_it_stops():
    """CMD-7."""
    held, board, _ = remembering()
    run(onboarding=board)
    assert held and held[0].cache.raw == {}

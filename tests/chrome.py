"""A real browser for the tests: Chrome, driven over its debugging pipe.

No package for it: Chrome is told what to do in JSON on one pipe and answers on
another (`--remote-debugging-pipe`), and that is all this is. It is how the page
is held to what it promises — real keys pressed, the real page asked what it shows.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

CHROME = next(
    (
        path
        for path in (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            shutil.which("google-chrome") or "",
            shutil.which("chromium") or "",
            shutil.which("chromium-browser") or "",
        )
        if path and Path(path).exists()
    ),
    None,
)

#: The keys that are not a letter, as Chrome wants them named.
_KEYS = {
    "Tab": ("Tab", 9, ""),
    "Enter": ("Enter", 13, "\r"),
    "Escape": ("Escape", 27, ""),
    " ": ("Space", 32, " "),
    "ArrowLeft": ("ArrowLeft", 37, ""),
    "ArrowUp": ("ArrowUp", 38, ""),
    "ArrowRight": ("ArrowRight", 39, ""),
    "ArrowDown": ("ArrowDown", 40, ""),
    "/": ("Slash", 191, "/"),
    "?": ("Slash", 191, "?"),
}
SHIFT = 8


class Browser:
    def __init__(self) -> None:
        assert CHROME, "needs Chrome"
        to_chrome, ours_out = os.pipe()
        ours_in, from_chrome = os.pipe()

        def as_chrome_wants() -> None:
            # Chrome reads what it is told on 3 and answers on 4. Move both out
            # of the way first, so that neither lands on the other.
            read = fcntl.fcntl(to_chrome, fcntl.F_DUPFD, 10)
            write = fcntl.fcntl(from_chrome, fcntl.F_DUPFD, 10)
            os.dup2(read, 3)
            os.dup2(write, 4)

        self._profile = tempfile.mkdtemp(prefix="caland-chrome-")
        flags = [
            "--headless=new",
            "--remote-debugging-pipe",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--disable-extensions",
            "--window-size=1320,800",
            f"--user-data-dir={self._profile}",
        ]
        if sys.platform.startswith("linux"):
            flags.append("--no-sandbox")  # a CI runner gives Chrome no sandbox to use
        self._chrome = subprocess.Popen(  # noqa: S603
            [CHROME, *flags],
            preexec_fn=as_chrome_wants,  # noqa: PLW1509
            close_fds=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.close(to_chrome)
        os.close(from_chrome)
        self._out, self._in = ours_out, ours_in
        self._buffer = b""
        self._count = 0
        # a first start can take its time, on a machine that has never run it
        self.call("Browser.getVersion", seconds=120)
        # the clipboard is the tests' to read: what was copied is looked at
        self.call(
            "Browser.grantPermissions",
            {"permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"]},
        )

    def call(
        self,
        method: str,
        params: dict | None = None,
        session: str | None = None,
        seconds: float = 30,
    ) -> Any:
        self._count += 1
        message: dict[str, Any] = {
            "id": self._count,
            "method": method,
            "params": params or {},
        }
        if session:
            message["sessionId"] = session
        os.write(self._out, json.dumps(message).encode() + b"\0")
        deadline = time.monotonic() + seconds
        while True:
            answer = self._read(deadline)
            if answer.get("id") == self._count:
                if "error" in answer:
                    raise RuntimeError(f"{method}: {answer['error']}")
                return answer["result"]

    def _read(self, deadline: float) -> dict:
        while b"\0" not in self._buffer:
            ready, _, _ = select.select(
                [self._in], [], [], max(0.0, deadline - time.monotonic())
            )
            if not ready:
                raise TimeoutError("Chrome did not answer")
            chunk = os.read(self._in, 65536)
            if not chunk:
                raise RuntimeError("Chrome went away")
            self._buffer += chunk
        message, _, self._buffer = self._buffer.partition(b"\0")
        return json.loads(message)

    def tab(self, address: str = "about:blank") -> Tab:
        target = self.call("Target.createTarget", {"url": "about:blank"})["targetId"]
        session = self.call(
            "Target.attachToTarget", {"targetId": target, "flatten": True}
        )
        tab = Tab(self, session["sessionId"])
        tab.call("Emulation.setFocusEmulationEnabled", {"enabled": True})
        tab.call("Page.enable")
        # a click on "choose a file" opens no dialog of the system's here: the tests
        # hand files to the input themselves (`choose_files`)
        tab.call("Page.setInterceptFileChooserDialog", {"enabled": True})
        if address != "about:blank":
            tab.go(address)
        return tab

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.call("Browser.close")
        with contextlib.suppress(Exception):
            self._chrome.wait(timeout=5)
        if self._chrome.poll() is None:
            self._chrome.kill()
        for fd in (self._out, self._in):
            with contextlib.suppress(OSError):
                os.close(fd)
        shutil.rmtree(self._profile, ignore_errors=True)


class Tab:
    def __init__(self, browser: Browser, session: str) -> None:
        self._browser, self._session = browser, session

    def call(self, method: str, params: dict | None = None) -> Any:
        return self._browser.call(method, params, self._session)

    def go(self, address: str) -> None:
        self.call("Page.navigate", {"url": address})
        self.wait("document.readyState === 'complete'")

    def reload(self) -> None:
        """What the reload button does."""
        self.call("Page.reload")
        self.wait("document.readyState === 'complete'")

    def js(self, expression: str) -> Any:
        """What an expression is worth in the page. A promise is waited for."""
        answer = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        if "exceptionDetails" in answer:
            raise RuntimeError(answer["exceptionDetails"].get("text", "the page threw"))
        return answer["result"].get("value")

    def wait(self, expression: str, seconds: float = 10) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            with contextlib.suppress(RuntimeError):
                # asked as yes or no: an element is not something Chrome can hand over
                if self.js(f"Boolean({expression})"):
                    return
            time.sleep(0.02)
        raise TimeoutError(f"never true in the page: {expression}")

    def press(self, *keys: str, shift: bool = False) -> None:
        """Press keys as a person does: a real key down and up, to what has focus."""
        for key in keys:
            if key in _KEYS:
                code, number, text = _KEYS[key]
            else:
                code, number, text = f"Key{key.upper()}", ord(key.upper()), key
            modifiers = (
                SHIFT if shift or (len(key) == 1 and key.isupper()) or key == "?" else 0
            )
            event = {
                "key": key,
                "code": code,
                "windowsVirtualKeyCode": number,
                "modifiers": modifiers,
            }
            down = {**event, "type": "keyDown" if text else "rawKeyDown"}
            if text:
                down["text"] = text
            self.call("Input.dispatchKeyEvent", down)
            self.call("Input.dispatchKeyEvent", {**event, "type": "keyUp"})

    def type(self, text: str) -> None:
        self.call("Input.insertText", {"text": text})

    def choose_files(self, selector: str, *paths: str) -> None:
        """What the system's file dialog does once a file is picked in it: hand
        the file to the page's input. The dialog itself is the browser's."""
        root = self.call("DOM.getDocument")["root"]["nodeId"]
        node = self.call("DOM.querySelector", {"nodeId": root, "selector": selector})
        self.call(
            "DOM.setFileInputFiles", {"files": list(paths), "nodeId": node["nodeId"]}
        )

    def clipboard(self) -> str:
        """What is on the clipboard."""
        return self.js("navigator.clipboard.readText()")

    def focus(self) -> str:
        """What has the keyboard: its id, or failing that what it says."""
        return self.js(
            "(() => { const a = document.activeElement;"
            " return a.id || a.textContent.trim().split(/\\s+/)[0]; })()"
        )

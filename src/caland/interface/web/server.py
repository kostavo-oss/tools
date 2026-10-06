"""The local server — caland's page, for the one person who started it.

It listens on this machine only, answers to nothing the gate (`gate.py`) does
not let through, and gives a secret's value to one request only: a `POST` from
its own page, carrying the session's token. Stopping it forgets everything.

Python's own HTTP server is enough for one person on one machine, and is one
dependency fewer to trust.
"""

from __future__ import annotations

import json
import secrets
import socketserver
import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any
from urllib.parse import parse_qs, urlsplit

from ...application import Loader
from ...domain import StoreError, Workspace
from . import gate, views

#: The most a request may say. Nothing the page sends comes near it.
BODY_LIMIT = 64 * 1024

#: The page: where each file is asked for, what it is called, and what it is.
_FILES = {
    "/": ("page.html", "text/html; charset=utf-8"),
    "/page.css": ("page.css", "text/css; charset=utf-8"),
    "/page.js": ("page.js", "text/javascript; charset=utf-8"),
}

#: Said with every answer. The page loads nothing that is not caland's own, runs
#: no script written into it, is kept by nothing, and is framed by nobody.
HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class Page:
    """One run of caland's page: a workspace, and who may ask about it."""

    def __init__(
        self,
        loader: Loader,
        *,
        workspace: Workspace,
        read_only: bool = False,
        show_all: bool = False,
        version: str = "",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.loader = loader
        self.workspace = workspace
        self.read_only = read_only
        self.show_all = show_all
        self.version = version
        #: What every request but the first must carry. Never leaves this process
        #: but as the answer to the one-time key.
        self.token = secrets.token_urlsafe(32)
        self._key: str | None = None
        self._lock = threading.Lock()
        self._clock = clock
        self._used = clock()
        #: Called when a key has been used: the file that held it can go.
        self.entered: Callable[[], None] = lambda: None

    def new_key(self) -> str:
        """A key that lets one page in, once. A key not yet used is dropped."""
        with self._lock:
            self._key = secrets.token_urlsafe(32)
            return self._key

    def enter(self, key: object) -> str | None:
        """The session's token for the right key — which is then spent."""
        with self._lock:
            if not isinstance(key, str) or self._key is None:
                return None
            if not gate.same(key, self._key):
                return None
            self._key = None
        self.entered()
        return self.token

    def touch(self) -> None:
        self._used = self._clock()

    def idle(self) -> float:
        """Seconds since the page last asked for anything."""
        return self._clock() - self._used


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, page: Page, port: int = 0) -> None:
        self.page = page
        # this machine only. There is no way to ask for anything wider.
        super().__init__(("127.0.0.1", port), Handler)

    def server_bind(self) -> None:
        # not HTTPServer's: it looks the machine's name up, which can take seconds
        socketserver.TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]

    @property
    def port(self) -> int:
        return self.server_address[1]

    @property
    def address(self) -> str:
        return f"http://127.0.0.1:{self.port}/"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "caland"
    sys_version = ""
    timeout = 30
    server: Server

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Nothing a request says is written anywhere."""

    def do_GET(self) -> None:  # noqa: N802
        self._answer("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._answer("POST")

    def _other(self) -> None:
        self._answer(self.command)

    do_HEAD = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _other  # noqa: N815

    # -- one request ----------------------------------------------------
    def _answer(self, method: str) -> None:
        page = self.server.page
        try:
            url = urlsplit(self.path)
            refusal = gate.check(
                method,
                url.path,
                self.headers.get,
                port=self.server.port,
                token=page.token,
            )
            if refusal:
                self._refuse(refusal.status, refusal.reason)
            elif url.path in _FILES:
                self._file(url.path)
            else:
                self._api(method, url.path, parse_qs(url.query))
        except _Refused as refused:
            self._refuse(refused.status, refused.reason)
        except Exception:  # noqa: BLE001 — never a traceback, or a detail, to the asker
            self._refuse(500, "caland failed")

    def _api(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        page = self.server.page
        body = self._body() if method == "POST" else {}

        if path == gate.ENTER:
            token = page.enter(body.get("key"))
            if token is None:
                raise _Refused(403, "this key was used, or never was one")
            return self._json({"token": token})

        page.touch()
        service = page.loader.service

        if (method, path) == ("GET", "/api/state"):
            return self._json(
                views.state(
                    page.loader.progress(),
                    service,
                    workspace=page.workspace,
                    read_only=page.read_only,
                    show_all=page.show_all,
                    version=page.version,
                )
            )
        if service is None:
            raise _Refused(409, "not connected yet")

        if (method, path) == ("GET", "/api/scope"):
            told = views.scope(service, _one(query, "name"))
            if told is None:
                raise _Refused(404, "no such scope")
            return self._json(told)
        if (method, path) == ("GET", "/api/keys"):
            return self._json(views.keys(service))
        if (method, path) == ("POST", "/api/value"):
            scope, key = _text(body, "scope"), _text(body, "key")
            if service.secret(scope, key) is None:
                raise _Refused(404, "no such secret")
            try:
                return self._json({"value": service.reveal(scope, key)})
            except StoreError as exc:
                raise _Refused(502, str(exc)) from exc
        if (method, path) == ("POST", "/api/forget"):
            service.forget_values()
            return self._json({})
        if (method, path) == ("POST", "/api/refresh"):
            scope = body.get("scope")
            if scope is not None and not isinstance(scope, str):
                raise _Refused(400, "a scope is a name")
            page.loader.refresh(scope)
            return self._json({}, status=202)
        raise _Refused(404, "nothing here")

    def _body(self) -> dict[str, Any]:
        length = self.headers.get("Content-Length", "")
        if not length.isdigit():
            raise _Refused(411, "say how much is coming")
        if int(length) > BODY_LIMIT:
            raise _Refused(413, "too much")
        try:
            said = json.loads(self.rfile.read(int(length)) or b"{}")
        except (ValueError, UnicodeDecodeError) as exc:
            raise _Refused(400, "not JSON") from exc
        if not isinstance(said, dict):
            raise _Refused(400, "not an object")
        return said

    # -- answers --------------------------------------------------------
    def _file(self, path: str) -> None:
        name, kind = _FILES[path]
        data = (
            resources.files("caland.interface.web").joinpath("static", name).read_bytes()
        )
        self._send(200, data, kind)

    def _json(self, told: dict[str, Any], status: int = 200) -> None:
        self._send(status, json.dumps(told).encode(), "application/json")

    def _refuse(self, status: int, reason: str) -> None:
        # whatever came with a request that is refused is left unread — so the
        # connection ends here, and none of it is taken for a request of its own
        self.close_connection = True
        self._send(status, json.dumps({"error": reason}).encode(), "application/json")

    def _send(self, status: int, data: bytes, kind: str) -> None:
        self.send_response(HTTPStatus(status))
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        for name, value in HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)


class _Refused(Exception):
    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


def _one(query: dict[str, list[str]], name: str) -> str:
    values = query.get(name, [])
    if len(values) != 1:
        raise _Refused(400, f"say which {name}")
    return values[0]


def _text(body: dict[str, Any], name: str) -> str:
    value = body.get(name)
    if not isinstance(value, str) or not value:
        raise _Refused(400, f"say which {name}")
    return value

"""The local server — caland's page, for the one person who started it.

It listens on this machine only, answers to nothing the gate (`gate.py`) does
not let through, and gives a secret's value to one request only: a `POST` from
its own page, carrying the session's token. Stopping it forgets everything.

Python's own HTTP server is enough for one person on one machine, and is one
dependency fewer to trust.
"""

from __future__ import annotations

import base64
import binascii
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

from ...application import Loader, WorkspaceService, files
from ...domain import Exists, StoreError, Workspace, same_name
from . import gate, views

#: The most a request may say: the largest value a secret may hold, as the page
#: sends a file (base64, which is a third longer), and room for the rest.
BODY_LIMIT = 256 * 1024

_TOO_BIG = "a secret holds 128 kB at most"

#: The longest a name may be. Databricks decides what else a name may be.
NAME_LIMIT = 128

_Said = dict[str, Any]
_Asked = dict[str, list[str]]
_Told = tuple[dict[str, Any], int]

#: How many connections are kept at once. A browser opens six; this is room for
#: that many times over, and far below what a process may hold open — so that
#: connections left hanging cannot use those up.
CONNECTIONS = 64

#: Seconds a connection may say nothing before it is closed.
QUIET = 10

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
        self._open = threading.BoundedSemaphore(CONNECTIONS)
        # this machine only. There is no way to ask for anything wider.
        super().__init__(("127.0.0.1", port), Handler)

    def process_request(self, request: Any, client_address: Any) -> None:
        # one connection more than there is room for is closed, not queued
        if not self._open.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._open.release()

    def handle_error(self, request: Any, client_address: Any) -> None:
        """A connection that broke is nobody's news: nothing is printed. Not a
        traceback either — anyone who can reach the port could fill a terminal."""

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
    timeout = QUIET
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
    do_TRACE = do_CONNECT = _other  # noqa: N815

    def send_error(
        self, code: int, message: str | None = None, explain: str | None = None
    ) -> None:
        """What `http.server` refuses by itself — a request it cannot read, a
        method it has never heard of — is refused as everything else is: shortly,
        with the same headers, and with nothing of the request said back."""
        if self.request_version == "HTTP/0.9":
            # what could not be read at all is taken for the oldest HTTP, which
            # has no headers: answer it as the oldest that has
            self.request_version = "HTTP/1.0"
        self._refuse(int(code), "not something caland can read")

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
        if (method, path) == ("POST", "/api/describe"):
            # what a file is: asked before there is a workspace to put it in, too
            return self._json(files.describe(_bytes(body, "base64")).told())
        if service is None:
            raise _Refused(409, "not connected yet")

        route = _ROUTES.get((method, path))
        if route is None:
            raise _Refused(404, "nothing here")
        try:
            told, status = route(self, service, body, query)
        except Exists as exc:
            raise _Refused(409, str(exc)) from exc
        except StoreError as exc:
            # what the workspace said, shortly: it is the person's own to read
            raise _Refused(502, str(exc)) from exc
        return self._json(told, status=status)

    # -- reading --------------------------------------------------------
    def _scope(self, service: WorkspaceService, body: _Said, query: _Asked) -> _Told:
        told = views.scope(service, _one(query, "name"))
        if told is None:
            raise _Refused(404, "no such scope")
        return told, 200

    def _keys(self, service: WorkspaceService, body: _Said, query: _Asked) -> _Told:
        return views.keys(service), 200

    def _value(self, service: WorkspaceService, body: _Said, query: _Asked) -> _Told:
        scope, key = _text(body, "scope"), _text(body, "key")
        if service.secret(scope, key) is None:
            raise _Refused(404, "no such secret")
        return views.value(service.reveal_bytes(scope, key)), 200

    def _forget(self, service: WorkspaceService, body: _Said, query: _Asked) -> _Told:
        service.forget_values()
        self.server.page.loader.changed()
        return {}, 200

    def _refresh(self, service: WorkspaceService, body: _Said, query: _Asked) -> _Told:
        scope = body.get("scope")
        if scope is not None and not isinstance(scope, str):
            raise _Refused(400, "a scope is a name")
        self.server.page.loader.refresh(scope)
        return {}, 202

    # -- changing: nothing here runs when caland was started read-only ----
    def _may_change(self, service: WorkspaceService, scope: str | None = None) -> None:
        """Refuse a change that may not be made. With a scope: one to its secrets."""
        if self.server.page.read_only:
            raise _Refused(403, "caland was started read-only: it changes nothing")
        if scope is None:
            return
        found = service.scope(scope)
        if found is None:
            raise _Refused(404, "no such scope")
        if found.is_keyvault:
            raise _Refused(
                409, f"“{scope}” is Azure Key Vault's: change its secrets there"
            )

    def _changed(self) -> None:
        self.server.page.loader.changed()

    def _put(self, service: WorkspaceService, body: _Said, query: _Asked) -> _Told:
        scope, key = _text(body, "scope"), _name(body, "key")
        self._may_change(service, scope)
        if ("text" in body) == ("base64" in body):
            raise _Refused(400, "a value is text or a file, one of the two")
        if "text" in body:
            if not isinstance(body["text"], str):
                raise _Refused(400, "that is no text")
            try:
                data = body["text"].encode("utf-8")
            except UnicodeEncodeError as exc:
                raise _Refused(400, "that is no text") from exc
            if len(data) > files.LIMIT:
                raise _Refused(413, _TOO_BIG)
        else:
            data = _bytes(body, "base64")
        if not data:
            # an empty value is taken for a slip, not for a wish to wipe —
            # typed, or a file with nothing in it
            raise _Refused(400, "there is nothing to save: the value is empty")
        if body.get("new") is True:
            service.create_secret_bytes(scope, key, data)
        else:
            service.put_secret_bytes(scope, key, data)
        self._changed()
        return {}, 200

    def _delete(self, service: WorkspaceService, body: _Said, query: _Asked) -> _Told:
        scope, key = _text(body, "scope"), _text(body, "key")
        self._may_change(service, scope)
        if service.secret(scope, key) is None:
            raise _Refused(404, "no such secret")
        kept = service.delete_secret_kept(scope, key)
        self._changed()
        return {"kept": kept}, 200

    def _move(self, service: WorkspaceService, body: _Said, query: _Asked) -> _Told:
        scope, key = _text(body, "scope"), _text(body, "key")
        to_scope, to_key = _text(body, "to_scope"), _name(body, "to_key")
        keep = body.get("keep") is True
        self._may_change(service, to_scope)
        if not keep:
            self._may_change(service, scope)  # moving away is a change there too
        if service.secret(scope, key) is None:
            raise _Refused(404, "no such secret")
        # that the new place is free, and is not the old one, is the service's to
        # say: it asks the workspace, and one change at a time
        service.move_secret(scope, key, to_scope, to_key, keep=keep)
        self._changed()
        return {}, 200

    def _undo(self, service: WorkspaceService, body: _Said, query: _Asked) -> _Told:
        self._may_change(service)
        if service.taken is None:
            raise _Refused(409, "There is nothing to put back.")
        try:
            scope, key = service.put_back()
        finally:
            self._changed()
        return {"scope": scope, "key": key}, 200

    def _grant(self, service: WorkspaceService, body: _Said, query: _Asked) -> _Told:
        scope, principal = _text(body, "scope"), _name(body, "principal")
        permission = body.get("permission")
        self._may_change(service)
        if service.scope(scope) is None:
            raise _Refused(404, "no such scope")
        if permission not in ("READ", "WRITE", "MANAGE"):
            raise _Refused(400, "a grant is READ, WRITE or MANAGE")
        service.set_acl(scope, principal, permission)
        self._changed()
        return {}, 200

    def _revoke(self, service: WorkspaceService, body: _Said, query: _Asked) -> _Told:
        scope, principal = _text(body, "scope"), _text(body, "principal")
        self._may_change(service)
        if service.scope(scope) is None:
            raise _Refused(404, "no such scope")
        service.remove_acl(scope, principal)
        self._changed()
        return {}, 200

    def _create_scope(
        self, service: WorkspaceService, body: _Said, query: _Asked
    ) -> _Told:
        name = _name(body, "name")
        self._may_change(service)
        there = next((s.name for s in service.scopes if same_name(s.name, name)), None)
        if there is not None:
            raise _Refused(409, f"there is a scope “{there}” already")
        service.create_scope(name)
        service.refresh_scope(name)  # so that who made it is seen to have it
        self._changed()
        return {}, 200

    def _delete_scope(
        self, service: WorkspaceService, body: _Said, query: _Asked
    ) -> _Told:
        name = _text(body, "name")
        self._may_change(service)
        if service.scope(name) is None:
            raise _Refused(404, "no such scope")
        service.delete_scope(name)
        self._changed()
        return {}, 200

    def _body(self) -> dict[str, Any]:
        length = self.headers.get("Content-Length", "")
        if not length.isdigit():
            raise _Refused(411, "say how much is coming")
        if int(length) > BODY_LIMIT:
            raise _Refused(413, "too much")
        try:
            said = json.loads(self.rfile.read(int(length)) or b"{}")
        except (ValueError, UnicodeDecodeError, RecursionError) as exc:
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


def _name(body: dict[str, Any], name: str) -> str:
    """A name that is about to be made: said, not padded, and not endless."""
    value = _text(body, name)
    if value != value.strip() or len(value) > NAME_LIMIT:
        raise _Refused(400, f"that is no {name}")
    return value


def _bytes(body: dict[str, Any], name: str) -> bytes:
    """A file as the page sends it: base64, and no more than a secret may hold."""
    value = body.get(name)
    if not isinstance(value, str):
        raise _Refused(400, "send the file")
    if len(value) > files.LIMIT * 4 // 3 + 4:
        raise _Refused(413, _TOO_BIG)
    try:
        data = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise _Refused(400, "that is no file") from exc
    if len(data) > files.LIMIT:
        raise _Refused(413, _TOO_BIG)
    return data


#: What is answered under `/api/`, once the gate has let a request through and
#: there is a workspace. Everything that changes one goes through `_may_change`.
_ROUTES = {
    ("GET", "/api/scope"): Handler._scope,
    ("GET", "/api/keys"): Handler._keys,
    ("POST", "/api/value"): Handler._value,
    ("POST", "/api/forget"): Handler._forget,
    ("POST", "/api/refresh"): Handler._refresh,
    ("POST", "/api/secret/put"): Handler._put,
    ("POST", "/api/secret/delete"): Handler._delete,
    ("POST", "/api/secret/move"): Handler._move,
    ("POST", "/api/undo"): Handler._undo,
    ("POST", "/api/grant/put"): Handler._grant,
    ("POST", "/api/grant/delete"): Handler._revoke,
    ("POST", "/api/scope/create"): Handler._create_scope,
    ("POST", "/api/scope/delete"): Handler._delete_scope,
}

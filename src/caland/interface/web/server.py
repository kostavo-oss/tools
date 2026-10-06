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
import re
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

from ...application import (
    DotenvError,
    Loader,
    OnboardingService,
    WorkspaceService,
    files,
    format_dotenv,
    parse_dotenv,
)
from ...domain import (
    SOURCE_URL,
    AuthError,
    Exists,
    Settings,
    StoreError,
    Workspace,
    same_name,
)
from . import gate, views

#: The most a request may say: the largest value a secret may hold, as the page
#: sends a file (base64, which is a third longer), and room for the rest.
BODY_LIMIT = 256 * 1024

_TOO_BIG = "a secret holds 128 kB at most"

#: The longest a name may be. Databricks decides what else a name may be.
NAME_LIMIT = 128

#: After how many days a secret counts as stale: the choices there are.
STALE_AFTER = (30, 90, 180, 365)

#: The most secrets one import brings: what a scope holds.
#: https://docs.databricks.com/aws/en/security/secrets/
PAIRS_LIMIT = 1000

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
    """One run of caland's page: a workspace — or none yet, and the choice of one
    — and who may ask about it."""

    def __init__(
        self,
        loader: Loader | None = None,
        *,
        workspace: Workspace | None = None,
        onboarding: OnboardingService | None = None,
        read_only: bool = False,
        show_all: bool = False,
        version: str = "",
        clock: Callable[[], float] = time.monotonic,
        settings: Settings | None = None,
        keep: Callable[[Settings], None] = lambda settings: None,
    ) -> None:
        #: The workspace that is shown, being read in the background. None
        #: while the person has yet to say which.
        self.loader = loader
        self.workspace = workspace
        #: What there is to choose from, and how one is connected to.
        self.onboarding = onboarding
        #: Which workspace this is, counted from the first: so that what the page
        #: holds of one workspace is never taken for another's.
        self.turn = 0
        self.read_only = read_only
        #: What the person prefers — how things are shown, never a secret — and
        #: what keeps it for the next run.
        self.settings = settings or Settings(show_all_scopes=show_all)
        self.keep = keep
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

    def connect(self, workspace: Workspace, save_as: str = "") -> None:
        """Leave the workspace that is shown, if any, and start on another.
        Returns at once: connecting, and signing in, happen in the background.
        With `save_as`, the address is kept as a profile of that name once the
        sign-in has worked — the address and how to sign in, never a token."""
        onboarding = self.onboarding
        if onboarding is None:
            raise AuthError("There is nothing to choose a workspace from.")

        def connected() -> WorkspaceService:
            connection = onboarding.connect(workspace)
            if save_as and connection.host:
                onboarding.save_profile(save_as, connection.host)
            return connection.service

        loader = Loader(connected)
        with self._lock:
            left = self.loader
            self.turn += 1
            self.workspace, self.loader = workspace, loader
        if left is not None and left.service is not None:
            left.service.forget_values()  # nothing of the one that is left is kept
        loader.start()

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
        loader = page.loader
        service = loader.service if loader else None

        if (method, path) == ("GET", "/api/state"):
            return self._json(
                views.state(
                    loader.progress() if loader else None,
                    service,
                    workspace=page.workspace,
                    read_only=page.read_only,
                    settings=page.settings,
                    version=page.version,
                    turn=page.turn,
                )
            )
        if (method, path) == ("GET", "/api/workspaces"):
            return self._json(self._workspaces())
        if (method, path) == ("POST", "/api/connect"):
            return self._json(self._connect(body), status=202)
        if (method, path) == ("POST", "/api/describe"):
            # what a file is: asked before there is a workspace to put it in, too
            return self._json(files.describe(_bytes(body, "base64")).told())
        if (method, path) == ("POST", "/api/settings"):
            return self._json(self._prefer(body))
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

    def _loader(self) -> Loader:
        """The workspace that is shown. Asked for only where there is one."""
        loader = self.server.page.loader
        if loader is None:
            raise _Refused(409, "not connected yet")
        return loader

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
        self._loader().changed()
        return {}, 200

    def _refresh(self, service: WorkspaceService, body: _Said, query: _Asked) -> _Told:
        scope = body.get("scope")
        if scope is not None and not isinstance(scope, str):
            raise _Refused(400, "a scope is a name")
        self._loader().refresh(scope)
        return {}, 202

    # -- which workspace -------------------------------------------------
    def _workspaces(self) -> dict[str, Any]:
        """What there is to choose from, and where each was found."""
        onboarding = self.server.page.onboarding
        return views.workspaces(
            onboarding.available_workspaces() if onboarding else [],
            self.server.page.workspace,
        )

    def _connect(self, body: _Said) -> dict[str, Any]:
        """Go to another workspace: one that was found, by its name — or one at
        an address, signed in to through the browser. It changes no workspace;
        read-only does not mind."""
        page = self.server.page
        onboarding = page.onboarding
        if onboarding is None:
            raise _Refused(409, "there is nothing to choose a workspace from")
        if ("name" in body) == ("url" in body):
            raise _Refused(400, "say which workspace: its name, or its address")
        try:
            if "name" in body:
                page.connect(onboarding.choose(_text(body, "name")))
                return {}
            host = _address(body)
            save_as = body.get("save_as", "")
            if save_as:
                save_as = _profile(
                    save_as, [w.profile for w in onboarding.available_workspaces()]
                )
            page.connect(Workspace(host=host, source=SOURCE_URL), save_as)
        except AuthError as exc:
            raise _Refused(404, str(exc)) from exc
        return {}

    def _grants(self, service: WorkspaceService, body: _Said, query: _Asked) -> _Told:
        return views.grants(service), 200

    def _prefer(self, body: _Said) -> dict[str, Any]:
        """Keep a preference. It changes no workspace: read-only does not mind.
        All of what is asked is looked at before any of it is taken."""
        show_all, stale_after = body.get("show_all"), body.get("stale_after")
        if "show_all" in body and not isinstance(show_all, bool):
            raise _Refused(400, "show_all is yes or no")
        if "stale_after" in body and not (
            type(stale_after) is int and stale_after in STALE_AFTER
        ):
            raise _Refused(400, "stale_after is 30, 90, 180 or 365")
        settings = self.server.page.settings
        if isinstance(show_all, bool):
            settings.show_all_scopes = show_all
        if isinstance(stale_after, int):
            settings.audit_threshold = stale_after
        self.server.page.keep(settings)
        return {}

    # -- .env: a scope's secrets as lines of text -------------------------
    def _env_preview(
        self, service: WorkspaceService, body: _Said, query: _Asked
    ) -> _Told:
        """What an import would do, before it does it: the keys, and which of
        them are there already. No value is said back."""
        scope = _text(body, "scope")
        self._may_change(service, scope)
        pairs, empty = _pairs(body)
        return {
            "keys": list(pairs),
            "overwrite": service.taken_over(scope, list(pairs)),
            "empty": empty,
        }, 200

    def _env_import(self, service: WorkspaceService, body: _Said, query: _Asked) -> _Told:
        scope = _text(body, "scope")
        self._may_change(service, scope)
        pairs, empty = _pairs(body)
        try:
            done, stopped_at = service.import_secrets(scope, pairs)
        finally:
            self._changed()  # whatever went in is there: the page reads again
        return {
            "done": done,
            "total": len(pairs),
            "stopped_at": stopped_at,
            "error": service.import_error,
            "empty": empty,
        }, 200

    def _env_export(self, service: WorkspaceService, body: _Said, query: _Asked) -> _Told:
        """A scope's values as .env text, for the clipboard. Reads every value
        in it — the one request that does — and so it is a POST like a value."""
        scope = _text(body, "scope")
        if service.scope(scope) is None:
            raise _Refused(404, "no such scope")
        pairs, left_out = service.export_secrets(scope)
        return {"text": format_dotenv(pairs), "left_out": left_out}, 200

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
        self._loader().changed()

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


_PROFILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def _address(body: dict[str, Any]) -> str:
    """A workspace's address as it was typed: https, a host, and nothing more.
    A name alone is taken to be https."""
    typed = _text(body, "url").strip()
    if "://" not in typed:
        typed = "https://" + typed
    try:
        url = urlsplit(typed)
        host, port = url.hostname, url.port
    except ValueError as exc:
        raise _Refused(400, "that is no address") from exc
    if (
        url.scheme != "https"
        or not host
        or "." not in host
        or url.username is not None
        or url.path not in ("", "/")
        or url.query
        or url.fragment
        or len(typed) > 255
    ):
        raise _Refused(
            400, "a workspace's address is https, its host, and nothing after it"
        )
    return f"https://{host}" + (f":{port}" if port else "")


def _profile(name: object, there: list[str]) -> str:
    """A name a workspace's address can be kept under. Letters, digits, dots,
    dashes — it becomes a heading in ~/.databrickscfg, and nothing but a name
    may be written there. Not a name that is in use: a profile keeps its way of
    signing in, and must not be pointed at another address under it."""
    if not isinstance(name, str) or not _PROFILE.fullmatch(name):
        raise _Refused(400, "a profile's name is letters, digits, dots and dashes")
    if name.casefold() == "default" or any(same_name(name, other) for other in there):
        raise _Refused(409, f"there is a profile “{name}” already: give it another name")
    return name


def _pairs(body: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """A .env file as the page sends it, as KEY to value — and the keys that had
    no value, which are left out: an empty value is a slip, not a wish to wipe.

    A file that cannot be read without guessing is refused whole, before any of
    it is used: a quote that is never closed, a value that is no text, two keys
    that are one secret to Databricks."""
    data = _bytes(body, "base64")
    try:
        pairs = parse_dotenv(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise _Refused(400, "that is no text file") from exc
    except DotenvError as exc:
        raise _Refused(400, f"that file cannot be read: {exc}") from exc
    if len(pairs) > PAIRS_LIMIT:
        raise _Refused(413, f"that is {len(pairs)} entries: a scope holds {PAIRS_LIMIT}")
    seen: dict[str, str] = {}
    for key, value in pairs.items():
        if key.casefold() in seen:
            raise _Refused(
                400,
                f"{seen[key.casefold()]} and {key} are one secret to Databricks: "
                "the file has both",
            )
        seen[key.casefold()] = key
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise _Refused(
                400, f"the value of {key} is no text that can be stored"
            ) from exc
    empty = [key for key, value in pairs.items() if not value]
    return {key: value for key, value in pairs.items() if value}, empty


#: What is answered under `/api/`, once the gate has let a request through and
#: there is a workspace. Everything that changes one goes through `_may_change`.
_ROUTES = {
    ("GET", "/api/scope"): Handler._scope,
    ("GET", "/api/keys"): Handler._keys,
    ("GET", "/api/grants"): Handler._grants,
    ("POST", "/api/env/preview"): Handler._env_preview,
    ("POST", "/api/env/import"): Handler._env_import,
    ("POST", "/api/env/export"): Handler._env_export,
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

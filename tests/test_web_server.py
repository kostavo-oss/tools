"""The local server, asked over real HTTP — against the fake workspace."""

from __future__ import annotations

import http.client
import json
import socket
import threading

import pytest

from caland.application import Loader, WorkspaceService
from caland.domain import Workspace
from caland.interface.web import Page, Server, gate
from caland.interface.web.server import BODY_LIMIT, HEADERS
from fakes import seeded_store

SECRET = "value::prod/api-key"


class Served:
    """A running server, and a way to ask it as the page does — or does not."""

    def __init__(self, server: Server, store) -> None:
        self.server, self.page, self.store = server, server.page, store
        self.token: str | None = None

    def ask(self, method, path, body=None, *, headers=None, token=..., raw=None):
        sent = {"Host": f"127.0.0.1:{self.server.port}"}
        if token is ...:
            token = self.token
        if token:
            sent[gate.TOKEN_HEADER] = token
        # as the page does: it says which workspace it believes it is in
        sent[gate.WORKSPACE_HEADER] = str(self.server.page.turn)
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
        if method == "POST":
            sent["Content-Type"] = "application/json"
        sent.update(headers or {})
        sent = {name: value for name, value in sent.items() if value is not None}
        connection = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5)
        try:
            connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            if data is not None and "Content-Length" not in sent:
                sent["Content-Length"] = str(len(data))
            for name, value in sent.items():
                connection.putheader(name, value)
            connection.endheaders(data)
            answer = connection.getresponse()
            text = answer.read()
            return answer.status, dict(answer.getheaders()), text
        finally:
            connection.close()

    def json(self, method, path, body=None, **kwargs):
        status, _, text = self.ask(method, path, body, **kwargs)
        return status, json.loads(text)

    def enter(self) -> str:
        status, told = self.json(
            "POST", "/api/enter", {"key": self.page.new_key()}, token=None
        )
        assert status == 200
        self.token = told["token"]
        return self.token


@pytest.fixture
def served():
    store = seeded_store()
    loader = Loader(lambda: WorkspaceService(store, "test"))
    page = Page(
        loader,
        workspace=Workspace(profile="test", host="https://x.example"),
        version="9.9",
    )
    server = Server(page)
    loader.start().join(timeout=5)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        yield Served(server, store)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ── where it listens ─────────────────────────────────────────────────
def test_it_listens_on_this_machine_only(served):
    assert served.server.server_address[0] == "127.0.0.1"
    assert served.server.address == f"http://127.0.0.1:{served.server.port}/"


def test_it_cannot_be_reached_by_the_machines_other_address(served):
    """Skipped where the machine has no other address to try."""
    try:
        other = socket.gethostbyname(socket.gethostname())
    except OSError:
        pytest.skip("this machine's name has no address")
    if other.startswith("127."):
        pytest.skip("this machine's name is the loopback")
    with pytest.raises(OSError):
        socket.create_connection((other, served.server.port), timeout=0.5).close()


# ── getting in ───────────────────────────────────────────────────────
def test_the_key_gives_the_token_once(served):
    key = served.page.new_key()
    status, told = served.json("POST", "/api/enter", {"key": key}, token=None)
    assert (status, told) == (200, {"token": served.page.token})
    status, told = served.json("POST", "/api/enter", {"key": key}, token=None)
    assert status == 403 and "token" not in told


@pytest.mark.parametrize("key", ["", "wrong", None, 7, ["a"], {"a": 1}])
def test_a_wrong_key_gives_nothing_and_does_not_spend_the_right_one(served, key):
    right = served.page.new_key()
    status, told = served.json("POST", "/api/enter", {"key": key}, token=None)
    assert status == 403 and "token" not in told
    assert served.json("POST", "/api/enter", {"key": right}, token=None)[0] == 200


def test_there_is_no_key_until_one_is_made(served):
    assert served.json("POST", "/api/enter", {"key": ""}, token=None)[0] == 403
    assert served.page.enter(None) is None


def test_a_new_key_ends_the_one_before_it(served):
    old, new = served.page.new_key(), served.page.new_key()
    assert served.json("POST", "/api/enter", {"key": old}, token=None)[0] == 403
    assert served.json("POST", "/api/enter", {"key": new}, token=None)[0] == 200


def test_entering_is_told_to_who_holds_the_file_with_the_key(served):
    told = []
    served.page.entered = lambda: told.append("entered")
    served.enter()
    assert told == ["entered"]


def test_the_token_is_long_and_differs_from_run_to_run(served):
    other = Page(served.page.loader, workspace=served.page.workspace)
    assert len(served.page.token) >= 40 and served.page.token != other.token
    assert served.page.new_key() != served.page.new_key()


# ── without the token, nothing ───────────────────────────────────────
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/state", None),
        ("GET", "/api/keys", None),
        ("GET", "/api/scope?name=prod", None),
        ("POST", "/api/value", {"scope": "prod", "key": "api-key"}),
        ("POST", "/api/forget", {}),
        ("POST", "/api/refresh", {}),
    ],
)
def test_nothing_is_answered_without_the_token(served, method, path, body):
    for token in (None, "wrong", served.page.token[:-1]):
        status, _, text = served.ask(method, path, body, token=token)
        assert status == 401
        assert SECRET.encode() not in text and b"api-key" not in text
    assert served.store.reads() == 0


def test_a_site_whose_name_points_here_gets_nothing(served):
    served.enter()
    status, _, text = served.ask(
        "GET", "/api/keys", headers={"Host": f"evil.example:{served.server.port}"}
    )
    assert status == 403 and b"api-key" not in text


def test_another_site_gets_nothing_even_with_the_token(served):
    served.enter()
    status, headers, text = served.ask(
        "POST",
        "/api/value",
        {"scope": "prod", "key": "api-key"},
        headers={"Origin": "https://evil.example"},
    )
    assert status == 403 and SECRET.encode() not in text
    assert not any(name.lower().startswith("access-control") for name in headers)
    assert served.store.reads() == 0


def test_asking_for_permission_from_another_site_is_refused(served):
    status, headers, _ = served.ask(
        "OPTIONS",
        "/api/value",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-caland-token, content-type",
        },
    )
    assert status in (403, 405)
    assert not any(name.lower().startswith("access-control") for name in headers)


# ── what it tells ────────────────────────────────────────────────────
def test_state_says_who_and_what_and_how_far(served):
    served.enter()
    status, told = served.json("GET", "/api/state")
    assert status == 200
    assert told["phase"] == "ready" and (told["done"], told["total"]) == (2, 2)
    assert told["workspace"] == {"name": "test", "host": "x.example"}
    assert told["identity"] == {"user": "me@corp.com", "name": "Me"}
    assert told["caland"] == "9.9" and told["read_only"] is False
    assert told["scopes"] == [
        {"name": "kv", "keyvault": True, "access": "READ", "count": 1, "loaded": True},
        {
            "name": "prod",
            "keyvault": False,
            "access": "MANAGE",
            "count": 2,
            "loaded": True,
        },
    ]


def test_a_scope_says_its_secrets_and_its_grants(served):
    served.enter()
    status, told = served.json("GET", "/api/scope?name=prod")
    assert status == 200
    assert told["secrets"] == [
        ["api-key", 1_718_000_000_000],
        ["db-password", 1_718_500_000_000],
    ]
    assert told["grants"] == [["me@corp.com", "MANAGE"], ["users", "READ"]]
    assert (told["access"], told["keyvault"]) == ("MANAGE", False)


def test_keys_says_every_name_and_no_value(served):
    served.enter()
    status, _, text = served.ask("GET", "/api/keys")
    assert status == 200
    assert json.loads(text)["scopes"]["kv"] == [["tenant-id", 1_717_000_000_000]]
    assert b"value::" not in text


def test_no_get_ever_reads_a_value(served):
    served.enter()
    for path in (
        "/api/state",
        "/api/keys",
        "/api/scope?name=prod",
        "/api/value",
        "/api/value?scope=prod&key=api-key",
    ):
        _, _, text = served.ask("GET", path)
        assert SECRET.encode() not in text
    assert served.store.reads() == 0


def test_a_value_is_the_answer_to_a_post_with_the_token(served):
    served.enter()
    status, told = served.json("POST", "/api/value", {"scope": "prod", "key": "api-key"})
    assert (status, told) == (200, {"value": SECRET})
    assert served.store.reads() == 1


def test_a_value_is_read_from_the_workspace_once(served):
    served.enter()
    for _ in range(3):
        served.json("POST", "/api/value", {"scope": "prod", "key": "api-key"})
    assert served.store.reads() == 1


def test_forgetting_drops_every_value_held(served):
    served.enter()
    served.json("POST", "/api/value", {"scope": "prod", "key": "api-key"})
    assert served.json("POST", "/api/forget", {})[0] == 200
    assert served.page.loader.service.cache.raw == {}


@pytest.mark.parametrize(
    "body",
    [{"scope": "prod", "key": "nope"}, {"scope": "nope", "key": "api-key"}],
)
def test_a_secret_that_is_not_there_is_not_asked_for(served, body):
    served.enter()
    assert served.json("POST", "/api/value", body)[0] == 404
    assert served.store.reads() == 0


@pytest.mark.parametrize(
    "body", [{}, {"scope": "prod"}, {"scope": 1, "key": 2}, {"scope": "", "key": ""}]
)
def test_a_value_asked_for_badly_is_refused(served, body):
    served.enter()
    assert served.json("POST", "/api/value", body)[0] == 400


def test_a_value_the_workspace_refuses_says_so_shortly(served):
    served.enter()
    served.store._fail_on.add("get_secret_bytes")
    status, told = served.json("POST", "/api/value", {"scope": "prod", "key": "api-key"})
    assert status == 502 and told == {"error": "boom:get_secret_bytes"}


def test_a_scope_that_is_not_there(served):
    served.enter()
    assert served.json("GET", "/api/scope?name=nope")[0] == 404
    assert served.json("GET", "/api/scope")[0] == 400
    assert served.json("GET", "/api/scope?name=a&name=b")[0] == 400


def test_reading_again_is_started_and_answered_at_once(served):
    served.enter()
    before = served.store.count("list_secrets")
    assert served.json("POST", "/api/refresh", {"scope": "prod"})[0] == 202
    assert served.json("POST", "/api/refresh", {"scope": 7})[0] == 400
    for _ in range(200):
        if served.store.count("list_secrets") > before:
            break
        threading.Event().wait(0.01)
    assert served.store.count("list_secrets") == before + 1


# ── what it sends ────────────────────────────────────────────────────
@pytest.mark.parametrize("path", ["/", "/page.css", "/page.js", "/api/state", "/nope"])
def test_every_answer_carries_the_same_care(served, path):
    served.enter()
    _, headers, _ = served.ask("GET", path)
    for name, value in HEADERS.items():
        assert headers[name] == value
    assert not any(name.lower() == "set-cookie" for name in headers)
    assert headers.get("Server", "").strip() == "caland"


def test_the_policy_lets_the_page_load_only_what_is_calands_own():
    policy = HEADERS["Content-Security-Policy"]
    assert "default-src 'none'" in policy and "frame-ancestors 'none'" in policy
    assert "script-src 'self'" in policy and "unsafe" not in policy and "*" not in policy


def test_the_page_is_three_files_and_holds_no_secret_and_no_token(served):
    served.enter()
    served.json("POST", "/api/value", {"scope": "prod", "key": "api-key"})
    for path, kind in [
        ("/", "text/html"),
        ("/page.css", "text/css"),
        ("/page.js", "text/javascript"),
    ]:
        status, headers, text = served.ask("GET", path, token=None)
        assert status == 200 and headers["Content-Type"].startswith(kind)
        assert served.page.token.encode() not in text and SECRET.encode() not in text
        assert b"api-key" not in text


def test_the_page_has_no_script_or_style_written_into_it(served):
    _, _, text = served.ask("GET", "/", token=None)
    page = text.decode()
    assert "<style" not in page and " style=" not in page and "onclick" not in page
    assert page.count("<script") == 1 and '<script src="/page.js" defer></script>' in page
    assert (
        "http://" not in page
        and "https://" not in page
        and "//" not in page.replace("<!--", "")
    )


def test_the_script_writes_text_never_markup():
    from importlib import resources

    script = (
        resources.files("caland.interface.web")
        .joinpath("static", "page.js")
        .read_text("utf-8")
    )
    for word in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
        "localStorage",
        "document.cookie",
    ):
        assert word not in script, word


@pytest.mark.parametrize(
    "path",
    [
        "/page.html",
        "/static/page.js",
        "/../pyproject.toml",
        "/%2e%2e/pyproject.toml",
        "/page.js/..",
        "/favicon.ico",
    ],
)
def test_no_other_file_is_served(served, path):
    status, _, text = served.ask("GET", path, token=None)
    assert status == 404 and b"caland" not in text.replace(b'"error"', b"")


# ── what it will not take ────────────────────────────────────────────
def test_too_much_is_refused_unread(served):
    served.enter()
    status, _, _ = served.ask(
        "POST", "/api/value", raw=b"", headers={"Content-Length": str(BODY_LIMIT + 1)}
    )
    assert status == 413


@pytest.mark.parametrize("raw", [b"not json", b"[1, 2]", b'"text"', b"\xff\xfe", b"{"])
def test_what_is_not_a_json_object_is_refused(served, raw):
    served.enter()
    assert served.ask("POST", "/api/value", raw=raw)[0] == 400


def test_a_post_that_does_not_say_how_long_it_is_is_refused(served):
    served.enter()
    assert served.ask("POST", "/api/forget", headers={"Content-Length": None})[0] == 411
    assert (
        served.ask("POST", "/api/forget", raw=b"{}", headers={"Content-Length": "-1"})[0]
        == 411
    )


def test_what_came_with_a_refused_request_is_not_taken_for_the_next(served):
    """On a connection that is kept open, the body of a refused request would be
    read as a request of its own — and that one could be made to look allowed."""
    served.enter()
    smuggled = (
        f"GET /api/keys HTTP/1.1\r\nHost: 127.0.0.1:{served.server.port}\r\n"
        f"{gate.TOKEN_HEADER}: {served.page.token}\r\n\r\n"
    ).encode()
    request = (
        f"POST /api/value HTTP/1.1\r\nHost: 127.0.0.1:{served.server.port}\r\n"
        f"Origin: https://evil.example\r\nContent-Type: text/plain\r\n"
        f"Content-Length: {len(smuggled)}\r\n\r\n"
    ).encode() + smuggled
    with socket.create_connection(("127.0.0.1", served.server.port), timeout=5) as raw:
        raw.sendall(request)
        answer = b""
        while chunk := raw.recv(65536):
            answer += chunk
    assert answer.count(b"HTTP/1.1 ") == 1 and answer.startswith(b"HTTP/1.1 403")
    assert b"api-key" not in answer


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [("TRACE", "/api/value", 405), ("BREW", "/", 501), ("GET", "/" + "a" * 70_000, 414)],
)
def test_what_the_server_refuses_by_itself_is_refused_like_everything_else(
    served, method, path, status
):
    """`http.server` answers some requests before the gate is asked — with a page
    of its own, and none of the headers. Not here."""
    answered, headers, text = served.ask(method, path, headers={"Host": "evil.example"})
    assert answered in (status, 403)
    for name, value in HEADERS.items():
        assert headers[name] == value
    assert headers["Content-Type"] == "application/json" and json.loads(text)["error"]
    assert b"<" not in text and method.encode() not in text


def test_a_request_that_cannot_be_read_is_refused_the_same_way(served):
    with socket.create_connection(("127.0.0.1", served.server.port), timeout=5) as raw:
        raw.sendall(b"NOT A REQUEST AT ALL\r\n\r\n")
        answer = b""
        while chunk := raw.recv(65536):
            answer += chunk
    assert answer.startswith(b"HTTP/1.1 400") or answer.startswith(b"HTTP/1.0 400")
    assert b"Content-Security-Policy" in answer and b"<html" not in answer.lower()
    assert b"NOT A REQUEST" not in answer


def test_a_connection_that_breaks_prints_nothing(served, capfd):
    import struct

    for _ in range(5):
        raw = socket.create_connection(("127.0.0.1", served.server.port), timeout=5)
        raw.sendall(b"POST /api/value HTTP/1.1\r\nHost: x\r\nContent-Length: 50\r\n\r\n{")
        # closed the hard way: the server finds the connection reset under it
        raw.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        raw.close()
    served.enter()
    assert served.json("GET", "/api/state")[0] == 200
    printed = capfd.readouterr()
    assert printed.out == "" and printed.err == ""


def test_connections_left_hanging_do_not_use_the_server_up(served):
    from caland.interface.web.server import CONNECTIONS

    hanging = [
        socket.create_connection(("127.0.0.1", served.server.port), timeout=5)
        for _ in range(CONNECTIONS + 20)
    ]
    try:
        for _ in range(100):  # until the server has taken all it has room for
            if not served.server._open.acquire(blocking=False):
                break
            served.server._open.release()
            threading.Event().wait(0.01)
        else:
            pytest.fail("the server never filled up")
        # one more than there is room for is closed at once, not kept
        extra = socket.create_connection(("127.0.0.1", served.server.port), timeout=5)
        extra.settimeout(2)
        try:
            assert extra.recv(1) == b""
        except ConnectionError:
            pass
        finally:
            extra.close()
    finally:
        for raw in hanging:
            raw.close()
    for _ in range(200):  # and when they let go, it answers again
        try:
            served.enter()
            break
        except (OSError, AssertionError, http.client.HTTPException):
            threading.Event().wait(0.02)
    assert served.json("GET", "/api/state")[0] == 200


def test_a_failure_inside_says_nothing_of_what_failed(served):
    served.enter()

    def broken(*args, **kwargs):
        raise RuntimeError("the secret is hunter2")

    served.page.loader.service.forget_values = broken
    status, _, text = served.ask("POST", "/api/forget", {})
    assert status == 500 and b"hunter2" not in text and b"Traceback" not in text


def test_nothing_a_request_says_is_printed(served, capfd):
    served.enter()
    served.json("POST", "/api/value", {"scope": "prod", "key": "api-key"})
    served.ask("GET", "/api/scope?name=prod")
    printed = capfd.readouterr()
    assert printed.out == "" and printed.err == ""


def test_before_the_workspace_is_there_the_state_says_so():
    hold = threading.Event()

    def connect():
        hold.wait(5)
        return WorkspaceService(seeded_store(), "test")

    loader = Loader(connect)
    server = Server(Page(loader, workspace=Workspace(profile="test")))
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        loader.start()
        served = Served(server, None)
        served.enter()
        status, told = served.json("GET", "/api/state")
        assert status == 200 and told["phase"] == "connecting" and told["scopes"] == []
        assert told["identity"] is None
        assert served.json("GET", "/api/keys")[0] == 409
    finally:
        hold.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_idle_counts_from_the_last_thing_asked():
    now = [100.0]
    page = Page(
        Loader(lambda: WorkspaceService(seeded_store(), "t")),
        workspace=Workspace(),
        clock=lambda: now[0],
    )
    now[0] = 160.0
    assert page.idle() == 60.0
    page.touch()
    assert page.idle() == 0.0

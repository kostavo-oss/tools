"""The gate: which requests the local server answers (GATE-2 to GATE-7, GATE-15)."""

from __future__ import annotations

import pytest

from caland.interface.web import gate

PORT = 5123
TOKEN = "the-session-token"
HERE = f"127.0.0.1:{PORT}"


def ask(method="GET", path="/api/state", **headers):
    """A request as caland's own page makes it, with what is given changed.
    A header given as None is left out."""
    sent = {
        "Host": HERE,
        "Origin": f"http://{HERE}",
        "Sec-Fetch-Site": "same-origin",
        gate.TOKEN_HEADER: TOKEN,
    }
    if method == "POST":
        sent["Content-Type"] = "application/json"
    for name, value in headers.items():
        sent[name.replace("_", "-")] = value
    sent = {name: value for name, value in sent.items() if value is not None}
    return gate.check(method, path, sent.get, port=PORT, token=TOKEN)


def test_its_own_page_is_answered():
    """GATE-2."""
    assert ask() is None
    assert ask("POST", "/api/value") is None


def test_localhost_is_this_server_too():
    """GATE-2."""
    assert ask(Host=f"localhost:{PORT}", Origin=f"http://localhost:{PORT}") is None


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        f"evil.example:{PORT}",
        "127.0.0.1",
        "127.0.0.1:1",
        f"127.0.0.1.evil.example:{PORT}",
        "",
    ],
)
def test_a_name_that_was_pointed_at_this_machine_is_refused(host):
    """DNS rebinding: the browser thinks it talks to the site, and says so."""
    refusal = ask(Host=host)
    assert refusal and refusal.status == 403


def test_a_request_with_no_host_is_refused():
    assert ask(Host=None).status == 403


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        "null",
        f"https://{HERE}",
        "http://127.0.0.1:1",
        f"http://{HERE}.evil.example",
    ],
)
def test_another_site_is_refused_even_with_the_token(origin):
    """GATE-3."""
    refusal = ask("POST", "/api/value", Origin=origin)
    assert refusal and refusal.status == 403


@pytest.mark.parametrize("site", ["cross-site", "same-site", "none"])
def test_the_api_is_only_for_the_page_itself(site):
    """GATE-3.

    `same-site` is another port of this machine; `none` is an address typed in.
    """
    assert ask(Sec_Fetch_Site=site).status == 403


def test_something_that_is_no_browser_is_held_to_the_token():
    assert ask(Origin=None, Sec_Fetch_Site=None) is None
    assert ask(Origin=None, Sec_Fetch_Site=None, X_Caland_Token=None).status == 401


@pytest.mark.parametrize("token", [None, "", "wrong", TOKEN + "x", TOKEN[:-1]])
def test_without_the_token_nothing_under_api_is_answered(token):
    """GATE-4."""
    for method, path in [
        ("GET", "/api/state"),
        ("GET", "/api/keys"),
        ("POST", "/api/value"),
    ]:
        assert ask(method, path, X_Caland_Token=token).status == 401


def test_a_token_in_the_address_is_not_a_token():
    """GATE-4."""
    assert ask(path=f"/api/state?token={TOKEN}", X_Caland_Token=None).status in (401, 404)


def test_the_page_itself_needs_no_token_and_holds_nothing():
    """GATE-6."""
    for path in gate.STATIC:
        assert (
            ask(path=path, X_Caland_Token=None, Origin=None, Sec_Fetch_Site="none")
            is None
        )
        # opened from the file that carries the key, the browser calls it cross-site
        assert (
            ask(path=path, X_Caland_Token=None, Sec_Fetch_Site="cross-site", Origin=None)
            is None
        )


def test_the_page_is_only_read():
    """GATE-6."""
    assert ask("POST", "/").status == 405


def test_entering_needs_the_key_not_the_token():
    """GATE-7."""
    assert ask("POST", gate.ENTER, X_Caland_Token=None) is None
    assert ask("GET", gate.ENTER, X_Caland_Token=None).status == 405


def test_entering_from_another_site_is_refused():
    """GATE-7."""
    assert (
        ask("POST", gate.ENTER, X_Caland_Token=None, Origin="https://evil.example").status
        == 403
    )
    assert (
        ask("POST", gate.ENTER, X_Caland_Token=None, Sec_Fetch_Site="cross-site").status
        == 403
    )


@pytest.mark.parametrize(
    "kind",
    [None, "text/plain", "application/x-www-form-urlencoded", "multipart/form-data"],
)
def test_what_a_form_on_another_site_can_send_is_refused(kind):
    """GATE-5. Those three need no permission to send across sites; JSON does."""
    assert ask("POST", "/api/value", Content_Type=kind).status == 415


def test_json_with_a_charset_is_json():
    assert (
        ask("POST", "/api/value", Content_Type="application/json; charset=utf-8") is None
    )


@pytest.mark.parametrize(
    "method", ["PUT", "DELETE", "PATCH", "OPTIONS", "HEAD", "TRACE", "CONNECT"]
)
def test_nothing_but_get_and_post(method):
    """GATE-5.

    OPTIONS above all: it is how another site asks for permission, and it gets none.
    """
    assert ask(method).status == 405


@pytest.mark.parametrize(
    "path",
    ["/api", "/page.js.map", "/../etc/passwd", "/static/page.js", "//api/state", ""],
)
def test_nothing_else_is_here(path):
    assert ask(path=path).status == 404


def test_the_pages_own_look_while_it_waits_is_a_read_of_the_state_and_nothing_else():
    assert ask(X_Caland_Waiting="1") is None
    assert gate.waits("GET", "/api/state", {gate.WAITING_HEADER: "1"}.get)
    assert not gate.waits("GET", "/api/state", {}.get)  # not said: it was asked


@pytest.mark.parametrize(
    "method, path",
    [
        ("POST", "/api/state"),
        ("GET", "/api/keys"),
        ("GET", "/api/workspaces"),
        ("POST", "/api/value"),
        ("POST", "/api/put"),
        ("POST", "/api/connect"),
        ("POST", "/api/enter"),
    ],
)
def test_anything_else_that_says_it_only_waits_is_refused(method, path):
    """GATE-15. With the token, from caland's own page, and with any value."""
    for said in ("1", "", "0"):
        refusal = ask(method, path, X_Caland_Waiting=said)
        assert refusal and refusal.status == 400
        assert not gate.waits(method, path, {gate.WAITING_HEADER: said}.get)


def test_a_look_that_waits_needs_the_token_like_any_other():
    assert ask(X_Caland_Waiting="1", X_Caland_Token=None).status == 401
    assert ask(X_Caland_Waiting="1", Origin="http://evil.example").status == 403


def test_secrets_are_compared_whole():
    assert gate.same("abc", "abc")
    assert not gate.same("abc", "abd")
    assert not gate.same("", "abc")
    assert not gate.same("ábc", "abc")

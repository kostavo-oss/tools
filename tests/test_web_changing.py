"""The local server, changing a workspace — over real HTTP, against the fake."""

from __future__ import annotations

import base64
import threading

import pytest

from caland.application import Loader, WorkspaceService
from caland.application.files import LIMIT
from caland.domain import Workspace
from caland.interface.web import Page, Server
from fakes import seeded_store
from test_web_server import Served

BUNDLE = bytes(range(256)) * 2
CHANGES = [
    ("/api/secret/put", {"scope": "prod", "key": "new", "text": "x"}),
    ("/api/secret/delete", {"scope": "prod", "key": "api-key"}),
    (
        "/api/secret/move",
        {"scope": "prod", "key": "api-key", "to_scope": "prod", "to_key": "b"},
    ),
    ("/api/undo", {}),
    ("/api/grant/put", {"scope": "prod", "principal": "a@b.c", "permission": "READ"}),
    ("/api/grant/delete", {"scope": "prod", "principal": "users"}),
    ("/api/scope/create", {"name": "new-scope"}),
    ("/api/scope/delete", {"name": "prod"}),
]
WRITES = (
    "put_secret",
    "put_secret_bytes",
    "delete_secret",
    "put_acl",
    "delete_acl",
    "create_scope",
    "delete_scope",
)


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def start(read_only: bool = False):
    store = seeded_store()
    loader = Loader(lambda: WorkspaceService(store, "test"))
    page = Page(loader, workspace=Workspace(profile="test"), read_only=read_only)
    server = Server(page)
    loader.start().join(timeout=5)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    return Served(server, store), thread


@pytest.fixture
def served():
    made, thread = start()
    made.enter()
    try:
        yield made
    finally:
        made.server.shutdown()
        made.server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def read_only():
    made, thread = start(read_only=True)
    made.enter()
    try:
        yield made
    finally:
        made.server.shutdown()
        made.server.server_close()
        thread.join(timeout=5)


def wrote(served) -> list[str]:
    return [call[0] for call in served.store.calls if call[0] in WRITES]


def post(served, path, body):
    return served.json("POST", path, body)


# ── nothing changes that may not ─────────────────────────────────────
@pytest.mark.parametrize(("path", "body"), CHANGES)
def test_read_only_is_the_servers_to_hold(read_only, path, body):
    status, told = post(read_only, path, body)
    assert status == 403 and "read-only" in told["error"]
    assert wrote(read_only) == []


def test_read_only_still_reads(read_only):
    assert post(read_only, "/api/value", {"scope": "prod", "key": "api-key"})[0] == 200
    assert read_only.json("GET", "/api/state")[1]["read_only"] is True
    assert post(read_only, "/api/describe", {"base64": b64(b"x")})[0] == 200


@pytest.mark.parametrize(("path", "body"), CHANGES)
def test_no_change_without_the_token_or_from_another_site(served, path, body):
    assert served.ask("POST", path, body, token="wrong")[0] == 401
    assert (
        served.ask("POST", path, body, headers={"Origin": "https://evil.example"})[0]
        == 403
    )
    assert (
        served.ask("POST", path, body, headers={"Content-Type": "text/plain"})[0] == 415
    )
    assert wrote(served) == []


@pytest.mark.parametrize(("path", "body"), CHANGES)
def test_no_change_by_a_get(served, path, body):
    assert served.ask("GET", path)[0] == 404
    assert wrote(served) == []


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/secret/put", {"scope": "kv", "key": "new", "text": "x"}),
        ("/api/secret/delete", {"scope": "kv", "key": "tenant-id"}),
        (
            "/api/secret/move",
            {"scope": "kv", "key": "tenant-id", "to_scope": "kv", "to_key": "b"},
        ),
        (
            "/api/secret/move",
            {"scope": "prod", "key": "api-key", "to_scope": "kv", "to_key": "b"},
        ),
        (
            "/api/secret/move",
            {"scope": "kv", "key": "tenant-id", "to_scope": "prod", "to_key": "b"},
        ),
    ],
)
def test_a_key_vault_scopes_secrets_are_azures(served, path, body):
    status, told = post(served, path, body)
    assert status == 409 and "Azure Key Vault" in told["error"]
    assert wrote(served) == []


def test_a_secret_can_be_copied_out_of_a_key_vault_scope(served):
    body = {
        "scope": "kv",
        "key": "tenant-id",
        "to_scope": "prod",
        "to_key": "tenant",
        "keep": True,
    }
    assert post(served, "/api/secret/move", body)[0] == 200
    assert wrote(served) == ["put_secret_bytes"]


# ── a secret ─────────────────────────────────────────────────────────
def test_text_is_stored_as_it_was_typed(served):
    assert (
        post(
            served,
            "/api/secret/put",
            {"scope": "prod", "key": "new", "text": "pä55 wörd"},
        )[0]
        == 200
    )
    assert served.store._values[("prod", "new")] == "pä55 wörd".encode()
    assert ["new", None] in served.json("GET", "/api/scope?name=prod")[1]["secrets"]


def test_a_file_is_stored_byte_for_byte_and_comes_back_the_same(served):
    assert (
        post(
            served,
            "/api/secret/put",
            {"scope": "prod", "key": "bundle", "base64": b64(BUNDLE)},
        )[0]
        == 200
    )
    assert served.store._values[("prod", "bundle")] == BUNDLE
    served.json("POST", "/api/forget", {})
    status, told = post(served, "/api/value", {"scope": "prod", "key": "bundle"})
    assert status == 200 and told == {
        "binary": True,
        "size": len(BUNDLE),
        "base64": b64(BUNDLE),
    }


def test_text_comes_back_as_text(served):
    assert post(served, "/api/value", {"scope": "prod", "key": "api-key"})[1] == {
        "value": "value::prod/api-key"
    }


@pytest.mark.parametrize(
    "body",
    [
        {"scope": "prod", "key": "k"},
        {"scope": "prod", "key": "k", "text": "a", "base64": "YQ=="},
        {"scope": "prod", "key": "k", "text": ""},
        {"scope": "prod", "key": "k", "text": 7},
        {"scope": "prod", "key": "k", "base64": "not base64!"},
        {"scope": "prod", "key": "k", "base64": 7},
        {"scope": "prod", "key": "", "text": "x"},
        {"scope": "prod", "key": " padded ", "text": "x"},
        {"scope": "prod", "key": "k" * 129, "text": "x"},
        {"scope": "", "key": "k", "text": "x"},
    ],
)
def test_a_secret_said_badly_is_not_saved(served, body):
    assert post(served, "/api/secret/put", body)[0] == 400
    assert wrote(served) == []


def test_an_empty_value_is_a_slip_not_a_wish_to_wipe(served):
    status, told = post(
        served, "/api/secret/put", {"scope": "prod", "key": "api-key", "text": ""}
    )
    assert status == 400 and "empty" in told["error"]
    assert wrote(served) == []


def test_a_scope_that_is_not_there_is_not_written_to(served):
    assert (
        post(served, "/api/secret/put", {"scope": "nope", "key": "k", "text": "x"})[0]
        == 404
    )


def test_a_new_secret_does_not_overwrite_one_that_is_there(served):
    body = {"scope": "prod", "key": "api-key", "text": "oops", "new": True}
    status, told = post(served, "/api/secret/put", body)
    assert status == 409 and "already" in told["error"] and wrote(served) == []
    assert post(served, "/api/secret/put", {**body, "new": False})[0] == 200


def test_a_value_may_be_as_large_as_a_secret_holds_and_no_larger(served):
    fits = {"scope": "prod", "key": "big", "base64": b64(b"x" * LIMIT)}
    assert post(served, "/api/secret/put", fits)[0] == 200
    over = {"scope": "prod", "key": "bigger", "base64": b64(b"x" * (LIMIT + 1))}
    status, told = post(served, "/api/secret/put", over)
    assert status == 413 and "128 kB" in told["error"]
    text = {"scope": "prod", "key": "bigger", "text": "é" * (LIMIT // 2 + 1)}
    assert post(served, "/api/secret/put", text)[0] == 413
    assert ("prod", "bigger") not in served.store._values


def test_what_the_workspace_refuses_is_said_shortly(served):
    served.store._fail_on.add("put_secret_bytes")
    status, told = post(
        served, "/api/secret/put", {"scope": "prod", "key": "k", "text": "x"}
    )
    assert (status, told) == (502, {"error": "boom:put_secret_bytes"})


# ── deleting, and taking it back ─────────────────────────────────────
def test_deleting_keeps_what_it_held_and_undo_puts_it_back(served):
    assert post(served, "/api/secret/delete", {"scope": "prod", "key": "api-key"}) == (
        200,
        {"kept": True},
    )
    state = served.json("GET", "/api/state")[1]
    assert state["taken"] == {"scope": "prod", "key": "api-key"}
    assert b"value::" not in served.ask("GET", "/api/state")[2]
    assert post(served, "/api/undo", {}) == (200, {"scope": "prod", "key": "api-key"})
    assert served.store._values[("prod", "api-key")] == b"value::prod/api-key"
    assert served.json("GET", "/api/state")[1]["taken"] is None


def test_undo_with_nothing_to_put_back(served):
    status, told = post(served, "/api/undo", {})
    assert status == 409 and wrote(served) == []


def test_deleting_what_is_not_there(served):
    assert post(served, "/api/secret/delete", {"scope": "prod", "key": "nope"})[0] == 404
    assert (
        post(served, "/api/secret/delete", {"scope": "nope", "key": "api-key"})[0] == 404
    )


def test_forgetting_ends_the_chance_to_put_it_back(served):
    post(served, "/api/secret/delete", {"scope": "prod", "key": "api-key"})
    post(served, "/api/forget", {})
    assert served.json("GET", "/api/state")[1]["taken"] is None
    assert post(served, "/api/undo", {})[0] == 409


# ── moving ───────────────────────────────────────────────────────────
def test_a_move_a_rename_and_a_copy(served):
    move = {"scope": "prod", "key": "api-key", "to_scope": "prod", "to_key": "renamed"}
    assert post(served, "/api/secret/move", move)[0] == 200
    keys = [row[0] for row in served.json("GET", "/api/scope?name=prod")[1]["secrets"]]
    assert "renamed" in keys and "api-key" not in keys
    assert served.json("GET", "/api/state")[1]["taken"] == {
        "scope": "prod",
        "key": "api-key",
    }
    copy = {
        "scope": "prod",
        "key": "renamed",
        "to_scope": "prod",
        "to_key": "copy",
        "keep": True,
    }
    assert post(served, "/api/secret/move", copy)[0] == 200
    keys = [row[0] for row in served.json("GET", "/api/scope?name=prod")[1]["secrets"]]
    assert {"renamed", "copy"} <= set(keys)


@pytest.mark.parametrize(
    ("change", "status"),
    [
        ({"to_key": "api-key"}, 400),  # where it is
        ({"to_key": "db-password"}, 409),  # something is there
        ({"key": "nope"}, 404),
        ({"to_scope": "nope"}, 404),
        ({"to_key": ""}, 400),
        ({"to_key": " x "}, 400),
    ],
)
def test_a_move_that_makes_no_sense_moves_nothing(served, change, status):
    body = {
        "scope": "prod",
        "key": "api-key",
        "to_scope": "prod",
        "to_key": "new",
        **change,
    }
    assert post(served, "/api/secret/move", body)[0] == status
    assert wrote(served) == []


# ── grants and scopes ────────────────────────────────────────────────
def test_a_grant_is_given_changed_and_taken(served):
    give = {"scope": "prod", "principal": "data-engineers", "permission": "WRITE"}
    assert post(served, "/api/grant/put", give)[0] == 200
    assert ["data-engineers", "WRITE"] in served.json("GET", "/api/scope?name=prod")[1][
        "grants"
    ]
    assert post(served, "/api/grant/put", {**give, "permission": "READ"})[0] == 200
    assert ["data-engineers", "READ"] in served.json("GET", "/api/scope?name=prod")[1][
        "grants"
    ]
    assert (
        post(
            served, "/api/grant/delete", {"scope": "prod", "principal": "data-engineers"}
        )[0]
        == 200
    )
    grants = served.json("GET", "/api/scope?name=prod")[1]["grants"]
    assert all(who != "data-engineers" for who, _ in grants)


def test_grants_on_a_key_vault_scope_are_changed_like_any(served):
    give = {"scope": "kv", "principal": "analysts", "permission": "READ"}
    assert post(served, "/api/grant/put", give)[0] == 200


@pytest.mark.parametrize(
    "body",
    [
        {"scope": "prod", "principal": "x", "permission": "OWN"},
        {"scope": "prod", "principal": "x", "permission": None},
        {"scope": "prod", "principal": "", "permission": "READ"},
        {"scope": "prod", "principal": " x", "permission": "READ"},
    ],
)
def test_a_grant_said_badly_is_not_given(served, body):
    assert post(served, "/api/grant/put", body)[0] == 400
    assert wrote(served) == []


def test_a_grant_on_a_scope_that_is_not_there(served):
    assert (
        post(
            served,
            "/api/grant/put",
            {"scope": "no", "principal": "x", "permission": "READ"},
        )[0]
        == 404
    )
    assert post(served, "/api/grant/delete", {"scope": "no", "principal": "x"})[0] == 404


def test_a_scope_is_made_and_seen_at_once(served):
    before = served.json("GET", "/api/state")[1]["version"]
    assert post(served, "/api/scope/create", {"name": "fresh"})[0] == 200
    state = served.json("GET", "/api/state")[1]
    assert state["version"] > before
    assert {
        "name": "fresh",
        "keyvault": False,
        "access": "READ",
        "count": 0,
        "loaded": True,
    } in (state["scopes"])


def test_a_scope_that_is_there_is_not_made_again(served):
    assert post(served, "/api/scope/create", {"name": "prod"})[0] == 409
    assert post(served, "/api/scope/create", {"name": ""})[0] == 400
    assert wrote(served) == []


def test_a_scope_is_deleted_with_what_was_in_it(served):
    assert post(served, "/api/scope/delete", {"name": "prod"})[0] == 200
    assert [scope["name"] for scope in served.json("GET", "/api/state")[1]["scopes"]] == [
        "kv"
    ]
    assert post(served, "/api/scope/delete", {"name": "prod"})[0] == 404


def test_every_change_moves_the_version(served):
    seen = [served.json("GET", "/api/state")[1]["version"]]
    changes = [
        CHANGES[0],
        ("/api/secret/delete", {"scope": "prod", "key": "db-password"}),
        CHANGES[2],
        CHANGES[4],
    ]
    for path, body in changes:
        assert post(served, path, body)[0] == 200
        seen.append(served.json("GET", "/api/state")[1]["version"])
    assert seen == sorted(set(seen))


# ── what a file is ───────────────────────────────────────────────────
def test_a_file_is_described_and_kept_nowhere(served):
    status, told = post(served, "/api/describe", {"base64": b64(b"KEY=value\n")})
    assert status == 200 and told["kind"] == "text, 1 line" and told["size"] == 10
    assert wrote(served) == [] and served.page.loader.service.cache.raw == {}


def test_describing_takes_the_token_like_everything_else(served):
    assert (
        served.ask("POST", "/api/describe", {"base64": "YQ=="}, token="wrong")[0] == 401
    )


@pytest.mark.parametrize("body", [{}, {"base64": 7}, {"base64": "!!"}, {"base64": "YQ"}])
def test_what_is_no_file_is_not_described(served, body):
    assert post(served, "/api/describe", body)[0] == 400


def test_a_file_too_large_to_be_a_secret_is_said_to_be(served):
    status, told = post(served, "/api/describe", {"base64": b64(b"x" * (LIMIT + 1))})
    assert status == 413 and "128 kB" in told["error"]

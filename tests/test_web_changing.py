"""The local server, changing a workspace — over real HTTP, against the fake."""

from __future__ import annotations

import base64
import json
import threading

import pytest

from caland.application import Loader, WorkspaceService
from caland.application.files import LIMIT
from caland.domain import StoreError, Workspace
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
    # sent as it is, not escaped: escaped it would be more than a request may say at
    # all, and refused before it was read — which a client sees as a broken pipe
    text = {"scope": "prod", "key": "bigger", "text": "é" * (LIMIT // 2 + 1)}
    raw = json.dumps(text, ensure_ascii=False).encode()
    assert served.ask("POST", "/api/secret/put", raw=raw)[0] == 413
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
        ({"to_key": "api-key"}, 409),  # where it is
        ({"to_key": "API-KEY"}, 409),  # where it is, to Databricks
        ({"to_key": "db-password"}, 409),  # something is there
        ({"to_key": "DB-Password"}, 409),  # something is there, to Databricks
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


# ── what a second pair of eyes found ─────────────────────────────────
@pytest.mark.parametrize("new", [True, False])
def test_an_empty_file_wipes_nothing(served, new):
    body = {
        "scope": "prod",
        "key": "api-key" if not new else "fresh",
        "base64": "",
        "new": new,
    }
    status, told = post(served, "/api/secret/put", body)
    assert status == 400 and "empty" in told["error"] and wrote(served) == []


def test_text_that_is_no_text_is_refused_not_failed_on(served):
    raw = b'{"scope": "prod", "key": "k", "text": "\\ud800"}'
    assert served.ask("POST", "/api/secret/put", raw=raw)[0] == 400


def test_json_nested_beyond_reason_is_refused_not_failed_on(served):
    raw = b"[" * 100_000 + b"]" * 100_000
    assert served.ask("POST", "/api/secret/put", raw=raw)[0] in (400, 413)


def test_a_new_secret_in_another_case_does_not_overwrite(served):
    body = {"scope": "prod", "key": "API-Key", "text": "oops", "new": True}
    status, told = post(served, "/api/secret/put", body)
    assert status == 409 and "api-key" in told["error"] and wrote(served) == []


def test_a_scope_in_another_case_is_there_already(served):
    status, told = post(served, "/api/scope/create", {"name": "PROD"})
    assert status == 409 and "“prod”" in told["error"] and wrote(served) == []


def test_undo_does_not_overwrite_a_secret_made_since_and_keeps_what_it_holds(served):
    post(served, "/api/secret/delete", {"scope": "prod", "key": "api-key"})
    post(
        served,
        "/api/secret/put",
        {"scope": "prod", "key": "api-key", "text": "ROTATED", "new": True},
    )
    status, told = post(served, "/api/undo", {})
    assert status == 409 and "overwrite" in told["error"]
    assert served.store._values[("prod", "api-key")] == b"ROTATED"
    assert served.json("GET", "/api/state")[1]["taken"] == {
        "scope": "prod",
        "key": "api-key",
    }


def test_a_move_takes_the_value_that_is_there_now(served):
    post(served, "/api/value", {"scope": "prod", "key": "api-key"})  # shown earlier
    served.store._values[("prod", "api-key")] = b"rotated elsewhere"
    move = {"scope": "prod", "key": "api-key", "to_scope": "prod", "to_key": "moved"}
    assert post(served, "/api/secret/move", move)[0] == 200
    assert served.store._values[("prod", "moved")] == b"rotated elsewhere"


def test_reading_again_shows_the_value_that_is_there_now(served):
    post(served, "/api/value", {"scope": "prod", "key": "api-key"})
    served.store._values[("prod", "api-key")] = b"rotated elsewhere"
    post(served, "/api/refresh", {"scope": "prod"})
    for _ in range(200):
        if served.page.loader.service.cache.raw == {}:
            break
        threading.Event().wait(0.01)
    assert post(served, "/api/value", {"scope": "prod", "key": "api-key"})[1] == {
        "value": "rotated elsewhere"
    }


def test_describing_any_file_answers(served):
    import os

    for data in (
        os.urandom(300),
        b"\x30\x82\x03\x0d" + os.urandom(200),
        b"-----BEGIN CERTIFICATE-----\n",
    ):
        status, told = post(served, "/api/describe", {"base64": b64(data)})
        assert status == 200 and told["kind"]


# ── .env: a scope's secrets as lines of text ─────────────────────────
ENV = (
    b"# a comment\nexport NEW_ONE=first\nAPI-KEY='rotated'\nEMPTY=\n"
    b'MULTI="line one\\nline two"\n'
)


def test_an_import_is_shown_before_it_is_done_and_says_no_value(served):
    status, told = post(served, "/api/env/preview", {"scope": "prod", "base64": b64(ENV)})
    assert status == 200
    assert told == {
        "keys": ["NEW_ONE", "API-KEY", "MULTI"],
        "overwrite": ["api-key"],  # the same secret, whatever its case
        "empty": ["EMPTY"],
    }
    assert wrote(served) == []


def test_an_import_puts_every_pair_and_leaves_out_the_empty(served):
    status, told = post(served, "/api/env/import", {"scope": "prod", "base64": b64(ENV)})
    assert status == 200 and told["done"] == ["NEW_ONE", "API-KEY", "MULTI"]
    assert (told["total"], told["stopped_at"], told["empty"]) == (3, "", ["EMPTY"])
    assert served.store._values[("prod", "NEW_ONE")] == b"first"
    assert served.store._values[("prod", "api-key")] == b"rotated"
    assert served.store._values[("prod", "MULTI")] == b"line one\nline two"
    assert ("prod", "EMPTY") not in served.store._values


def test_an_import_that_stops_says_how_far_it_got_and_at_which_key(served):
    real = served.store.put_secret_bytes

    def refusing(scope, key, value):
        if key == "API-KEY":
            raise StoreError("the workspace said no")
        real(scope, key, value)

    served.store.put_secret_bytes = refusing
    status, told = post(served, "/api/env/import", {"scope": "prod", "base64": b64(ENV)})
    assert status == 200
    assert (told["done"], told["stopped_at"], told["total"]) == (
        ["NEW_ONE"],
        "API-KEY",
        3,
    )
    assert told["error"] == "the workspace said no"
    assert ("prod", "MULTI") not in served.store._values


@pytest.mark.parametrize("path", ["/api/env/preview", "/api/env/import"])
def test_an_import_is_a_change_like_any(read_only, served, path):
    body = {"scope": "prod", "base64": b64(ENV)}
    assert post(read_only, path, body)[0] == 403
    assert post(served, path, {**body, "scope": "kv"})[0] == 409
    assert post(served, path, {**body, "scope": "nope"})[0] == 404
    assert post(served, path, {"scope": "prod", "base64": b64(b"\xff\xfe\x00")})[0] == 400
    assert served.ask("POST", path, body, token="wrong")[0] == 401
    assert wrote(read_only) == [] and wrote(served) == []


def test_an_import_of_more_than_a_scope_holds_is_refused(served):
    many = "".join(f"K{n}=v\n" for n in range(1001)).encode()
    status, told = post(served, "/api/env/import", {"scope": "prod", "base64": b64(many)})
    assert status == 413 and "1001" in told["error"] and wrote(served) == []


def test_an_export_is_the_scopes_text_values_and_names_what_it_left_out(served):
    post(
        served,
        "/api/secret/put",
        {"scope": "prod", "key": "bundle", "base64": b64(BUNDLE)},
    )
    post(served, "/api/secret/put", {"scope": "prod", "key": "multi", "text": "a\nb"})
    status, told = post(served, "/api/env/export", {"scope": "prod"})
    assert status == 200 and told["left_out"] == ["bundle"]
    assert told["text"] == (
        "api-key=value::prod/api-key\n"
        "db-password=value::prod/db-password\n"
        'multi="a\\nb"\n'
    )


def test_an_export_reads_values_so_it_is_no_get_and_takes_the_token(served):
    assert served.ask("GET", "/api/env/export?scope=prod")[0] == 404
    assert (
        served.ask("POST", "/api/env/export", {"scope": "prod"}, token="wrong")[0] == 401
    )
    assert post(served, "/api/env/export", {"scope": "nope"})[0] == 404
    assert served.store.reads() == 0


def test_an_export_is_reading_and_works_read_only(read_only):
    assert post(read_only, "/api/env/export", {"scope": "prod"})[0] == 200


# ── preferences, and every scope's grants ────────────────────────────
def test_every_scopes_grants_at_once(served):
    status, told = served.json("GET", "/api/grants")
    assert status == 200 and told["scopes"] == {
        "kv": [["users", "READ"]],
        "prod": [["me@corp.com", "MANAGE"], ["users", "READ"]],
    }


def test_a_preference_is_kept_and_said_back():
    kept = []
    store = seeded_store()
    loader = Loader(lambda: WorkspaceService(store, "test"))
    page = Page(
        loader, workspace=Workspace(profile="test"), read_only=True, keep=kept.append
    )
    server = Server(page)
    loader.start().join(timeout=5)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        served = Served(server, store)
        served.enter()
        state = served.json("GET", "/api/state")[1]
        assert (state["show_all"], state["stale_after"]) == (False, 90)
        # a preference changes no workspace: read-only does not mind
        assert (
            post(served, "/api/settings", {"show_all": True, "stale_after": 365})[0]
            == 200
        )
        state = served.json("GET", "/api/state")[1]
        assert (state["show_all"], state["stale_after"]) == (True, 365)
        assert kept[-1].show_all_scopes is True and kept[-1].audit_threshold == 365
        for body in ({"show_all": "yes"}, {"stale_after": 45}, {"stale_after": "90"}):
            assert post(served, "/api/settings", body)[0] == 400
        assert (
            served.ask("POST", "/api/settings", {"show_all": False}, token="wrong")[0]
            == 401
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

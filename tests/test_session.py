from __future__ import annotations

from caland.application import WorkspaceService
from caland.domain import Scope
from fakes import FakeSecretStore, seeded_store


def test_authenticate_and_load_scopes_populate_cache():
    gw = seeded_store()
    s = WorkspaceService(gw, "t")
    assert s.authenticate().authenticated
    assert [sc.name for sc in s.load_scopes()] == ["kv", "prod"]
    assert s.scopes  # cached


def test_warm_scope_pulls_secrets_and_acls():
    s = WorkspaceService(seeded_store(), "t")
    s.load_scopes()
    s.warm_scope("prod")
    assert {sec.key for sec in s.secrets_for("prod")} == {"api-key", "db-password"}
    assert any(a.permission == "MANAGE" for a in s.acls_for("prod"))


def test_warm_scope_swallows_store_errors():
    gw = FakeSecretStore(scopes=[Scope("prod")], fail_on={"list_secrets"})
    s = WorkspaceService(gw, "t")
    s.load_scopes()
    s.warm_scope("prod")  # must not raise
    assert s.secrets_for("prod") == []


def test_warm_scope_marks_readability_per_scope():
    # 'mine' lists fine (readable); 'theirs' denies reads (visible but no access)
    gw = FakeSecretStore(
        scopes=[Scope("mine"), Scope("theirs")],
        secrets={"mine": []},
        no_read={"theirs"},
    )
    s = WorkspaceService(gw, "t")
    s.load_scopes()
    s.warm_scope("mine")
    s.warm_scope("theirs")  # must not raise even though both reads fail
    assert s.cache.readable == {"mine"}
    # the auth summary reflects it: READ floor for the one you can read, none else
    access = {a.scope: a.effective for a in s.auth_summary()}
    assert access == {"mine": "READ", "theirs": "—"}


def test_created_scope_is_readable():
    s = WorkspaceService(FakeSecretStore(scopes=[]), "t")
    s.load_scopes()
    s.create_scope("fresh")
    assert "fresh" in s.cache.readable


def test_delete_secret_and_scope(session: WorkspaceService):
    session.delete_secret("prod", "api-key")
    assert all(sec.key != "api-key" for sec in session.secrets_for("prod"))
    session.delete_scope("kv")
    assert all(sc.name != "kv" for sc in session.scopes)


def test_create_scope(session: WorkspaceService):
    session.create_scope("staging")
    assert any(sc.name == "staging" for sc in session.scopes)


def test_auth_summary_delegates(session: WorkspaceService):
    session.authenticate()
    summary = {s.scope: s for s in session.auth_summary()}
    assert summary["prod"].effective == "MANAGE"


def test_set_acl_grants_permission(session: WorkspaceService):
    session.set_acl("kv", "newbie@corp.com", "WRITE")
    perms = {a.principal: a.permission for a in session.acls_for("kv")}
    assert perms["newbie@corp.com"] == "WRITE"


def test_set_acl_is_an_upsert(session: WorkspaceService):
    session.set_acl("prod", "me@corp.com", "READ")  # was MANAGE
    perms = {a.principal: a.permission for a in session.acls_for("prod")}
    assert perms["me@corp.com"] == "READ"
    # auth summary reflects the downgrade
    session.authenticate()
    summary = {s.scope: s for s in session.auth_summary()}
    assert summary["prod"].effective == "READ"


def test_remove_acl(session: WorkspaceService):
    session.remove_acl("prod", "users")
    assert all(a.principal != "users" for a in session.acls_for("prod"))

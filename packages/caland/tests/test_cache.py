from __future__ import annotations

from caland.application import WorkspaceCache
from caland.domain import Scope, Secret


def test_upsert_secret_adds_updates_and_sorts():
    cache = WorkspaceCache(label="t")
    cache.upsert_secret(Secret("s", "b"))
    cache.upsert_secret(Secret("s", "a"))
    assert [s.key for s in cache.secrets_for("s")] == ["a", "b"]
    # updating an existing key replaces it, not duplicates
    cache.upsert_secret(Secret("s", "a", last_updated_ms=123))
    rows = cache.secrets_for("s")
    assert len(rows) == 2
    assert rows[0].last_updated_ms == 123


def test_remove_secret_drops_row_and_the_value_held_of_it():
    cache = WorkspaceCache(label="t")
    cache.upsert_secret(Secret("s", "a"))
    cache.raw[("s", "a")] = b"secret"
    cache.remove_secret("s", "a")
    assert cache.secrets_for("s") == []
    assert cache.raw == {}


def test_add_and_remove_scope():
    cache = WorkspaceCache(label="t")
    cache.add_scope(Scope("s"))
    cache.raw[("s", "k")] = b"v"
    assert any(sc.name == "s" for sc in cache.scopes)
    cache.remove_scope("s")
    assert cache.scopes == []
    assert cache.raw == {}

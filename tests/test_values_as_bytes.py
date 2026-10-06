"""A value as it is — bytes — through the use-cases the page works with."""

from __future__ import annotations

import contextlib

import pytest

from caland.application import WorkspaceService
from caland.domain import Exists, Scope, Secret, StoreError
from fakes import FakeSecretStore, seeded_store

BUNDLE = bytes(range(256)) * 3  # no text at all: every byte there is


class Looked(WorkspaceService):
    """A service whose store the tests can look at."""

    store: FakeSecretStore


@pytest.fixture
def service() -> Looked:
    store = seeded_store()
    made = Looked(store, "test")
    made.authenticate()
    made.load_scopes()
    for scope in made.scopes:
        made.warm_scope(scope.name)
    made.store = store  # for the tests to look at
    return made


def test_bytes_go_in_and_come_back_as_they_were(service):
    service.put_secret_bytes("prod", "bundle", BUNDLE)
    assert service.store._values[("prod", "bundle")] == BUNDLE
    service.forget_values()
    assert service.reveal_bytes("prod", "bundle") == BUNDLE
    assert service.secret("prod", "bundle") is not None


def test_a_value_is_read_once_and_kept_for_the_session(service):
    for _ in range(3):
        service.reveal_bytes("prod", "api-key")
    assert service.store.count("get_secret_bytes") == 1


def test_writing_drops_what_the_text_of_it_was(service):
    assert service.reveal("prod", "api-key") == "value::prod/api-key"
    service.put_secret_bytes("prod", "api-key", b"new")
    assert service.cached_value("prod", "api-key") is None
    assert service.reveal_bytes("prod", "api-key") == b"new"


def test_moving_keeps_every_byte(service):
    service.put_secret_bytes("prod", "bundle", BUNDLE)
    service.move_secret("prod", "bundle", "prod", "renamed")
    assert service.secret("prod", "bundle") is None
    assert service.store._values[("prod", "renamed")] == BUNDLE


def test_moving_is_done_in_the_safe_order(service):
    service.move_secret("prod", "api-key", "prod", "moved")
    done = [call[0] for call in service.store.calls if call[0] != "list_secrets"]
    assert done[-3:] == ["get_secret_bytes", "put_secret_bytes", "delete_secret"]


def test_a_move_that_fails_halfway_leaves_the_secret_in_two_places(service):
    service.store._fail_on.add("delete_secret")
    with pytest.raises(StoreError):
        service.move_secret("prod", "api-key", "prod", "moved")
    assert service.store._values[("prod", "moved")] == b"value::prod/api-key"
    assert any(s.key == "api-key" for s in service.store._secrets["prod"])
    assert service.taken is None


def test_a_move_that_cannot_write_removes_nothing(service):
    service.store._fail_on.add("put_secret_bytes")
    with pytest.raises(StoreError):
        service.move_secret("prod", "api-key", "prod", "moved")
    assert service.store.count("delete_secret") == 0


def test_copying_keeps_the_original_and_has_nothing_to_put_back(service):
    service.move_secret("prod", "api-key", "prod", "copy", keep=True)
    assert service.secret("prod", "api-key") is not None
    assert service.secret("prod", "copy") is not None
    assert service.taken is None


def test_a_deleted_secret_can_be_put_back_with_what_it_held(service):
    service.put_secret_bytes("prod", "bundle", BUNDLE)
    assert service.delete_secret_kept("prod", "bundle") is True
    assert service.secret("prod", "bundle") is None and service.taken == (
        "prod",
        "bundle",
    )
    assert service.put_back() == ("prod", "bundle")
    assert service.store._values[("prod", "bundle")] == BUNDLE and service.taken is None


def test_a_secret_moved_away_can_be_put_back_and_the_copy_stays(service):
    service.move_secret("prod", "api-key", "prod", "moved")
    service.put_back()
    assert service.secret("prod", "api-key") is not None
    assert service.secret("prod", "moved") is not None


def test_putting_back_is_one_deep(service):
    service.delete_secret_kept("prod", "api-key")
    service.delete_secret_kept("prod", "db-password")
    assert service.taken == ("prod", "db-password")
    service.put_back()
    with pytest.raises(StoreError, match="nothing to put back"):
        service.put_back()
    assert service.secret("prod", "api-key") is None


def test_a_secret_whose_value_cannot_be_read_is_deleted_for_good(service):
    service.store._fail_on.add("get_secret_bytes")
    assert service.delete_secret_kept("prod", "api-key") is False
    assert service.secret("prod", "api-key") is None and service.taken is None


def test_what_cannot_be_put_back_now_is_kept_for_when_it_can(service):
    service.delete_secret_kept("prod", "api-key")
    service.delete_scope("prod")
    with pytest.raises(StoreError, match="scope “prod” is gone"):
        service.put_back()
    assert service.taken == ("prod", "api-key")
    service.create_scope("prod")
    assert service.put_back() == ("prod", "api-key")
    assert service.store._values[("prod", "api-key")] == b"value::prod/api-key"


def test_it_is_not_put_back_over_a_secret_made_since(service):
    service.delete_secret_kept("prod", "api-key")
    service.put_secret_bytes("prod", "api-key", b"ROTATED-NEW")
    with pytest.raises(Exists, match="would overwrite it"):
        service.put_back()
    assert service.store._values[("prod", "api-key")] == b"ROTATED-NEW"
    assert service.taken == ("prod", "api-key")


def test_it_is_not_put_back_into_a_scope_that_is_azures(service):
    service.delete_secret_kept("prod", "api-key")
    next(
        s for s in service.cache.scopes if s.name == "prod"
    ).backend_type = "AZURE_KEYVAULT"
    with pytest.raises(StoreError, match="Azure Key Vault"):
        service.put_back()
    assert service.store.count("put_secret_bytes") == 0 and service.taken is not None


# ── what is there now, not what was read before ──────────────────────
def test_a_move_takes_the_value_as_it_is_now(service):
    assert service.reveal_bytes("prod", "api-key") == b"value::prod/api-key"
    service.store._values[("prod", "api-key")] = b"rotated elsewhere"
    service.move_secret("prod", "api-key", "prod", "moved")
    assert service.store._values[("prod", "moved")] == b"rotated elsewhere"
    service.put_back()
    assert service.store._values[("prod", "api-key")] == b"rotated elsewhere"


def test_a_delete_keeps_the_value_as_it_was_when_deleted(service):
    service.reveal_bytes("prod", "api-key")
    service.store._values[("prod", "api-key")] = b"rotated elsewhere"
    service.delete_secret_kept("prod", "api-key")
    service.put_back()
    assert service.store._values[("prod", "api-key")] == b"rotated elsewhere"


def test_reading_a_scope_again_lets_go_of_what_was_read_of_it(service):
    service.reveal_bytes("prod", "api-key")
    service.reveal("prod", "db-password")
    service.reveal_bytes("kv", "tenant-id")
    service.refresh_scope("prod")
    assert list(service.cache.raw) == [("kv", "tenant-id")] and service.cache.values == {}


# ── nothing lands on what is there ───────────────────────────────────
def test_a_new_secret_is_not_put_over_one_made_elsewhere_since(service):
    service.store._secrets["prod"].append(Secret("prod", "made-elsewhere"))
    service.store._values[("prod", "made-elsewhere")] = b"theirs"
    with pytest.raises(Exists, match="made-elsewhere"):
        service.create_secret_bytes("prod", "made-elsewhere", b"mine")
    assert service.store._values[("prod", "made-elsewhere")] == b"theirs"
    assert service.secret("prod", "made-elsewhere") is not None  # and now it is seen


def test_a_move_does_not_land_on_one_made_elsewhere_since(service):
    service.store._secrets["prod"].append(Secret("prod", "made-elsewhere"))
    with pytest.raises(Exists):
        service.move_secret("prod", "api-key", "prod", "made-elsewhere")
    assert service.store.count("put_secret_bytes") == 0
    assert service.store.count("delete_secret") == 0


@pytest.mark.parametrize("key", ["API-KEY", "Api-Key", "api-KEY"])
def test_a_name_in_another_case_is_the_same_name(service, key):
    """To Databricks it is one secret. A new one would overwrite it, and a rename
    would write it and then remove it — altogether."""
    with pytest.raises(Exists):
        service.create_secret_bytes("prod", key, b"mine")
    with pytest.raises(Exists, match="does not tell names apart by case"):
        service.move_secret("prod", "api-key", "prod", key)
    with pytest.raises(Exists):
        service.move_secret("prod", "api-key", "PROD", key, keep=True)
    assert service.store._values.get(("prod", "api-key")) is None  # untouched: never read
    assert service.store.count("put_secret_bytes") == 0
    assert service.store.count("delete_secret") == 0
    assert any(s.key == "api-key" for s in service.store._secrets["prod"])


def test_the_fake_takes_a_name_in_another_case_for_the_same_secret():
    store = FakeSecretStore(scopes=[Scope("s")], secrets={"s": [Secret("s", "Case-Key")]})
    store.put_secret_bytes("s", "case-key", b"lower")
    assert [x.key for x in store.list_secrets("s")] == ["Case-Key"]
    assert store.get_secret_bytes("s", "CASE-KEY") == b"lower"
    store.delete_secret("s", "case-KEY")
    assert store.list_secrets("s") == []


# ── one change at a time ─────────────────────────────────────────────
def test_a_put_back_asked_for_while_a_delete_is_under_way_loses_nothing():
    """`d`, `y`, and `u` before the answer: the secret just deleted must be either
    back or still held — never gone with nothing to put back."""
    import threading
    import time

    class Slow(FakeSecretStore):
        def get_secret_bytes(self, scope, key):
            time.sleep(0.05)
            return super().get_secret_bytes(scope, key)

    seeded = seeded_store()
    store = Slow(scopes=seeded._scopes, secrets=seeded._secrets, acls=seeded._acls)
    service = WorkspaceService(store, "test")
    service.load_scopes()
    for scope in service.scopes:
        service.warm_scope(scope.name)
    service.delete_secret_kept("prod", "db-password")  # an earlier one, waiting

    def put_back():
        with contextlib.suppress(StoreError):
            service.put_back()

    for _ in range(20):
        service.put_secret_bytes("prod", "api-key", b"the value")
        deleting = threading.Thread(
            target=service.delete_secret_kept, args=("prod", "api-key")
        )
        undoing = threading.Thread(target=put_back)
        deleting.start()
        time.sleep(0.01)
        undoing.start()
        deleting.join(timeout=5)
        undoing.join(timeout=5)
        back = any(s.key == "api-key" for s in store._secrets["prod"])
        assert back or service.taken == ("prod", "api-key")
        if back:
            assert store._values[("prod", "api-key")] == b"the value"


def test_two_new_secrets_of_one_name_at_once_make_one():
    import threading

    store = seeded_store()
    service = WorkspaceService(store, "test")
    service.load_scopes()
    refused = []

    def make(value: bytes) -> None:
        try:
            service.create_secret_bytes("prod", "raced", value)
        except Exists:
            refused.append(value)

    threads = [threading.Thread(target=make, args=(bytes([n]),)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert len(refused) == 7 and store.count("put_secret_bytes") == 1


def test_forgetting_forgets_what_could_be_put_back_too(service):
    service.reveal_bytes("prod", "db-password")
    service.delete_secret_kept("prod", "api-key")
    service.forget_values()
    assert service.taken is None and service.cache.raw == {}


def test_deleting_a_scope_drops_the_values_held_from_it(service):
    service.reveal_bytes("prod", "api-key")
    service.delete_scope("prod")
    assert service.cache.raw == {}


def test_the_fake_reads_text_it_was_given_as_bytes():
    store = FakeSecretStore(values={("s", "k"): "text"})
    assert store.get_secret_bytes("s", "k") == b"text"

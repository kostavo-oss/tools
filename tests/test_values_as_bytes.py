"""A value as it is — bytes — through the use-cases the page works with."""

from __future__ import annotations

import pytest

from caland.application import WorkspaceService
from caland.domain import StoreError
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
    with pytest.raises(StoreError, match="Nothing to put back"):
        service.put_back()
    assert service.secret("prod", "api-key") is None


def test_a_secret_whose_value_cannot_be_read_is_deleted_for_good(service):
    service.store._fail_on.add("get_secret_bytes")
    assert service.delete_secret_kept("prod", "api-key") is False
    assert service.secret("prod", "api-key") is None and service.taken is None


def test_it_cannot_be_put_back_into_a_scope_that_is_gone(service):
    service.delete_secret_kept("prod", "api-key")
    service.delete_scope("prod")
    with pytest.raises(StoreError, match="scope “prod” is gone"):
        service.put_back()
    assert service.taken is None


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

"""The loader: connect and warm in the background, eight scopes at a time."""

from __future__ import annotations

import threading
import time

from caland.application import Loader, WorkspaceService
from caland.application.loading import CONNECTING, FAILED, READY, WORKERS
from caland.domain import AuthError, Identity, Scope
from fakes import FakeSecretStore, seeded_store


def loaded(store=None, **kwargs) -> Loader:
    loader = Loader(lambda: WorkspaceService(store or seeded_store(), "test"), **kwargs)
    loader.start().join(timeout=5)
    return loader


def service(loader: Loader) -> WorkspaceService:
    assert loader.service is not None
    return loader.service


def again(loader: Loader, scope: str | None = None) -> None:
    """Read again, and wait until that is done."""
    thread = loader.refresh(scope)
    assert thread is not None
    thread.join(timeout=5)


def test_it_starts_out_connecting_with_nothing_to_show():
    loader = Loader(lambda: WorkspaceService(seeded_store(), "test"))
    assert loader.progress().phase == CONNECTING
    assert loader.service is None


def test_it_ends_ready_with_every_scope_read():
    loader = loaded()
    progress = loader.progress()
    assert (progress.phase, progress.done, progress.total) == (READY, 2, 2)
    assert [s.key for s in service(loader).secrets_for("prod")] == [
        "api-key",
        "db-password",
    ]
    assert service(loader).identity.user_name == "me@corp.com"


def test_no_value_is_read_while_loading():
    store = seeded_store()
    loaded(store)
    assert store.reads() == 0


def test_every_change_moves_the_version():
    loader = Loader(lambda: WorkspaceService(seeded_store(), "test"))
    before = loader.progress().version
    loader.start().join(timeout=5)
    assert loader.progress().version > before


def test_a_connection_that_fails_says_why():
    def connect():
        raise AuthError("the browser sign-in was cancelled")

    loader = Loader(connect)
    loader.start().join(timeout=5)
    assert loader.progress().phase == FAILED
    assert "cancelled" in loader.progress().error
    assert loader.service is None


def test_being_refused_by_the_workspace_says_why():
    store = FakeSecretStore(identity=Identity(authenticated=False, error="token expired"))
    loader = loaded(store)
    assert (loader.progress().phase, loader.progress().error) == (FAILED, "token expired")
    assert loader.service is None


def test_scopes_that_cannot_be_listed_say_why():
    loader = loaded(FakeSecretStore(fail_on={"list_scopes"}))
    assert loader.progress().phase == FAILED
    assert "list_scopes" in loader.progress().error


def test_a_scope_out_of_reach_is_empty_not_an_error():
    store = FakeSecretStore(scopes=[Scope("open"), Scope("shut")], no_read={"shut"})
    loader = loaded(store)
    assert loader.progress().phase == READY
    assert service(loader).cache.readable == {"open"}


def test_at_most_eight_scopes_are_asked_for_at_once():
    busy, most, lock = 0, 0, threading.Lock()

    class Slow(FakeSecretStore):
        def list_secrets(self, scope):
            nonlocal busy, most
            with lock:
                busy += 1
                most = max(most, busy)
            time.sleep(0.01)
            with lock:
                busy -= 1
            return super().list_secrets(scope)

    loader = loaded(Slow(scopes=[Scope(f"s{i}") for i in range(40)]))
    assert loader.progress().done == 40
    assert 1 < most <= WORKERS


def test_one_scope_can_be_read_again():
    store = seeded_store()
    loader = loaded(store)
    before = (store.count("list_secrets"), loader.progress().version)
    again(loader, "prod")
    assert store.count("list_secrets") == before[0] + 1
    assert loader.progress().version > before[1]
    assert loader.progress().phase == READY


def test_the_whole_workspace_can_be_read_again():
    store = seeded_store()
    loader = loaded(store)
    again(loader)
    assert store.count("list_scopes") == 2
    assert loader.progress().phase == READY


def test_reading_again_needs_a_workspace_and_a_scope_that_is_there():
    store = seeded_store()
    assert Loader(lambda: WorkspaceService(store, "test")).refresh() is None
    loader = loaded(store)
    before = store.count("list_secrets")
    again(loader, "no-such-scope")
    assert store.count("list_secrets") == before

"""Loader — connect to a workspace and warm it, in the background.

The use-case behind "the page is there before the workspace is": something that
shows a workspace starts a `Loader`, draws at once, and asks `progress()` how far
it is. Scopes are warmed eight at a time — enough that hundreds are ready in
seconds, few enough not to hammer the API.

It does no I/O of its own: `connect` hands it a `WorkspaceService`, and every
call goes through that.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

from ..domain import AuthError, StoreError
from .workspace import WorkspaceService

#: How many scopes are asked for at the same time.
WORKERS = 8

CONNECTING = "connecting"
LOADING = "loading"
READY = "ready"
FAILED = "failed"


@dataclass(frozen=True)
class Progress:
    """How far a `Loader` is. `version` goes up with every change, so that who
    asks can tell whether there is anything new."""

    phase: str = CONNECTING
    done: int = 0
    total: int = 0
    error: str = ""
    version: int = 0


class Loader:
    def __init__(
        self, connect: Callable[[], WorkspaceService], workers: int = WORKERS
    ) -> None:
        self._connect = connect
        self._workers = workers
        self._lock = threading.Lock()
        self._progress = Progress()
        self._service: WorkspaceService | None = None
        # one run at a time: a refresh asked for during a load waits its turn
        self._turn = threading.Lock()

    @property
    def service(self) -> WorkspaceService | None:
        """The workspace, once connected."""
        return self._service

    def progress(self) -> Progress:
        with self._lock:
            return self._progress

    # -- starting work --------------------------------------------------
    def start(self) -> threading.Thread:
        """Connect, sign in and warm every scope. Returns at once."""
        return self._run(self._load)

    def refresh(self, scope: str | None = None) -> threading.Thread | None:
        """Read one scope again, or with no name the whole workspace. Returns at
        once; nothing happens when there is no workspace to read."""
        if self._service is None:
            return None
        if scope is None:
            return self._run(self._warm)
        return self._run(lambda: self._warm_one(scope))

    def changed(self) -> None:
        """Something in the workspace was changed through its service: whoever is
        showing it has something new to read."""
        self._set()

    def _run(self, work: Callable[[], None]) -> threading.Thread:
        def in_turn() -> None:
            with self._turn:
                work()

        thread = threading.Thread(target=in_turn, name="caland-loader", daemon=True)
        thread.start()
        return thread

    # -- the work -------------------------------------------------------
    def _set(self, **changes: object) -> None:
        with self._lock:
            now = self._progress
            self._progress = replace(now, **changes, version=now.version + 1)

    def _one_more(self) -> None:
        with self._lock:
            now = self._progress
            self._progress = replace(now, done=now.done + 1, version=now.version + 1)

    def _load(self) -> None:
        self._set(phase=CONNECTING, done=0, total=0, error="")
        try:
            service = self._connect()
            identity = service.authenticate()
        except (AuthError, StoreError) as exc:
            self._set(phase=FAILED, error=str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            # whatever else goes wrong on the way in is said, not waited on for ever
            self._set(phase=FAILED, error=str(exc) or type(exc).__name__)
            return
        if not identity.authenticated:
            self._set(phase=FAILED, error=identity.error or "Access denied.")
            return
        self._service = service
        self._warm()

    def _warm(self) -> None:
        service = self._service
        if service is None:
            return
        self._set(phase=LOADING, done=0, total=0, error="")
        try:
            scopes = service.load_scopes()
        except StoreError as exc:
            self._set(phase=FAILED, error=str(exc))
            return
        self._set(total=len(scopes))

        def warm(name: str) -> None:
            service.warm_scope(name)  # never raises: a scope it can't read is empty
            self._one_more()

        # each scope is written under its own key, and what is held of its values
        # is let go of key by key (`forget_scope`): the writes don't race
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            list(pool.map(warm, [scope.name for scope in scopes]))
        self._set(phase=READY)

    def _warm_one(self, scope: str) -> None:
        service = self._service
        if service is None or service.scope(scope) is None:
            return
        service.refresh_scope(scope)
        self._set()  # nothing but the version: there is something new to read

"""The scopes pane filters to scopes the user can access; `f` toggles all."""

from __future__ import annotations

from typing import cast

from textual.widgets import DataTable

from caland.app import CalandApp
from caland.application import WorkspaceService
from caland.domain import Acl, Scope, Secret
from caland.interface.screens.main import MainScreen
from caland.interface.widgets import ScopesPane
from fakes import FakeSecretStore, stub_onboarding


def _app() -> CalandApp:
    # 'mine' is readable; 'theirs' is visible to list_scopes but denies reads.
    store = FakeSecretStore(
        scopes=[Scope("mine"), Scope("theirs")],
        secrets={"mine": [Secret("mine", "k", 1_718_000_000_000)]},
        acls={"mine": [Acl("me@corp.com", "MANAGE")]},
        no_read={"theirs"},
    )
    return CalandApp(onboarding=stub_onboarding(), session=WorkspaceService(store, "t"))


def _scope_names(app: CalandApp) -> set[str]:
    table = cast(MainScreen, app.screen).query_one(ScopesPane).query_one(DataTable)
    return {table.get_row_at(i)[0] for i in range(table.row_count)}


async def test_inaccessible_scopes_hidden_by_default_and_f_reveals_them():
    app = _app()
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        # only the scope you can access shows
        assert _scope_names(app) == {"mine"}

        await pilot.press("f")  # show all
        await pilot.pause()
        assert _scope_names(app) == {"mine", "theirs"}

        await pilot.press("f")  # back to only mine
        await pilot.pause()
        assert _scope_names(app) == {"mine"}


async def test_all_denied_shows_hint_not_a_blank_pane():
    store = FakeSecretStore(
        scopes=[Scope("a"), Scope("b")],
        no_read={"a", "b"},  # you can't read any of them
    )
    app = CalandApp(onboarding=stub_onboarding(), session=WorkspaceService(store, "t"))
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        pane = cast(MainScreen, app.screen).query_one(ScopesPane)
        assert pane.query_one(DataTable).row_count == 0
        # a purpose-built empty hint is shown (not the generic "no scopes yet")
        assert pane.query_one("#scopes-empty").display
        assert pane._empty_hint and "show all 2" in pane._empty_hint

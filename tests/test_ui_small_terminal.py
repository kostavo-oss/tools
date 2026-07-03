"""Small-terminal regressions — the VS Code integrated-terminal panel.

A cramped viewport (short and narrow) used to clip modal tables to zero data
rows and squeeze the breadcrumb's `secret:` segment out of the banner, leaving
the identity email where the secret name should be.
"""

from __future__ import annotations

from fakes import seeded_store, stub_onboarding
from isolinear.app import IsolinearApp
from isolinear.application import WorkspaceService
from isolinear.domain import Identity
from isolinear.interface.modals import SearchModal

PANEL = (98, 12)  # a cramped VS Code panel


def _rendered_text(app: IsolinearApp) -> str:
    """The visible screen as text (the SVG export encodes spaces as &#160;)."""
    return app.export_screenshot().replace("&#160;", " ")


def _app() -> IsolinearApp:
    store = seeded_store()
    store._identity = Identity("misja@prorexconsultancy.nl", "Misja", authenticated=True)
    session = WorkspaceService(store, "acme-prod-workspace")
    return IsolinearApp(onboarding=stub_onboarding(), session=session)


async def test_breadcrumb_keeps_the_secret_segment_when_narrow():
    app = _app()
    async with app.run_test(size=PANEL) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("j", "tab")  # prod / api-key selected
        await pilot.pause()
        screen = _rendered_text(app)
        assert "secret:" in screen  # the breadcrumb outranks the identity chip


async def test_permissions_list_renders_on_a_short_terminal():
    app = _app()
    async with app.run_test(size=PANEL) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("j", "p")  # permissions for prod
        await pilot.pause()
        screen = _rendered_text(app)
        assert "users" in screen  # a data row is actually visible


async def test_audit_list_renders_on_a_short_terminal():
    app = _app()
    async with app.run_test(size=PANEL) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        screen = _rendered_text(app)
        assert "tenant-id" in screen  # the oldest secret's row is visible


async def test_help_shows_multiple_rows_on_a_short_terminal():
    app = _app()
    async with app.run_test(size=PANEL) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        screen = _rendered_text(app)
        # more than the single first row used to survive the clipping
        assert "Move within a pane" in screen
        assert "Move between panes" in screen


async def test_plain_letter_fallbacks_for_vscode():
    """F = search and P = palette, for terminals that eat ctrl+f / ctrl+p."""
    app = _app()
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("F")
        await pilot.pause()
        assert isinstance(app.screen, SearchModal)
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("P")
        await pilot.pause()
        assert "CommandPalette" in app.screen.__class__.__name__

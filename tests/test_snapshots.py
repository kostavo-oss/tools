"""Visual regression snapshots (pytest-textual-snapshot).

Each test renders the real app (driven by the fakes) to SVG and compares it to
the committed baseline in __snapshots__/. When a UI change is intentional,
regenerate with:

    uv run pytest tests/test_snapshots.py --snapshot-update
"""

from __future__ import annotations

from fakes import seeded_store, stub_onboarding
from isolinear.app import IsolinearApp
from isolinear.application import WorkspaceService

SIZE = (110, 30)


def _steps(*keys: str):
    """A run_before that presses keys and fully settles the message cascade.

    snap_compare's own `press=` screenshots as soon as the keys are sent; a
    slow CI runner can catch the panes mid-update (each keypress fans out
    highlight → selection → re-render messages). Settling explicitly after
    the presses makes the render deterministic.
    """

    async def run(pilot) -> None:
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        for key in keys:
            await pilot.press(key)
            await pilot.app.workers.wait_for_complete()
            await pilot.pause()
        await pilot.pause()

    return run


def _app(*, session: bool = True) -> IsolinearApp:
    svc = WorkspaceService(seeded_store(), "test") if session else None
    return IsolinearApp(onboarding=stub_onboarding(), session=svc)


def test_browse_screen(snap_compare):
    assert snap_compare(_app(), run_before=_steps("j", "tab"), terminal_size=SIZE)


def test_login_empty_state(snap_compare):
    assert snap_compare(_app(session=False), run_before=_steps(), terminal_size=SIZE)


def test_audit_screen(snap_compare):
    assert snap_compare(_app(), run_before=_steps("A"), terminal_size=SIZE)

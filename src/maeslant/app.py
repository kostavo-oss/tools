"""Maeslant — a terminal Databricks secret manager.

The App is the composition root: it builds the infrastructure adapters, wires
them into the `OnboardingService`, installs the theme, and hands off to
`MainScreen`. Domain logic lives in `maeslant.domain`, use-cases in
`maeslant.application`, adapters in `maeslant.infrastructure`; UI in
`maeslant.interface`.
"""

from __future__ import annotations

from textual.app import App

from .application import OnboardingService, WorkspaceService
from .domain import Settings, SettingsStore
from .infrastructure import (
    DatabricksBundleStore,
    DatabricksCfgProfileStore,
    DatabricksConnector,
    JsonSettingsStore,
)
from .interface.screens.main import MainScreen
from .interface.theme import MAESLANT_THEMES


class EphemeralSettingsStore:
    """Fallback `SettingsStore`: keeps preferences for this process only.

    The default for programmatic use (tests, embedding) so constructing the app
    never touches the user's real config; `main()` passes the JSON store.
    """

    def __init__(self) -> None:
        self._settings = Settings()

    def load(self) -> Settings:
        return self._settings

    def save(self, settings: Settings) -> None:
        self._settings = settings


class MaeslantApp(App[None]):
    CSS_PATH = "styles.tcss"
    TITLE = "Maeslant"
    # `q` quits from the browse/login screens only (they bind it themselves) —
    # an app-level binding would bubble up from dialogs and quit mid-confirm.

    def __init__(
        self,
        onboarding: OnboardingService | None = None,
        session: WorkspaceService | None = None,
        read_only: bool = False,
        settings_store: SettingsStore | None = None,
        profile: str | None = None,
    ) -> None:
        super().__init__()
        self._onboarding = onboarding
        self._initial_session = session
        self.read_only = read_only
        self._settings_store = settings_store or EphemeralSettingsStore()
        self.settings = self._settings_store.load()
        self._profile = profile  # workspace to auto-connect to (--profile)

    def get_theme_variable_defaults(self) -> dict[str, str]:
        # The stylesheet is parsed under Textual's default theme before ours is
        # applied, so the per-section accents must resolve there too. Each
        # Maeslant theme overrides these with its own values.
        return {
            **super().get_theme_variable_defaults(),
            "scopes-color": "#8b7cff",
            "secrets-color": "#4ec9e0",
            "detail-color": "#e0b24a",
            "value-color": "#5fd39a",
        }

    def save_settings(self) -> None:
        self._settings_store.save(self.settings)

    def _remember_theme(self, theme: str) -> None:
        self.settings.theme = theme
        self.save_settings()

    def on_mount(self) -> None:
        for theme in MAESLANT_THEMES:
            self.register_theme(theme)
        # apply the persisted theme (fall back if it no longer exists), then
        # remember every change the user makes via the palette
        wanted = self.settings.theme
        self.theme = wanted if wanted in self.available_themes else "maeslant"
        self.watch(self, "theme", self._remember_theme, init=False)
        onboarding = self._onboarding or OnboardingService(
            DatabricksConnector(),
            DatabricksCfgProfileStore(),
            DatabricksBundleStore(),
        )
        self.push_screen(
            MainScreen(
                onboarding,
                self._initial_session,
                read_only=self.read_only,
                settings=self.settings,
                save_settings=self.save_settings,
                auto_connect=self._profile,
            )
        )


_USAGE = """\
maeslant — a keyboard-driven terminal UI for managing Databricks secrets.

usage: maeslant [WORKSPACE] [--profile NAME] [--read-only] [--version] [--help]

  WORKSPACE / --profile NAME
                connect straight to a discovered workspace (a
                ~/.databrickscfg profile or bundle target) and skip
                the picker
  --read-only   browse, reveal, and copy — but disable every mutation
                (safe for poking around production)

Run with no arguments to launch the TUI. Inside: ? for help, ctrl+p for the
command palette, q to quit.
"""


def main() -> None:
    import sys

    args = sys.argv[1:]
    if {"-V", "--version"} & set(args):
        from importlib.metadata import version

        print(f"maeslant {version('maeslant')}")
        return
    if {"-h", "--help"} & set(args):
        print(_USAGE, end="")
        return
    profile: str | None = None
    if "--profile" in args:
        i = args.index("--profile")
        if i + 1 >= len(args):
            print("error: --profile needs a workspace name", file=sys.stderr)
            raise SystemExit(2)
        profile = args[i + 1]
    else:  # a bare positional is the workspace name
        positional = [a for a in args if not a.startswith("-")]
        if positional:
            profile = positional[0]
    MaeslantApp(
        read_only="--read-only" in args,
        settings_store=JsonSettingsStore(),
        profile=profile,
    ).run()


if __name__ == "__main__":
    main()

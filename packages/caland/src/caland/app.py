"""Caland — Databricks secrets, by hand.

`main` is the command: it reads what was asked for, builds the adapters that
reach a workspace, and starts the page (`interface/web`).

Domain logic lives in `caland.domain`, use-cases in `caland.application`,
adapters in `caland.infrastructure`; the page in `caland.interface.web`.
"""

from __future__ import annotations

import sys

from .application import OnboardingService
from .infrastructure import (
    DatabricksBundleStore,
    DatabricksCfgProfileStore,
    DatabricksConnector,
    JsonSettingsStore,
)

_USAGE = """\
caland — Databricks secrets, from a page in your browser.

usage: caland [WORKSPACE] [--profile NAME] [--read-only] [--no-open]

  WORKSPACE / --profile NAME
                 go straight to a workspace that was found — a profile in
                 ~/.databrickscfg, or the target of a bundle here. Without it
                 the page asks which, when there is more than one
  --read-only    look, show and copy, and change nothing in the workspace
  --no-open      print the link instead of opening a browser
  -V, --version  which caland this is
  -h, --help     this

The page is served from this machine only, to you only. ctrl+c stops it and
forgets every value it held. On the page: ? for the keys.
"""

#: The options that take no value. Anything else that starts with a dash is not
#: caland's — and is refused: `--readonly` taken for nothing would open a
#: workspace to change, when what was meant was that it should not be.
#: `--page` is from when the page was not yet all there was. It is taken, and
#: does nothing, so that an old command line still works — and is left out of
#: `--help` on purpose: there is nothing to say it for.
_FLAGS = ("--page", "--read-only", "--no-open")

#: Until 0.6 caland had a terminal version, and `--tui` was how to ask for it.
_NO_TERMINAL = (
    "there is no terminal version in caland any more: caland is the page. "
    "The terminal app is isolinear, as it was — `uvx isolinear`"
)


def _asked(args: list[str]) -> tuple[str | None, set[str]]:
    """Which workspace was named, and which options were given. Raises
    `SystemExit(2)`, having said why, for what cannot be understood."""

    def refuse(why: str, hint: bool = True) -> SystemExit:
        said = f"caland: {why}" + (" (caland --help says what there is)" if hint else "")
        print(said, file=sys.stderr)
        return SystemExit(2)

    profile: str | None = None
    flags: set[str] = set()
    rest = iter(args)
    for arg in rest:
        if arg == "--profile" or arg.startswith("--profile="):
            name = arg.partition("=")[2] if "=" in arg else next(rest, "")
            if not name or name.startswith("-"):
                raise refuse("--profile needs a workspace name")
            if profile is not None:
                raise refuse("one workspace at a time")
            profile = name
        elif arg in _FLAGS:
            flags.add(arg)
        elif arg == "--tui":
            raise refuse(_NO_TERMINAL, hint=False)
        elif arg.startswith("-"):
            raise refuse(f"there is no option {arg}")
        elif profile is not None:
            raise refuse("one workspace at a time")
        else:
            profile = arg  # a bare word is the workspace's name
    return profile, flags


def main() -> None:
    args = sys.argv[1:]
    if {"-V", "--version"} & set(args):
        from importlib.metadata import version

        print(f"caland {version('caland')}")
        return
    if {"-h", "--help"} & set(args):
        print(_USAGE, end="")
        return
    profile, flags = _asked(args)
    raise SystemExit(_page(profile, sorted(flags)))


def _page(profile: str | None, args: list[str]) -> int:
    """caland: a workspace's secrets, as a page in the browser."""
    from importlib.metadata import version

    from .interface import web

    onboarding = OnboardingService(
        DatabricksConnector(), DatabricksCfgProfileStore(), DatabricksBundleStore()
    )
    return web.run(
        onboarding,
        profile,
        read_only="--read-only" in args,
        settings_store=JsonSettingsStore(),
        version=version("caland"),
        open_browser="--no-open" not in args,
    )


if __name__ == "__main__":
    main()

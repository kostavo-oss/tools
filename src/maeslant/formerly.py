"""The names maeslant had when it was isolinear, and still answers to.

Up to 0.4.1 this tool was released as `isolinear`. Renaming it could not rename
what was already on somebody's machine, so three things still answer to the old
name — and this module is the only place in the package that spells it.

**The settings file.** `~/.config/isolinear/settings.json` is read when there is
no settings file under the new name yet. It is never written: the next change
of a preference saves under the new name, and the old file is left where it is.

**The themes.** A saved `isolinear-violet` is `maeslant-violet`, so a theme
somebody picked is still the theme they get.

**The commands.** `isolinear` and `iso` still run. They say what the tool is
called now, on stderr, and then are `maeslant`.
"""

from __future__ import annotations

#: The directory under the config home the settings file used to live in.
CONFIG_DIR = "isolinear"

#: What every built-in theme's name used to start with (and one was, exactly).
THEME_PREFIX = "isolinear"

#: What the commands were called. Installed beside `maeslant`, in no help text.
COMMANDS = ("isolinear", "iso")


def theme(name: str) -> str:
    """Today's name for a theme that may have been saved under its former one."""
    if name == THEME_PREFIX or name.startswith(f"{THEME_PREFIX}-"):
        return "maeslant" + name[len(THEME_PREFIX) :]
    return name


def main() -> None:
    """The `isolinear` and `iso` commands: a line about the new name, then maeslant."""
    import sys

    # here, not at the top: the settings adapter imports this module for a name
    from .app import main as maeslant

    print(
        f"{COMMANDS[0]} is now maeslant — the same app, under a new name. "
        f"`{COMMANDS[0]}` and `{COMMANDS[1]}` still work for now; "
        "say `maeslant` when you can.",
        file=sys.stderr,
    )
    maeslant()

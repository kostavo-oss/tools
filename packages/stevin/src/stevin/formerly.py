"""The names stevin had when it was deltaplan, and still answers to.

Up to 0.2.0a4 this tool was released as `deltaplan`. Renaming it could not
rename what was already out there, so some of the old name lives on — and this
module is the only place in the package that spells it.

**What is written on tables.** A table deltaplan made carries
`deltaplan.managed`, and that property is how the next run knows the table may
be dropped when its spec goes. stevin reads and writes the same names, so a
workspace doesn't notice the rename: nothing is claimed again, seeded again or
left behind. Changing them would be a migration, not a rename, and it hasn't
been done.

**The project file.** `deltaplan.yml` is still found, after `stevin.yml`.

**The command.** `deltaplan` still runs. It says what it is called now, on
stderr, and then does what `stevin` does — so a script or a pipeline written
for deltaplan keeps working until someone has the time to change a word in it.
"""

from __future__ import annotations

#: Set on every table stevin creates. Only tables carrying it can ever become
#: drop candidates; everything else is reported as unmanaged and left alone.
MANAGED_PROPERTY = "deltaplan.managed"

#: The digest of the rows a seeded table was last loaded with. Comparing this
#: with the spec's is how stevin knows a seed changed without reading a
#: single row back.
SEED_PROPERTY = "deltaplan.seed"

#: Appended to a table's name for the table a rewrite stages its data in.
STAGING_SUFFIX = "__deltaplan_rewrite"

#: Appended to a table's name for its pre-change clone.
BACKUP_SUFFIX = "__deltaplan_backup"

#: What the project file was called. Looked for after `stevin.yml`.
CONFIG_NAMES = ("deltaplan.yml", "deltaplan.yaml")

#: What the command was called. Installed beside `stevin`, and in no help text.
COMMAND = "deltaplan"


def main() -> None:
    """The `deltaplan` command: a line about its new name, then `stevin`."""
    # here, not at the top: the model imports this module for its constants
    from stevin.cli import app, err

    err.print(
        f"[yellow]{COMMAND} is now stevin — the same commands, under a new name. "
        f"`{COMMAND}` still works for now; say `stevin` when you can.[/]"
    )
    app(prog_name="stevin")

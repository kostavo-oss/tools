# 006 — the stevin plugin

**Status:** parked. The owner takes stevin up separately (2026-10-05); nothing in phase one waits
for this, and nothing here is agreed.

## What exists

The plan half of a `stevin` plugin is in the code: it runs the `stevin` command, reads its plan
file, and shows one change per table. stevin is not a dependency of lely. That code is left as it
is — kept working when the contract around it changes ([002](002-plugins.md)), and not extended.

## Notes for when it is taken up

Not requirements; the questions this will have to answer.

- **Apply** is straightforward: hand the approved plan back to `stevin apply`, and pass
  `--allow-destructive` only when lely was given it.
- **Outputs.** What does a stevin step give the steps after it — the names of the tables it
  manages? Under [002/R14](002-plugins.md) they have to be declared.
- **Overview.** stevin can plan and report drift, but it has no command that just lists what it
  manages, which is what [002/R6](002-plugins.md) asks of a plugin.
- **Destroy.** The bundle's resources can be deployed again; a dropped table is its rows. stevin
  has no destroy and, on purpose, never drops what it didn't create. Whether lely's `destroy`
  leaves tables alone, drops them only for targets that say so, or always, is the first thing to
  settle.
- **Its own view.** stevin already renders a plan as a page, which [007](007-ui.md) could show
  as it is.

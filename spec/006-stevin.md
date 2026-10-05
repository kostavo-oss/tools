# 006 — the stevin plugin

**Status:** draft. Phase one, after the Asset Bundle. The plan half is built.

## Why

Tables are the part of a deploy that can't simply be run again, and stevin already plans and
applies them. lely doesn't redo that: it runs stevin at the right place in the order and shows
stevin's plan inside its own.

## Requirements

- **R1** — `uses: stevin`. Options: stevin's project file, its target (lely's when not given), a
  selection of tables, and how to run stevin. *(built)*
- **R2** — stevin is not a dependency of lely. The plugin runs the `stevin` command; a project
  without tables never installs it, and a project with them gets a message that says how when it
  is missing. *(built)*
- **R3** — The contract between the two is stevin's command line and its plan file, not its
  Python modules, so each keeps its own releases. A plan file in a format this lely doesn't read
  is refused with a message that names both versions. *(built)*
- **R4 — Plan.** `stevin plan`, as JSON. One change per table that has something to do; a change
  stevin calls destructive is destructive here, and a rewrite is named in the detail. *(built)*
- **R5 — Apply.** The approved plan is handed back to `stevin apply`, with `--allow-destructive`
  only when lely was given it. A plan that went stale is stevin's to refuse, and lely reports the
  refusal as it is. *(design)*
- **R6 — Overview.** The tables, views and functions stevin manages for this target, by name.
  Whether stevin can answer that today is [D2](#to-decide). *(owner)*
- **R7 — Its own view in the UI.** stevin already renders a plan as a page; the plugin hands that
  to lely's UI instead of having lely draw tables a second time. → [007](007-ui.md) *(proposed)*

## To decide

- **D1 — What `destroy` does to tables.** The bundle's resources can be deployed again; a
  dropped table is its rows. stevin has no destroy of its own, and on purpose never drops what it
  didn't create. Three ways:
  1. *Tables are left alone.* The step is skipped on destroy, and the plan says the tables stay.
  2. *Only for targets that say so* — a dev target's tables go, a prod target's never do.
  3. *Always*, which needs a new command in stevin first.

  *(proposed: 1 for phase one. It is the only one that can't lose data, and 2 can be added
  without breaking it.)*
- **D2 — The overview needs stevin's help.** stevin can plan and it can report drift, but it has
  no command that just lists what it manages. Either stevin gains one, or the plugin's overview
  is limited to what the last plan touched. *(proposed: a small command in stevin — the bundle's
  overview sets the bar, and tables shouldn't be the step you can't see)*

## Done when

- R1–R7 each have a test against the fake `stevin` and the recorded plan files.
- The plugin passes the contract kit, with destroy behaving as D1 settles.
- A table change has been planned and applied through lely on a real target, with the bundle
  before it.

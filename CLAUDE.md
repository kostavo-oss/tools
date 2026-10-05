# CLAUDE.md

`lely`: one plan/apply for a whole Databricks deploy — pre-deploy steps, the bundle,
post-deploy steps. Read `docs/DESIGN.md` first; it is the source of truth. If code and
design disagree, flag it instead of silently picking one.

`spec/` says *what* each piece of work must deliver and when it is done; the design says
*how*. The owner set a new direction on 2026-10-05 that the design doesn't have yet — plugins,
destroy, the bundle as one of them — so **where `spec/` and `docs/DESIGN.md` disagree today, the
spec is right**, and the design is rewritten once the specs are agreed. Before starting any
work, read its spec, and don't build past a "To decide" that is still open — those are the
owner's to answer. A requirement marked *(proposed)* is not agreed either.

## Rules

- The core is pure: config, references, ordering, plan assembly, the approval check and
  renderers do no I/O, no SDK calls, no clock, no env. I/O lives in the CLI runner, the
  workspace client and the steps.
- Domain model: frozen, slotted stdlib dataclasses with tuples.
- The bundle is the Databricks CLI's: ask it (`bundle validate/plan/summary -o json`),
  never reimplement what it resolves. If a bundle resource can manage something, no step
  does.
- A step touches only what its options name; anything else is unmanaged, never removed.
- No destructive change without `destructive`, and none applied without
  `--allow-destructive`.
- Plan files carry no secrets.
- Every Databricks behaviour assumption gets a test and a link to the docs in its
  docstring. If unsure, say so and add a `TODO(verify)` — do not guess.
- Small PR-sized commits, conventional commit messages.

## Commands

Tooling is mise + the Astral stack (uv, ruff, ty) — same as `stevin` and `maeslant`.
Never use pip/virtualenv, black/flake8/isort, or mypy.

## Status

**Milestone 1 (read-only) is done**: `validate`, `steps`, `plan` and `show`, with the
`stevin`, `bundle.run` and `command` steps and steps from a repo file. Its departures
are listed under Milestones in `docs/DESIGN.md`. Work through the milestones in order and
stop after each one to summarise what was built and what was assumed.

`mise run check` is the gate (lint, format check, types, unit tests). There is no
Databricks CLI or workspace in the unit suite:
- `tests/fixtures/cli/` holds the CLI's own recorded outputs, from its acceptance tests.
- `tests/fixtures/stevin-*.json` are real stevin plan files, written by stevin
  against its fake warehouse. They are the contract between the two tools.
- `tests/fake_databricks.py` and `tests/fake_stevin.py` answer from those and fail
  loudly on anything else.

**lely was sluis** until 2026-10-05, when the suite took its names from Dutch engineers and
works (stevin, lely, maeslant). It had never been published, so nothing answers to the old
name: the config file is `lely.yml`, the plugin entry-point group is `lely.steps`, the
errors descend from `LelyError`, and a `command` step sees `LELY_TARGET`, `LELY_STEP` and
`LELY_PHASE`. The step for tables is `stevin` and runs the `stevin` command. The recorded
plans in `tests/fixtures/stevin-*.json` still carry `deltaplan.managed` — that is the
property stevin really writes onto tables, and it kept its name on purpose.

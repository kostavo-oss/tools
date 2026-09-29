# CLAUDE.md

`sluis`: one plan/apply for a whole Databricks deploy — pre-deploy steps, the bundle,
post-deploy steps. Read `docs/DESIGN.md` first; it is the source of truth. If code and
design disagree, flag it instead of silently picking one.

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

Tooling is mise + the Astral stack (uv, ruff, ty) — same as `deltaplan` and `isolinear`.
Never use pip/virtualenv, black/flake8/isort, or mypy.

## Status

**Milestone 1 (read-only) is done**: `validate`, `steps`, `plan` and `show`, with the
`deltaplan`, `bundle.run` and `command` steps and steps from a repo file. Its departures
are listed under Milestones in `docs/DESIGN.md`. Work through the milestones in order and
stop after each one to summarise what was built and what was assumed.

`mise run check` is the gate (lint, format check, types, unit tests). There is no
Databricks CLI or workspace in the unit suite:
- `tests/fixtures/cli/` holds the CLI's own recorded outputs, from its acceptance tests.
- `tests/fixtures/deltaplan-*.json` are real deltaplan plan files, written by deltaplan
  against its fake warehouse. They are the contract between the two tools.
- `tests/fake_databricks.py` and `tests/fake_deltaplan.py` answer from those and fail
  loudly on anything else.

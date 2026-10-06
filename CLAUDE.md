# CLAUDE.md

`lely`: one plan for a whole Databricks deploy. It plans, applies and destroys an ordered list
of steps, each done by a plugin, and keeps no state. The Asset Bundle is one of those plugins.

`spec/` says *what* each piece of work must deliver and when it is done; `docs/DESIGN.md` says
*how* it is built. Read the spec of a piece before working on it. Since 2026-10-05 the two
agree: if they disagree, or the code disagrees with either, flag it instead of silently picking
one. Don't build past a "To decide" that is still open — those are the owner's to answer.

## Rules

- The core is pure: config, references, the wiring, plan assembly, the approval check and the
  renderers do no I/O, no SDK calls, no clock, no env. I/O lives at the edges: the plugins, the
  Databricks CLI runner, the workspace client, `git`, the command line.
- No module outside `src/lely/steps/` knows a plugin by name — the bundle included.
- Domain model: frozen, slotted stdlib dataclasses with tuples.
- The bundle is the Databricks CLI's: the `bundle` plugin asks it
  (`bundle summary/plan -o json`, `deploy --plan`, `destroy`) and never reimplements what it
  resolves. Not `bundle validate`: on a real workspace it creates a folder, and a plan changes
  nothing. If a bundle resource can manage something, no plugin does.
- A step is given its own options and a way to reach the workspace, nothing else. What it takes
  from another step is `${steps.<name>.<output>}` in its `with:`, from a step above it.
- A plugin declares its outputs, touches only what its options name, and destroys only what it
  can show is its own.
- No destructive change without `destructive`, and none applied without `--allow-destructive`.
- Nothing that changes a workspace runs unasked. A refusal is a `Refused` (exit 2); a failure
  is any other `LelyError` (exit 1).
- Plan files carry no secrets. A value from the environment is a `Secret`.
- Nothing a plan says is Markdown or markup where it is shown: in a terminal its control
  characters are made visible, on GitHub it stands in a block or a code span, on the page it
  is escaped — and a plugin's view is written again from a short list of elements.
- Showing a plan runs none of the project's code: `show` and `ui` load no plugin.
- No raw invisible character in any file: write its escape. A test holds the repository to it.
- A file lely writes is written beside its place and moved there (`cli._write`): never
  through a link, never half.
- Every Databricks behaviour assumption gets a test and a link to the docs in its
  docstring. If unsure, say so and add a `TODO(verify)` — do not guess.
- Small PR-sized commits, conventional commit messages.

## Commands

Tooling is mise + the Astral stack (uv, ruff, ty) — same as `stevin` and `maeslant`.
Never use pip/virtualenv, black/flake8/isort, or mypy.

`mise run check` is the gate (lint, format check, types, unit tests). `ruff format` also
formats the Python in Markdown code blocks, so the gate covers `docs/` and `spec/`. When
chaining the gate in a shell, a pipe hides a failing test: check the test count, not the exit
code of `tail`.

## Status

**Phase one is built (2026-10-05) and was run on a real workspace once (2026-10-06).** `validate`, `steps`, `schema`, `plan`,
`show`, `apply`, `destroy`, `status` and `doctor`; the `bundle`, `command` and `bundle.run`
plugins and plugins from a repo file; the config in `lely.yml` or `pyproject.toml`.

Not built, or not proven:

- **One run on a real workspace is a first proof, not a track record.** What it settled, what
  it corrected (the CLI goes to the bundle's host with the credentials at hand; `bundle
  validate` writes, so the plugin uses `bundle summary`) and what it couldn't show is in
  `spec/004-asset-bundle.md`, "Run on a workspace". What is still assumed is a `TODO(verify)`
  in `src/lely/steps/bundle.py`.
- **`stevin` is parked** (`spec/006-stevin.md`): its plan half works; `apply` refuses a project
  that uses it. The owner takes it up separately — don't extend it.
- **GitHub is built (2026-10-06) and unproven**: `--github` and `-f md`
  (`spec/008-github-actions.md`, `docs/GITHUB.md`), tested against `tests/fake_github.py`. No
  pull request in a real repository has carried a plan yet, and the workflows in the docs
  have never run.
- **The page is built (2026-10-06)**: `lely ui`, `StepPlan.view`, a run's record with
  `apply -o` (`spec/007-ui.md`). Looked at in a browser and reviewed once. Whether a plugin's
  view stays in its frame is asked of a real browser: `uv run pytest tests/browser`. It needs
  Chrome and skips without it; `mise run check` doesn't run it, CI does (its runners have
  Chrome). Run it after any change to `render/html.py`.

There is no Databricks CLI or workspace in the unit suite:

- `tests/fake_databricks.py` is the CLI as a fake, as a program and in process. It answers from
  recordings, or simulates a bundle in a workspace kept in a folder: `plan`, `deploy`,
  `summary`, `destroy`, `run`. What it simulates is what lely *believes* the CLI does.
- `tests/fixtures/cli/` holds the CLI's own recorded outputs, from its acceptance tests.
- `tests/fake_github.py` is a pull request's comments in memory, and a run's environment. What
  it simulates is what lely *believes* GitHub does.
- `tests/fixtures/stevin-*.json` are real stevin plan files, written by stevin against its fake
  warehouse; `tests/fake_stevin.py` answers from them.
- `tests/project.py` is the scenario most tests share.

**lely was sluis** until 2026-10-05, when the suite took its names from Dutch engineers and
works (stevin, lely, maeslant). It had never been published, so nothing answers to the old
name. The recorded plans in `tests/fixtures/stevin-*.json` still carry `deltaplan.managed` —
that is the property stevin really writes onto tables, and it kept its name on purpose.

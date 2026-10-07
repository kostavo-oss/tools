# CLAUDE.md

`stevin`: safe plan/apply migrations for Unity Catalog tables and schemas. Read `docs/DESIGN.md` first; it is the source of truth. If code and design disagree, flag it instead of silently picking one.

## Rules

- Differ and planner are pure: no I/O, no SDK imports, no clock, no env.
- Domain model: frozen, slotted stdlib dataclasses with tuples. Pydantic/msgspec only in the loader.
- Never generate SQL by string-concatenating unquoted identifiers. One `quote_ident()` helper, used everywhere.
- Anything not modelled on a live table is reported as unmanaged, never diffed away.
- No destructive step without the `destructive` risk class.
- Every Databricks behaviour assumption gets a test and a link to the docs in the test docstring. If unsure about a behaviour, say so and add a `TODO(verify)` — do not guess.
- Small PR-sized commits, conventional commit messages.

## How changes land

`main` is protected: every change is a pull request, and the `ci` checks must
pass (they enforce for admins too) — eleven jobs: lint + types, the unit tests
on Python 3.11–3.14 on Linux and on 3.14 on macOS and Windows, the unit tests
on the lowest dependency versions `pyproject.toml` allows, actionlint, the
strict docs build, and the wheel + sdist build. A job added to `ci.yml` is not
required until it is added to the branch protection. `integration` — the live suite against the
workspace, ~40 minutes — runs on every pull request that touches code, and nightly;
it isn't required, so read it before merging anything that changes the SQL stevin
sends. Its credentials are GitHub environment secrets in `databricks-test`.

A release is a version: bump `version` in `pyproject.toml` and move the CHANGELOG's
`[Unreleased]` notes under it in a PR. Merging that PR is the release — `release.yml`
watches `pyproject.toml` on `main`, publishes to PyPI and makes the tag. Ask before
merging a bump PR; it ships. CONTRIBUTING.md has the details.

## Layout

```
src/stevin/
  model/          types.py, table.py, view.py, function.py, schema.py, volume.py,
                  change.py, plan.py — frozen dataclasses; Relation = any of the five
  typeparser.py   Databricks type strings -> the type tree
  sql.py          quote_ident() and literals: every identifier goes through here
  loader.py       stevin.yml and YAML specs -> model; the only validator
  sqlspec.py      .sql specs (sqlglot) -> the same model
  features.py     what each spec format can say; docs/formats.md is made from it
  spec_schema.py  the editors' JSON Schema, from the loader's key sets
  bundle.py       a Databricks Asset Bundle's targets and objects; asks the CLI
  manage.py       what a project hands to another tool (`manage:`)
  formerly.py     the names from when this was deltaplan — the only place they are
  connect.py      Connection: the workspace client and the warehouse
  introspect.py   live state from Unity Catalog; WarehouseRunner
  ddl.py          column details out of SHOW CREATE TABLE
  differ.py       desired minus live -> changes            (pure)
  planner.py      changes -> ordered steps with risk       (pure)
  planning.py     specs + a warehouse -> a plan; ownership, order, orphans
  executor.py     runs a plan: lock, stale check, skip, resume, restore points
  history.py      the runs / steps / lock tables; MemoryHistory, NoHistory
  adopt.py        live state back into a spec file
  yamledit.py     editing YAML text through its node tree, for adopt
  probes.py       what stevin assumes about Databricks, as runnable probes
  doctor.py       the checks behind `stevin doctor`
  advice.py       what stevin knows about common Databricks refusals
  api.py          the verbs as functions: plan, apply, drift, adopt, verify, …
  cli.py          the thirteen commands: argument parsing and printing
  serve.py        the localhost page server for `stevin ui`
  errors.py       StevinError, the root of every deliberate error
  render/         rich.py, markdown.py, json.py, html.py, compare.py, labels.py
tests/
  unit/           offline: fake warehouse, snapshots, the docs' pictures
  integration/    live workspace only
  snapshots/      golden plans
  transcripts/    recorded workspace answers — none yet
  fake_warehouse.py, screens.py, transcript.py, messy_schema.py, helpers.py
action.yml, action/upsert_comment.py   the GitHub Action and its comment script
deltaplan-shim/   the last `deltaplan` release for PyPI; published by no workflow
docs/             DESIGN.md (source of truth) + the mkdocs site
examples/
```

## Commands

Tooling is mise + the Astral stack (uv, ruff, ty) — same as `lely` and `caland`.
Never use pip/virtualenv, black/flake8/isort, or mypy.

```
mise install                   # pinned Python + uv
uv sync
uv run pytest tests/unit
uv run pytest -m integration   # needs DATABRICKS_HOST / token / warehouse id
uv run ruff check . && uv run ruff format --check .
uv run ty check
```

`mise run check` is the full gate (lint + format check + types + unit tests);
`mise tasks` lists the rest. Docs: `mise run docs` (mkdocs-material, published to
Pages). Releases are version-driven from `pyproject.toml` — see CONTRIBUTING.md.

## Milestone 1 (read-only) — done

All eight items are built, lint/type/test clean, with golden plans in
`tests/snapshots/` and a live suite in `tests/integration/`. Deliberate
departures from this document, each explained in the commit that made it:
`ty` instead of pyright; a hand-written validator in the loader rather than
Pydantic/msgspec, so errors carry file:line:column; `stevin.yml` invented for
the project/target config; nested YAML types extended from struct to array and
map; `sql.py` added for `quote_ident()`; rewrites classified but not generated (milestone 3); the Markdown
renderer deferred to milestone 4.

**Milestone 2 (apply) is done too**: `executor.py`, `history.py` (the design's
runs/steps/lock tables), `apply` and `force-unlock`. Two more departures worth
knowing: the design's per-step precheck/postcheck queries are replaced by
`differ.is_applied()`, which asks the *model* whether a change is already true
of the live table — it reuses tested code instead of inventing SQL we cannot
verify (`precheck` survives as a precondition guard, e.g. SET NOT NULL); and
`history.py` is a module the design doesn't have, because putting the
history tables inside `executor.py` would have made one file do two jobs.

Testing without a workspace: `tests/fake_warehouse.py` is an in-memory catalog
that interprets stevin's own SQL, so plan → apply → re-plan can be asserted
offline for every change kind. It proves our SQL matches our intent; only
`tests/integration/` proves Databricks agrees. Read `docs/testing.md` before
adding a test, and keep the fake's `FakeSqlError` loud — a statement shape it
doesn't know must fail, not pass.

**Milestone 3 (rewrites) is done.** A table with a rewrite-class change is
rebuilt whole rather than patched: stage the converted data, REPLACE the table
from the staging table (identity and history kept, no empty window), put back
what a query result can't carry with ordinary ALTERs, drop the staging table.
Two departures worth knowing: the design's single `CREATE OR REPLACE TABLE …
AS SELECT` is staged in two statements, because staging makes the expensive
step repeatable and checkable before the table is touched (a self-referencing
RTAS does work — `test_live_assumptions.py` runs one); and `using:` is a new spec hint for conversions stevin won't
invent. A nested field's NOT NULL is an ordinary ALTER (verified live, against
the design's guess), so a rewrite puts it back like everything else.

**The rest of the design's safety model is in too**: ownership claims (a spec
for someone else's table plans a visible `claim_table`), strict schemas (managed
tables whose spec is gone become `drop_table`, destructive), and
`plan --clone` for a SHALLOW CLONE before risky steps. The specs-to-plan
pipeline lives in `planning.py` (a module the design doesn't have),
because `plan`, `drift` and the Action all need it. One departure: the design
says the mode is per schema; `stevin.yml` has a per-schema `schemas:` map
*and* keeps the target's `mode` as the default for unlisted schemas.

**Milestone 4 (CI) is done**: `render/markdown.py`, `show`, `drift` (exit 0/2/1),
and a composite GitHub Action — `action.yml` at the repo root, with its comment
script in `action/upsert_comment.py` (stdlib only, tested against a fake API).
Change labels are shared by both renderers in `render/labels.py`. The Action
must never interpolate `${{ }}` into a `run:` script — `test_action.py`
enforces it.

**Milestone 5 (governance) is done**: column tags, grants (per principal),
column masks and row filters (additive, never removed, never rewritten), and
views (`model/view.py`; `Relation = Table | View`; tables and views share
`Securable`). Every milestone in DESIGN.md is built.

Since then, beyond the design: schema creation, hooks and backfills, identity /
generated / default columns, foreign keys, SQL functions (`model/function.py`;
`Relation = Table | View | Function`) and Asset Bundle targets (`bundle.py`, a
module of its own: it reads someone else's YAML leniently,
which `loader.py`'s strict validator shouldn't). A bundle is resolved by asking
the Databricks CLI (`bundle validate -o json -t <target>`), whose answer carries
the variables, the lookups and the names a deploy really uses. A CLI that is
there and fails stops the command (`BundleError`); reading the file is what a
machine with no CLI gets — and what `validate` always does, because it runs
nothing — and says *unknown* rather than guessing. Offline tests hide a real
`databricks` and a real workspace: PATH, every `DATABRICKS_*` variable and
`~/.databrickscfg` (`tests/unit/conftest.py`). External tables are out of
scope for now — managed tables only.

**SQL specs** (`sqlspec.py`, `features.py`) overturn a DESIGN.md non-goal, by
the owner's decision (noted there). The rule is fixed: a SQL spec supports
exactly what sqlglot parses into structure — never hand-parse around sqlglot to
add a feature to SQL; add it to YAML and mark it `—` for SQL in `FEATURES`.
Every row of `FEATURES` is a test, and `docs/formats.md` is generated from it.

**Also since:** schemas and managed volumes as specs (`model/schema.py`,
`model/volume.py` — never dropped: nothing marks them as stevin's, and a
dropped volume loses its files); `spec_schema.py`, the editors' JSON Schema,
built from the loader's key sets (every accepted key set is a named constant
in `loader.py` — add keys there, never inline); `ddl.py`, which reads column
details from `SHOW CREATE TABLE` because `information_schema.columns` doesn't
report identity, generation or defaults on a live workspace. Introspection
reads only described tables in full and runs per-table queries in parallel.

**The docs' terminal pictures are real output**: `tests/screens.py` runs the CLI
against the fake warehouse and records SVGs into `docs/assets/screens/`, and
`test_screens.py` fails when one is stale — `mise run screens` remakes them.
Anything a user sees gets a scene; a new feature gets a section in
`docs/features.md`. Writing the scenes found six output bugs, so look at the
pictures, not just the diff.

**Since 0.1.0a6** (the feature set the owner settled on after a competitor survey):
`stevin apply` without a plan file — plan, show, ask, run — and `--select`; a first
`import` writes `stevin.yml`; owners; partitioning, including the move to liquid
clustering; removing a tag or property with `null`; `command: apply` in the Action.
**The scope is closed.** stevin is for engineers who need a data model in Unity
Catalog, and it manages what a spec can declare about one: tables, views, SQL
functions, schemas and managed volumes, and what governs them — tags, grants,
column masks, row filters and owners. It puts in place what a spec says; it
does not decide what a spec may say. So it is not a policy engine: no rules
about who may have what, no approvals, no audit beyond its own run history.
Deliberately skipped, with reasons in the memory `product-focus`: policy rules
in `validate`, a `protect:` flag, a breaking-change flag, a `restore` command,
ABAC, catalogs, external tables.

**The Databricks assumptions are `probes.py`**, not a test file: `stevin verify`
runs them in a user's own scratch schema, and
`tests/integration/test_live_assumptions.py` is a thin parametrised caller of the
same list. A new assumption about Databricks goes in `PROBES`; a new assumption
about *stevin* is still a test. **`adopt.py` + `yamledit.py`** are the way back:
`stevin adopt` writes live state into the spec file that already describes an
object by editing the YAML text through its node tree, so comments, `${var}` and
spec-only hints survive.

**Transcripts** are the third level between the fake and the live suite — built,
and **empty until a live run records them**: `tests/transcripts/` holds only its
README, so the replay test skips and the layer proves nothing yet.
`STEVIN_RECORD=tests/transcripts` on a live run writes what the workspace
answered per probe (`tests/transcript.py`), and `tests/unit/test_transcripts.py`
replays each one offline. A statement a recording doesn't cover fails loudly, like
`FakeSqlError`. Only a probe that held is written.

**Live verification** runs in CI on every pull request (`integration.yml`), and by
hand with `uv run pytest -m integration` and the workspace env (see memory). By hand,
run it from a separate `git worktree` of the commit under test — editing files mid-run
mixes old and new modules. Before building on a Databricks behaviour, probe it on the
workspace in a throwaway `stevin_probe_*` schema and drop the schema after.

The `TODO(verify)` list was settled against a live workspace on 2026-09-19
(`tests/integration/test_live_assumptions.py`). Three are open, and
`grep -rn "TODO(verify)" src/` is the list: a seed's `INSERT OVERWRITE …
(columns) VALUES …`, which no workspace has taken from stevin yet
(`planner._load_seed`; `test_live_seeds.py` and a probe are waiting for a live
run); `CLUSTER BY AUTO` without predictive optimization
(`planner._clustering_clause`); and sending a step with `wait_timeout="0s"`
(`introspect.WarehouseRunner`), the API's documented asynchronous mode, which would
give Ctrl-C a statement id from the first moment — not done until a workspace has
taken it. `docs/testing.md` says the same to users. A new
Databricks assumption still gets a `TODO(verify)` until a live test settles it.

**stevin was deltaplan** up to 0.2.0a4 — renamed on its way into the Kostavo tools
(`kostavo-oss`: stevin, lely, caland). The rename changed what people type and read,
never what is sent to Databricks: `formerly.py` is the one module that spells the old
name, and `test_formerly.py` keeps it that way. It holds the four names written onto
tables in a workspace (`deltaplan.managed`, `deltaplan.seed`, the `__deltaplan_rewrite`
and `__deltaplan_backup` suffixes — **do not rename them**: that orphans every table that
carries one, and is a migration the owner hasn't decided on), the project file's former
names (still found), and the `deltaplan` command (still installed; it says its new name
on stderr and runs stevin). The GitHub secret `DELTAPLAN_TEST_CATALOG` kept its name too.
`deltaplan-shim/` is the last `deltaplan` release for PyPI — it installs stevin — and is
not published by any workflow.

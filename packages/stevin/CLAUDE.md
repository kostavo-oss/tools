# CLAUDE.md

`stevin`: plan and apply for the Unity Catalog tables, and the access around them, that
no transformation tool owns. The root `CLAUDE.md` has what holds for every package, how
changes land and how a release is made.

## Where a fact lives

One place per fact. Write a fact where it lives, and link to it from anywhere else.

| The fact | Its one place |
|---|---|
| What stevin is for, what it will not do, when it is no longer needed | `README.md` |
| What must be true of the code | `RULES.md`: numbered rules, each with the tests that hold it |
| Why it is so, and what it replaced | `DECISIONS.md`: appended to, never edited |
| How it works: the pipeline, the model, a plan, ownership | `docs/how-it-works.md` |
| How to use it, and the safety model as a user meets it | `docs/`, and only there |
| How it is tested, what ran on a real workspace, what is still open | `docs/testing.md` |
| What Databricks does that the code leans on | a probe in `src/stevin/probes.py`, or the docstring that leans on it |
| What changed for a user, per release | `CHANGELOG.md` |
| An idea that is wanted and not built | a GitHub issue |
| How it came to be | git |

There is no design document. If the code and a page disagree, say which is wrong.

## Rules of working

- **A change to behaviour changes its rule, in the same pull request.** Change the rule
  in `RULES.md` or add one with the next number of its area, name the tests that hold
  it, and cite it in each of them as `# RULES.md: OWN-2.` The root's
  `tests/test_rules.py` fails when a citation, a rule and a test disagree.
- **A rule states the whole promise.** What the code does not keep yet gets an issue,
  and the rule says `Not kept yet:` with its number.
- **A decision goes into `DECISIONS.md` only with its reason** or with what was put
  aside, appended, never edited.
- The rules broken most easily: the differ and the planner are pure and the model is
  frozen dataclasses (PLAN-1); every identifier goes through `quote_ident()` (SQL-1);
  what is not modelled is reported and never diffed away (OWN-5); a step that can lose
  data is `destructive` (RISK-1); the Action puts no `${{ }}` in a `run:` (ACT-1).
- An assumption about Databricks is a probe in `PROBES` with a docs link; an assumption
  about stevin is a test (DBX-1). If unsure, add a `TODO(verify)` and say so: do not
  guess. `grep -rn "TODO(verify)" src/` is the open list.
- A SQL spec supports what sqlglot parses into structure. Never parse around sqlglot:
  add the feature to YAML and mark it `—` for SQL in `FEATURES`. Every key set the
  loader accepts is a named constant in `loader.py`, which the editors' schema is built
  from: add a key there, never inline.
- `formerly.py` holds four names that are written onto tables in workspaces. Do not
  rename them (NAME-1).

## What is not obvious

- **The fake warehouse must fail loudly** (TEST-1). `tests/fake_warehouse.py` interprets
  stevin's own SQL, and a statement it does not know raises `FakeSqlError`: teach it the
  statement, never let it pass. It proves stevin's SQL matches stevin's intent. Only
  `tests/integration/` proves Databricks agrees.
- **The docs' terminal pictures are real output** (TEST-2). After changing anything a
  user sees, run `mise run screens` and look at the pictures. A new feature gets a
  scene in `tests/screens.py` and a section in `docs/features.md`. Two more files are
  made by a command and tested for staleness: `uv run python -m stevin.features
  docs/formats.md` and `uv run python -m stevin.spec_schema docs/schema`.
- **Never start a live run without being asked to** (TEST-3, TEST-4). The workspace is
  its owner's own, and Unity Catalog counts a metastore's tables with an estimate that
  comes down slowly: on 2026-10-10 fifteen runs in a day left the owner unable to
  create a table. Ask first, and say which suite and why. Never a full run for what
  `smoke` or `-k` can check, never more than one full run a day, and never a schedule
  or a pull-request trigger on `integration.yml`. `docs/testing.md` says how to write a
  live test that keeps to the budget.
- `render/base.css` is the look shared with lely's and caland's page, byte for byte:
  change all three in one pull request (the root's `tests/test_workspace.py`).
- `deltaplan-shim/` is the last `deltaplan` release for PyPI. No workflow publishes it.

## Layout

```
src/stevin/
  model/        the frozen dataclasses: types, table, view, function, schema, volume,
                change, plan; policy and access are read, never written
  loader.py, sqlspec.py, typeparser.py   stevin.yml, YAML and SQL specs -> the model
  features.py, spec_schema.py   what each format can say; the editors' JSON Schema
  bundle.py, contract.py, owned.py, manage.py   a bundle, a data contract, whose tables
                are whose, what a project hands to another tool
  connect.py, introspect.py, ddl.py   the connection; live state -> the model
  differ.py, planner.py   changes, then ordered steps with risk          (pure)
  planning.py   specs + a warehouse -> a plan: ownership, order, orphans
  executor.py, history.py   run a plan; the runs, steps and lock tables
  adopt.py, yamledit.py   live state back into a spec file's text
  probes.py, doctor.py, access.py, advice.py   verify, doctor, access, refusals
  api.py, cli.py, serve.py   the verbs as functions, the fourteen commands, the ui page
  sql.py, formerly.py, errors.py   quoting, the old names, StevinError
  render/       rich, markdown, json, html, compare, labels, access; base.css
tests/unit/         offline: the fake warehouse, snapshots, the docs' pictures
tests/integration/  a live workspace only; its conftest.py counts the tables
tests/              fake_warehouse.py, screens.py, transcript.py, table_budget.py, helpers
action.yml, action/   the GitHub Action and its comment script
docs/               the site's pages (mkdocs.yml); assets/screens and schema are generated
examples/           two projects that a test validates
```

## Commands

uv, ruff and ty. Never pip, black or mypy.

```sh
uv run pytest tests/unit      # from packages/stevin: the offline tests
uv run ty check               # from packages/stevin: the types
uv run ruff check . && uv run ruff format --check .   # from the root
uv run pytest tests           # from the root: the rules file, and what holds across packages
uv run --group docs mkdocs build --strict             # from the root: the site
```

`mise run check` at the root is the gate for every package.

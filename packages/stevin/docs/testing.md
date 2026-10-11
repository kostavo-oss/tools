# Testing without a workspace

stevin generates SQL for a system most contributors can't run on a laptop, and
that CI shouldn't need credentials to check. The suite is built in four layers, and
each one is honest about what it can and cannot prove.

```sh
uv run pytest tests/unit        # layers 1 and 2, and 3 once it is recorded — offline, every PR
uv run pytest -m "integration and smoke"   # layer 4 — real workspace, by hand
```

| Layer | Proves |
|---|---|
| Unit tests | the pure middle of the pipeline does what it says |
| The fake warehouse | stevin's SQL matches **stevin's reading** of the manual |
| Transcripts | what **Databricks answered**, on the day they were recorded — built, and **empty until a live run records them** |
| The live suite | that it still does |

<hr class="dp-rule">

## 1. Unit tests

The type parser, loader, differ and planner are pure functions, so they are tested the
ordinary way: inputs in, values out, with golden plans in `tests/snapshots/` for
anything shaped like a document.

This is where most of the tests live, and it is only possible because the middle of the
pipeline does no I/O.

No unit test can reach a workspace, also on a laptop that is signed in to one:
`tests/unit/conftest.py` hides the Databricks CLI, every `DATABRICKS_*` variable and
`~/.databrickscfg` from every test.

Which tests hold which promise is written down:
[RULES.md](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/RULES.md)
names, under each rule, the tests that hold it, and each of those tests names the rule.

## 2. Convergence against a fake warehouse

`tests/fake_warehouse.py` is an in-memory Unity Catalog. It holds `Table` models,
answers the introspector's `information_schema` and `DESCRIBE` queries by rendering
them into the row shapes the real API returns, and **interprets the statements the
planner generates** by mutating those models.

That closes the loop offline:

```python
plan = build_plan(diff(desired, live))  # what we would do
run(plan, fake)  # do it
assert diff(desired, live_now(fake)) == ()  # nothing left to do
```

`tests/unit/test_convergence.py` makes that assertion for every kind of change —
creates, nested adds, renames, widenings, drops, constraints, reordering — and
`tests/unit/test_executor.py` uses the same fake to test skip, resume, failure,
locking and the destructive gate.

**What this proves.** That every statement stevin emits says what the change it came
from meant; that a plan closes the diff it was built from; that `is_applied` — the
executor's idempotency check — agrees with the differ; and that the executor's own
machinery behaves. In milliseconds, with no credentials.

!!! warning "What it does not prove"
    The fake implements *stevin's* reading of the Databricks manual. If we have
    misread it, the fake misreads it the same way and the tests still pass. It cannot
    tell you that Databricks accepts a statement, that a widening is permitted, or that
    a nested rename works.

    Anything the fake doesn't recognise raises `FakeSqlError` rather than passing
    quietly, so a new statement shape can't slip through untested — but a *wrong*
    statement the fake also gets wrong will sail through. That is what layer 3 is for.

## 3. Transcripts: what the workspace actually answered

The layer above proves that stevin's SQL matches stevin's reading of the manual.
Where that reading is wrong, the fake is wrong in the same direction and the offline
suite agrees with the mistake. A transcript is the answer to that.

!!! warning "Built, and empty"
    No transcript has been recorded yet: `tests/transcripts/` holds its README and
    nothing else. The recorder and the replay are there and tested, and the test that
    replays the recordings skips itself while there are none — so today this layer
    proves nothing about Databricks. What follows is how it works once a live run has
    written them.

One live run writes down every statement it sent and the rows or the error that came
back, per assumption. `tests/unit/test_transcripts.py` then replays each recording
through the probe it was recorded for — offline, with no credentials — so an assumption
keeps being checked against **answers Databricks really gave**, between live runs.

```sh
STEVIN_RECORD=tests/transcripts \
  uv run pytest -m integration tests/integration/test_live_assumptions.py
```

Only a probe that held is written: one that didn't is something to fix in the code, and
a transcript of it would assert the mistake. What is masked is only what is new on every
run — the schemas the run makes, and the principal a grant names — and nothing else is
touched, so the diff of a transcript is the diff of what Databricks answers. Read it.

A statement the transcript hasn't got **fails**, with the statement in the message: a
recording that no longer covers what stevin sends has stopped being evidence about
it, and needs recording again. See `tests/transcripts/README.md`.

A transcript says what was true when it was recorded. That is one thing more than the
fake can say, and one less than the live suite — which is why the live suite stays.

## 4. Integration tests

`tests/integration/` is the only source of truth about Databricks. Each test works in a
schema the suite makes and drops: one of its own when it changes a table, one its module
shares when it only reads. They are marked `@pytest.mark.integration` and skip themselves
without credentials, so forks and laptops stay green. In CI they run only when somebody
starts them: [never on a schedule or a pull request](#when-the-suite-runs).

They assert the things nothing else can:

- a table created from a spec reads back as that spec;
- plan → apply → re-plan is empty, against the real thing;
- `DROP COLUMN` really is refused until column mapping is on;
- every widening `widens()` claims is one Databricks accepts;
- the history and lock SQL — `MERGE`, `INTERVAL`, `current_user()` — is valid;
- **dogfooding**: `tests/messy_schema.py` builds a schema the way a real team ends up
  with one — years of `ALTER`s, masks, a Python UDF, legacy partitioning, awkward names —
  and `test_live_dogfood.py` imports it, requires a plan of nothing but ownership
  claims, adopts it, and changes it. When you meet a real-world table stevin
  misreads, add its shape to the messy schema.

Every Databricks behaviour stevin relies on should have a test here and a link to the
documentation in its docstring. Where a behaviour is assumed but unverified, the code
says `TODO(verify)` rather than pretending.

### What the live suite has not settled

Most of what stevin assumes about Databricks has been run against a workspace: the
`TODO(verify)` list was settled on 2026-09-19, and a seed's load — `INSERT OVERWRITE …
(columns) VALUES …` — on 2026-10-10 (`tests/integration/test_live_seeds.py`, and the probe
*a seed's INSERT OVERWRITE with a column list is accepted*). Five things are still open.
They are six `TODO(verify)` marks in the source, because reading policies has two:

- **`CLUSTER BY AUTO` without predictive optimization.** It was on in the workspace this
  was tested in (`planner._clustering_clause`); the probe *CLUSTER BY AUTO is accepted
  and reads back* answers it for the workspace in front of you.
- **Sending a step without waiting for it** — not done yet. `apply` waits up to 30
  seconds for a statement's first answer, and an interrupt in that time has no statement
  id to cancel by; `apply` says so when it happens. Sending with `wait_timeout="0s"` is
  the Statement Execution API's documented way to get the id at once
  (`introspect.WarehouseRunner`). It changes how every step is sent, so it waits for a
  run against a workspace.

- **The rest of a policy's details.** Reading ABAC policies was settled on 2026-10-10
  (below), for the one kind of policy the live suite makes: a row filter for one
  principal. Still read from [the manual](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-describe-policy) alone are `DESCRIBE POLICY`'s labels
  `Except Principals`, `When Condition`, `Match Columns` and `On Column` (the last a
  guess from the others), how several principals are listed (stevin splits on commas),
  the values for a column mask policy and for a policy on a catalog, and what a refusal
  of `SHOW EFFECTIVE POLICIES` looks like (`introspect.Introspector._policies` and
  `._describe_policy`). The suite makes nothing outside its scratch schema, has only
  `account users` to name, and a `MATCH COLUMNS` condition wants a governed tag. Where a
  label is wrong, a plan still names the policy and where it is defined.

- **A rewrite of a table under an ABAC policy.** Not tried on a workspace: what a
  `CREATE OR REPLACE TABLE … AS SELECT` reads and writes for a principal a row filter
  policy or a column mask policy applies to. From the manual, stevin expects two things.
  The statement reads the table as that principal sees it, so the copy holds fewer rows
  or masked values. And the staging table is a new table, which a policy defined on the
  table does not cover. So stevin refuses the rewrite (`planner._Planner._rewrite`), and
  neither consequence has been seen. Whether a `SHALLOW CLONE` of such a table is
  accepted, and whether the policy reaches the clone, is not tried either: `--clone` is
  refused for it. There is no probe for this. It would have to create a policy, and
  one that applies to the principal that runs `verify`.

- **A grant inherited from a catalog.** `stevin access` reads where a privilege is
  granted from `table_privileges.inherited_from`. `NONE` for the table's own and
  `SCHEMA` for one on its schema were read from a workspace on 2026-10-10
  (`tests/integration/test_live_access.py`, and the probe *table_privileges says where
  an inherited grant comes from*). `CATALOG` is read the same way
  (`introspect.Introspector.privileges`), and the suite grants nothing outside its
  scratch schema, so no workspace has said it to stevin. Another value is shown as the
  workspace spelled it.

`stevin verify` runs the first of these as a probe in a workspace of your own.

**A key of `owned_elsewhere` with a bundle reference — not tried on a workspace.** The
unit tests hand stevin the mapping the Databricks CLI prints for a target
(`tests/unit/test_owned_elsewhere.py`). That the CLI names a development target's
schema `dev_<user>_…` was read from a real CLI (`tests/integration/test_live_bundle.py`).
No live run has planned a project whose `owned_elsewhere` names a schema by that
reference. The same holds for a key of `schemas:` (`tests/unit/test_schema_modes.py`).

**Reading ABAC policies — settled 2026-10-10.** A SQL warehouse accepts `SHOW EFFECTIVE
POLICIES ON TABLE` and `ON SCHEMA` and answers in the eight columns
[the manual](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-show-policies) lists; `Policy Type` read `ROW_FILTER` and `on_securable_type` `SCHEMA` or
`TABLE`. `DESCRIBE POLICY`, which the manual calls "a formatted report", is one row per
property in two columns, `info_name` and `info_value`, with the function under an
indented `  Function Name`. Three probes hold it: *SHOW EFFECTIVE POLICIES lists a
table's policies in the documented columns*, *a table under no policy lists none,
without an error* and *DESCRIBE POLICY says a policy's function and principals*.

To read a policy back, the first and the last of those probes create one on a scratch
table of their own with `CREATE POLICY` and drop it — the only place stevin's code
writes a policy — which takes `MANAGE` on that table and a workspace with ABAC;
elsewhere they come out *unknown*. Because stevin otherwise never writes a policy, they
are marked (`Probe.creates_policy`) and `stevin verify` runs them only with
`--create-policy`; a plain `verify` runs the one that only reads, and says the other two
were left out. The live suite runs all three, and
`tests/integration/test_live_policies.py` does the same for the feature itself: a
policy made by hand on a scratch schema, then a plan, a conflict warning, `drift` and
`doctor` read against it. It skips, with the workspace's own sentence, where `CREATE
POLICY` is refused.

### The assumptions live in `src/`, not here

The behaviour assumptions themselves are `stevin.probes.PROBES`: a list of named
probes, each with its docs link, what stevin does because of it, and a check that
makes its own objects in a scratch schema. `test_live_assumptions.py` is a thin
parametrised caller of that list, and `stevin verify` runs the same list in a user's
workspace. So an assumption is written down **once**, and a user can settle it on the
runtime they actually have.

A new Databricks assumption therefore goes in `probes.py`, not in a test of its own —
unless what you are testing is stevin's own logic, which belongs in a test. The rule
of thumb: if the sentence is about what *Databricks* does, it is a probe; if it is about
what *stevin* plans, it is a test.

Offline, `tests/unit/test_probes.py` runs the probe machinery against the fake
warehouse. It deliberately asserts nothing about whether a probe *holds*: the fake
interprets stevin's own SQL, so a ✓ from it would be stevin agreeing with itself.

### Running the live suite

Nothing in stevin has been verified against a real workspace until this has run. Every
`TODO(verify)` in the source names an assumption one of these tests settles.

You need:

- a **catalog you can write to** — the suite creates schemas called
  `stevin_it_<random>` in it and drops each, with everything inside, when the test or
  the module that asked for it finishes;
- a **SQL warehouse** — the tests run a few dozen small statements; a 2X-Small
  serverless warehouse is plenty;
- a principal allowed to `CREATE SCHEMA` in that catalog and `CREATE FUNCTION` in its
  schemas (the mask test creates a masking function);
- optionally a principal to grant to — `account users` by default;
- **room in the metastore's table quota**: 15 tables for `smoke`, 60 for everything.

```sh
databricks auth login --host https://<workspace> --profile stevin-test

DATABRICKS_CONFIG_PROFILE=stevin-test \
DATABRICKS_WAREHOUSE_ID=<warehouse id> \
STEVIN_TEST_CATALOG=<scratch catalog> \
STEVIN_TEST_PRINCIPAL="account users" \
  uv run pytest -m "integration and smoke" -v
```

Run it from a separate `git worktree` of the commit under test: editing files while a
run is going mixes old and new modules.

A failure here is the point of the suite: an assumption about Databricks was wrong. Fix
the code, keep the test, and remove the `TODO(verify)` it settled — and if the fake
warehouse agreed with the wrong assumption, fix the fake too, so the offline suite stops
agreeing with it.

### What a run costs

A live run costs the workspace **tables**, and it goes on costing them after it has
dropped them. Unity Catalog allows a metastore a number of tables, 500 by default, and
[counts them with an estimate](https://docs.databricks.com/aws/en/data-governance/unity-catalog/resource-quotas)
that goes up when a table is created and comes down later. The estimate is what a
`CREATE TABLE` is refused by. So a suite that makes many tables fills a metastore that
holds almost none, and then nobody can create a table there, the owner of the
workspace included.

That happened on 2026-10-10. The suite ran on every pull request then, and made more
than a hundred tables a run. About fifteen runs in one day took the estimate to 510 of
500 while the catalog held 46 tables. The next run failed 68 tests on
`QUOTA_EXCEEDED.UC_RESOURCE_QUOTA_EXCEEDED`.

So a run has a **budget**, and the suite keeps to it by itself:

| Selection | Budget | Counted from the code |
|---|---|---|
| `-m "integration and smoke"` | at most **15** tables | 13 |
| `-m integration` | at most **60** tables | 59 |

- **Every table is counted as it is made.** All of the suite's statements go through
  one runner, and it counts each that creates a table: `CREATE TABLE` in every form,
  `CREATE OR REPLACE TABLE`, a clone, a streaming table, a materialized view, and the
  tables stevin's own apply makes, the staging copy of a rewrite and the three history
  tables included. A statement that was refused is not counted. A replace of a table
  the run made is counted, because nobody has shown that Unity Catalog does not count
  it.
- **The session says what it spent.** At its end it prints the total and the ten
  tests that made the most. A table a module shares is charged to the fixture that
  made it.
- **A session over its budget fails**, with one line, whatever its tests did. The
  budget is `FULL_BUDGET` and `SMOKE_BUDGET` in `tests/table_budget.py`; raise one only
  with the reason beside it.
- **A session does not start without room.** Before any test creates anything it
  reads the metastore's estimate. When the estimate and the budget together are over
  the limit, the whole session stops with one error that says the numbers, and nothing
  has been created. When the quota cannot be read, the session says so and goes on.

The two numbers in the last column are counts from reading the code, not from a run.
What Databricks makes behind a statement is not in them: the storage table of a
materialized view or a streaming table, for one. The first live run after a change to
the suite is where the count is checked.

What each file makes, counted the same way, before and after the suite was cut:

| File | Tests | Before | Now | How |
|---|---|---|---|---|
| `test_live_assumptions.py` | 24 probes | 28 | 17 | the probes share one schema and five tables |
| `test_live_apply.py` | 10 | 33 | 14 | the history tables are made once; one applied plan and one rewrite serve two tests each |
| `test_live_round_trip.py` | 22 | 24 | 8 | one table has a column for every widening |
| `test_live_governance.py` | 14 | 11 | 9 | one table to read from and point at; one for the two tests about tags |
| `test_live_dogfood.py` | 1 | 6 | 5 | a table whose shape was there twice is gone |
| `test_live_policies.py` | 5 | 5 | 1 | the tests only read: one fixture for the module |
| `test_live_access.py` | 3 | 2 | 1 | the same |
| `test_live_seeds.py` | 2 | 2 | 1 | both load into one table |
| `test_live_adopt.py`, `test_live_notebook_tables.py`, `test_live_sql_specs.py` | 3 | 3 | 3 | |
| `test_live_bundle.py` | 4 | 0 | 0 | |
| **All** | | **114** | **59** | |

Two rules keep it there. **A test that only reads shares a table**: a module-scoped
fixture makes it once in `shared_schema`, and no test may depend on which ran first, so
`-k` on one test still finds what it needs. **A test that changes a table's shape, or
has to start from nothing, has its own**, in `schema`. A probe follows the same rule
through `Bench.once()`.

Recording transcripts (`STEVIN_RECORD`) is the exception. A recording has to stand on
its own, so each probe gets a schema of its own and shares nothing: that run costs 28
tables for the probes instead of 17.

### When the suite runs

- **When somebody starts it** (`workflow_dispatch`), `smoke` unless they ask for `full`.
- **Never on a schedule.** The workspace is its owner's own, and a run that nobody
  chose to start is a run nobody is watching.
- **Never on a pull request.** A pull request that changes what stevin sends to
  Databricks is checked by starting `smoke` on its branch, by whoever may start the
  workflow: a maintainer. Say in the pull request that it wants one.

```sh
gh workflow run integration.yml --ref my-branch                 # smoke
gh workflow run integration.yml --ref my-branch -f suite=full   # everything
```

The rule, for people and for coding agents alike: **never a full run for a change that
`smoke` or `-k` can check, and never more than one full run a day on a workspace
somebody else uses.** One suite runs at a time; a second waits.

### What `smoke` covers

Eight tests that together walk the path a release takes, in 13 tables:

| Test | What it proves |
|---|---|
| `test_apply_converges_and_records_what_it_did` | plan → apply → an empty re-plan; the history and lock SQL |
| `test_a_rewrite_converts_the_data_it_moves` | a rewrite: staged, replaced, the rows converted, the staging copy gone |
| `test_a_seed_is_loaded_typed_and_replaced` | a seed's load, typed, and planning nothing after |
| `test_a_notebooks_write_is_seen_and_adopted` | drift, then `adopt`, then an empty plan |
| `test_grants_read_back` | a grant reads back as the table's own |
| `test_a_function_and_the_mask_that_calls_it_in_one_plan` | a function and the column mask that calls it |
| `test_a_plan_lists_the_policy_with_its_function_and_principals` | the policies reader, on a table under a policy |
| `test_the_report_says_what_is_inherited_and_what_is_the_tables_own` | the access report |

Only `full` covers the rest: the 24 probes, which are every assumption about Databricks
`stevin verify` runs; every widening and the three refused ones; partitioning and
clustering, there and back; the messy schema; a table rename; the lock, a plan that
already ran, a project that hands grants over, an apply with no history; views, foreign
keys, functions, schemas, volumes, owners, removing a tag; SQL specs; the Databricks
CLI's reading of a bundle; `drift` and `doctor` under a policy.

### Asking one question of the workspace

A single live question doesn't need the whole suite. Push a branch with the test on it
and run the suite against it, filtered. `k` narrows the suite that was chosen, so a
test outside `smoke` wants `suite=full` beside it:

```sh
gh workflow run integration.yml --ref my-branch -f suite=full -f k=the_test_name
```

That's the honest way to settle a Databricks behaviour before building on it: probe it,
read the answer, then write the code and the test that keeps it. By hand the same
question costs one table: ask it in a throwaway `stevin_probe_*` schema and drop the
schema after.

### When the metastore says it is full

`QUOTA_EXCEEDED.UC_RESOURCE_QUOTA_EXCEEDED` — *"Cannot create 1 Table(s) ... (estimated
count: 523, limit: 500)"* — usually isn't. Unity Catalog
[counts tables as they are created](https://docs.databricks.com/aws/en/data-governance/unity-catalog/resource-quotas)
and catches up with deletions later, so a day of live runs leaves the count far above
what is really there.

Four things keep it from happening, and the last says so when it does:

- **A run makes few tables**, and fails when it makes more than its budget
  ([above](#what-a-run-costs)).
- **A test schema keeps nothing it drops.** `ALTER SCHEMA … SET RETAIN DROPPED TO 0
  HOURS` turns off the seven-day
  [recovery period](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-undrop-table),
  because a dropped table still counts against the quota for as long as `UNDROP` could
  bring it back.
- **Schemas a cancelled run left behind are swept.** A run that is cancelled mid-test
  never drops its `stevin_it_*` schemas; anything older than two hours goes.
- **Then the quota is read**, which is also what asks Unity Catalog to recount it. If
  this run's budget does not fit under the limit, the session stops before it creates
  anything, with one line that says the estimate, the limit and the budget.

If the count stays above what the catalogs really hold, it is dropped tables still inside
their recovery period, or an estimate that has not caught up. Both come down by
themselves. A metastore that needs to run this suite often is worth asking your
Databricks account team to raise the table quota on.

## The docs' pictures

Every terminal on the docs site is stevin's own output. `tests/screens.py` writes a
small project for each scene, applies its "before" specs through the CLI into the fake
warehouse, runs the command the page shows, and records what the CLI printed as an SVG.
The spec files a page quotes are written alongside, so the YAML next to a plan is the
YAML that made it.

`test_screens.py` fails when a picture no longer matches what the CLI prints. After
changing anything a user sees, remake them and look at the diff:

```sh
mise run screens
```

A new feature earns a scene in the [feature gallery](features.md): add it to
`tests/screens.py` and a section to `docs/features.md`.

## Where a new test goes

| You changed | Test it in |
|---|---|
| The type parser, loader, differ, planner | `tests/unit/`, with a snapshot if it shapes a plan |
| The SQL a step generates | `tests/unit/test_convergence.py` — teach the fake the statement |
| The executor, history, locking | `tests/unit/test_executor.py` with `MemoryHistory` |
| An assumption about what Databricks does | a probe in `src/stevin/probes.py`, with the docs link — then record it |
| Anything a user sees in the terminal | a scene in `tests/screens.py`, then `mise run screens` |

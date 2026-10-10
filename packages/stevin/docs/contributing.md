# Contributing

Issues and pull requests are welcome. stevin is one package of
[kostavo-oss/tools](https://github.com/kostavo-oss/tools), and what a contributor needs
is in that repository, each fact in one place:

| What | Where |
|---|---|
| How a change lands, the toolchain, how a release is made | the repository's [CONTRIBUTING.md](https://github.com/kostavo-oss/tools/blob/main/CONTRIBUTING.md) |
| What is particular to stevin: its tests, its generated files, the live suite | stevin's [CONTRIBUTING.md](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/CONTRIBUTING.md) |
| What must be true of the code, and the tests that hold it | [RULES.md](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/RULES.md) |
| Why it is so, and what it replaced | [DECISIONS.md](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/DECISIONS.md) |
| How stevin works | [How it works](how-it-works.md) |
| How it is tested, and what has run on a real workspace | [Testing](testing.md) |

## The short version

```sh
mise install            # once: the pinned Python and uv
uv sync                 # once: one .venv for the repository

cd packages/stevin
uv run stevin                     # the command
uv run pytest tests/unit          # the offline tests: no workspace needed
uv run ty check                   # the types
```

From the root of the repository, `mise run check` runs the whole gate: lint, format
check, types and unit tests. Use uv, ruff and ty, and no other tool for those jobs.

## What a change has to keep

The rules are in
[RULES.md](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/RULES.md),
each with an identifier. The ones a change breaks most easily:

- The differ and the planner do no I/O, and the model is frozen dataclasses that hold
  tuples (PLAN-1).
- Every identifier in a statement goes through `quote_ident()` (SQL-1).
- What a spec does not mention on a live object is reported as unmanaged and never
  diffed away (OWN-5).
- A step that can lose data is `destructive` (RISK-1).
- An assumption about what Databricks does is a probe with a link to its documentation
  (DBX-1). If you are not sure, write `TODO(verify)` and say so.

A change to behaviour changes its rule and its test in the same pull request, and a
changed plan comes with refreshed snapshots.

## The live suite

`tests/integration/` runs against a real workspace, by hand, and never on a pull
request. A pull request that changes what stevin sends to Databricks asks a maintainer
for the `smoke` tests on its branch. [Testing](testing.md#what-a-run-costs) says what a
run costs the workspace, and the rule that follows: never a full run for a change that
`smoke` or `-k` can check.

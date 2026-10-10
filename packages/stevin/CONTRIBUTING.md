# Contributing to stevin

Issues and pull requests are welcome. How a change lands, the checks it has to pass, the
toolchain and how a release is made are the same for every package of this repository:
the root [CONTRIBUTING.md](../../CONTRIBUTING.md) has them. This file is what is
particular to stevin.

stevin is alpha, and the spec format may still change before the first stable release.

## Its tests

```sh
uv sync                                            # once, anywhere in the repository
cd packages/stevin && uv run pytest tests/unit     # its offline tests, from its own directory
uv run ty check                                    # its types, from the same directory
```

The unit tests need no workspace and no network. A fake warehouse interprets the SQL
stevin sends, and every test runs with the Databricks CLI and any signed-in workspace
hidden. [docs/testing.md](docs/testing.md) says what each layer of tests proves, and
where a new test goes.

Three things are made by a command, and a test fails when one is stale:

```sh
uv run python tests/screens.py docs/assets/screens   # the docs' terminal pictures (`mise run screens`)
uv run python -m stevin.features docs/formats.md     # the table of what YAML and SQL specs can say
uv run python -m stevin.spec_schema docs/schema      # the JSON Schemas editors use
```

Run the first after changing anything a user sees in a terminal, and look at the
pictures. A new feature gets a scene in `tests/screens.py` and a section in
`docs/features.md`.

## The live suite

`tests/integration/` runs against a real workspace, and only when a maintainer starts
it: never on a schedule and never on a pull request. A pull request that changes what
stevin sends to Databricks says that it wants the `smoke` tests on its branch, and a
maintainer starts them and reads the result before merging:

```sh
gh workflow run integration.yml --ref <branch>                            # smoke
gh workflow run integration.yml --ref <branch> -f suite=full -f k=<test>  # one test
```

The workspace is its owner's own, and every table a run makes counts against that
metastore's quota for a while after it is dropped. So, for people and for coding agents:
**never a full run for a change that `smoke` or `-k` can check, and never more than one
full run a day.** [docs/testing.md](docs/testing.md#what-a-run-costs) says what a run
costs, what `smoke` covers and how to write a live test that keeps to the budget.

An assumption about what Databricks does is a probe in `src/stevin/probes.py`, with a
link to the documentation. The live suite and `stevin verify` both run that list.

## Its rules and decisions

- [RULES.md](RULES.md) is what must be true of the code: numbered rules, each with the
  tests that hold it. A change to behaviour changes its rule in the same pull request,
  and the test that holds it cites the rule's identifier.
- [DECISIONS.md](DECISIONS.md) is why: a log that is appended to and never edited.
- [docs/how-it-works.md](docs/how-it-works.md) is how stevin works: the pipeline, the
  model, what a plan holds, how ownership is known. If the code and that page disagree,
  one of them has a bug: say which.
- [docs/testing.md](docs/testing.md) is how it is tested, what has run on a real
  workspace, and what is still open.
- [CLAUDE.md](CLAUDE.md) has the layout and the rules of working.

From the root of the repository, this checks that the rules, the code and the tests
agree:

```sh
uv run pytest tests/test_rules.py
```

`CHANGELOG.md` gets a line under `## [Unreleased]` for anything a user would notice.

# Contributing to leeghwater

Issues and pull requests are welcome. How a change lands, the checks it has to pass, the
toolchain and how a release is made are the same for every package of this repository:
the root [CONTRIBUTING.md](../../CONTRIBUTING.md) has them. This file is what is
particular to leeghwater.

## Its tests

```sh
uv sync                                    # once, anywhere in the repository
cd packages/leeghwater && uv run pytest    # its tests, from its own directory
uv run ty check                            # its types, from the same directory
```

The tests need no workspace, no Azure and no network. Databricks is one environment
variable and a stand-in for the workspace client (`tests/conftest.py`), a secret scope
is a dictionary, a Key Vault is a stand-in client, and dlt loads into a DuckDB file in
a temporary folder. They need what `uv sync` installs: dlt with its `duckdb` extra, and
leeghwater's own `keyvault` extra. Some tests run the app in a process of its own.

## Its rules and decisions

- [RULES.md](RULES.md) is what must be true of the code: numbered rules, each with the
  tests that hold it. A change to behaviour changes its rule in the same pull request,
  and the test that holds it cites the rule's identifier.
- [DECISIONS.md](DECISIONS.md) is why: a log that is appended to and never edited.
- [docs/tried.md](docs/tried.md) is what ran on a real workspace, and what did not.
- [CLAUDE.md](CLAUDE.md) has the layout and the rules of working.

From the root of the repository, this checks that the rules, the code and the tests
agree:

```sh
uv run pytest tests/test_rules.py
```

`CHANGELOG.md` gets a line under `## [Unreleased]` for anything a user would notice.

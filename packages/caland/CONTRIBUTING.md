# Contributing to caland

Issues and pull requests are welcome. How a change lands, the checks it has to pass, the
toolchain and how a release is made are the same for every package of this repository:
the root [CONTRIBUTING.md](../../CONTRIBUTING.md) has them. This file is what is
particular to caland.

## Its tests

```sh
uv sync                                 # once, anywhere in the repository
cd packages/caland && uv run pytest     # its tests, from its own directory
uv run ty check                         # its types, from the same directory
uv run pytest tests/test_page_in_a_browser.py   # only the page in Chrome
```

The tests need no workspace and no network. Databricks is a stand-in behind the same
ports (`tests/fakes.py`), the server is asked over real HTTP on `127.0.0.1`, and the page
is driven in a real browser: Chrome, over its debugging pipe (`tests/chrome.py`), with
real keys, real files and the real clipboard. Those tests are skipped where there is no
Chrome; CI has one. Run them after any change to `src/caland/interface/web/static/`.

To look at the page without a workspace, start it where none is found, and open the
link it prints. It shows the choice of a workspace and the list of keys:

```sh
DATABRICKS_CONFIG_FILE=/nonexistent uv run caland --no-open
```

## Its rules and decisions

- [RULES.md](RULES.md) is what must be true of the code: numbered rules, each with the
  tests that hold it. A change to behaviour changes its rule in the same pull request,
  and the test that holds it cites the rule's identifier.
- [DECISIONS.md](DECISIONS.md) is why, and what was turned down.
- [docs/tried.md](docs/tried.md) is what ran on a real workspace, and what did not.
- [CLAUDE.md](CLAUDE.md) has the layout and the rules of working.

From the root of the repository, this checks that the rules, the code and the tests
agree:

```sh
uv run pytest tests/test_rules.py
```

`CHANGELOG.md` gets a line under `## [Unreleased]` for anything a user would notice.

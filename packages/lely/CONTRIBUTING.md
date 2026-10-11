# Contributing to lely

Issues and pull requests are welcome. How a change lands, the checks it has to pass, the
toolchain and how a release is made are the same for every package of this repository:
the root [CONTRIBUTING.md](https://github.com/kostavo-oss/tools/blob/main/CONTRIBUTING.md) has them. This file is what is
particular to lely. Its links are whole addresses, because the docs site shows this
file too.

## Its tests

```sh
uv sync                                          # once, anywhere in the repository
cd packages/lely && uv run pytest tests/unit     # its tests, from its own directory
uv run pytest tests/browser                      # a plugin's view, as Chrome reads it
uv run ty check                                  # its types, from the same directory
```

The unit tests need no workspace, no Databricks CLI and no network:
`tests/fake_databricks.py` and `tests/fake_github.py` stand in, and simulate what lely
*believes* those do. The browser tests need Chrome and skip without it; CI runs them.
Run them after a change to `src/lely/render/html.py`.

## Its rules and decisions

- [RULES.md](https://github.com/kostavo-oss/tools/blob/main/packages/lely/RULES.md) is what must be true of the code: numbered rules, each with the
  tests that hold it. A change to behaviour changes its rule in the same pull request,
  and the test that holds it cites the rule's identifier.
- [DECISIONS.md](https://github.com/kostavo-oss/tools/blob/main/packages/lely/DECISIONS.md) is why: a log that is appended to and never edited.
- [docs/tried.md](https://kostavo-oss.github.io/tools/lely/tried/) is what ran on a real workspace and on GitHub, and what
  did not. A new assumption about either gets a test, a link to the docs it rests on,
  and a `TODO(verify)` until it has been seen.
- [CLAUDE.md](https://github.com/kostavo-oss/tools/blob/main/packages/lely/CLAUDE.md) has the layout and the rules of working.

From the root of the repository, this checks that the rules, the code and the tests
agree:

```sh
uv run pytest tests/test_rules.py
```

## A second reader

Some files decide what may run, or handle what is not trusted: `approval.py`,
`running.py`, `source.py`, `planfile.py`, `cli.py`, `github.py` and the renderers. A
change there is reviewed by someone who did not write it before it is opened as a pull
request.

`CHANGELOG.md` gets a line under `## [Unreleased]` for anything a user would notice.

# Contributing to lely

Issues and pull requests are welcome.

`lely` is pre-alpha: everything in the specs is built, and it has run for real only a few
times. `spec/` says what each piece must deliver, `docs/DESIGN.md` how it is built. If the
code disagrees with either, that is a bug in one of them — please say which.

## How a change lands

Every change is a pull request against `main`, merged by a maintainer once its checks pass.

- **`ci`** — lint, format, types, and the tests on Python 3.11–3.13. Required.
- Small commits with [conventional](https://www.conventionalcommits.org) messages. New
  behaviour comes with a test; a fix comes with the test that would have caught it.
- A change to what lely shows, asks or refuses updates the spec's "As built" and, where a
  user would notice, `CHANGELOG.md`.

Some parts decide what may run, or handle what isn't trusted: `approval.py`, `running.py`,
`source.py`, `planfile.py`, `cli.py`, `github.py`, and the renderers. **A change there is
reviewed by someone who didn't write it before it is opened as a pull request** — in this
project's short history, most defects in those files came in with the fix for another.

## Toolchain

[`mise`](https://mise.jdx.dev) pins the tools, and the stack is Astral's:
[`uv`](https://docs.astral.sh/uv/), [`ruff`](https://docs.astral.sh/ruff/) and
[`ty`](https://docs.astral.sh/ty/).

```sh
mise install     # the pinned Python and uv (optional but recommended)
uv sync          # .venv with dependencies and dev tools
mise run check   # the gate: lint, format check, types, unit tests
```

## Day to day

```sh
uv run lely                    # the CLI
uv run pytest tests/unit       # the unit tests: no workspace, no network
uv run pytest tests/browser    # a plugin's view, as Chrome reads it (needs Chrome)
uv run ruff check . && uv run ruff format .
uv run ty check
mise run docs                  # the docs site, at localhost:8000
```

`ruff format` also formats the Python in Markdown code blocks, so the gate covers `docs/` and
`spec/`. When you chain the gate in a shell, a pipe hides a failing test: read the test
count, not the exit code of `tail`.

The unit suite never reaches a workspace or GitHub: `tests/fake_databricks.py` and
`tests/fake_github.py` stand in, and simulate what lely *believes* those do. What has been
seen on the real things is written down in `spec/004-asset-bundle.md` and `docs/GITHUB.md`;
a new assumption about either gets a test, a link to the docs it rests on, and — until it has
been seen — a `TODO(verify)`.

## Rules the code keeps

`CLAUDE.md` lists them. The ones a contributor trips over first:

- The core is pure. I/O lives at the edges: the plugins, the Databricks CLI runner, `git`,
  GitHub, the command line.
- No module outside `src/lely/steps/` knows a plugin by name — the bundle included.
- Nothing that changes a workspace runs unasked, and nothing destructive without
  `--allow-destructive`.
- Nothing a plan says is obeyed where it is shown — a terminal, Markdown, the page.
- A plan file carries no secret.

## Releases

A release is a version, the same way as for stevin and caland: a pull request bumps
`version` in `pyproject.toml` and moves the changelog's *Unreleased* notes under a
`## [X.Y.Z] - <date>` heading, and merging it is the release. `.github/workflows/release.yml`
notices the new version on `main`, runs the gate, publishes to PyPI with Trusted Publishing —
no token — and makes the GitHub release and its tag. A change to `pyproject.toml` that isn't a
new version releases nothing.

No version of lely has been released yet.

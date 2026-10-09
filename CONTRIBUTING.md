# Contributing

Thanks for your interest! Issues and pull requests are very welcome.

This repository holds four tools, each a package under `packages/`, each with its own
version, changelog, docs and rules. What is shared is here: the lock file, the gate, the
site, the workflows. A package's own `CONTRIBUTING.md` says what holds inside it —
stevin's, for one, has the architecture and the house rules of a plan/apply tool.

## How changes land

`main` is protected: every change is a pull request, merged once its checks pass.

- **`ci`** — lint over everything, then for each package that changed: types, the unit
  tests on Python 3.11–3.14 (stevin also on macOS and Windows, caland on macOS), the
  tests on the lowest dependency versions its `pyproject.toml` allows, and the wheel and
  source package. The docs site in strict mode and the workflows, always.
- **`integration`** — stevin's live suite, against a real workspace, on every pull
  request that touches its code and nightly. About 40 minutes, not required: read it
  before merging anything that changes what stevin sends to Databricks.

One package per pull request where you can; a shared change (the lock file, a workflow)
is its own pull request. Run `mise run check` before pushing; it is the `ci` gate minus
the matrix. If you changed anything stevin shows in the terminal, `mise run screens`
remakes its docs' pictures, and the check fails until you do.

## Toolchain

[`mise`](https://mise.jdx.dev) pins the tools; the rest is the Astral stack —
[`uv`](https://docs.astral.sh/uv/) (one workspace, one `.venv`, one lock file),
[`ruff`](https://docs.astral.sh/ruff/) (lint + format, configured once at the root) and
[`ty`](https://docs.astral.sh/ty/) (type check, run per package).

```sh
mise install             # the pinned Python + uv
uv sync                  # .venv with every package, editable, and the dev tools
uvx pre-commit install   # optional: ruff on every commit
```

## Day-to-day

```sh
uv run stevin                          # any package's command, from anywhere in the repo
cd packages/stevin && uv run pytest tests/unit   # one package's tests, from its directory
uv run ruff check . && uv run ruff format .      # lint + format, everything
mise run typecheck                     # ty, each package from its own directory
```

`mise run check` runs the whole gate; `mise tasks` lists the rest. A package's tests run
from its own directory — their helper modules share names across packages, so one
pytest run over all of them would mix them up.

## Rules that hold for every package

- **No package imports another.** Each does one job and none needs another; lely runs
  stevin as a command, which is the one way allowed. `tests/test_workspace.py` enforces
  it. There is no shared library and there will not be one.
- Every Databricks behaviour assumption gets a test and a link to the docs in the test
  docstring. If unsure, say so and add a `TODO(verify)` — do not guess.
- New behaviour comes with a test, and a line under `## [Unreleased]` in the package's
  `CHANGELOG.md`.
- Small, PR-sized commits with [conventional commit](https://www.conventionalcommits.org/)
  messages (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`), the *why* in the
  body. By contributing you agree your work is licensed under [Apache-2.0](LICENSE).

## Releasing

A release is a version of one package. Its `pyproject.toml` says what it is, and merging
the bump is what ships it.

In a pull request, bump that package's version and move its changelog notes under it:

```sh
cd packages/stevin && uv version 0.4.0a1    # or: uv version --bump patch / minor / major
```

In `packages/stevin/CHANGELOG.md`, rename `## [Unreleased]` to `## [0.4.0a1] - <date>`
and start a fresh, empty `## [Unreleased]` above it. Merge it once `ci` passes — that is
the whole release.

The [`release`](.github/workflows/release.yml) workflow watches every package's
`pyproject.toml` on `main`. When it finds a version that isn't tagged and isn't on PyPI,
it runs the gate on that package, publishes it to **PyPI** (Trusted Publishing, one
publisher per package, no API token), and creates the GitHub release with the
changelog's notes, which is what makes the `stevin-v0.4.0a1` tag. A version with `a`,
`b` or `rc` is marked a pre-release. For stevin the Action's `stevin-v0` tag moves to
every 0.x release, so `uses: kostavo-oss/tools/packages/stevin@stevin-v0` follows the
newest. Two packages bumped in one merge are two releases, one after the other.

Nothing else triggers it, so a `pyproject.toml` change that isn't a bump — a dependency,
a classifier — costs one run that says "nothing to release" and stops. A bump without
changelog notes under that version fails instead of publishing something unexplained.

If a release fails halfway, fix what broke and run the workflow again from the Actions
tab, choosing the package: whatever already landed (the PyPI file, the tag) makes it stop
rather than repeat itself. Started by hand is also the only way a version that is on
`main` but was never published goes out — a later push won't pick it up.

## Previewing the docs

```sh
mise run docs    # uv run --group docs mkdocs serve
```

One site, one section per tool: the root `mkdocs.yml` includes each package's
`mkdocs.yml`, and each package's `docs/` is its own.

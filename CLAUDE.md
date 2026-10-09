# CLAUDE.md

Four small tools for the ugly gaps on Databricks, in one repository: a uv workspace
with one lock file, one `.venv`, one gate, one docs site. **Each package's own
`CLAUDE.md` is the source of truth inside that package** — read it before touching
`packages/<name>/`. This file is only what holds across them.

## Layout

```
packages/stevin       tables and access no transformation tool owns (plan/apply, the GitHub Action)
packages/lely         one plan for the whole deploy (plan/apply/destroy around a bundle)
packages/leeghwater   a dlt pipeline, the same on a laptop and in a job
packages/caland       a local page for a workspace's secrets
pyproject.toml        the workspace: members, the dev/docs groups, ruff for everything
mise.toml             the tasks; `mise run check` is the gate
mkdocs.yml, docs/     the site's front page; each package's docs are included under /<name>/
tests/                what holds across packages (no cross-imports, every package's files)
.github/workflows     ci (path-filtered per package), release (per package), integration (stevin), docs
```

## Rules for every package

- **No package imports another**, ever. lely runs stevin as a command; that is the one
  allowed coupling. No shared library, no `kostavo-core`. `tests/test_workspace.py`
  enforces it.
- Tests run **from the package's directory** (`cd packages/x && uv run pytest`); their
  helper modules share names across packages. `ty` runs per package too. ruff runs from
  the root, configured once.
- Differ-and-planner purity, `quote_ident()`, the destructive risk class, probes for
  Databricks assumptions: those are stevin's rules, in stevin's `CLAUDE.md`.
- Every Databricks behaviour assumption gets a test and a docs link; unsure means
  `TODO(verify)`, never a guess.
- Never `git add -A` or `git add .`: name the paths. A report a tool wrote can hold the
  environment of the machine it ran on, and one was committed that way once.

## How changes land

`main` is protected; every change is a pull request, one package per PR where possible.
`ci` lints everything and runs types, tests, lowest-dependency tests and the build only
for packages that changed; docs (strict) and the workflows always. stevin's live suite
(`integration`) runs on PRs touching its code and nightly, from the `databricks-test`
environment; it isn't required.

**A release is a version of one package:** bump `version` in `packages/<name>/pyproject.toml`
and move that package's `[Unreleased]` notes under it, in a PR. Merging ships it:
`release.yml` publishes to PyPI by Trusted Publishing (one publisher per package,
repository `kostavo-oss/tools`, workflow `release.yml`, environment `pypi`) and makes the
`<name>-vX.Y.Z` tag; stevin's `stevin-v0` moves with it. Ask before merging a bump PR.

## Commands

```
mise install && uv sync        # pinned Python + uv; one .venv for everything
mise run check                 # lint, format check, types, unit tests — every package
mise run test:lowest           # each package on its lowest dependency floors
mise run docs:build            # the whole site, strict
mise run screens               # stevin's terminal pictures (its tests fail when stale)
mise run build                 # every wheel and sdist into dist/
```

## History

Until 2026-10-09 each tool was a repository of its own, generated from
`kostavo-oss/template-python` with copier. They were merged here with their history
(`git subtree`); the old repositories are archived and their Pages left serving, so an
old link and stevin's old JSON-schema URL still resolve. data-product-template (was vierlingh), the copier template
for a data product that uses these tools, stays a repository of its own: copier needs
its config at a source repository's root.

# 009 — first release

**Status:** not started. Independent of the phases; it happens when the owner says.

## Why

lely is public but can't be installed: it isn't on PyPI, and the repository has the code and a CI
gate but none of what the other Kostavo tools have around them. This is the list of what stands
between the repository and `uvx lely`.

## Requirements

- **R1 — A changelog.** `CHANGELOG.md`, Keep a Changelog format, starting with what is built.
- **R2 — A contributing guide.** The gate (`mise run check`), how a change lands, how a release
  is made.
- **R3 — A release workflow** that publishes to PyPI with Trusted Publishing, no token. Its
  trigger is [D1](#to-decide).
- **R4 — The gate in CI is the gate at a desk.** CI runs ruff and the tests on Python 3.11–3.13
  through the shared workflow. `mise run check` also runs `ty`, which the shared workflow doesn't.
  Either the shared workflow learns `ty`, or lely's CI adds it.
- **R5 — The README says what a new user needs**: install from PyPI, the quickstart, what is and
  isn't built. It already says the rest.
- **R6 — Docs**, if lely gets a site like stevin's and maeslant's: [D2](#to-decide).

## What only the owner can do

- Register a Trusted Publisher for `lely` on PyPI: owner `kostavo-oss`, repository `lely`, the
  release workflow's file name, environment `pypi`.
- Protect `main`, if lely should work the way stevin does (every change a pull request, the
  checks required).

## To decide

- **D1 — How a release is made.** The setup plan for the Kostavo tools says: push a `vX.Y.Z` tag.
  stevin and maeslant do it differently today: merging a version bump to `main` is the release.
  One way for all three, or each its own?
- **D2 — A docs site?** stevin and maeslant have one (MkDocs Material, on Pages). For lely the
  README and `docs/DESIGN.md` may be enough until `apply` exists.
- **D3 — The recorded CLI outputs.** `tests/fixtures/cli/*.json` are derived from the Databricks
  CLI's own acceptance tests, and that repository is under the Databricks License, not an
  open-source one. They are what the CLI prints, edited by hand, and the folder's README says
  where each came from. Keep them as they are, replace them with outputs recorded from lely's own
  runs against a workspace, or write them by hand from the CLI's documented output?
- **D4 — The author's email in the package.** `pyproject.toml` lists a ProRex address under
  `authors`, as stevin and maeslant do. It becomes public metadata on PyPI with the first
  release. Keep, or name only?
- **D5 — What the first version is.** `0.0.1` today, classified pre-alpha. Does a first release
  wait for `apply` ([005](005-plan-apply-destroy.md)), or go out read-only so the name is taken and
  `plan` can be tried?

## Done when

`uvx lely --version` works on a machine that has never seen this repository.

# 009 — first release

**Status:** prepared in part, 2026-10-06: R1, R2 and R4 are done, and the open questions
have a proposal each ([Proposed](#proposed)). Nothing is published, tagged or registered: a
release happens when the owner says.

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

## Proposed

The builder's answers, 2026-10-06, for the owner to take or change. None is decided.

- **D1 — as stevin and maeslant do it**: merging a version bump to `main` is the release. A
  workflow started by a change to `pyproject.toml` checks that the version is new and that
  `CHANGELOG.md` has a section for it, runs the gate, publishes with Trusted Publishing and
  tags. One way for all three tools; the setup plan's "push a tag" is the odd one out.
  *Not written for lely yet, on purpose: the day that workflow is on `main` with a publisher
  registered, `0.0.1` goes out.*
- **D2 — no docs site yet.** The README, `docs/DESIGN.md` and `docs/GITHUB.md` carry it. A
  site when there is more to say than they hold.
- **D3 — replace the recorded CLI outputs before a release**, with outputs recorded from
  lely's own runs. They are what the CLI printed for a bundle of ours, which is ours to
  keep; what is in `tests/fixtures/cli/` today is taken from a repository under a licence
  that is not an open-source one. lely has now run on a real workspace three times, so they
  can be recorded. This is the one thing in the way of a release that is work and not a
  decision.
- **D4 — name only.** The address under `authors` would be public on PyPI for good. GitHub's
  issues are where lely is reached.
- **D5 — `0.1.0`, as alpha, once D3 is done.** `apply` exists and has run for real; nothing
  is gained by a read-only release first. The name is free on PyPI (looked on 2026-10-06).

What was done towards the requirements, 2026-10-06:

- **R1** — `CHANGELOG.md`, with what is built under *Unreleased*.
- **R2** — `CONTRIBUTING.md`: the gate, how a change lands, and that the parts that decide
  what may run are reviewed before a pull request is opened. How a release is made waits for
  D1.
- **R4** — lely's CI runs `ty` in a job of its own, beside the shared workflow.
- **R3, R5, R6** — not done: they follow from D1, from a release existing, and from D2.

## Done when

`uvx lely --version` works on a machine that has never seen this repository.

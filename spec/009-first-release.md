# 009 — first release

**Status:** prepared, 2026-10-06: the questions are answered ([Decided](#decided)) and R1–R4
are done. Nothing is published, tagged or registered: the release is one pull request, opened
when the owner says.

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

## Decided

By the owner, on 2026-10-06, to the builder's proposals:

- **How a release is made** (was D1): the same way for all three tools — merging a version
  bump to `main` is the release, as stevin and maeslant do it. *(owner: "i want them all to
  use the same")* `.github/workflows/release.yml` is that workflow: it notices a version on
  `main` that isn't out, checks that `CHANGELOG.md` has a section for it, runs the gate,
  publishes with Trusted Publishing and makes the GitHub release and its tag. A change to
  `pyproject.toml` that isn't a new version releases nothing.
- **A docs site** (was D2): yes. *(owner: "make a nice docs site")* → R6.
- **The recorded CLI outputs** (was D3): they stay as they are. *(owner: "i dont think i
  care")* `tests/fixtures/cli/README.md` says where each came from.
- **The author's email in the package** (was D4): name only. *(owner: "sounds good")*
- **The first version** (was D5): `0.1.0`, as alpha. *(owner: "sounds good")* The name was
  free on PyPI on 2026-10-06.

## To decide

Nothing. What is left is the owner's to do — register the publisher on PyPI — and then to
say: the release is one pull request that bumps the version, and merging it publishes.

## As prepared, 2026-10-06

- **R1** — `CHANGELOG.md`, with what is built under *Unreleased*.
- **R2** — `CONTRIBUTING.md`: the gate, how a change lands, how a release is made, and that
  the parts that decide what may run are reviewed before a pull request is opened.
- **R3** — `.github/workflows/release.yml`, on stevin's pattern. It has never run: it has
  nothing to release until the version is bumped, and can't publish until PyPI knows the
  publisher (owner `kostavo-oss`, repository `lely`, workflow `release.yml`, environment
  `pypi`).
- **R4** — lely's CI runs `ty` in a job of its own, beside the shared workflow.
- **R5** — waits for the release: until then the README's "isn't on PyPI yet" is true.
- **R6** — the docs site: MkDocs Material, as stevin's, built in strict mode on every pull
  request that touches it and deployed to Pages from `main`
  (<https://kostavo-oss.github.io/lely/>). The contributing guide and the changelog are
  quoted from the top of the repository, where GitHub looks for them.

The release itself will be one pull request: `version = "0.1.0"`, the classifier *Alpha*,
the name alone under `authors`, the changelog's notes moved under `## [0.1.0]`, and the
README's install line. Nothing in it is done yet, so that merging anything else releases
nothing.

## Done when

`uvx lely --version` works on a machine that has never seen this repository.

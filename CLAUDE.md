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
tests/                what holds across packages (no cross-imports, every package's files, a RULES.md that is true)
.github/workflows     ci (path-filtered per package), release (per package), integration (stevin), docs
```

## Rules for every package

- **No package imports another**, ever. lely runs stevin as a command; that is the one
  allowed coupling. No shared library, no `kostavo-core`. `tests/test_workspace.py`
  enforces it.
- **The three local pages share one look, as a file and not as code.** caland, lely's
  plan as a page and stevin's each hold a copy of `base.css` (colours, type, a table, a
  badge, a button, code, the keyboard) and load it before their own layout. The copies
  are byte-identical and `tests/test_workspace.py` holds them so: change the look in all
  three, in one pull request. No framework, no build step, nothing fetched.
- Tests run **from the package's directory** (`cd packages/x && uv run pytest`); their
  helper modules share names across packages. `ty` runs per package too. ruff runs from
  the root, configured once.
- Differ-and-planner purity, `quote_ident()`, the destructive risk class, probes for
  Databricks assumptions: those are stevin's rules, in stevin's `CLAUDE.md`.
- Every Databricks behaviour assumption gets a test and a docs link; unsure means
  `TODO(verify)`, never a guess.
- Never `git add -A` or `git add .`: name the paths. A report a tool wrote can hold the
  environment of the machine it ran on, and one was committed that way once.

## Where a fact lives

One place per fact, in every package. A fact written in two places goes stale in one of
them.

| The fact | Its one place in `packages/<name>/` |
|---|---|
| What the tool is for, when not to use it, when it is no longer needed | `README.md` |
| What must be true of the code | `RULES.md`: numbered rules in the present tense, each with the tests that hold it |
| Why it is so, and what it replaced | `DECISIONS.md`: a log with dates, appended to and never edited |
| What ran on a real workspace, and what did not | the docs page for it (`docs/tried.md` in leeghwater) |
| What changed for a user, per release | `CHANGELOG.md` |
| How to work in the package: its layout, its commands, its rules of working | `CLAUDE.md` |
| An idea that is wanted and not built | a GitHub issue |
| How it came to be | git |

A rule has an identifier, an area and a number such as `APP-3`, that code, tests and
docs cite. A number is never reused. `tests/test_rules.py` holds every package that has
a `RULES.md` to it: a cited rule exists, a rule is cited by the tests it names or says
`Not tested:` and why, no identifier is used twice, and there is no `spec/` folder
beside it.

**leeghwater follows this.** lely and caland still have a `spec/` folder that holds
rules, decisions, runs and history together, and stevin keeps its rules in its
`CLAUDE.md` and its docs. Each is converted in a pull request of its own, with
leeghwater's `RULES.md`, `DECISIONS.md` and `CLAUDE.md` as the pattern. Until then a
package's rules are where its own `CLAUDE.md` says they are.

## How changes land

`main` is protected; every change is a pull request, one package per PR where possible.
`ci` lints everything and runs types, tests, lowest-dependency tests and the build only
for packages that changed; docs (strict) and the workflows always. stevin's live suite
(`integration`) runs only when it is started by hand, from the `databricks-test`
environment; never on a pull request, and it isn't required. It costs the owner's
workspace tables against a quota: never start a full run for a change `smoke` or `-k`
can check, never more than one full run a day, and as an agent never start one unasked
(`packages/stevin/CLAUDE.md` has the rule and the reason).

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
(`git subtree`). The old repositories and that template are deleted: a link to
`kostavo-oss/stevin`, `/lely`, `/caland` or `/leeghwater`, or to
`kostavo-oss.github.io/<tool>/` without `/tools/`, is dead. data-product-template, the
copier template for a data product that uses these tools, stays a repository of its own:
copier needs its config at a source repository's root. It was called `vierlingh` until
2026-10-10.

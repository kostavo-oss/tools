# spec

What lely has to do, and how we will know that it does.

`docs/DESIGN.md` says *how* lely is built and why it is built that way. This folder says *what*
each piece of work must deliver and when it counts as done. A requirement here that the design
contradicts is a mistake in one of the two: say which, don't pick one quietly.

## The specs

| Spec | What it covers | Status |
|---|---|---|
| [000 — what lely is](000-what-lely-is.md) | Who it is for, what it does, what it refuses to do | draft, **scope to confirm** |
| [001 — read-only](001-read-only.md) | `validate`, `steps`, `plan`, `show` | built |
| [002 — apply](002-apply.md) | `apply`, the approval check, resuming, `doctor` | **next** — not started |
| [003 — CI](003-ci.md) | The Markdown plan and the GitHub Action | after 002 |
| [004 — first release](004-first-release.md) | What the repo needs before a version goes to PyPI | not started |

## How a spec is written

- **Status** — draft, agreed, in progress, built.
- **Why** — the problem, in a few lines.
- **Requirements** — numbered (`R1`, `R2`, …), each one a thing you can check. Refer to one as
  `002/R7`.
- **Not in this spec** — what was left out on purpose, and where it went.
- **To decide** — questions only the owner can answer. Work that depends on one waits for it.
- **Done when** — the checks that close the spec.

A requirement is marked *(design)* when `docs/DESIGN.md` already says it, and *(proposed)* when the
design is silent and this is a suggestion to be agreed.

## Decisions waiting on the owner

Collected here so they can be answered in one pass. Each links to where it matters.

1. **Is the design still the product?** The setup plan for the Kostavo tools describes lely as
   "better Asset Bundle deployments" and says to port existing bundle tooling into it. That
   tooling isn't in this repo or beside it. What from it, if anything, does lely have to do?
   → [000, To decide](000-what-lely-is.md#to-decide)
2. **What happens without a terminal and without `--yes`?** → [002/D1](002-apply.md#to-decide)
3. **A step that could only be planned at apply: run it, or show it and ask first?**
   → [002/D2](002-apply.md#to-decide)
4. **What must be proven on a real workspace before `apply` is called done?**
   → [002/D5](002-apply.md#to-decide)
5. **How does lely release: on a tag, or on a version bump merged to `main`?**
   → [004/D1](004-first-release.md#to-decide)
6. **The Databricks CLI's recorded outputs in `tests/fixtures/cli/`** come from a repository under
   the Databricks License. Keep, replace or re-record them? → [004/D3](004-first-release.md#to-decide)

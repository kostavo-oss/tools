# spec

What lely has to do, and how we will know that it does.

`docs/DESIGN.md` says *how* lely is built and why. This folder says *what* each piece of work must
deliver and when it counts as done. Where the two disagree, one of them is wrong: say which,
don't pick one quietly. Right now they disagree on purpose — the owner set a new direction on
2026-10-05, [000](000-what-lely-is.md) records it, and the design is rewritten once these specs
are agreed.

## The specs

| Spec | What it covers | Phase | Status |
|---|---|---|---|
| [000 — what lely is](000-what-lely-is.md) | Plugins, three verbs, no state | — | draft |
| [001 — what is built](001-what-is-built.md) | `validate`, `steps`, `plan`, `show` — and what of it moves | — | built |
| [002 — plugins](002-plugins.md) | The one contract: plan, apply, overview, destroy | 1 | draft |
| [003 — config](003-config.md) | `lely.yml` or `pyproject.toml`; the bundle as a step | 1 | draft |
| [004 — the Asset Bundle plugin](004-asset-bundle.md) | The first plugin, with a detailed overview of what it created | 1 | draft — **first to build** |
| [005 — plan, apply, destroy](005-plan-apply-destroy.md) | The commands and their safety rules | 1 | draft |
| [006 — the stevin plugin](006-stevin.md) | Tables, through stevin | 1 | draft |
| [007 — a UI for plans](007-ui.md) | A plan as a page, each step with its own detail | 2 | draft |
| [008 — GitHub Actions](008-github-actions.md) | The pull-request comment, the job summary, the Action | 2 | draft |
| [009 — first release](009-first-release.md) | What the repo needs before `uvx lely` works | — | not started |

## How a spec is written

- **Status** — draft, agreed, in progress, built.
- **Why** — the problem, in a few lines.
- **Requirements** — numbered (`R1`, `R2`, …), each one a thing you can check. Refer to one as
  `004/R7`. Each says where it comes from: *(owner)* the direction of 2026-10-05, *(design)*
  `docs/DESIGN.md`, *(built)* the code today, *(proposed)* a suggestion nobody has agreed to yet.
- **Not in this spec** — what was left out on purpose, and where it went.
- **To decide** — questions only the owner can answer, each with a proposal where there is one.
  Work that depends on one waits for it.
- **Done when** — the checks that close the spec.

## Decisions waiting on the owner

In the order they block work. A proposal is given with each, in its spec; "go with the proposals"
is an answer.

**Before the Asset Bundle plugin can be built**

1. **The config's shape** — one ordered list of steps with the bundle as one of them, or today's
   pre / bundle / post? → [003/D1](003-config.md#to-decide)
2. **Where the target and the workspace come from** when the bundle is no longer special.
   → [002/D2](002-plugins.md#to-decide)
3. **What it takes to destroy** — is running the command and answering its question enough, or
   does `prod` need more protection than that? → [005/D2](005-plan-apply-destroy.md#to-decide)
4. **No terminal and no `--yes`:** refuse, or run? → [005/D1](005-plan-apply-destroy.md#to-decide)
5. **What must be proven on a real workspace**, and on which one.
   → [005/D7](005-plan-apply-destroy.md#to-decide)

**Before stevin**

6. **What `destroy` does to tables:** leave them, drop them only for targets that say so, or
   always? → [006/D1](006-stevin.md#to-decide)

**Before phase two**

7. **What "update GitHub Actions" means:** what GitHub shows, the workflow files themselves, or
   both? → [008/D1](008-github-actions.md#to-decide)
8. **What kind of UI:** a page like stevin's, or a terminal app like maeslant's?
   → [007/D1](007-ui.md#to-decide)
9. **Which of the two comes first.** → [000/D1](000-what-lely-is.md#to-decide)

**Whenever**

10. **How lely releases**, and whether the recorded Databricks CLI outputs in the tests can stay.
    → [009](009-first-release.md#to-decide)

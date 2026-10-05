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
| [002 — plugins](002-plugins.md) | The one contract; what flows between steps | 1 | draft |
| [003 — config](003-config.md) | One list of steps, in `lely.yml` or `pyproject.toml` | 1 | draft, shape decided |
| [004 — the Asset Bundle plugin](004-asset-bundle.md) | The first plugin: plan, apply, overview, destroy | 1 | draft — **first to build** |
| [005 — plan, apply, destroy](005-plan-apply-destroy.md) | The commands, consent, and what happens on failure | 1 | draft |
| [006 — the stevin plugin](006-stevin.md) | Tables, through stevin | — | parked |
| [007 — a UI for plans](007-ui.md) | A plan as a page, each step with its own detail | 2 | draft |
| [008 — GitHub Actions](008-github-actions.md) | The pull-request comment, the job summary, the Action | 2 | draft |
| [009 — first release](009-first-release.md) | What the repo needs before `uvx lely` works | — | not started |

## How a spec is written

- **Status** — draft, agreed, in progress, built, parked.
- **Why** — the problem, in a few lines.
- **Requirements** — numbered (`R1`, `R2`, …), each one a thing you can check. Refer to one as
  `004/R7`. Each says where it comes from: *(owner)* the owner's direction, *(design)*
  `docs/DESIGN.md`, *(built)* the code today, *(proposed)* a suggestion nobody has agreed to yet.
- **Not in this spec** — what was left out on purpose, and where it went.
- **Decided** — questions the owner has answered, with the date.
- **To decide** — questions only the owner can answer, each with a proposal where there is one.
  Work that depends on one waits for it.
- **Done when** — the checks that close the spec.

## Decided so far

2026-10-05, by the owner:

- **The config is one ordered list of steps,** the bundle one entry in it. → [003/R1](003-config.md)
- **What flows between steps is written down and checked:** outputs are declared, an input is a
  reference in a step's own options, and references only point up the list — so what feeds the
  bundle is above it and what needs something from it is below. → [002/R14](002-plugins.md)
- **The target is a bare name** each plugin reads its own way, and the workspace comes from
  `--profile` or the environment. → [002/R23](002-plugins.md)
- **Destroy asks for the target's name at a terminal; headless, consent is `--yes` in the
  command.** Without either, nothing that changes a workspace runs.
  → [005/R9a](005-plan-apply-destroy.md)
- **stevin is out of this for now.** → [006](006-stevin.md)

## Decisions waiting on the owner

A proposal is given with each, in its spec; "go with the proposals" is an answer.

**While building the Asset Bundle plugin** — none of these stops the first lines of code, each
is needed before its part is finished:

1. **One spelling for a reference** — always `${steps.<name>.…}`, and the short `${var.…}` and
   `${resources.…}` go? → [002/D4](002-plugins.md#to-decide)
2. **A destroy plan as a file,** reviewed like any other plan and then applied — or is destroy
   always one command? → [005/D3](005-plan-apply-destroy.md#to-decide)
3. **A step that can't destroy:** skip it and say so, or stop? → [002/D3](002-plugins.md#to-decide)
4. **The name of the command that shows the overview** without changing anything.
   → [005/D5](005-plan-apply-destroy.md#to-decide)
5. **What must be proven on a real workspace**, and on which one — the test workspace's token has
   expired. → [005/D7](005-plan-apply-destroy.md#to-decide)

**Before phase two**

6. **What "update GitHub Actions" means:** what GitHub shows, the workflow files themselves, or
   both? → [008/D1](008-github-actions.md#to-decide)
7. **What kind of UI:** a page like stevin's, or a terminal app like maeslant's?
   → [007/D1](007-ui.md#to-decide)
8. **Which of the two comes first.** → [000/D1](000-what-lely-is.md#to-decide)

**Whenever**

9. **How lely releases**, and whether the recorded Databricks CLI outputs in the tests can stay.
   → [009](009-first-release.md#to-decide)

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

All on 2026-10-05, by the owner.

**The shape**

- **The config is one ordered list of steps,** the bundle one entry in it. → [003/R1](003-config.md)
- **What flows between steps is written down and checked:** outputs are declared, an input is a
  reference in a step's own options, and references only point up the list — so what feeds the
  bundle is above it and what needs something from it is below. → [002/R14](002-plugins.md)
- **One spelling for a reference:** always `${steps.<name>.<output>}`. → [002/R15a](002-plugins.md)
- **The target is a bare name** each plugin reads its own way, and the workspace comes from
  `--profile` or the environment. → [002/R23](002-plugins.md)

**Destroy and consent**

- **Destroy asks for the target's name at a terminal; headless, consent is `--yes` in the
  command.** Without either, nothing that changes a workspace runs.
  → [005/R9a](005-plan-apply-destroy.md)
- **A destroy can be saved to a file and reviewed first,** like an apply.
  → [005/R11a](005-plan-apply-destroy.md)
- **A step that can't destroy is skipped, visibly;** a `command` step may bring a destroy command.
  → [002/R8a](002-plugins.md)

**Seeing what is there**

- **`lely status`** shows what every step has deployed, without changing anything.
  → [005/R17](005-plan-apply-destroy.md)
- **The UI is a web page,** like `stevin ui`. → [007](007-ui.md)
- **"Update GitHub Actions" means what GitHub shows:** the pull-request comment and the job
  summary. Not generating workflow files, and no ready-made Action. → [008](008-github-actions.md)

**Scope**

- **Fake tools only, for now.** Nothing is run against a real workspace yet; what is assumed
  about the Databricks CLI stays marked as unverified.
  → [004, To verify](004-asset-bundle.md#to-verify-on-a-workspace)
- **stevin is out of this for now.** → [006](006-stevin.md)

## Decisions waiting on the owner

A proposal is given with each, in its spec; "go with the proposals" is an answer.

**Under discussion**

1. **A step that can't be planned yet** — what apply does when it reaches one, and the mental
   model behind it. → [005/D4](005-plan-apply-destroy.md#to-decide)

**Small, with a proposal each**

2. Exit codes. → [005/D6](005-plan-apply-destroy.md#to-decide)
3. More than one bundle in a project, and what `status` shows before a first deploy.
   → [004](004-asset-bundle.md#to-decide)
4. Whether the config file is looked for in parent directories.
   → [003/D2](003-config.md#to-decide)
5. Whether the word in the config stays "step" (`uses:`, `lely steps`).
   → [002/D1](002-plugins.md#to-decide)

**Before phase two**

6. How a project asks for the pull-request comment, and which plan a merge applies.
   → [008](008-github-actions.md#to-decide)
7. Whether the page only shows, and how a plugin supplies its own view. → [007](007-ui.md#to-decide)
8. The UI first, or GitHub first. → [000/D1](000-what-lely-is.md#to-decide)

**Whenever**

9. How lely releases, and whether the recorded Databricks CLI outputs in the tests can stay.
   → [009](009-first-release.md#to-decide)

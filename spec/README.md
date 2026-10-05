# spec

What lely has to do, and how we will know that it does.

`docs/DESIGN.md` says *how* lely is built and why. This folder says *what* each piece of work must
deliver and when it counts as done. Where the two disagree, one of them is wrong: say which,
don't pick one quietly. Right now they disagree on purpose — the owner set a new direction on
2026-10-05, [000](000-what-lely-is.md) records it, and the design is rewritten once these specs
are agreed.

## The specs

The numbers are names, not an order; the order of work is the phase column and
[000, Phases](000-what-lely-is.md#phases).

| Spec | What it covers | Phase | Status |
|---|---|---|---|
| [000 — what lely is](000-what-lely-is.md) | Why it exists, where it stands, what it does and doesn't | — | draft; positioning decided |
| [001 — what is built](001-what-is-built.md) | `validate`, `steps`, `plan`, `show` — and what of it moves | — | built |
| [002 — plugins](002-plugins.md) | The one contract; what flows between steps | 1 | draft — **first to build** |
| [003 — config](003-config.md) | One list of steps, in `lely.yml` or `pyproject.toml` | 1 | draft, shape decided |
| [004 — the Asset Bundle plugin](004-asset-bundle.md) | The first plugin: plan, apply, overview, destroy | 1 | draft |
| [010 — `command` and `bundle.run`](010-command-and-bundle-run.md) | The steps around the bundle | 1 | draft |
| [005 — plan, apply, destroy](005-plan-apply-destroy.md) | The commands, consent, and what happens on failure | 1 | draft |
| [006 — the stevin plugin](006-stevin.md) | Tables, through stevin | — | parked |
| [007 — a UI for plans](007-ui.md) | A plan as a page, each step with its own detail | 2 | draft |
| [008 — GitHub](008-github-actions.md) | The pull-request comment and the job summary | 2 | draft |
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

**What lely is, and how it is introduced**

- **The first line:** "One plan for your whole Databricks deploy." → [000](000-what-lely-is.md#in-one-line)
- **The Kostavo line gets a place for lely:** "…and lely to deploy them as one."
- **Terraform's words, and the difference stated:** not a small Terraform.
  → [000](000-what-lely-is.md#where-it-stands)
- **Phase one is built whole,** and called usable only then. → [000](000-what-lely-is.md#phases)

**The shape**

- **The config is one ordered list of steps,** the bundle one entry in it — and there may be more
  than one bundle. → [003/R1](003-config.md), [004/R3a](004-asset-bundle.md)
- **What flows between steps is written down and checked:** an input is a reference in a step's
  own options, and references only point up the list — so what feeds the bundle is above it and
  what needs something from it is below. → [002/R15](002-plugins.md), [002/R16](002-plugins.md).
  *How* it is checked — plugins declaring their outputs — is still a proposal:
  [002/R14](002-plugins.md).
- **One spelling for a reference:** always `${steps.<name>.<output>}`. → [002/R15a](002-plugins.md)
- **The target is a bare name** each plugin reads its own way, and the workspace comes from
  `--profile` or the environment. → [002/R23](002-plugins.md)
- **The config is found from a subfolder,** by walking up. → [003/R5a](003-config.md)

**Consent**

- **Nothing that changes a workspace runs unasked.** Destroy asks for the target's name at a
  terminal; headless, consent is `--yes` in the command. → [005/R17](005-plan-apply-destroy.md)
- **A step that can't be planned yet** is shown as waiting. A reviewed plan file stops there and
  asks for a new plan; `--yes` without a file runs it; the same rule above the bundle as below.
  → [005/R25](005-plan-apply-destroy.md)
- **Three exit codes:** done, failed, refused. → [005/R31](005-plan-apply-destroy.md)

**Destroy**

- **A destroy can be saved to a file and reviewed first,** like an apply.
  → [005/R14](005-plan-apply-destroy.md)
- **A step that can't destroy is skipped, visibly;** a `command` step may bring a destroy command.
  → [002/R8a](002-plugins.md)

**Seeing what is there**

- **`lely status`** shows what every step has deployed, without changing anything — and before a
  first deploy, what would exist. → [005/R32](005-plan-apply-destroy.md),
  [004/R9a](004-asset-bundle.md)
- **The UI is a web page,** like `stevin ui`. → [007](007-ui.md)
- **"Update GitHub Actions" means what GitHub shows:** the pull-request comment and the job
  summary. Not generating workflow files, and no ready-made Action. → [008](008-github-actions.md)

**Scope**

- **Fake tools only, for now.** Nothing is run against a real workspace yet; what is assumed
  about the Databricks CLI stays marked as unverified.
  → [004, To verify](004-asset-bundle.md#to-verify-on-a-workspace)
- **stevin is out of this for now.** → [006](006-stevin.md)

## Still open

Each has a proposal in its spec.

**Changed in review — these touch something the owner already decided**

1. **A saved destroy plan is run by `lely destroy <file> -t <target>`, not by `lely apply`.** As
   first decided, `lely apply destroy.json --yes` would have destroyed a target with neither word
   on the command line. → [005/R14](005-plan-apply-destroy.md), [005/R20](005-plan-apply-destroy.md)
2. **Fake tools only — with a risk now written next to it.** Seven things about the real CLI are
   assumed, and five of them decide how apply and destroy are built.
   → [004, To verify](004-asset-bundle.md#to-verify-on-a-workspace)

**Found in review — safety**

3. **A reviewed plan is tied to the code it was made from** (the git tree), so a plan approved
   for one commit can't be applied on another. → [005/R36](005-plan-apply-destroy.md)
4. **Every plan, question and file names the workspace and the identity,** and a file is refused
   on another workspace. → [005/R35](005-plan-apply-destroy.md)
5. **How strictly a re-planned step must match what was approved.** Proposed: every change must
   be one that was shown; changes that are gone are fine. → [005/D9](005-plan-apply-destroy.md#to-decide)
6. **Values from the environment, and a plugin's raw data, stay out of files, pages and
   comments.** → [005/R34](005-plan-apply-destroy.md)
7. **Planning runs the project's own code,** so a pull request's plan needs read-only
   credentials; lely says so and `doctor` checks. → [002/R13a](002-plugins.md)

**Found in review — how it works**

8. **A bundle step always deploys** — code is uploaded even when no resource changes — and
   deploys a fresh plan checked against the approved one, so a second run can finish a first.
   → [004/R5a](004-asset-bundle.md), [004/R6](004-asset-bundle.md)
9. **Three answers to "when is an output known":** at plan, once it exists, after every run. A
   step that takes the third kind waits on every deploy, and the plan says so.
   → [002/R14](002-plugins.md), [005/R26](005-plan-apply-destroy.md)
10. **`status` and `destroy` say whose view they show,** because a bundle's deployment record
    depends on who deployed it and where. → [004/R9b](004-asset-bundle.md)
11. **What `command` and `bundle.run` do on apply, destroy and status,** and how a command says
    what it gives. → [010](010-command-and-bundle-run.md)
12. **Whether `-t` is always needed.** → [005/D8](005-plan-apply-destroy.md#to-decide)

**Standing proposals in phase one** — confirm or change

13. Asking again at a terminal before a step that was waiting. → [005/R29](005-plan-apply-destroy.md)
14. `lely.yml` and `[tool.lely]` both present is an error. → [003/R6](003-config.md)
15. The word in the config stays "step" (`uses:`, `lely steps`). → [002/D1](002-plugins.md#to-decide)

**Before phase two**

16. How a project asks for the pull-request comment, and which plan a merge applies.
    → [008](008-github-actions.md#to-decide)
17. Whether the page only shows, and how a plugin supplies its own view. → [007](007-ui.md#to-decide)
18. The UI first, or GitHub first. → [000/D1](000-what-lely-is.md#to-decide)

**Whenever**

19. How lely releases, and whether the recorded Databricks CLI outputs in the tests can stay.
    → [009](009-first-release.md#to-decide)

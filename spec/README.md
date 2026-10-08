# spec

What lely has to do, and how we will know that it does.

`docs/DESIGN.md` says *how* lely is built and why. This folder says *what* each piece of work must
deliver and when it counts as done. Where the two disagree, one of them is wrong: say which,
don't pick one quietly. The owner set a new direction on 2026-10-05,
[000](000-what-lely-is.md) records it, and the design was rewritten to it the same day.

**Phases one and two are built**, tested against fake tools, and run for real on 2026-10-06:
twice on a workspace, and once through the three GitHub workflows. 0.1.0 was released on
2026-10-07. Each spec that was built has an "As built" section: what the code does where the
spec left room, and where it stops short.

## The specs

The numbers are names, not an order; the order of work is in
[000, Phases](000-what-lely-is.md#phases).

| Spec | What it covers | Phase | Status |
|---|---|---|---|
| [000 — what lely is](000-what-lely-is.md) | Why it exists, where it stands, what it does and doesn't | — | agreed |
| [001 — what is built](001-what-is-built.md) | The read-only half as it stood before phase one | — | superseded |
| [002 — plugins](002-plugins.md) | The one contract; what flows between steps | 1 | built |
| [003 — config](003-config.md) | One list of steps, in `lely.yml` or `pyproject.toml` | 1 | built |
| [004 — the Asset Bundle plugin](004-asset-bundle.md) | The first plugin: plan, apply, overview, destroy | 1 | built; run on a workspace twice |
| [010 — `command` and `bundle.run`](010-command-and-bundle-run.md) | The steps around the bundle | 1 | built; `command` removed by 011 on 2026-10-08, `bundle.run` stays |
| [005 — plan, apply, destroy](005-plan-apply-destroy.md) | The commands, consent, and what happens on failure | 1 | built; run on a workspace twice |
| [006 — the stevin plugin](006-stevin.md) | Tables, through stevin | — | parked |
| [007 — a UI for plans](007-ui.md) | A plan as a page, each step with its own detail | 2 | built |
| [008 — GitHub](008-github-actions.md) | The pull-request comment and the job summary | 2 | built; run once through the three workflows |
| [009 — first release](009-first-release.md) | What the repo needs before `uvx lely` works | — | released: 0.1.0, 2026-10-07 |
| [011 — a step on its own](011-a-step-on-its-own.md) | A step as a single script with its own command line; `command` retired; a `Program` base | 3 | built, 2026-10-08; `command` removed the same day |

## How a spec is written

- **Status** — draft, agreed, in progress, built, parked, superseded.
- **Why** — the problem, in a few lines.
- **Requirements** — numbered (`R1`, `R2`, …), each one a thing you can check. Refer to one as
  `004/R7`. Each says where it comes from:
  - *(owner)* — the owner said it, or chose it from options put to them;
  - *(agreed)* — the spec's author proposed it, and the owner accepted the proposals as a
    whole on 2026-10-05. Accepted in one go, not one by one: if one of these turns out to be
    wrong while it is being built, say so before building around it;
  - *(design)* — `docs/DESIGN.md` already said it;
  - *(built)* — the code already does it.
- **Not in this spec** — what was left out on purpose, and where it went.
- **Decided** — questions the owner has answered, with the date.
- **To decide** — questions only the owner can answer. Work that depends on one waits for it.
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
  *How* it is checked: plugins declare their outputs. → [002/R14](002-plugins.md)
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

- **Fake tools only, at first.** That was the decision on 2026-10-05, and phase one was built
  to it. lely has since run on a real workspace twice and once through the three GitHub
  workflows (2026-10-06); what is still assumed about the Databricks CLI stays marked as
  unverified. → [004, Run on a workspace](004-asset-bundle.md#run-on-a-workspace-2026-10-06)
- **stevin is out of this for now.** → [006](006-stevin.md)

**Agreed as proposed**, in one go

Everything the spec's author had proposed, including what came out of the review of the spec.
The ones worth remembering:

- **A saved destroy plan is run by `lely destroy <file> -t <target>`,** never by `lely apply`.
  → [005/R14](005-plan-apply-destroy.md), [005/R20](005-plan-apply-destroy.md)
- **A reviewed plan is tied to what it was made from** — the git tree and the workspace — and
  refused anywhere else. The identity it was planned as is recorded and shown, and may
  differ: a plan is made with credentials that can read, and applied with ones that can
  write. → [005/R35](005-plan-apply-destroy.md),
  [005/R36](005-plan-apply-destroy.md)
- **The approval check:** every change in a re-planned step must be one that was shown; changes
  that are gone are fine. → [005/R7](005-plan-apply-destroy.md)
- **`-t` is always given.** → [005/R37](005-plan-apply-destroy.md)
- **A bundle step always deploys,** with a fresh plan checked against the approved one.
  → [004/R5a](004-asset-bundle.md), [004/R6](004-asset-bundle.md)
- **Plugins declare their outputs,** with one of three answers to "when is it known": at plan,
  once it exists, after every run. → [002/R14](002-plugins.md)
- **A `command` step lists what it gives.** → [010](010-command-and-bundle-run.md#decided)
- **Values from the environment and plugins' raw data stay out of files, pages and comments;**
  planning a pull request needs read-only credentials. → [005/R34](005-plan-apply-destroy.md),
  [002/R13a](002-plugins.md)
- **`status` and `destroy` say whose view they show.** → [004/R9b](004-asset-bundle.md)
- **The config says "step"; a step uses a plugin.** → [002](002-plugins.md#decided)
- **The page only shows; a plugin's view is HTML in lely's frame; GitHub is asked for with
  `--github`.** → [007](007-ui.md#decided), [008](008-github-actions.md#decided)

## Still open

1. **lely has run against a real workspace twice**, on 2026-10-06, with small bundles. Six of
   the eight assumptions held, one could not be tried, and one was wrong: the CLI does not
   refuse a bundle whose target names another host. What the runs couldn't show is listed with
   them: another identity, `bundle.run`, credentials that can only read.
   → [004, Run on a workspace](004-asset-bundle.md#run-on-a-workspace-2026-10-06)
2. **What the builder decided where the specs left room** is in each spec's "As built", and in
   `docs/DESIGN.md` under "Decided while building". None of it is the owner's yet. The one that
   adds something the specs didn't name: an option that names a whole step.
   → [002, As built](002-plugins.md#as-built)
3. **What the bundle resolves from outside lely is not held**: `BUNDLE_VAR_x` at apply, or a
   variable's lookup answering something else, changes what is deployed without changing a line
   of the plan. Whether to fingerprint the resolved variables is the owner's to decide.
   → [004, As built](004-asset-bundle.md#as-built)
4. **Phase two is built: GitHub, then the page.** The order was the owner's to decide; the
   builder took GitHub first, said so, and was told to continue. What the builder decided is
   in [008, As built](008-github-actions.md#as-built) and
   [007, As built](007-ui.md#as-built). The three workflows in `docs/GITHUB.md` have run once
   on a real repository; what that didn't try is listed there. Which plugins come after is still
   open. → [000](000-what-lely-is.md#to-decide)
5. **The first release is out**: 0.1.0, on 2026-10-07, when the owner said.
   → [009](009-first-release.md#as-released-2026-10-07)

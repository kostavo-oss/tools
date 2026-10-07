# 000 — what lely is

**Status:** agreed, 2026-10-05; phases one and two are built, and lely has run on a real
workspace twice and once through the three GitHub workflows (2026-10-06). The direction is the
owner's. Two questions about what comes *after* phase one are still open, under
[To decide](#to-decide).

Requirements are marked *(owner)* where they come from that direction, *(design)* where
`docs/DESIGN.md` already says them, and *(agreed)* where the spec's author proposed them and the
owner accepted them with "go with the proposals".

## In one line

> **One plan for your whole Databricks deploy.**
> The bundle and everything around it — the steps before, the steps after — reviewed before
> anything runs, and taken down again when you say so.

That is the line people meet first *(owner, 2026-10-05: lead with the reviewed deploy)*. Under it
goes what lely replaces: the script around `databricks bundle deploy` *(agreed)*.

The definition, for whoever builds it: lely plans, applies and destroys an ordered list of
steps, each done by a plugin, and keeps no state of its own. The Asset Bundle is one of those
plugins.

## Why it exists

A real deploy to Databricks is an Asset Bundle and the things around it: a table that has to
exist first, a model version looked up and handed to the bundle, a job that has to run once the
bundle is there, a seed, a migration. The bundle has a plan and a deploy. The things around it
have a shell script, or a list of steps in a CI workflow.

That glue is what lely replaces, because glue fails in four ways a team feels:

1. **Nobody sees the whole deploy before it runs.** The bundle can be planned; the script around
   it can't. A reviewer approves a pull request without knowing what the merge will do.
2. **What one step hands the next is invisible.** An environment variable set three lines up, a
   file left in a temp directory. It works until someone reorders two lines.
3. **Nothing is guarded the same way twice.** Whether a destructive change asks first depends on
   who wrote that part of the script.
4. **It only goes one way.** There is a deploy script and no teardown, so dev and pull-request
   environments are made and never removed.

lely's answer to each, in the same order: one plan for every step (R3); values that pass between
steps written down and checked (R4a); one rule for consent and for destructive changes (R9); and
`destroy` (R3).

## Where it stands

- **Beside the bundle, not instead of it.** The bundle stays the bundle and the Databricks CLI
  stays the tool that deploys it. If a bundle resource can do something, the bundle does it, and
  when Databricks adds one, the step that covered it is retired. *(design)*
- **Not a small Terraform.** The words are the same — plan, apply, destroy — and lely uses them
  because everyone already knows what they promise. The job is not the same. lely manages no
  resource itself and remembers nothing: the Databricks CLI knows what a bundle deployed. lely
  owns the order, the review and the consent. Terraform is still for the platform — and it can
  do what lely by its nature can't: notice drift, and clean up what a config no longer names.
  *(owner, 2026-10-05: borrow the words, state the difference)*
- **Not a task runner.** Make and a CI workflow run commands in order. A lely step can say what
  it *would* do before it does it, hands on what it produced in a way that is checked, and can be
  undone. *(agreed)*
- **Not a workflow engine.** It runs at deploy time, once, top to bottom. What runs every night
  is a job, and jobs are the bundle's. *(design)*
- **In the Kostavo line** lely is not a fourth layer: it is what carries the layers out
  together. The line becomes: **"Terraform for your platform, Asset Bundles for your code, stevin
  for your data model — and lely to deploy them as one."** *(owner, 2026-10-05. The other
  repositories and the organisation's front page still carry the three-part line.)*

### When not to use it

Said on the first page, because a tool that names who it isn't for is easier to trust:

- **One bundle and nothing around it.** `databricks bundle deploy` is all you need.
- **Every extra step is an opaque script.** lely gives it an order, checked inputs and one rule
  for consent, but a plan that reads "runs `deploy.sh`" shows a reviewer little
  ([010](010-command-and-bundle-run.md)).
- **You need an audit trail, drift detection, or cleanup of what you stopped declaring.** Those
  need state, and lely has none.
- **Your CI isn't GitHub Actions,** for now.

*(agreed)*

## Who it is for

A team that deploys to Databricks with a bundle and has more to deploy than the bundle covers,
to more than one target, through pull requests — and that today keeps a deploy script it would
rather not own.

## What it does

- **R1 — Steps, in order.** A project lists its steps in a config file. What comes before the
  bundle is a pre-deploy step and what comes after is a post-deploy step; to lely they are all
  steps. *(owner)*
- **R2 — Every step is a plugin's.** The Asset Bundle is a plugin. Running a command is a
  plugin. stevin will be one. The core knows none of them by name. → [002](002-plugins.md)
  *(owner)*
- **R3 — Three verbs: `plan`, `apply`, `destroy`.** Plan says what would change and changes
  nothing. Apply does it. Destroy takes it down again. → [005](005-plan-apply-destroy.md)
  *(owner; plan and apply are also the design's)*
- **R4 — No state.** lely writes no state file and keeps no history. Whatever a plugin needs to
  know, it reads from the system it manages — the bundle plugin from the Databricks CLI.
  *(owner, design)*
- **R4a — What passes between steps is written down.** A step that feeds the bundle and a step
  that needs something from it both say so in their own options, and lely checks it before
  anything runs. → [002/R14–R21](002-plugins.md) *(owner)*
- **R5 — Its own config, in its own file or in `pyproject.toml`.** → [003](003-config.md)
  *(owner)*
- **R6 — A plugin can say, in detail, what it created.** Not "3 changes": which things, under
  which names, with their ids and links. → [002/R6](002-plugins.md), [004/R7](004-asset-bundle.md)
  *(owner)*
- **R7 — A plan can be looked at in a UI,** each step with its own detail. → [007](007-ui.md)
  *(owner)*
- **R8 — It keeps GitHub up to date:** the plan as one comment on the pull request, and the
  result on the run's page. → [008](008-github-actions.md) *(owner)*
- **R9 — Nothing that changes a workspace runs unasked, and a destructive change is named and
  refused unless allowed.** → [005](005-plan-apply-destroy.md) *(owner, design)*
- **R10 — What isn't known at plan time is said, not guessed.** *(design)*
- **R11 — A plugin is small and yours to write:** a Python class in the repo, an installed
  package, or a pair of commands, under the same rules as the ones lely ships. *(design)*

## What it does not do

Kept from the design:

- be a workflow engine — one ordered list, no DAG, no parallel steps, no retries
- roll back a failed apply; running it again finishes it
- keep a state file or a run history — and so it cannot see what the config no longer names. A
  step that is removed or renamed, a target taken out of a step's `targets:`, a bundle moved to
  another path: what they deployed stays, and neither `destroy` nor `status` knows it is there.
  Destroy first, then remove the step. *(the price of no state, found in review)*
- build artifacts
- do through a step what a bundle resource can do
- generate YAML for a bundle to include: a bundle is fed variables, nothing else
- support the Terraform engine
- CI systems other than GitHub Actions, for now

No longer excluded: `bundle destroy` and teardown.

## Phases

1. **The Asset Bundle, as a plugin, with steps around it** — built as one piece, and called
   usable only when all of it is there. *(owner: "start with asset bundles"; and, 2026-10-05,
   "all of phase one, then use it")* The order it is built in, each on the one before:
   1. the contract, and the bundle moved out of the core with every test still passing —
      [002](002-plugins.md)
   2. the config as one list — [003](003-config.md)
   3. the bundle plugin — [004](004-asset-bundle.md)
   4. `command` and `bundle.run` — [010](010-command-and-bundle-run.md)
   5. apply, status, destroy, doctor — [005](005-plan-apply-destroy.md)
2. **Around it:** the UI ([007](007-ui.md)) and GitHub ([008](008-github-actions.md)). Which
   first is [D1](#to-decide).

Outside the phases: **stevin** ([006](006-stevin.md)) is the owner's to take up separately, and
[009 — first release](009-first-release.md) happened on 2026-10-07, when the owner said.

## What this changes

Against `docs/DESIGN.md` and the code as built ([001](001-what-is-built.md)):

| Was | Becomes |
|---|---|
| `bundle destroy` and teardown are a non-goal | `destroy` is the third verb |
| The bundle is the fixed middle: pre steps, *the bundle*, post steps | The bundle is a plugin like any other, at whatever place it is listed |
| The core resolves the bundle: targets, `${var.…}`, `${resources.…}`, `bundle_vars` | The bundle plugin does, and hands them on as its outputs |
| Config is `lely.yml` | `lely.yml` or `pyproject.toml` |
| Three renderers: terminal, Markdown, JSON | Those, and a UI |
| A step reports changes | A plugin can also report, in detail, what exists because of it |

`docs/DESIGN.md` was rewritten to match on 2026-10-05, once these specs were agreed.

## Decided

All by the owner, on 2026-10-05.

- **The first line** (was D3): the reviewed deploy — "One plan for your whole Databricks
  deploy."
- **The Kostavo line** (was D4): lely is added to it — "…and lely to deploy them as one."
- **Terraform:** borrow its words and state the difference; don't avoid the comparison and don't
  lean on it.
- **How phase one becomes usable** (was D5): all of it, then use it — no slices.

## To decide

- **D1 — After phase one: the UI first, or GitHub first?**
- **D2 — Further plugins.** The design names Lakebase schemas and three MLflow steps as "later".
  Still the next ones, and in which order?

## Done when

The repository's README opens with the line above, `docs/DESIGN.md` says what this folder says
— both done, 2026-10-05 — and the two questions under "To decide" are answered.

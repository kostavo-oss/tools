# 000 — what lely is

**Status:** draft. The direction is the owner's, given on 2026-10-05; it replaces parts of
`docs/DESIGN.md`, listed under [What this changes](#what-this-changes). The positioning —
[Why it exists](#why-it-exists) and [Where it stands](#where-it-stands) — is a proposal.

Requirements are marked *(owner)* where they come from that direction, *(design)* where
`docs/DESIGN.md` already says them, and *(proposed)* where neither does and this is a suggestion.

## In one line

lely plans, applies and destroys everything a Databricks deploy consists of — as an ordered list
of steps, each done by a plugin — and keeps no state of its own. The Asset Bundle is one of those
plugins.

That is the *definition*. The line people should meet first is a different question:
[D3](#to-decide).

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

*(proposed)*

- **Beside the bundle, not instead of it.** The bundle stays the bundle and the Databricks CLI
  stays the tool that deploys it. If a bundle resource can do something, the bundle does it, and
  when Databricks adds one, the step that covered it is retired.
- **Not a small Terraform.** `plan`, `apply`, `destroy` sound like one. But lely manages no
  resource itself and remembers nothing: each plugin's own tool knows what exists. lely owns the
  order, the review and the consent — not the resources. Terraform is still for the platform.
- **Not a task runner.** Make and a CI workflow run commands in order. A lely step can say what
  it *would* do before it does it, and can be undone.
- **Not a workflow engine.** It runs at deploy time, once, top to bottom. What runs every night
  is a job, and jobs are the bundle's.
- **In the Kostavo line** — "Terraform for your platform, Asset Bundles for your code, stevin for
  your data model" — lely is not a fourth layer. It is what carries the layers out together, as
  one deploy. Whether the line should say so is [D4](#to-decide).

**When not to use it.** One bundle and nothing around it: `databricks bundle deploy` is all you
need, and lely would add a file and no value. That is worth saying on the first page.

## Who it is for

A team that deploys to Databricks with a bundle and has more to deploy than the bundle covers,
to more than one target, through pull requests — and that today keeps a deploy script it would
rather not own. Which of them lely speaks to *first* is [D3](#to-decide).

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
- keep a state file or a run history
- build artifacts
- do through a step what a bundle resource can do
- generate YAML for a bundle to include: a bundle is fed variables, nothing else
- support the Terraform engine
- CI systems other than GitHub Actions, for now

No longer excluded: `bundle destroy` and teardown.

## Phases

1. **The Asset Bundle, as a plugin, with steps around it** — [002](002-plugins.md),
   [003](003-config.md), [004](004-asset-bundle.md), [010](010-command-and-bundle-run.md),
   [005](005-plan-apply-destroy.md). *(owner: "start with asset bundles")* In what order these
   become usable is [D5](#to-decide).
2. **Around it:** the UI ([007](007-ui.md)) and GitHub ([008](008-github-actions.md)). Which
   first is [D1](#to-decide).

Outside the phases: **stevin** ([006](006-stevin.md)) is the owner's to take up separately, and
[009 — first release](009-first-release.md) happens when the owner says.

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

`docs/DESIGN.md` is rewritten to match once these specs are agreed — not before, so there is one
place to argue in.

## To decide

- **D1 — After phase one: the UI first, or GitHub first?**
- **D2 — Further plugins.** The design names Lakebase schemas and three MLflow steps as "later".
  Still the next ones, and in which order?
- **D3 — The first line, and who it is said to.** The definition above is accurate and sells
  nothing. Three ways to lead, each for a different reader:
  1. *The reviewed deploy* — "One plan for your whole Databricks deploy: the bundle and
     everything around it, reviewed before anything runs." For the team that got burned by a
     merge.
  2. *The deploy script, gone* — "Replace the script around `bundle deploy`: steps before and
     after, with a plan, a teardown, and nothing passed along by accident." For the person who
     maintains that script.
  3. *Environments that go away again* — "Stand up a whole Databricks environment for a branch,
     and take it down again: plan, apply, destroy." For teams that want a workspace per pull
     request.

  *(proposed: 1 as the headline, with 2 as the sentence under it. 3 is real, but it only becomes
  true once destroy has run against a workspace.)*
- **D4 — The Kostavo line.** Today: "Terraform for your platform, Asset Bundles for your code,
  stevin for your data model." lely is in none of the three. Extend it — "…and lely to deploy
  them as one" — or leave the line alone and describe lely next to it? *(proposed: extend it;
  otherwise the family's own tagline has no place for one of its three tools)*
- **D5 — The first usable cut of phase one.** All of phase one before anything can be used, or
  in slices: first plan and apply for a bundle with `command` steps around it and `status`; then
  destroy; then `bundle.run`, `pyproject.toml` and `doctor`? *(proposed: slices, in that order —
  each one a tool somebody could run)*

## Done when

Every "to decide" in this folder that touches phase one is answered, D3 and D4 have an answer the
README can open with, and this page describes lely without a proposal in it.

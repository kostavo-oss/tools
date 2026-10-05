# 000 — what lely is

**Status:** draft. The direction is the owner's, given on 2026-10-05; it replaces parts of
`docs/DESIGN.md`, listed under [What this changes](#what-this-changes).

Requirements are marked *(owner)* where they come from that direction, *(design)* where
`docs/DESIGN.md` already says them, and *(proposed)* where neither does and this is a suggestion.

## In one line

lely plans, applies and destroys everything a Databricks deploy consists of — as an ordered list
of steps, each done by a plugin — and keeps no state of its own. The Asset Bundle is one of those
plugins.

## Who it is for

A team that deploys to Databricks and has more to deploy than one tool covers: a bundle, table
schemas, a job that has to run in between, a lookup one step needs from another. Today that is a
shell script around `bundle deploy`, which nobody reviews before it runs and nothing can undo.

## What it does

- **R1 — Steps, in order.** A project lists its steps in a config file. What comes before the
  bundle is a pre-deploy step and what comes after is a post-deploy step; to lely they are all
  steps. *(owner)*
- **R2 — Every step is a plugin's.** The Asset Bundle is a plugin. stevin is a plugin. Running a
  command is a plugin. The core knows none of them by name. → [002](002-plugins.md) *(owner)*
- **R3 — Three verbs: `plan`, `apply`, `destroy`.** Plan says what would change and changes
  nothing. Apply does it. Destroy takes it down again. → [005](005-plan-apply-destroy.md)
  *(owner; plan and apply are also the design's)*
- **R4 — No state.** lely writes no state file and keeps no history. Whatever a plugin needs to
  know, it reads from the system it manages — the bundle from the Databricks CLI, stevin from
  Unity Catalog. *(owner, design)*
- **R5 — Its own config, in its own file or in `pyproject.toml`.** → [003](003-config.md)
  *(owner)*
- **R6 — A plugin can say, in detail, what it created.** Not "3 changes": which things, under
  which names, with their ids and links. → [002/R6](002-plugins.md), [004/R7](004-asset-bundle.md)
  *(owner)*
- **R7 — A plan can be looked at in a UI,** each step with its own detail. → [007](007-ui.md)
  *(owner)*
- **R8 — It keeps GitHub Actions up to date.** → [008](008-github-actions.md) *(owner — what
  exactly is updated is that spec's first question)*
- **R9 — A destructive change is named, and refused unless allowed.** *(design)*
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

1. **The default plugins.** First the Asset Bundle — [002](002-plugins.md),
   [003](003-config.md), [004](004-asset-bundle.md), [005](005-plan-apply-destroy.md) — then
   stevin, [006](006-stevin.md). *(owner: "start with asset bundles")*
2. **Around them:** the UI ([007](007-ui.md)) and GitHub Actions
   ([008](008-github-actions.md)). Which first is [D1](#to-decide).

[009 — first release](009-first-release.md) is independent and happens when the owner says.

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

- **D1 — After the default plugins: the UI first, or GitHub Actions first?**
- **D2 — Further plugins.** The design names Lakebase schemas and three MLflow steps as "later".
  Still the next ones after stevin, and in which order?

## Done when

Every "to decide" in this folder that touches phase one is answered, and this page describes
lely without one.

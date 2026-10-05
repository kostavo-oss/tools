# 002 — plugins

**Status:** draft. Phase one, and the base for everything after it.

## Words

- A **plugin** is a kind of work lely can do: deploy an Asset Bundle, change tables with stevin,
  run a command. It is code — lely's own, an installed package's, or a file in the repo.
- A **step** is one use of a plugin in a project: an entry in the config with a name and
  options.

## Why

Today the bundle is built into the core: its own key in the config, its own place in the order,
its own code path. Everything else is a step. The owner's direction turns that around — the
bundle is just a plugin — so the core does one thing: run steps in order, through one contract.
What the bundle needs, every plugin can then have.

## Requirements

### One contract

- **R1** — The core has no special case for any plugin. The Asset Bundle, stevin and `command`
  go through the same contract as a class somebody wrote in their repo. *(owner)*
- **R2** — A plugin is found by a registered name (the entry-point group `lely.steps`), by
  `package.module:Class`, or by `./file.py:Class` in the repo. The plugins lely ships register
  the same way anyone's would. *(built)*
- **R3** — A plugin declares its options. A step's options are checked against them offline, by
  `lely validate`. *(built)*

### What a plugin can do

- **R4 — Plan.** Say what `apply` would change, and change nothing. *(built)*
- **R5 — Apply.** Do what the plan said, and no more. Return outputs for the steps after it.
  *(design)*
- **R6 — Overview.** Say, in detail, what exists because of this step: each thing with its kind,
  its name, its id and a link, where the system has them. Available right after an apply and on
  its own, without changing anything. *(owner)*
- **R7 — Destroy.** Say what `destroy` would remove, and then remove it. *(owner)*
- **R8 — Show itself.** Optionally, give the UI its own detailed view of a plan. Without one, the
  UI shows the plan's changes. → [007](007-ui.md) *(owner)*

Not every plugin has something to destroy or to show: `command` runs what it is told, and a step
that only *runs* a job deploys nothing. A plugin says which of R6–R8 it supports, and
`lely steps` lists that. What `destroy` does with a step that can't destroy is
[D3](#to-decide).

### Rules every plugin follows

- **R9 — It keeps no state.** `plan` and `apply` may run on different machines, days apart; only
  the plan passes between them. What a plugin knows, it reads from the system it manages.
  *(owner, design)*
- **R10 — It touches only what its options name.** Anything else it finds is reported as not its
  own, and never changed. *(design)*
- **R11 — It destroys only what it can show is its own.** A plugin that can't tell what it made
  from what it merely found has nothing it may destroy. *(proposed — it is R9 and R10 applied to
  the verb that can't be taken back)*
- **R12 — Destructive is declared.** Deleting, replacing or dropping data is marked, in a plan and
  in a destroy plan alike. *(design)*
- **R13 — No secrets in a plan.** *(built)*

### Between steps

- **R14** — What a step returns is available to every later step as
  `${steps.<name>.<output>}`. This is the only way one step feeds another — the bundle's
  variables included. *(design; the bundle part is new)*
- **R15** — A step gets: the target's name, its own options with references resolved, the
  outputs of earlier steps, the project's directory, a log, and a way to reach the workspace.
  Where that last one comes from is [D2](#to-decide).

### For people writing one

- **R16** — `lely.testing` checks a plugin against R4–R13: plan makes no writes; plan, apply,
  plan again is empty for a plugin that converges; apply then destroy then plan is what it was
  before; an overview changes nothing; no secret reaches a file. Every plugin lely ships passes
  it. *(plan half built)*

## The plugins of phase one

| `uses:` | Does | Spec |
|---|---|---|
| `bundle` | Deploys an Asset Bundle | [004](004-asset-bundle.md) |
| `stevin` | Tables, views, functions and grants, through stevin | [006](006-stevin.md) |
| `bundle.run` | Runs a job, pipeline or app from a bundle | built (plan half) |
| `command` | Runs commands you give it | built (plan half) |

## Not in this spec

- How steps are written down → [003](003-config.md)
- The commands and their flags → [005](005-plan-apply-destroy.md)

## To decide

- **D1 — Is "plugin" the word in the config too?** The config says `uses:`, the entry-point group
  is `lely.steps`, the command is `lely steps`. Nothing is published, so all three can still
  change — to `lely plugins`, say. *(proposed: keep them; a step uses a plugin)*
- **D2 — Where the target and the workspace come from.** Today both are the bundle's: `-t dev` is
  a bundle target, and the workspace is the one that target names. If the bundle is just a
  plugin, a project can have two bundles, or none. Then either lely has targets of its own, each
  naming a workspace, or `-t` stays a bare name that every plugin reads its own way and the
  workspace comes from `--profile` or the environment. *(proposed: the second — it adds no
  config, and it is what works today)*
- **D3 — A step that can't destroy.** Skip it and say so in the destroy plan, or refuse to destroy
  at all until the project says, per step, that skipping is fine? *(proposed: skip and say so —
  a `command` that seeds data shouldn't block taking a dev target down)*
- **D4 — The short references.** `${var.catalog}` and `${resources.jobs.backfill.id}` exist
  today because the bundle is built in. As a plugin's outputs they would be
  `${steps.<bundle step>.var.catalog}`. Keep the short forms as another spelling whenever a
  project has exactly one bundle step? *(proposed: yes)*

## Done when

- The bundle goes through the same contract as every other plugin, and no module in the core
  imports anything bundle-specific.
- `lely steps` shows each plugin with its options and which of overview, destroy and its own
  view it supports.
- R16's checks exist and the four plugins above pass the ones that apply to them.
- D1–D4 are answered here.

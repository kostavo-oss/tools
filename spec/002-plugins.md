# 002 — plugins

**Status:** draft. Phase one, and the base for everything after it.

## Words

- A **plugin** is a kind of work lely can do: deploy an Asset Bundle, run a command. It is code —
  lely's own, an installed package's, or a file in the repo.
- A **step** is one use of a plugin in a project: an entry in the config with a name and
  options.

## Why

Today the bundle is built into the core: its own key in the config, its own place in the order,
its own code path. Everything else is a step. The owner's direction turns that around — the
bundle is just a plugin — so the core does one thing: run steps in order, through one contract.
What the bundle needs, every plugin can then have.

## Requirements

### One contract

- **R1** — The core has no special case for any plugin. The Asset Bundle and `command` go through
  the same contract as a class somebody wrote in their repo. *(owner)*
- **R2** — A plugin is found by a registered name (the entry-point group `lely.steps`), by
  `package.module:Class`, or by `./file.py:Class` in the repo. The plugins lely ships register
  the same way anyone's would. *(built)*
- **R3** — A plugin declares its options. A step's options are checked against them offline, by
  `lely validate`. *(built)*

### What a plugin can do

- **R4 — Plan.** Say what `apply` would change, and change nothing. *(built)*
- **R5 — Apply.** Do what the plan said, and no more. *(design)*
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

### What flows between steps

Sometimes a step feeds the bundle: it looks up a model version, and the bundle needs it as a
variable. Sometimes a step needs something from the bundle: the id of a job it just created.
Both are the same thing — one step's output is another step's input — and these rules are what
make it impossible to be vague about which is which. *(owner: "how can we make sure that is
clearly defined")*

- **R14 — Outputs are declared.** A plugin lists what a step of it gives: each output's name, and
  when its value is known — *at plan*, before anything is deployed, or only *after apply*.
  `lely steps` prints them next to the options. *(proposed; today a plugin declares only its
  options, so an output's name can't be checked until it is used)*
- **R15 — An input is a reference, and nothing else.** A step takes a value from another step
  only by writing `${steps.<name>.<output>}` in its own options. There is no other channel: no
  file left behind, no environment handed on, no lookup behind the scenes. Whatever a step
  depends on can be read in its `with:`. *(design)*
- **R16 — References point up the list, never down.** A step can use the outputs of steps listed
  before it. So the order of the list *is* the order of dependency, and it reads top to bottom:
  what feeds the bundle is written above it, what needs something from the bundle below it.
  *(built, as pre and post)*
- **R17 — A step that needs both is two steps.** One above the bundle, one below. Because of R16
  there is no way to write a circle. *(follows from R16)*
- **R18 — All of it is checked offline.** `lely validate` refuses a reference to a step that
  isn't there; to one listed further down, with a message that says to move it; to an output its
  plugin doesn't declare; and to a step that is skipped for a target the referring step runs
  for. *(the first two built; the last two need R14)*
- **R19 — A value that isn't known yet is never guessed.** If a step's input is only known after
  apply — the id of a job this deploy creates — the plan shows that step as *decided at apply*
  and names the output it is waiting for. *(built)*
- **R20 — The wiring is shown.** In a plan — terminal, page or Markdown — every step lists what it
  takes, from which step, and the value where it is known:
  `model_version = 14  ← model.version`. And `lely validate` prints the wiring of the whole
  project: for each step, what it takes and what it gives. *(proposed)*
- **R21 — Destroy reads the same wiring.** Inputs are resolved from the top of the list down, as
  for a plan; removal then goes from the bottom up. So a step above the bundle that only looks
  something up still does its lookup, and the bundle can be resolved and destroyed; and a step
  below the bundle is destroyed while the bundle, and the id it needed, still exist. A value a
  destroy needs that can't be had without applying stops the destroy plan, with the reason.
  *(proposed)*

### What a step is given

- **R22** — The target's name; its own options, with references resolved; the project's
  directory; a log; and a way to reach the workspace. *(built)*
- **R23 — The target is a name, and each plugin reads it its own way.** `-t dev` is handed to
  every step as it is: the bundle plugin takes it as a bundle target. lely keeps no list of
  targets of its own. *(owner, 2026-10-05)*
- **R24 — The workspace comes from the command line or the environment:** `--profile`, or the
  variables the Databricks SDK and CLI already read. One run talks to one workspace.
  *(owner, 2026-10-05)*

### For people writing one

- **R25** — `lely.testing` checks a plugin against R4–R21: plan makes no writes; plan, apply,
  plan again is empty for a plugin that converges; apply then destroy then plan is what it was
  before; an overview changes nothing; every output a step returns was declared, and none that
  was declared *at plan* is missing from a plan; no secret reaches a file. Every plugin lely
  ships passes it. *(plan half built)*

## The plugins of phase one

| `uses:` | Does | State |
|---|---|---|
| `bundle` | Deploys an Asset Bundle | to build — [004](004-asset-bundle.md) |
| `bundle.run` | Runs a job, pipeline or app from a bundle | plan half built |
| `command` | Runs commands you give it | plan half built |

`stevin` is not part of this phase: the owner takes it up separately ([006](006-stevin.md)). Its
plan half exists in the code and is left as it is.

## Not in this spec

- How steps are written down → [003](003-config.md)
- The commands and their flags → [005](005-plan-apply-destroy.md)

## Decided

- **The target and the workspace** (was D2): a bare name each plugin reads its own way, and the
  workspace from `--profile` or the environment — R23 and R24. *(owner, 2026-10-05)*

## To decide

- **D1 — Is "plugin" the word in the config too?** The config says `uses:`, the entry-point group
  is `lely.steps`, the command is `lely steps`. Nothing is published, so all three can still
  change — to `lely plugins`, say. *(proposed: keep them; a step uses a plugin)*
- **D3 — A step that can't destroy.** Skip it and say so in the destroy plan, or refuse to destroy
  at all until the project says, per step, that skipping is fine? *(proposed: skip and say so —
  a `command` that seeds data shouldn't block taking a dev target down)*
- **D4 — One spelling for a reference.** `${var.catalog}` and `${resources.jobs.backfill.id}`
  exist today because the bundle is built in. As a plugin's outputs they are
  `${steps.app.var.catalog}` and `${steps.app.resources.jobs.backfill.id}`. Keep the short forms
  as a second spelling? *(proposed: no. One spelling, which always names the step a value comes
  from, is what R15 is for — and nothing is published, so nobody has to change a file.)*

## Done when

- The bundle goes through the same contract as every other plugin, and no module in the core
  imports anything bundle-specific.
- `lely steps` shows each plugin with its options, its outputs and when each is known, and which
  of overview, destroy and its own view it supports.
- `lely validate` on a project with a reference pointing down the list, and on one naming an
  output that doesn't exist, fails with a message that says what to change.
- R25's checks exist and the plugins above pass the ones that apply to them.
- D1, D3 and D4 are answered here.

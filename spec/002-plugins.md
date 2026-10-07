# 002 — plugins

**Status:** built, 2026-10-05, and tested against fakes; the bundle plugin was run on a real
workspace twice (2026-10-06) — see [As built](#as-built). The markers on
the requirements below (*built*, *design*, "today …") say where each came from, and describe the
code as it was before this was built.

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
  the same way anyone's would. `lely steps` lists the registered ones and the ones the project's
  config names. *(built, except that `lely steps` lists only the registered ones today)*
- **R3** — A plugin declares its options. A step's options are checked against them offline, by
  `lely validate`. *(built)*

### What a plugin can do

- **R4 — Plan.** Say what `apply` would change, and change nothing. *(built)*
- **R5 — Apply.** Do what the plan said, and no more. *(design)*
- **R6 — Overview.** Say what exists because of this step, one line per thing: its kind, its key
  and its name, always; its id and a link, where the system has them; and whether it is deployed.
  Available right after an apply and on its own, without changing anything.
  *(asked for by the owner: a detailed overview of what it created; the fields are agreed)*
- **R7 — Destroy.** Say what `destroy` would remove, and then remove it. *(owner)*
- **R8 — Show itself.** Optionally, give the UI its own detailed view of a plan. Without one, the
  UI shows the plan's changes. This arrives with the UI, in phase two. → [007](007-ui.md)
  *(owner)*
- **R8a — A plugin with nothing to undo says so.** Not every plugin has something to destroy or
  to list: a step that only *runs* a job deploys nothing. A plugin says which of R6 and R7 it
  supports, `lely steps` lists that, and `destroy` skips a step that can't destroy — visibly,
  with the reason. *(owner, 2026-10-05)*
- **R8b — `command` can be given a destroy command,** beside its plan and apply commands. With
  one, the step is destroyed by running it; without one, it is skipped as in R8a.
  *(owner, 2026-10-05)*

### Rules every plugin follows

- **R9 — It keeps no state.** `plan` and `apply` may run on different machines, days apart; only
  the plan passes between them. What a plugin knows, it reads from the system it manages.
  *(owner, design)*
- **R10 — It touches only what its options name.** Anything else it finds is reported as not its
  own, and never changed. *(design)*
- **R11 — It destroys only what it can show is its own.** A plugin that can't tell what it made
  from what it merely found has nothing it may destroy. `command` is the one exception, by its
  nature: its destroy command is whatever the project wrote, lely can vouch for none of it, and
  so the destroy plan shows that command line in full. *(agreed)*
- **R12 — Destructive is declared.** Deleting, replacing or dropping data is marked, in a plan and
  in a destroy plan alike. A change a plugin's tool reports and the plugin doesn't recognise is
  treated as destructive. *(design; the second sentence is built, for the bundle)*
- **R13 — No secrets in a plan.** → [005/R34](005-plan-apply-destroy.md) *(built, for values a
  plugin marks as secret)*
- **R13a — Planning runs the project's own code, and says so.** A plugin that is a file in the
  repo, and a `command` step's plan command, are run by `plan`; a repo plugin is loaded even by
  `validate`. So wherever that code isn't trusted yet — a pull request — `plan` must be given
  credentials that can read and nothing more. lely can't enforce that. It says it where people
  will read it: in the docs' workflow ([008/R7](008-github-actions.md)) and in `lely doctor`.
  *(agreed — found in review)*

### What flows between steps

Sometimes a step feeds the bundle: it looks up a model version, and the bundle needs it as a
variable. Sometimes a step needs something from the bundle: the id of a job it just created.
Both are the same thing — one step's output is another step's input — and these rules are what
make it impossible to be vague about which is which. *(the owner asked how this could be
made clearly defined; the principle is decided, the mechanics below are agreed where marked)*

- **R14 — Outputs are declared.** A plugin lists what a step of it gives. Each output has a name
  and one of three answers to "when is it known?":
  - **at plan** — always, before anything is deployed. A looked-up model version.
  - **once it exists** — when planning, if the thing is already there; otherwise only after
    apply. The id of a job the bundle deploys.
  - **after every run** — never when planning: it is produced by running. What a script writes
    while it applies.

  `lely steps` prints them next to the options. *(agreed; today a plugin declares only its
  options, so an output's name can't be checked until it is used)*
- **R14a — An output whose name depends on the project is declared as a shape.** The bundle
  plugin can't list `resources.jobs.backfill.id` ahead of time: the job is the project's. It
  declares `resources.<type>.<key>.id`, where each `<…>` stands for exactly one part of the
  name. Offline, a reference is checked against the shape; that the job itself exists is checked
  when the step is planned, with the same kind of message. *(agreed)*
- **R15 — An input is a reference, and nothing else.** A step takes a value from another step
  only by writing `${steps.<name>.<output>}` in its own options. There is no other channel: no
  file left behind, no environment handed on, no lookup behind the scenes. Whatever a step
  depends on can be read in its `with:`. *(design)*
- **R15a — There is one spelling.** Every reference names the step the value comes from. The
  short `${var.…}`, `${bundle.…}`, `${workspace.…}` and `${resources.…}` that exist today, from
  when the bundle was built in, go. `${env.<NAME>}` stays: the environment is not a step.
  *(owner, 2026-10-05)*
- **R16 — References point up the list, never down.** A step can use the outputs of steps listed
  before it. So the order of the list *is* the order of dependency, and it reads top to bottom:
  what feeds the bundle is written above it, what needs something from the bundle below it.
  *(built, as pre and post)*
- **R17 — A step that needs both is two steps.** One above the bundle, one below. Because of R16
  there is no way to write a circle. *(follows from R16)*
- **R18 — As much as can be is checked offline.** `lely validate` refuses a reference to a step
  that isn't there; to one listed further down, with a message that says to move it; to an output
  its plugin doesn't declare, or that doesn't fit a declared shape; and to a step whose `targets:`
  leave out a target the referring step runs for. What can only be known with the tool at hand —
  that a named job is really in the bundle — is refused by `plan`, before anything changes.
  *(the first two built; the rest need R14)*
- **R19 — A value that isn't known yet is never guessed.** A step that takes one is shown in the
  plan as *waiting*, with the output it is waiting for by name. A step that takes an *after every
  run* output waits on every deploy, not only the first — and `validate` says so when it prints
  the wiring, because such a step can never be approved ahead of time. What apply does at a
  waiting step is [005/R25–R30](005-plan-apply-destroy.md). *(built, as "decided at apply"; the
  warning is agreed)*
- **R20 — The wiring is shown.** In a plan, every step lists what it takes, from which step, and
  the value where it is known: `model_version = 14  ← model.version`. And `lely validate` prints
  the wiring of the whole project: for each step, what it takes and what it gives. In phase one
  that is the terminal and the plan file; the page and Markdown follow in phase two. *(agreed)*
- **R21 — Destroy reads the same wiring.** Inputs are resolved from the top of the list down, by
  planning each step as usual; removal then goes from the bottom up. So a step above the bundle
  that only looks something up still does its lookup, and a step below the bundle is destroyed
  while the bundle, and the id it needed, still exist. A step whose input doesn't exist — the
  job was never deployed, or the value only ever came from a run — is skipped, with the reason:
  lely can't know what it would have to remove. The rest of the destroy goes on. *(agreed)*

### What a step is given

- **R22 — Only this:** the target's name; its own options, with references resolved; the
  project's directory; a log; and a way to reach the workspace. Not the other steps' outputs as a
  whole — today a step is handed all of them, and the bundle besides, which would make R15 a
  habit instead of a rule. *(narrower than what is built)*
- **R23 — The target is a name, and each plugin reads it its own way.** `-t dev` is handed to
  every step as it is: the bundle plugin takes it as a bundle target. lely keeps no list of
  targets of its own — so a name no plugin knows is only caught by a plugin that checks it, as
  the bundle's does. *(owner, 2026-10-05)*
- **R24 — The workspace comes from the command line or the environment:** `--profile`, or the
  variables the Databricks SDK and CLI already read. One run talks to one workspace — every
  step in it, two bundle steps included. *(owner, 2026-10-05; today the host is taken from the
  bundle's target)*

### For people writing one

- **R25** — `lely.testing` checks a plugin against the rules above, each as something that can
  fail:
  - *plan changes nothing* — run against a recording fake, it makes no call outside a list of
    reads;
  - *apply does what the plan said* — plan, apply, plan again shows no changes, for a plugin that
    converges;
  - *destroy undoes it* — apply, destroy, plan shows what the first plan showed;
  - *only its own* — a look-alike object the plugin didn't make is reported as not its own, and
    is still there after apply and after destroy;
  - *an overview changes nothing*, and every line has a kind, a key and a name;
  - *outputs are as declared* — nothing undeclared is returned, and nothing declared *at plan* is
    missing from a plan;
  - *no secret reaches a file.*

  Every plugin lely ships passes the ones that apply to it. *(the plan half exists, without the
  recording fake)*

### The contract, as a sketch

*(agreed — the names are settled when it is built, the parts are what the rules above need)*

```python
class Plugin(Protocol):
    Options: type  # a frozen dataclass; `with:` is checked against it
    outputs: tuple[Output, ...]  # R14: name or shape, and when it is known

    def plan(self, ctx) -> StepPlan: ...  # R4
    def apply(self, ctx, plan) -> Outputs: ...  # R5

    # optional — a plugin without one says so by not having it (R8a)
    def overview(self, ctx) -> tuple[Item, ...]: ...  # R6
    def plan_destroy(self, ctx) -> StepPlan: ...  # R7
    def destroy(self, ctx, plan) -> None: ...  # R7


@dataclass(frozen=True, slots=True)
class Item:  # one line of an overview
    kind: str  # "job"
    key: str  # "jobs.backfill"
    name: str  # "shop-backfill"
    deployed: bool
    id: str | None = None
    url: str | None = None
```

## The plugins of phase one

| `uses:` | Does | State |
|---|---|---|
| `bundle` | Deploys an Asset Bundle | to build — [004](004-asset-bundle.md) |
| `command` | Runs commands you give it | plan half built — [010](010-command-and-bundle-run.md) |
| `bundle.run` | Runs a job, pipeline or app from a bundle | plan half built — [010](010-command-and-bundle-run.md) |
| a class in the repo | Whatever a team writes | plan half built; the contract above is its spec |

`stevin` is not part of this phase: the owner takes it up separately ([006](006-stevin.md)). Its
plan half exists in the code and is left as it is.

## Not in this spec

- How steps are written down → [003](003-config.md)
- The commands and their flags → [005](005-plan-apply-destroy.md)

## Decided

- **The target and the workspace** (was D2): a bare name each plugin reads its own way, and the
  workspace from `--profile` or the environment — R23 and R24. *(owner, 2026-10-05)*
- **A step that can't destroy** (was D3): skipped, and the destroy plan says so — R8a. A
  `command` step may bring a destroy command — R8b. *(owner, 2026-10-05)*
- **One spelling for a reference** (was D4): always `${steps.<name>.<output>}` — R15a.
  *(owner, 2026-10-05)*
- **The word in the config** (was D1): it stays "step" — `uses:`, `lely steps`, the entry-point
  group `lely.steps`. A step uses a plugin. *(owner, 2026-10-05: as proposed)*

## As built

2026-10-05. Where the code went further than the sketch above, or stopped short of a
requirement:

- **`overview` answers with an `Overview`**: its lines, and notes — the bundle uses the notes to
  say whose view it is ([004/R9b](004-asset-bundle.md)). `overview` and `plan_destroy` may also
  answer `Skip(reason)`: a `command` step without a destroy command has nothing to destroy,
  and which it is depends on the step, not on the plugin (R8a, R8b).
- **A plan names what comes later.** `StepPlan.later` lists the declared *once it exists*
  outputs that will exist only after apply. That is how a reference to a job that isn't in the
  bundle at all is told apart from one to a job this deploy creates (R14a): the first is an
  error at plan, the second makes a step wait.
- **A plugin's outputs may depend on a step's options.** `outputs` is a list, or a function of
  the options as written. `command` needs it: the step lists what it gives
  ([010](010-command-and-bundle-run.md#decided)).
- **An option can name a whole step** (type `Linked`), beside `${steps.<name>.<output>}`.
  `bundle.run` has to run the CLI exactly as its bundle step does — same directory, same
  `--var`s — and a step is given nothing but its options (R22). It is still R15: the dependency
  is written in `with:`, the named step stands above, and `validate` checks both. *This is a
  second way to depend on a step that the spec didn't name; the owner hasn't seen it.*
  What a plugin reads from the step it names is **not** held to the plan the way a referenced
  output is (005/R5): a plugin that acts on such a value puts it in the change it plans.
- **A step is told what it is planned for** — apply, destroy or status — because for the last
  two what exists now is what it gives the steps below, not what a deploy would make of it.
  *(fourth review, 2026-10-06; the owner hasn't seen it.)*
- **What a step is given (R22)** is also its own name, the workspace's host, the environment
  for a program it runs, and the Databricks CLI with this run's credentials — all "a way to
  reach the workspace", none another step's.
- **A literal `${…}` is written `$${…}`** (R15a) *(2026-10-07)*. `${` always starts a
  reference, so a shell's own `${HOME}` in a command could not be written at all. `$${` is
  the escape, as in Terraform and Compose: it is no reference, and the step is handed `${`.
  It is read from the left, so in `$$${` the first dollar is only a dollar; a `$$` before
  anything but `{` is two dollars.
- **A `${…}` that is no reference says how to write it** (R15a, R18): as a literal, and —
  when a step above gives an output of that name, which is how a bundle's own file spells
  `${var.catalog}` — as `${steps.<that step>.var.catalog}`, naming the step. No step is named
  that isn't there: the message used to say "write `${steps.<bundle step>.…}`" in a project
  without a bundle. The check reads what the steps above declare, so it knows no plugin by
  name; `${bundle.target}` gets the plain message, because no step gives a `bundle.target`.
- **A value from the environment is a `Secret`** (R13): it can go only where a plugin asked for
  one, which is what keeps it out of every plan and every line of output.
- **The kit (R25)** has `check_plan`, `check_apply`, `check_destroy` and `check_overview`.
  "Plan changes nothing" is held by running plan and overview with a Databricks CLI that
  refuses anything but reads; it can't see a write made through the SDK or another program.
  "Only its own" is not a check anyone can reuse: it is tested for the bundle plugin against
  the simulated workspace.
- **What a plugin hands back is checked for more than its shape:** a change's lines and an
  overview's id and link have to be text, and a plugin's own code failing — its options, its
  `outputs` — is reported with the step's name, not as a traceback.
- **`validate` knows where an environment value may not go** (R18): it is a secret whatever it
  turns out to be, so an option that can't take one is refused offline. It is not looked up and
  not stood in for: offline, a plugin's options aren't built with a made-up secret.
- **An option that wants text gets what was written**: a number or a boolean in a `lely.yml` is
  passed on as its own text, not as what YAML made of it — and what a step is "made from"
  follows that text. In a `pyproject.toml` a number is a number: text that has to stay as
  written is written as a string.
- **What a plugin prints goes to stderr.** stdout is lely's — a plan or a result as JSON, a
  schema — and a `print` left in a plugin would land in the middle of it.
- **What a program says while a step runs goes through the step's log** (R22), like a line
  the plugin logs itself: `lely.process.run(…, said=…)` passes on each line as it comes, and
  `lely.databricks.heard` does it for the Databricks CLI. What a step is given is unchanged —
  `ctx.databricks.run(args, cwd)` still answers when the program is done — so a stand-in for
  the CLI that keeps to that is heard when it is done, not while it runs.
- **Only what a config can set is an option**: a field the `Options` class fills in itself is
  not one. A `Literal` option takes one of its members and of its kind — `true` is not `1`.
- **A plugin's own view (R8)** is `StepPlan.view`: HTML, as text, made by `plan` (and by
  `plan_destroy`) and kept with the plan. The page shows it under the step's changes, in a
  frame: its structure and its words, nothing a browser would obey. A plugin escapes what it
  writes into it, and puts nothing secret there. → [007, As built](007-ui.md#as-built)

## Done when

- The bundle goes through the same contract as every other plugin, and no module in the core
  imports anything bundle-specific.
- `lely steps` shows each plugin with its options, its outputs and when each is known, and
  whether it has an overview and a destroy.
- `lely validate` on a project with a reference pointing down the list, and on one naming an
  output that doesn't exist, fails with a message that says what to change.
- R25's checks exist and the plugins above pass the ones that apply to them.

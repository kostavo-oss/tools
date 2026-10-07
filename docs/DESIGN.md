# lely — design

`lely`, after Cornelis Lely, who got the Zuiderzee Works built. It was designed under the working
name `sluis` — Dutch for a lock, which moves a ship through one chamber at a time — and that is
still how it works.

**One plan for your whole Databricks deploy.** The bundle and everything around it — the steps
before, the steps after — reviewed before anything runs, and taken down again when you say so.

lely plans, applies and destroys an ordered list of steps, each done by a plugin, and keeps no
state of its own. The Asset Bundle is one of those plugins.

`spec/` says *what* each piece must deliver and when it is done. This file says *how* it is built.
It was rewritten on 2026-10-05 to the direction the owner set that day, and phase one was built to
it the same day — against fake tools only. Where the two disagree, say so instead of picking one.

"Bundle" means a Declarative Automation Bundle, formerly Databricks Asset Bundle: `databricks.yml`,
deployed by the Databricks CLI.

## Why

A bundle deploys workspace resources. Much of a real deploy is not a resource: it's the state inside
a resource or next to it. The CLI, the SDK or a library can reach that state, but a bundle can't.
What a bundle offers for everything else, checked 2026-09-29 against CLI v1.18.0:

| Need | What the bundle has | What's missing |
|---|---|---|
| Run something before or after deploy | `experimental.scripts`: `preinit`, `postinit`, `prebuild`, `postbuild`, `predeploy`, `postdeploy` | Shell commands only. No auth or resolved config is passed in. Output is logged but can't set a variable. The only way back into the bundle is a `preinit` script writing a YAML file that is included. Still experimental. |
| Resources from code | Python for bundles (`databricks-bundles`, GA): `resources` and `mutators` | It produces config only. It runs on every command, `validate` included. Resource IDs aren't available yet, and there is nothing after deploy. |
| Review before deploy | `bundle plan -o json`, and `bundle deploy --plan` (direct engine) | Covers bundle resources only |
| Table schemas | — | [stevin](https://github.com/kostavo-oss/stevin) |
| Lakebase | `postgres_projects`, `_branches`, `_endpoints`, `_databases`, `_roles`, … | What's inside the database: tables and schemas |
| MLflow | `experiments`, `registered_models`, `model_serving_endpoints` | Model version aliases (the direct engine never reads `aliases` back), prompts and their aliases, scorers, evaluation datasets |

- https://docs.databricks.com/aws/en/dev-tools/bundles/reference
- https://docs.databricks.com/aws/en/dev-tools/bundles/python/
- https://docs.databricks.com/aws/en/dev-tools/cli/bundle-commands

So a real deploy is a bundle and glue around it, and the glue fails in four ways: nobody sees the
whole deploy before it runs; what one step hands the next is invisible; nothing is guarded the same
way twice; and it only goes one way. lely's answer to each: one plan for every step, values between
steps written down and checked, one rule for consent, and `destroy`.

## Goals

- One plan for the whole deploy: every step's changes, reviewable in one place.
- Three verbs — `plan`, `apply`, `destroy` — and `status` to see what is there.
- No state: whatever a plugin needs to know, it reads from the system it manages.
- What passes between steps is declared, checked offline, and shown.
- Nothing that changes a workspace runs unasked; a destructive change is named and refused unless
  allowed.
- A small plugin contract. A plugin is a Python class in the repo, an installed package, or a pair
  of commands, under the same rules as the ones lely ships.
- The bundle stays the bundle. The bundle plugin asks the Databricks CLI and never reimplements what
  the CLI resolves.

## Non-goals

- **Anything a bundle resource can manage.** If a resource type exists, the bundle does it. When a
  new resource type makes a step redundant, the step is retired, not defended.
- **Feeding the bundle anything but variables.** A step never generates YAML for the bundle to
  include, so everything the bundle deploys stays readable in its own files.
- **A workflow engine.** One ordered list: no DAG, no parallel steps, no retries.
- **Rollback.** See [When something fails](#when-something-fails).
- **Building artifacts.** The bundle's `artifacts` does that.
- **A state file or run history** — and so lely cannot see what the config no longer names. A step
  that is removed or renamed, a target taken out of `targets:`, a bundle moved to another path:
  what they deployed stays. Destroy first, then remove the step.
- **The Terraform engine.** The bundle plugin needs the direct engine: `bundle deploy --plan` is
  direct-only.
- **CI systems other than GitHub Actions**, for now.

## How a run goes

```
lely.yml  or  pyproject.toml [tool.lely]
        │
        ▼
   config ──▶ check ──▶ for each step, top to bottom:
   (one list)  (offline)   resolve its options from the outputs above it
                           ├─ all known  → the plugin plans it          (ready)
                           └─ something missing → no plan, by name      (waiting)
                                   │
                                   ▼
                              Plan ──▶ terminal · JSON file

apply:    top to bottom, each step planned again, checked against what was approved, applied
destroy:  options resolved top to bottom, then bottom to top: planned again, checked, destroyed
status:   options resolved top to bottom, each plugin asked what exists
```

The core does no I/O: config, references, the wiring, plan assembly, the approval check and the
renderers are pure. I/O happens at the edges: the plugins, the Databricks CLI runner, the workspace
client, `git`, and the command line.

| Module | Does |
|---|---|
| `config` | `lely.yml` or `pyproject.toml` → one list of steps, every value with its file, line and column |
| `refs` | `${steps.<name>.<output>}` and `${env.<NAME>}`: shape, where one may stand, what it answers |
| `options` | a step's `with:` → the plugin's `Options` dataclass, strictly |
| `registry` | `uses:` → a plugin class |
| `step` | the plugin contract and what a step is given |
| `model` | plans, changes, outputs, overviews, results — frozen dataclasses |
| `planning` | `check` (offline) and `plan`; one `Session` that resolves steps in order |
| `approval` | what may run: the plan file against the project, a fresh plan against the approved one |
| `running` | `apply`, `destroy`, `status` |
| `planfile` | the plan and the result, to JSON and back |
| `schema` | the config's shape as JSON Schema, built from the plugins, for editors |
| `render` | the terminal |
| `steps/` | the plugins lely ships: `bundle`, `bundle.run`, `command`, and `stevin`'s plan half |
| `databricks`, `source`, `process` | the Databricks CLI, `git`, any other program |
| `cli` | the commands, consent, exit codes |

No module outside `steps/` knows a plugin by name.

## Config

One ordered list. `lely.yml`, or `[tool.lely]` in `pyproject.toml` with the same keys; lely walks up
from the working directory to the first folder that has either. Both in one folder is an error that
names the two files.

```yaml
steps:
  - name: model                  # feeds the bundle: it is above it …
    uses: ./ops/steps.py:LatestModel
    with: {model: main.ml.churn, alias: candidate}

  - name: app
    uses: bundle
    with:
      path: .
      vars:
        model_version: ${steps.model.version}     # … and the bundle says what it takes

  - name: backfill               # needs something from the bundle: it is below it …
    uses: command
    with:
      apply: [./ops/backfill.sh, "${steps.app.resources.jobs.backfill.id}"]
    targets: [dev]               # skipped, visibly, for any other target
```

A step has `name`, `uses`, `with` and `targets`. Unknown keys are errors where they were written,
in either format. YAML is read through its node tree, so every value keeps its line and column.
TOML is read with `tomllib`, which keeps none: positions are found by scanning the text for each
key in the order it was read, which is exact for files written the usual way and a best effort
otherwise.

A step's paths are relative to the config file, not to where the command was run.

## What flows between steps

One step's output is another step's input, and there is one way to say so.

**Outputs are declared.** A plugin lists what a step of it gives, each with when it is known:

| Known | Means | Example |
|---|---|---|
| `plan` — *at plan* | always, before anything is deployed | a looked-up model version |
| `exists` — *once it exists* | at plan if the thing is there already, otherwise after apply | the id of a job the bundle deploys |
| `run` — *after every run* | never at plan: it is produced by running | what a script writes while it applies |

A name that depends on the project is declared as a shape — `resources.<type>.<key>.id` — where
each `<…>` stands for exactly one part. A reference is matched against the declared names; the most
literal one wins, and any parts left over walk into the value.

**An input is a reference in the step's own options:** `${steps.<name>.<output>}`. There is no other
channel. `${env.<NAME>}` reads the environment, which is not a step; its value is a `Secret`, so it
can only go where a plugin asked for one and is never shown or written. `$${` is no reference: it is
how a literal `${` is written, and the step is handed `${`.

An option can also name a whole step — `bundle: app` on a `bundle.run` step — when its type is
`Linked`. The plugin is then given that step's options and outputs. It is the same rule: the
dependency is written in `with:`, and the named step must stand above.

**References point up the list.** So the order of the list is the order of dependency, and there is
no way to write a circle. `lely validate` refuses, offline: a step that isn't there; one listed
further down; an output the plugin doesn't declare or that fits no shape; a step whose `targets:`
leave out a target the referring step runs for. It then prints the wiring: per step, what it takes
and what it gives.

**A value that isn't known yet is never guessed.** While planning, a step's plan may leave out a
declared *once it exists* output and name it in `later`. A step that takes a value that isn't there
is *waiting*, and the plan says for what, by name: `app.resources.jobs.bar.id`. A name that is
neither given nor promised is an error at plan, before anything changes.

## The plugin contract

```python
class Plugin(Protocol):
    Options: type  # a frozen dataclass; `with:` is checked against it
    outputs: tuple[Output, ...]  # optional; or a function of the options as written

    def plan(self, ctx: Context) -> StepPlan: ...
    def apply(self, ctx: Context, plan: StepPlan) -> Outputs: ...

    # optional — a plugin without one says so by not having it
    def overview(self, ctx: Context) -> Overview | Skip: ...
    def plan_destroy(self, ctx: Context) -> StepPlan | Skip: ...
    def destroy(self, ctx: Context, plan: StepPlan) -> None: ...


@dataclass(frozen=True, slots=True)
class Context:  # everything a step is given
    target: str  # `-t`, as typed; each plugin reads it its own way
    name: str  # the step's own name
    options: Options  # its `with:`, references resolved
    root: Path  # the project's directory
    host: str  # the workspace this run talks to
    env: Mapping[str, str]  # for a program the step runs
    databricks: Cli  # the Databricks CLI, with this run's credentials
    purpose: str  # what it is planned for: apply, destroy or status
    log: Log
    workspace: WorkspaceClient  # the SDK, connected on first use


@dataclass(frozen=True, slots=True)
class StepPlan:
    changes: tuple[Change, ...] = ()
    outputs: Outputs = {}  # what is known now, by declared name
    later: tuple[str, ...] = ()  # declared outputs that exist only after apply
    waiting: str | None = None  # why part of this plan can't be made yet
    notes: tuple[str, ...] = ()  # lines shown with the plan that are not changes
    payload: Json = None  # the plugin's own data, carried in the plan file
    view: str | None = None  # its own picture of the plan, as HTML, for the page


@dataclass(frozen=True, slots=True)
class Change:
    key: str  # identity across plans: "jobs.backfill"
    action: Literal["create", "update", "delete", "replace", "run"]
    summary: str
    destructive: bool = False  # delete and replace always are
    detail: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Item:  # one line of an overview
    kind: str  # "job"
    key: str  # "jobs.backfill"
    name: str  # "shop-backfill"
    deployed: bool
    id: str | None = None
    url: str | None = None
```

A step is not handed the other steps' outputs, or the bundle. What it depends on is in its options.

`run` is the action for what happens on every apply rather than being a difference between two
states: running a job, running a script, uploading a bundle's files. A plan that holds one is never
"nothing to do", and it is counted as a run, not as a change.

**Rules every plugin follows.** `lely.testing` checks each as something that can fail:

- **No state.** `plan` and `apply` may run on different machines, days apart; only the plan passes
  between them.
- **`plan` changes nothing**, and neither does `overview`. Both run on every pull request.
- **`apply` does what the plan says, and no more.** For a plugin that converges, planning again
  right after gives no changes.
- **Only what the options name.** Anything else is not its own, and never changed.
- **It destroys only what it can show is its own.** `command` is the exception by its nature, and
  its destroy plan shows the command line in full.
- **Destructive is declared.** A change the plugin's tool reports and the plugin doesn't recognise
  is destructive.
- **Outputs are as declared.** Nothing undeclared is given; nothing declared *at plan* is missing.
- **No secret in a plan.** A secret output is a `Secret`; a payload holds none.

**Planning runs the project's own code.** A plugin that is a file in the repo is loaded even by
`validate`; a `command` step's plan command is run by `plan`. On a pull request, `plan` must be
given credentials that can read and nothing more. lely can't enforce that; `lely doctor` and the
docs say it.

**Finding a plugin** (`uses:`): a registered name from the entry-point group `lely.steps`;
`package.module:Class`; or `./path/to/file.py:Class` in the repo. The plugins lely ships register
the same way. `lely steps` lists the registered ones and the ones the project names, each with its
options, its outputs and when each is known, and whether it can list and destroy.

## The plugins of phase one

### `bundle`

Deploys an Asset Bundle. Options: `path`, the directory holding `databricks.yml`, and `vars`, passed
as `--var` to every CLI call the step makes. A project can have several; each takes `-t` as its own
bundle target, and all deploy to the one workspace the run talks to. A bundle whose target names
another workspace is refused.

- **plan**: `bundle summary` and `bundle plan`, both `-o json` — not `bundle validate`, which
  creates a folder in the workspace. One change per
  resource that is created, updated, replaced or deleted, keyed `jobs.backfill`. A delete, a
  `recreate`, an `update_id` and any action lely doesn't know are destructive. One more line, a
  `run`: *uploads the bundle's files* — a deploy ships notebooks and wheels even when no resource
  changes, and `bundle plan` speaks only of resources. The payload is the CLI's own plan.
- **apply**: the core has just planned the step again and checked it. That fresh plan is written to
  a file and handed to `bundle deploy --plan`. The CLI checks its own part too: it refuses a plan
  whose state `lineage` or `serial` has moved on. A refusal by the CLI is passed on word for word
  and ends the run as refused.
- **overview**: from `bundle summary`, and from nothing else: every resource the bundle declares,
  with its name, and its id and link once deployed. It says whose view it is — the identity and the
  bundle's root path — because what a bundle deployed is recorded under a path that can depend on
  who deploys.
- **destroy**: the plan lists every resource the summary shows as deployed, each destructive, and
  says the uploaded files go with them. Destroying runs `bundle destroy` and nothing else.

It gives: `target` and `name`; `workspace.<field>`; `var.<name>`;
`resources.<type>.<key>.<field>` for every field the resolved config has — all *at plan* — and
`resources.<type>.<key>.id` and `.url`, *once it exists*. The id of a resource this deploy creates
or replaces is `later`.

### `command`

Runs commands the project gives it. Each is a list — a program and its arguments — never passed
through a shell.

```yaml
- name: seed
  uses: command
  with:
    plan: [./ops/seed.sh, --plan]      # optional; prints the step's plan as JSON on stdout
    apply: [./ops/seed.sh]
    destroy: [./ops/seed.sh, --drop]   # optional
    outputs: [count]                   # optional; what the step gives
```

- **plan**: with a plan command, what it prints. Without one, a single `run` line that shows the
  command.
- **apply**: the apply command, from the project's directory. It is given the environment lely was
  run in, the step's `env`, `LELY_TARGET` and `LELY_STEP`, and on apply `LELY_PLAN` (a file holding
  the plan that was approved for this step) and `LELY_OUTPUTS` (a file it writes outputs to, one
  `name=value` to a line).
- **outputs**: the step lists them. One the plan command prints is known at plan; one the apply
  command writes is known after the run. Without a plan command they are all *after every run*;
  with one, lely can't know before running it which it prints, so they are *once it exists*. A name
  it lists and gives in neither way is a failed step.
- **destroy**: with a destroy command, the plan shows that command line in full, marked
  destructive. Without one the step is skipped, visibly.
- No secret in its arguments: they would be visible to every process on the machine. `env` may hold
  one.

### `bundle.run`

Runs a job, pipeline or app from a bundle step, via `databricks bundle run <key>`. Options:
`bundle`, the bundle step it belongs to — always named; `resource` (`jobs.backfill`); and `args`.
Its plan is one `run` line. It has nothing to destroy and nothing to list.

### A class in the repo

Whatever a team writes, through the contract above.

### `stevin`

Parked: the owner takes it up separately ([spec 006](https://github.com/kostavo-oss/lely/blob/main/spec/006-stevin.md)). Its plan half exists
— `stevin plan --target <t> --config <c> --output <tmp> --format json`, the plan file as payload —
and is left as it is. A project that uses it can plan; `apply` refuses before anything runs.

## Ready, waiting, skipped

Every step in a plan is one of three things.

- **Ready**: all its inputs are known. The plan shows its changes, and approving the plan approves
  them.
- **Waiting**: it takes something that doesn't exist yet, or its plugin says part of its plan can't
  be made yet. The plan shows the step and what it waits for, and no changes.
- **Skipped**: its `targets:` leave this target out; or, in a destroy, its plugin has nothing to
  destroy or it needs something that isn't there. The plan says why.

At a waiting step, `apply` does one of three things, and never goes past it out of order:

| How it was started | At a waiting step |
|---|---|
| `lely apply plan.json` | stops, and says to plan again — a reviewed file runs what was reviewed |
| `lely apply -t <target>` at a terminal | plans it now, shows it, asks once more |
| `lely apply -t <target> --yes` | plans it now and runs it — lely's unreviewed way of running |

A step that waits for a *once it exists* output waits on the first deploy only; one that waits for
an *after every run* output waits on every deploy, and `validate` says so.

## What may run

**The plan file against the project.** A file is refused when the steps for its target, or any
step's options as written, differ from what it was planned with; when an input that was known at
plan has another value now — for an apply and for a destroy alike; when it was made against
another workspace, or for another project of the repository; or when the repository is not on
a clean checkout of the tree it was planned on. Environment values count by name. A plan made with
uncommitted changes says so and is not run from a file; one made outside a git repository says
that nothing could be recorded.

**The approval check.** Each step is planned again immediately before it runs. It may run only if
every change in the new plan is one that was shown: the same key, the same action, the same lines.
Fewer changes is fine — someone else did part of the work, or an earlier run did. Anything new, or
anything that reads differently, stops the run and asks for a new plan. A destroy gets the same
check.

**Destructive changes** need `--allow-destructive`. Where the plan already shows one, the refusal
comes before anything runs. In a destroy everything is destructive, and the flag plays no part.

**Consent.** `apply` and `destroy` either ask or were given `--yes`. With no terminal and no `--yes`
they refuse. To destroy at a terminal, the answer is the target's name, typed. A saved destroy plan
is run only by `lely destroy <file> -t <target>`: a command that destroys always has both words in
it. Every question names the workspace and the identity.

## When something fails

Nothing here is transactional, and there is no rollback.

- The first failing step stops the run. Nothing after it starts. The result has three lists: what
  ran, what failed (or was refused), what never started. A step with nothing to do didn't run.
- After a *failure*, running the same command again finishes the job: a step that already did its
  work plans as nothing to do, and the bundle deploys again, which only uploads its files.
- After a *refusal* — a stale plan, a waiting step in a reviewed file, a change that wasn't
  approved — the same file is refused again: it takes a new plan.
- `--from <step>` starts at a named step; in a destroy, it names where to start going up the list.
  The steps it passes over are still planned, for what they give the others.
- Exit codes: 0 done, 1 failed, 2 refused.
- Concurrency: `bundle deploy` holds the bundle's own lock only while it deploys. A GitHub Actions
  `concurrency:` group per target does the rest, for now.

## CLI

```
lely validate                          # config, options, references: offline; prints the wiring
lely steps                             # plugins: options, outputs, what each can do
lely schema [-o lely.schema.json]      # a JSON Schema of the config, for editors
lely plan -t <target> [--destroy] [-o plan.json] [-f rich|json|md] [--github]
lely show plan.json [-f rich|json|md] [--github]
lely apply [plan.json] [-t <target>] [--yes] [--allow-destructive] [--from <step>]
lely destroy [destroy.json] -t <target> [--yes] [--from <step>]
lely status -t <target> [-f rich|json|md]
lely ui <plan.json | result.json> [-o page.html] [--no-open]
lely doctor                            # tools, workspace, identity
```

`-t` is always given to a command that touches a workspace; there is no default target. The
workspace comes from `--profile` or from the variables the Databricks SDK and CLI already read. One
run talks to one workspace.

## The plan, in a terminal

```
lely plan · target dev · https://dbc-example.cloud.databricks.com as jane@example.com

  model  ./ops/steps.py:LatestModel
    → version = 14
  app  bundle
    model_version = 14  ← model.version
    + jobs.bar
    ± pipelines.foo  destructive
        replaced: storage (immutable)
    ▶ uploads the bundle's files
  notify  command
    ⏸ waiting for app.resources.jobs.bar.id
  backfill  bundle.run
    bundle  ← app
    ▶ runs jobs.backfill
  warm  command
    – skipped: not for target dev

Plan: 2 changes · 2 runs · 1 destructive · 1 waiting
Applied from a file, this stops before `notify`: a waiting step is planned once what it waits for exists.
```

Where a step gives something another step takes, it is shown there (`→ version = 14`) and where
it is taken (`model_version = 14  ← model.version`). The rest of what a step gives is in the plan
file.

## The plan file

JSON, format 2. At the top: the format version; lely's version; whether it is a plan to apply or to
destroy; the target; the workspace's host and the identity it was planned as; and the git tree it
was made on. Then every step in order: its name and plugin; ready, waiting (for what) or skipped
(why); a hash of its options as written; what it takes and from where, with the value where it was
known; its changes; the outputs it showed; and the plugin's payload.

It never holds a secret: a secret output is a marker, a payload with one is refused, and an
environment value is a secret. Nothing in it is kept for apply — every step is planned again, and
gives its values again.

## Testing

- **Unit**: config, references, the wiring, the approval check and the renderers are pure.
- **A fake `databricks`** (`tests/fake_databricks.py`), as a program and in process. It answers
  from recordings — the CLI's own acceptance-test outputs, `tests/fixtures/cli/` — or simulates a
  bundle in a small workspace kept in a folder: `plan`, `deploy`, `summary`, `destroy`, `run`. A
  call it can't answer fails loudly.
- **The contract kit, `lely.testing`**, which every plugin lely ships passes where it applies, and
  plugin authors reuse.

Settled from the CLI's source and its recorded acceptance tests (commit `e41a5c8`, see
`tests/fixtures/cli/README.md`):
- `bundle summary -o json` is the resolved config plus `id` and `url` per deployed resource.
- `--var` is a persistent flag of `bundle`, so every verb takes it (`cmd/bundle/variables.go`).
- `bundle deploy --plan` checks `lineage` and `serial` (`bundle/direct/bundle_plan.go`,
  `ValidatePlanAgainstState`).
- A failed `bundle validate` still prints JSON and exits 1. The exit code decides.

**Run on a real workspace once**, on 2026-10-06, with CLI v1.19.0 and one small bundle. Before
that, apply and destroy were built against the fake only, on eight assumptions; the table says
what became of each. [Spec 004](https://github.com/kostavo-oss/lely/blob/main/spec/004-asset-bundle.md#run-on-a-workspace-2026-10-06) has
the detail.

| | Assumed | Found |
|---|---|---|
| V1 | `bundle destroy` removes what `bundle summary` lists, and the bundle's files | so it did, for one job |
| V2 | `--auto-approve` answers for `deploy` and `destroy` when nobody can | yes; without it `destroy` refuses |
| V3 | `bundle summary -o json` has an `id` and a `url` for every resource type | for a job |
| V4 | the CLI refuses a bundle whose target names another workspace | **no**: it goes there, with the token from the environment. lely's own check stops the run after that first call |
| V5 | `bundle plan` speaks only of resources, not of files | yes |
| V6 | `deploy --plan` with nothing to change still uploads the files | yes |
| V7 | a bundle another identity deployed looks not deployed | not tried |
| V8 | `--var` reads its value as a line of CSV | yes |

And one thing nobody had assumed: `bundle validate` creates a folder in the workspace. So the
bundle plugin asks `bundle summary` for the resolved config instead, and a plan leaves the
workspace as it was.

What is still assumed is marked `TODO(verify)` where the code depends on it.

## Phases

1. **The Asset Bundle, as a plugin, with steps around it**: the contract, the config as one list,
   the `bundle` plugin, `command` and `bundle.run`, and `apply`, `status`, `destroy`, `doctor`.
   Called usable only when all of it is there.
2. **Around it**: GitHub — the plan as one comment on the pull request, the result on the run's
   page ([spec 008](https://github.com/kostavo-oss/lely/blob/main/spec/008-github-actions.md)), built on 2026-10-06 and described in
   [GITHUB.md](GITHUB.md) — and a page to look at a plan in ([spec 007](https://github.com/kostavo-oss/lely/blob/main/spec/007-ui.md)),
   built the same day.

## Later

Not in phase one. Written down so it doesn't paint them into a corner.

### Lakebase: declarative schemas

Desired state for the tables inside a Lakebase database, diffed and applied like stevin, by wrapping
an existing Postgres schema differ — not by building one, and not by teaching stevin Postgres.

- **Which differ**: to evaluate, among Atlas, pgschema and psqldef. The criteria are a dry-run plan
  that can be read as structure, how it marks destructive changes, its license, and whether it runs
  without an account.
- **Connection**, independent of the tool:
  - host: `w.postgres.get_endpoint(name).status.hosts.host` (`TODO(verify)`: source only)
  - password: `w.postgres.generate_database_credential(endpoint=…, ttl=…)`, a token valid for up to
    an hour
  - user: the identity lely runs as (an email, or a service principal's application ID)
- **An endpoint this deploy creates**: the step waits.
- **Autoscaling only.** New instances are Autoscaling since 2026-03-12.

Sources:
- https://docs.databricks.com/aws/en/oltp/projects/external-apps-connect
- https://docs.databricks.com/aws/en/oltp/update-to-autoscaling-dabs

### MLflow

- **`mlflow.lookup`**: a model version by alias or tag, as an output.
- **`mlflow.alias`**: sets UC model version aliases and never removes an unlisted one.
  `TODO(verify)`: `w.registered_models.set_alias` in the SDK, so this needs no mlflow.
- **`mlflow.prompts`**: keeps a folder of prompt templates registered. The prompt registry is in
  Beta and needs mlflow ≥ 3.1, so it would be an extra.

Source: https://docs.databricks.com/aws/en/mlflow3/genai/prompt-version-mgmt/prompt-registry/

## Suite

"Terraform for your platform, Asset Bundles for your code, stevin for your data model — and lely to
deploy them as one." lely is not a fourth layer: it carries the layers out together. stevin stays a
standalone CLI; caland stays a TUI for people.

All three live in the `kostavo-oss` GitHub organisation as **stevin**, **lely** and **caland**.
Package names are plain, with no `kostavo-` prefix, so `uvx lely` works.

## Open questions

- A lock for concurrent applies outside CI.
- Whether `.databricks/bundle/<target>/variable-overrides.json` is the supported route for bundle
  variables that aren't single values (`TODO(verify)`); `--var` can't carry them.
- Whether any API can say that credentials are read-only, for `lely doctor`.
- Which Postgres differ for Lakebase, when it's built.

## Decided with the owner, 2026-09-29

- MCP: nothing now. Managed servers need no deploy; a custom one is an app; an external one needs a
  UC HTTP connection, which isn't a bundle resource.
- Lakebase: declarative, by wrapping an existing tool. Not in phase one.
- The direct engine is required.
- Names and licence were decided here and superseded on 2026-10-05, below.

## Decided with the owner, 2026-10-05

- Names: **stevin** (was deltaplan), **lely** (was sluis) and **caland** (was isolinear; it
  was to be maeslant, after the storm surge barrier, until 2026-10-06 — the owner wanted an
  engineer's name there too).
- License: Apache-2.0, the same for every Kostavo tool.
- The direction in `spec/`: every step is a plugin, the bundle among them; three verbs; no state;
  one list of steps in `lely.yml` or `pyproject.toml`; declared outputs and one spelling for a
  reference; consent in the command for a headless run; `lely status`; exit codes 0, 1 and 2;
  stevin parked; fakes only for now.

## Decided while building, 2026-10-05

Each is the builder's call where the spec left room; none is the owner's yet.

- **The bundle's file upload is a `run`.** The spec had no word for "files are uploaded". A `run`
  already means "happens on every apply", is never "nothing to do", and is not counted as a change.
- **An option of type `Linked` names a whole step.** `bundle.run` has to run the CLI exactly as its
  bundle step does — same directory, same `--var`s — and a step is given nothing but its options.
- **A `command` step's outputs are *once it exists* when it has a plan command.** Which ones the
  plan command prints can't be known before running it.
- **An environment value is a `Secret`.** It is the one way to keep it out of every plan, file and
  line of output wherever it flows.
- **"Made from" is two things**: a hash of each step's options as written, and the value of every
  input that was known at plan.
- **A plan file is for a clean checkout.** It is held to `HEAD`'s tree of the whole repository,
  without the plan file itself, and to which project of the repository it is for. The whole
  repository because a step can reach outside the config's folder; without the plan file so
  that a plan committed for review doesn't refuse itself. A plan made while anything differed
  from `HEAD` says so and is not run from a file, and no plan is run from a file on such a
  checkout. git failing is not "no repository": it fails the plan.
- **A target no step runs for is refused**, since no plugin would be asked about it.
- **What a plugin hands back is made plain JSON when it is planned**, and inputs are compared as
  they would be written, so a plan is the same whether or not it went through a file.
- **Bundle variables are CSV-quoted** when they hold a comma or a quote, because `--var` is a list
  flag (V8, unverified).
- **The plan file keeps a step's named outputs and the ones another step takes**, not every field
  of every bundle resource; and a plan in a terminal shows, where it is given, only what another
  step takes.
- **A step that waits for what only a run produces is marked** as waiting on every deploy, in the
  plan and in its file.
- **`doctor` reports what it can read off**: the CLI's version, the workspace, the identity,
  whether it is a workspace admin, and whether each program a step runs is there. Not the
  bundle's engine, and not whether credentials are read-only.

## Decided in the fourth review, 2026-10-06

The builder's calls again; none is the owner's yet.

- **A step is told what it is planned for** (`Context.purpose`: apply, destroy or status). For
  a destroy and a status, `plan` is asked only for what the step gives the ones below, and
  there what exists now is what counts. The bundle held back the id of a pipeline the next
  deploy would replace — right for a deploy, and for a destroy it skipped the step that had to
  take down what it made for that pipeline.
- **A sparse checkout is the tree of what is checked out.** It read as the whole checkout, so
  a plan made where every file was there ran where a step would find some missing.
- **What a plugin reads from a linked step is not held to the plan.** Holding all of it was
  tried and backed out: a bundle step gives who is running, so a plan made by one person and
  applied by CI was refused for nothing. The rule is the plugin's: a value it acts on goes in
  the change it plans, and then a run on another value is a change nobody approved.
- **A plugin can't end lely or take its streams.** `sys.exit` in a plugin is that step's
  error. What a plugin prints, however it prints it, goes to stderr through a stream of its
  own.
- **A program is heard while it changes something** *(2026-10-07)*. `process.run` takes
  `said`: each line the program writes, on either stream, is passed to it as it comes and
  kept for the result. The plugins lely ships pass it to the step's log for an apply or a
  destroy command, `bundle deploy`, `bundle destroy` and `bundle run`; what only answers a
  question — a plan command, `bundle summary` — is run to its end and read. The log is the
  command line's, so a line a program wrote is cleaned and searched for the run's token like
  every other line lely says. A failure quotes both streams. Nothing has a time limit.

## The page, as built 2026-10-06

`src/lely/render/html.py` is pure: a plan or a result in, one HTML document out, with no
script and nothing to fetch. `lely ui` reads a plan file or a run's record, writes the page
and opens it; it loads no plugin and reaches no workspace.

A plugin's own view travels in the plan: `StepPlan.view`, HTML as text, made when the step is
planned. The page does not trust it — a plan file can be written by hand — and writes it
again from a short list of elements, every word escaped (`framed`). lely's own list of a
step's changes is always shown; the view stands under it.

A run's record is what `apply -o` and `destroy -o` write: the result as JSON. It is read back
only to be shown.

What it decided where [spec 007](https://github.com/kostavo-oss/lely/blob/main/spec/007-ui.md) left room is in that spec's "As built".

## GitHub, as built 2026-10-06

`src/lely/render/markdown.py` is pure: a plan, a result or a status in, text out.
`src/lely/render/words.py` holds what the terminal and Markdown say the same way — the counts,
the warnings, which outputs a plan shows. `src/lely/github.py` is the edge: it reads a run's
environment and its event, writes the summary file, and talks to GitHub's API through one
function that tests replace. The command line asks for it with `--github` and prints what it
did or couldn't do; nothing in it decides how a command ends.

What it decided where [spec 008](https://github.com/kostavo-oss/lely/blob/main/spec/008-github-actions.md) left room is in that spec's
"As built".

## Stack

Python ≥ 3.11 · mise · uv · src layout · typer + rich · databricks-sdk · PyYAML · pytest · ruff · ty ·
Apache-2.0. It needs a Databricks CLI with the direct engine (GA in v1.3.0); `lely doctor` shows the
version.

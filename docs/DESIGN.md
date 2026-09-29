# sluis — design

Working name: `sluis` (Dutch for a lock: it moves a ship through one chamber at a time).
It is one `plan` and one `apply` for a whole Databricks deploy. Pre-deploy steps run, then the bundle
deploys, then post-deploy steps run. Each step can see what the ones before it produced.

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
| Table schemas | — | [deltaplan](https://github.com/misja-pronk/deltaplan) |
| Lakebase | `postgres_projects`, `_branches`, `_endpoints`, `_databases`, `_roles`, … | What's inside the database: tables and schemas |
| MLflow | `experiments`, `registered_models`, `model_serving_endpoints` | Model version aliases (the direct engine never reads `aliases` back), prompts and their aliases, scorers, evaluation datasets |

- https://docs.databricks.com/aws/en/dev-tools/bundles/reference
- https://docs.databricks.com/aws/en/dev-tools/bundles/python/
- https://docs.databricks.com/aws/en/dev-tools/cli/bundle-commands

## Goals

- One plan for the whole deploy: every step's changes plus the bundle's, reviewable as one PR comment.
- One apply: pre steps, then `bundle deploy`, then post steps. Typed outputs flow forward, and running
  it again finishes an interrupted deploy.
- A small, explicit step interface. A step can be a Python class in the repo, an installed package,
  or a pair of commands.
- v1 ships two built-in steps: `deltaplan` and `bundle.run`. Lakebase and MLflow come later
  ([Later](#later)).
- The bundle stays the bundle. sluis asks the Databricks CLI and never reimplements what the CLI
  resolves.

## Non-goals

- **Anything a bundle resource can manage.** If a resource type exists, the bundle does it. When a
  new resource type makes a step redundant, the step is deprecated, not defended.
- **Feeding the bundle anything but variables.** Pre-step outputs become `--var`s. Steps never
  generate YAML for the bundle to include, so everything the bundle deploys stays readable in its
  own files. Python for bundles already covers generating resources from code.
- **A workflow engine.** There are three phases, each an ordered list. There is no DAG, no
  parallelism between steps and no retries.
- **Rollback.** See [Failure model](#failure-model).
- **Building artifacts.** The bundle's `artifacts` does that.
- **A state file or run history.** Each system a step touches is its own state.
- **The Terraform engine.** sluis requires the direct engine: `bundle deploy --plan` is direct-only,
  and Terraform is deprecated. `sluis doctor` reports a bundle's engine.
- **MCP.** Nothing is needed now. For the record: managed servers need no deploy; a custom server is
  an app (the bundle, plus `bundle.run` for its code); an external one needs a UC HTTP connection,
  which isn't a bundle resource.
- **`bundle destroy` and teardown**, in v1.
- **CI systems other than GitHub Actions**, in v1.

## Pipeline

```
sluis.yml ───────┐
databricks.yml ──┼─> resolve ─> context ─> plan: pre steps ─> bundle plan ─> post steps ─> Plan (JSON) ─> renderer
                 │  (bundle validate)                                                        │
                 │                                                                           └─> apply
                 │
apply:  pre[i]: re-plan, check, apply ─> bundle deploy --plan ─> bundle summary ─> post[i]: re-plan, check, apply
```

1. **Config**: `sluis.yml` becomes frozen dataclasses. It is validated at this edge only, with
   file:line:column errors and strict unknown-key errors. Each step's `with:` block is validated
   against that step's `Options`.
2. **Resolve**: `databricks bundle validate -o json -t <target>` gives targets, variables and resource
   names as a deploy would produce them.
3. **Plan**: each pre step plans, then the bundle (`bundle plan -o json`, with pre-step outputs as
   `--var`), then each post step. Nothing changes anywhere.
4. **Render**: Rich, Markdown for PR comments, and JSON, all from the same plan.
5. **Apply**: steps run in order. Each step is re-planned just before it runs and checked against
   what was approved. After the bundle deploys, `bundle summary -o json` adds IDs and URLs to the
   context.

The core does no I/O: config, references, ordering, plan assembly, the approval check and the
renderers. I/O happens only at the edges: the CLI runner, the workspace client, and the steps.

## Config: `sluis.yml`

Next to `databricks.yml`. The targets are the bundle's targets; there is no second list.

```yaml
bundle: .                            # directory holding databricks.yml

pre:
  - name: model
    uses: ./ops/steps.py:LatestModel # a step in the repo: looks something up, changes nothing
    with:
      model: ${var.catalog}.ml.churn
      alias: candidate

bundle_vars:                         # pre-step outputs into the bundle, as --var
  model_version: ${steps.model.version}

post:
  - name: tables
    uses: deltaplan
    with: {config: deltaplan.yml}
  - name: backfill
    uses: bundle.run
    with: {resource: jobs.backfill}
  - name: seed
    uses: command
    with: {apply: [./ops/seed.sh]}
    targets: [dev]                   # skipped for other targets
```

**References**, resolved by the core and checked offline by `sluis validate`:

| Reference | Source | Available |
|---|---|---|
| `${var.<name>}`, `${bundle.target}`, `${bundle.name}` | `bundle validate` | everywhere |
| `${resources.<type>.<key>.<field>}` | `bundle validate` | everywhere |
| `${resources.<type>.<key>.id}` / `.url` | `bundle summary` | post only |
| `${steps.<name>.<output>}` | an earlier step's outputs | after that step |
| `${env.<NAME>}` | the environment | everywhere; never printed, never written to a plan file |

A reference that can't be resolved in its position is an error, never an empty string. That covers
an `.id` in a pre step, a step that runs later, and a missing variable.

**Bundle variables**: scalars go through `--var`. Complex variables can't be passed that way.
`TODO(verify)`: whether `.databricks/bundle/<target>/variable-overrides.json` is the supported route
for them.

## The step interface

```python
class Step[O](Protocol):
    Options: type[O]                               # frozen dataclass; `with:` is validated into it

    def plan(self, ctx: Context[O]) -> StepPlan: ...
    def apply(self, ctx: Context[O], plan: StepPlan) -> Outputs: ...


@dataclass(frozen=True, slots=True)
class Context[O]:
    target: str
    options: O                                     # references already resolved
    bundle: Bundle                                 # `bundle validate -o json`
    deployed: Deployed | None                      # `bundle summary -o json`; None before deploy
    outputs: Mapping[str, Outputs]                 # earlier steps, by name
    workspace: WorkspaceClient                     # the target's workspace, same auth as the CLI
    root: Path
    log: Log                                       # progress lines; a heartbeat while waiting


@dataclass(frozen=True, slots=True)
class StepPlan:
    changes: tuple[Change, ...]
    outputs: Outputs                               # what is known at plan time
    deferred: str | None = None                    # why part of this is decided at apply
    payload: Json = None                           # the step's own data, carried in plan.json


@dataclass(frozen=True, slots=True)
class Change:
    key: str                                       # stable identity: "orders.amount", "jobs.backfill"
    action: Literal["create", "update", "delete", "replace", "run"]
    summary: str
    destructive: bool = False                      # delete and replace are always destructive
    detail: tuple[str, ...] = ()
```

**Rules every step follows.** The contract kit (see [Testing](#testing)) checks each one:

- **Stateless.** `plan` and `apply` may run on different machines, days apart. Only the `StepPlan`
  passes between them, serialised in `plan.json`.
- **`plan` changes nothing.** It runs on every pull request.
- **`apply` does what the plan says, and no more.** For a convergent step (no `run` changes),
  planning again right after `apply` gives an empty plan.
- **Only what the options name.** A step never touches what its config doesn't mention. Anything else
  is reported as unmanaged, never removed.
- **Destructive is declared.** Deleting, replacing or dropping data is `destructive`, and `apply`
  refuses it without `--allow-destructive`.
- **No secrets in plans.** Outputs may hold `Secret` values. They are rendered as `***`, never
  written to `plan.json`, and fetched again at apply.

**Finding a step** (`uses:`):

1. A registered name, from the entry-point group `sluis.steps`. Built-ins register the same way.
2. `package.module:Class`.
3. `./path/to/file.py:Class`, loaded from the repo.

`sluis steps` lists what's installed and each step's options. The editors' JSON Schema for
`sluis.yml` is built from the same `Options` classes.

## Built-in steps (v1)

### `deltaplan`

Runs the deltaplan CLI. The contract is deltaplan's CLI and its plan file (`PLAN_FORMAT_VERSION`), not
its Python modules, so deltaplan stays a standalone tool with its own releases.

- **plan**: `deltaplan plan -t <target> -o <tmp> -f json`. The payload is that plan file. deltaplan's
  `destructive` maps to `destructive`, and every other risk class maps to `update`. A `rewrite` is
  named in the detail.
- **apply**: writes the payload back to a file, then runs `deltaplan apply <file> --yes`, with
  `--allow-destructive` only if sluis was given it. deltaplan's own state fingerprint catches a stale
  plan.
- **Placement**: usually post, because a bundle that declares the schema creates it. It goes pre only
  when the schemas already exist.

### `bundle.run`

Runs a bundle resource (a job, pipeline or app) at its place in the order, via
`databricks bundle run <key>`. It is how a post step goes *between* things without a DAG: create the
tables, then run the backfill that fills them. Plain `bundle deploy` doesn't deploy app code, so this
is also how an app's code ships. Its plan is always one `run` change: it runs on every apply.

### `command`

The escape hatch, for steps that don't need Python:

```yaml
- name: seed
  uses: command
  with:
    plan: [./ops/seed.sh, --plan]  # optional; prints StepPlan JSON on stdout
    apply: [./ops/seed.sh]
```

- **Environment**: the command inherits sluis's environment, plus `DATABRICKS_HOST` (and
  `DATABRICKS_CONFIG_PROFILE` when a profile is used), so the CLI and the SDK inside it reach the
  same workspace. It also gets `SLUIS_TARGET`, `SLUIS_PLAN` (the step's plan, as a file) and
  `SLUIS_OUTPUTS`, a file it writes outputs to, as in GitHub Actions.
- **No `plan:` command**: the step's plan is one `run` change.

### Python classes

A class implementing `Step`, referenced by `module:Class` or `./file.py:Class`. This is how a team
writes its own plan/apply step, with the same rules and contract kit as the built-ins.

## Planning what doesn't exist yet

At plan time nothing is deployed. A post step plans against the workspace as it is now, with the
bundle's resolved config beside it:

1. **The target exists**: a normal plan.
2. **This deploy creates or changes the target**: the step plans what it can from files alone, and
   sets `deferred` to say why the rest waits. Example: "schema `sales` is created by this deploy:
   every table is new".
3. **Bundle variables from pre steps**: known at plan time in the common case, because a step
   computes its outputs in `plan`. If a variable isn't known, the bundle is planned at apply instead,
   and the plan says so.

**The approval check.** `apply` re-plans every step right before running it. It may continue only if
every change in the new plan matches an approved change by `key`, and none has become destructive.
Fewer changes is fine: someone else did part of the work. Anything new stops the run and asks for a
new plan. The bundle gets the same check: a resource key with an action, and `delete`, `recreate` and
`update_id` count as destructive. `TODO(verify)`: whether `bundle deploy --plan` itself refuses a
plan whose state `serial` has moved on.

`apply` also refuses a plan file whose `sluis.yml`, or any step's resolved options, differ from the
ones it was planned with.

## Failure model

Nothing here is transactional, and there is no rollback.

- The first failing step stops the run. Nothing after it runs.
- **Running `apply` again finishes the job.** Convergent steps re-plan and do what's left. `run`
  changes run again, so `apply --from <step>` resumes past them. Resuming is explicit, not based on a
  history.
- A failure after `bundle deploy` leaves the bundle deployed. The summary says which steps ran, which
  failed, and which never started.
- Concurrency: `bundle deploy` holds the bundle's own lock only while it deploys. v1 relies on a
  GitHub Actions `concurrency:` group per target, and the docs will show the snippet. Open question:
  a sluis lock file in the bundle's state path.

## CLI

```
sluis validate                          # config, references, step options: offline
sluis steps                             # installed steps and their options
sluis plan -t <target> [-o plan.json] [-f rich|md|json]
sluis show plan.json [-f rich|md|json]
sluis apply [plan.json] [-t <target>] [--yes] [--allow-destructive] [--from <step>]
sluis doctor                            # CLI version and engine, auth, each step's tools on PATH
```

`apply` without a plan file plans, shows the plan, asks, and runs, like deltaplan.

## Plan output (target look)

```
sluis plan · shop · target prod

pre
  model        LatestModel     = churn@candidate → version 14

bundle                         + 1 job · ~ 2 jobs · ~ 1 serving endpoint
  var model_version = 14  (from model)

post
  tables       deltaplan       ~ 2 tables · 5 steps
                                 ⏸ schema sales is created by this deploy: checked again before running
  backfill     bundle.run      ▶ runs jobs.backfill

Plan: 4 changes · 1 run · 0 destructive · 1 decided at apply
```

## CI

A composite GitHub Action. It posts `sluis plan -f md` as a single comment on the pull request that
covers the bundle and every step, and updates that comment rather than adding new ones. It runs
`apply` on merge. As in deltaplan: no `${{ }}` interpolated into a `run:` script.

## Testing

- **Unit**: config, references, ordering, the approval check and the renderers are pure, tested
  with golden plans.
- **Fake CLI**: a fake `databricks` on PATH answers from recorded JSON (transcripts of real runs). A
  command it has no recording for fails loudly. The same goes for a fake `deltaplan`.
- **Contract kit, `sluis.testing`**, which every built-in step passes and plugin authors reuse:
  - `plan` makes no writes;
  - `plan`, then `apply`, then `plan` again gives an empty plan (for convergent steps);
  - `StepPlan` round-trips through `plan.json`;
  - no `Secret` reaches the file.
- **Live**: every assumption about Databricks behaviour is a probe with a doc link, in the pattern of
  deltaplan's `probes.py`.

`TODO(verify)`, at the start. These are from reading the CLI source rather than the docs:
- `bundle summary -o json` carries `id` and `url` per resource.
- `bundle plan` and `bundle deploy --plan` accept `--var`.
- Whether `bundle deploy --plan` checks staleness.
- Whether `bundle deploy` asks before deleting or recreating, and fails when it can't ask.

## Milestones

1. **Read-only**: config and `validate`, references, resolve via the CLI, the step interface and
   discovery, the `command`, Python-class and `deltaplan` steps, `bundle plan`, `plan` and `show`
   (Rich and JSON), and the contract kit.
2. **Apply**: pre steps, then `bundle deploy --plan`, then `summary`, then post steps. Outputs,
   `bundle_vars`, the approval check, `--from`, `--allow-destructive`, `bundle.run`.
3. **CI**: the Markdown renderer and the GitHub Action with one comment.

## Later

Not in v1. Written down so v1 doesn't paint them into a corner.

### Lakebase: declarative schemas

Desired state for the tables inside a Lakebase database, diffed and applied like deltaplan. This
works by wrapping an existing Postgres schema differ, not by building one, and not by teaching
deltaplan Postgres.

- **Which differ**: to evaluate, among Atlas, pgschema and psqldef. The criteria are a dry-run plan
  that can be read as structure, how it marks destructive changes, its license, and whether it runs
  without an account.
- **Connection**, independent of the tool:
  - host: `w.postgres.get_endpoint(name).status.hosts.host` (`TODO(verify)`: source only)
  - password: `w.postgres.generate_database_credential(endpoint=…, ttl=…)`, a token valid for up to
    an hour
  - user: the identity sluis runs as (an email, or a service principal's application ID)

  These are passed as libpq variables (`PGHOST`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`,
  `PGSSLMODE=require`).
- **An endpoint this deploy creates**: the plan is `deferred`, and everything in the spec is new.
- **Testing a plan first**: apply it to a throwaway branch of the database. Autoscaling branches make
  this cheap. It is the Lakebase version of deltaplan's `--clone`.
- **Autoscaling only.** New instances are Autoscaling since 2026-03-12, and provisioned ones are
  being upgraded.

Sources:
- https://docs.databricks.com/aws/en/oltp/projects/external-apps-connect
- https://docs.databricks.com/aws/en/oltp/update-to-autoscaling-dabs

### MLflow

- **`mlflow.lookup`**: a model version by alias or tag, as an output. It is what a serving endpoint
  in the bundle usually needs as a variable.
- **`mlflow.alias`**: sets UC model version aliases and never removes an unlisted one. `TODO(verify)`:
  `w.registered_models.set_alias` in the SDK, so this needs no mlflow.
- **`mlflow.prompts`**: keeps a folder of prompt templates registered (`mlflow.genai.register_prompt`,
  `set_prompt_alias`). The prompt registry is in Beta and needs mlflow ≥ 3.1, so it would be an extra.

Source: https://docs.databricks.com/aws/en/mlflow3/genai/prompt-version-mgmt/prompt-registry/

## Suite

sluis is the hub. deltaplan is its first step and stays a standalone CLI. isolinear stays a TUI for
people. The shared pieces are workspace auth and bundle resolution: deltaplan's `bundle.py` asks the
CLI and falls back to reading the file, and isolinear's picker reads `databricks.yml`. They become a
small shared package once sluis is a second real user of them, not before.

All three will move to the `kostavo-oss` GitHub organisation. The tools' names, including this one,
are to be decided with that move.

## Open questions

- Names under `kostavo-oss`.
- A lock file for concurrent applies outside CI.
- Which Postgres differ for Lakebase, when it's built.

## Decided with the owner, 2026-09-29

- MCP: nothing now; it was only an example.
- Lakebase: declarative, by wrapping an existing tool. Not in v1.
- v1 built-in steps: `deltaplan` and `bundle.run`, plus custom Python and `command` steps.
- Pre steps feed the bundle variables only.
- CI first after the core, on GitHub Actions only.
- The direct engine is required.
- License: MIT.
- Commit locally; no GitHub repo until the move to `kostavo-oss`.

## Stack

Python ≥ 3.11 · mise · uv · src layout · typer + rich · databricks-sdk · PyYAML · pytest · ruff · ty ·
MIT. It needs a Databricks CLI with the direct engine (GA in v1.3.0); `doctor` checks the version.

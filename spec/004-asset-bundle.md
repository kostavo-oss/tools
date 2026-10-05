# 004 — the Asset Bundle plugin

**Status:** draft. Phase one, and the first plugin to be finished. *(owner: "start with asset
bundles")*

## Why

The bundle is the centre of most deploys, and it is the plugin with the most to offer: the
Databricks CLI already plans it, deploys it, lists what it deployed and destroys it. Getting this
one right through the plugin contract proves the contract.

Most of the reading half exists — lely already asks the CLI to validate, plan and summarise a
bundle. It lives in the core today; this spec moves it into a plugin and adds apply, destroy and
the overview.

## Requirements

### As a step

- **R1** — `uses: bundle`. Options: `path`, the directory holding `databricks.yml`; and `vars`,
  values passed to the bundle as `--var`, which may come from earlier steps
  (`${steps.model.version}`). *(the options are today's `bundle:` and `bundle_vars:`)*
- **R2** — The plugin asks the Databricks CLI and never works out itself what the CLI resolves:
  targets, variables, names, ids. *(design)*
- **R3** — It needs the direct engine. A bundle on the Terraform engine is refused with a message
  that says so. *(design)*

### Plan

- **R4** — One change per bundle resource that would be created, changed, replaced or deleted,
  named by type and key (`jobs.backfill`), from `bundle plan -o json`. A delete, a recreate and a
  change of id are destructive. *(built, in the core)*
- **R5** — What only exists after the deploy — the id and link of a resource this deploy creates
  — is shown as decided at apply, and a later step that needs it waits for it. *(built)*

### Apply

- **R6** — `bundle deploy --plan`, with the plan that was approved. If the CLI refuses it because
  the bundle's state moved on, that refusal is reported as it is, and nothing else runs.
  *(design)*

### Overview — what it created

- **R7** — After an apply, and on its own at any time, the plugin lists every resource the bundle
  has deployed for this target: its type, its key, the name it has in the workspace, its id and
  a link to it. Right after an apply each line also says what happened to it: created, changed,
  unchanged, deleted. *(owner)*
- **R8** — The same overview is available four ways: a table in the terminal, a section in the
  UI ([007](007-ui.md)), Markdown for a pull request or a job summary
  ([008](008-github-actions.md)), and JSON for anything else. *(proposed)*
- **R9** — It comes from the CLI (`bundle summary -o json`), not from anything lely remembered.
  Run on another machine, a week later, it gives the same answer. *(owner: no state)*

### What it takes and what it gives

The whole of what passes between the bundle and the steps around it, declared as
[002/R14](002-plugins.md) asks. A step listed above the bundle can fill what it takes; a step
listed below can use what it gives.

- **R10 — It takes** `vars`, and nothing else: each is passed to the bundle as `--var`. A step
  that feeds the bundle does it here, in the bundle step's own options, where it can be read.
  *(design: a bundle is fed variables, nothing else)*
- **R10a — It gives:**

  | Output | Known |
  |---|---|
  | `target`, `name` | at plan |
  | `var.<name>` — every variable, resolved | at plan |
  | `resources.<type>.<key>.name`, and the other fields the bundle's own config has | at plan |
  | `resources.<type>.<key>.id` and `.url` | at plan for what is already deployed; after apply for what this deploy creates |

  *(built, as `${var.…}` and `${resources.…}` in the core; whether those short spellings stay is
  [002/D4](002-plugins.md#to-decide))*
- **R10b** — A step that uses an id this deploy creates is shown in the plan as decided at apply,
  waiting for `<bundle step>.resources.<type>.<key>.id` by name. *(built)*

### Destroy

- **R11** — A destroy plan lists every resource that would be removed — the same list as the
  overview — each marked destructive. *(owner)*
- **R12** — Destroying runs `bundle destroy` for the target and nothing else: no resource is
  deleted by lely itself. *(proposed — the CLI knows the order and what it may not delete)*
- **R13** — A target the bundle was never deployed to has an empty destroy plan, and says so.
  *(proposed)*

## Not in this spec

- Running a job, pipeline or app from the bundle: that stays its own plugin, `bundle.run`
- Building artifacts, which is the bundle's own `artifacts`
- Bundle variables that aren't single values: `--var` can't carry them, and the design has a
  `TODO(verify)` on the other route

## To verify on a workspace

lely's rule is that nothing about Databricks is assumed without a test and a link. Three things
here are assumed so far:

- **V1** — Whether the CLI can list what `bundle destroy` would remove without removing it, or
  whether the destroy plan has to be built from `bundle summary`.
- **V2** — How `bundle destroy` and `bundle deploy` behave when they want to ask something and
  nobody is there: which flag answers for them, and what they do without it. (The design already
  carries this as a `TODO(verify)` for deploy.)
- **V3** — That `bundle summary -o json` has an id and a link for every resource type, not only
  the ones in the CLI's recorded tests (jobs and pipelines).
- **V4** — What the CLI does when the bundle's target names one workspace and the credentials at
  hand reach another ([002/R24](002-plugins.md)): lely expects a refusal it can pass on.

## To decide

- **D1 — More than one bundle in a project.** It falls out of the bundle being a plugin: two
  steps, two paths. Allow it from the start, or one bundle per project for now? *(proposed: allow
  it; it costs nothing now that the config is one list, [003/R1](003-config.md))*
- **D2 — The overview when nothing is deployed yet.** An empty table, or the resources the bundle
  *would* create, marked as not there? *(proposed: the second — it is the same list a first plan
  shows)*

## Done when

- Each of R1–R13 has a test against the fake `databricks`.
- The plugin passes the whole contract kit ([002/R25](002-plugins.md)).
- V1–V4 have each been run on a workspace, and what they found is written beside the code that
  depends on it.
- A bundle has been planned, applied, listed and destroyed on a real target, end to end.

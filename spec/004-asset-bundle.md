# 004 — the Asset Bundle plugin

**Status:** draft. Phase one, and the first plugin to be finished — after the contract
([002](002-plugins.md)) and the config's shape ([003/R1](003-config.md)), which it stands on.
*(owner: "start with asset bundles")*

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
  (`${steps.model.version}`). The same `vars` go to every CLI call the step makes — validate,
  plan, deploy, summary, destroy. *(the options are today's `bundle:` and `bundle_vars:`)*
- **R2** — The plugin asks the Databricks CLI and never works out itself what the CLI resolves:
  targets, variables, names, ids. *(design)*
- **R3** — It needs the direct engine. A bundle on the Terraform engine is refused with a message
  that says so. *(design)*
- **R3a — A project can have more than one bundle step.** Each has its own name, its own path
  and its own outputs, and one can feed another like any two steps. All of them are deployed to
  the one workspace the run talks to ([002/R24](002-plugins.md)), and each takes `-t` as its own
  bundle target. *(owner, 2026-10-05)*

### Plan

- **R4** — One change per bundle resource that would be created, changed, replaced or deleted,
  named by type and key (`jobs.backfill`), from `bundle plan -o json`. A delete, a recreate and a
  change of id are destructive, and so is any action of the CLI's that lely doesn't recognise.
  *(built, in the core)*
- **R5** — What only exists after the deploy — the id and link of a resource this deploy creates
  — is shown as not known yet, and a later step that needs it is *waiting*
  ([005/R25](005-plan-apply-destroy.md)). *(built, as "decided at apply")*
- **R5a — A deploy uploads the bundle's files even when no resource changes.** `bundle plan`
  speaks of resources; a changed notebook or a rebuilt wheel isn't one. So the plan always
  carries one line for the bundle saying its files are uploaded, the deploy always runs, and "no
  changes" is never shown for a bundle step. That line is not counted as a change: a plan with
  only that line is still "nothing changes in the workspace's resources". *(proposed — without
  it, a plan that says nothing changes would be followed by a deploy that ships new code; see
  V5)*

### Apply

- **R6 — It deploys a fresh plan, checked against the approved one.** Right before deploying,
  the plugin asks the CLI for its plan again, lely checks it against what was approved
  ([005/R7](005-plan-apply-destroy.md)), and that fresh plan is what `bundle deploy --plan` is
  given — not the document from the plan file, which the CLI would refuse as stale the moment
  anything had been deployed. The CLI's own check then only has to cover the seconds in between.
  *(proposed; the design left open which of the two is handed over)*
- **R6a — So a second run finishes the first.** If an apply failed after the bundle deployed,
  running it again finds no resource left to change, deploys anyway — the files are uploaded
  again, nothing else moves — and goes on to the steps after it. *(follows from R5a and R6; see
  V6)*
- **R6b — A refusal by the CLI is passed on as it is:** its message shown word for word, the run
  ended as refused ([005/R31](005-plan-apply-destroy.md)), and no later step started. *(design)*

### Overview — what it created

- **R7** — After an apply, and on its own at any time, the plugin lists every resource the bundle
  has deployed for this target: its type, its key, the name it has in the workspace, its id and
  a link to it. *(owner)*
- **R7a — Right after an apply, each line also says what happened to it:** created, changed,
  unchanged, deleted. That comes from the plan that was just applied, in the same run — it is
  not remembered. `lely status`, run later, says what exists and nothing about how it got there;
  and a run that finishes an earlier, failed one shows as unchanged what that one created.
  *(owner; the limits follow from keeping no state)*
- **R8** — The overview is a table in the terminal and JSON for anything else. The page and the
  Markdown for a pull request use the same data when they arrive ([007](007-ui.md),
  [008](008-github-actions.md)). *(proposed)*
- **R9** — It comes from `bundle summary -o json` and from nothing else: nothing lely remembered,
  nothing in the plan file. *(owner: no state)*
- **R9a — Before a first deploy, it shows what would exist.** For a target the bundle was never
  deployed to, the overview lists the resources the bundle declares, each marked as not deployed
  — the shape of the target and what is missing from it. *(owner, 2026-10-05)*
- **R9b — It says whose view it is.** What a bundle has deployed is recorded by Databricks, in
  the workspace, under the bundle's own path — and that path can depend on who deploys. So
  `status` and `destroy` see what was deployed *by this identity, to this path, with these
  variables*, and print the identity and the path they looked under. A bundle that someone else
  deployed elsewhere looks "not deployed" from here, and lely says "not deployed, as far as
  `<identity>` can see under `<path>`" — never a bare "nothing there". *(proposed — found in
  review; see V7)*

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
  | `workspace.host`, and the other `workspace.<field>`s the CLI resolves | at plan |
  | `var.<name>` — every variable, resolved | at plan |
  | `resources.<type>.<key>.name`, and the other fields the bundle's own config has | at plan |
  | `resources.<type>.<key>.id` and `.url` | once it exists |

  *(built, as `${var.…}`, `${workspace.…}` and `${resources.…}` in the core; from here on they
  are spelled with the step's name, [002/R15a](002-plugins.md))*
- **R10b** — A step that uses an id this deploy creates is shown in the plan as waiting for
  `<bundle step>.resources.<type>.<key>.id`, by name. *(built, as "decided at apply")*

### Destroy

- **R11** — A destroy plan lists every resource lely can see the bundle has deployed — the same
  list as the overview — each marked destructive, and says that the bundle's uploaded files go
  with them. Whether the CLI would remove anything beyond that list is V1; until it is settled
  the plan says "and whatever else `bundle destroy` removes". *(owner; the caveat is proposed)*
- **R12** — Destroying runs `bundle destroy` for the target and nothing else: no resource is
  deleted by lely itself. *(proposed — the CLI knows the order and what it may not delete)*
- **R13** — A target with nothing deployed, as far as R9b can see, has an empty destroy plan and
  says so in R9b's words. *(proposed)*

## Not in this spec

- Running a job, pipeline or app from the bundle: that stays its own plugin, `bundle.run`
  ([010](010-command-and-bundle-run.md))
- Building artifacts, which is the bundle's own `artifacts`
- Bundle variables that aren't single values: `--var` can't carry them, and the design has a
  `TODO(verify)` on the other route
- A bundle step with a target of its own, different from `-t`: one name, said once, is what the
  person giving consent typed

## To verify on a workspace

lely's rule is that nothing about Databricks is assumed without a test and a link. The owner
decided on 2026-10-05 that this plugin is built against a fake CLI for now, with no run on a real
workspace. So these seven stay **assumed**: each is marked as unverified where the code depends
on it, and the README says that apply and destroy are untried on a real workspace until they are
settled.

- **V1** — Whether the CLI can list what `bundle destroy` would remove without removing it, or
  whether the destroy plan has to be built from `bundle summary` — and whether destroy removes
  more than the summary lists.
- **V2** — How `bundle destroy` and `bundle deploy` behave when they want to ask something and
  nobody is there: which flag answers for them, and what they do without it. (The design already
  carries this as a `TODO(verify)` for deploy.)
- **V3** — That `bundle summary -o json` has an id and a link for every resource type, not only
  the ones in the CLI's recorded tests (jobs and pipelines).
- **V4** — What the CLI does when the bundle's target names one workspace and the credentials at
  hand reach another ([002/R24](002-plugins.md)): lely expects a refusal it can pass on.
- **V5** — Whether `bundle plan` says anything about files that would be uploaded, or only about
  resources (R5a assumes: only resources).
- **V6** — That `bundle deploy --plan`, given a plan with no resource changes, still uploads the
  files and succeeds (R6a depends on it).
- **V7** — What `bundle summary` and `bundle destroy` answer for a bundle that another identity
  deployed, or that was deployed under another root path (R9b).

**A risk worth naming.** The fake CLI that this plugin is tested against has to answer for
deploy and destroy, and what it answers is these seven assumptions written down as code. Tests
that pass against it prove lely is consistent with what we believe, not with what the CLI does.
V2, V5 and V6 decide how apply is built, and V1 and V7 how destroy is; an hour with a real
workspace before those two are written would cost less than finding out afterwards. The owner's
decision stands; the risk is written here so that it is taken knowingly, and looked at again
when apply is about to be built.

## Decided

- **More than one bundle in a project** (was D1): yes, from the start — R3a.
  *(owner, 2026-10-05)*
- **The overview when nothing is deployed yet** (was D2): what would exist, marked as not
  deployed — R9a. *(owner, 2026-10-05)*
- **No run on a real workspace for now:** see [To verify](#to-verify-on-a-workspace).
  *(owner, 2026-10-05)*

## Done when

- Each requirement here has a test against the fake `databricks`.
- The plugin passes the whole contract kit ([002/R25](002-plugins.md)).
- V1–V7 are each marked as unverified in the code that depends on them, and listed in the README
  as what has not been tried on a real workspace.
- Every requirement still marked *(proposed)* here is agreed or changed.

Not part of done, by the owner's decision, and the first thing to do afterwards: a bundle
planned, applied, listed and destroyed on a real target, end to end, settling V1–V7.

# 004 — the Asset Bundle plugin

**Status:** built, 2026-10-05, and run on a real workspace twice, on 2026-10-06 — see
[Run on a workspace](#run-on-a-workspace-2026-10-06) for what that settled and what it didn't.

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
  only that line is still "nothing changes in the workspace's resources". *(agreed — without
  it, a plan that says nothing changes would be followed by a deploy that ships new code; see
  V5)*

### Apply

- **R6 — It deploys a fresh plan, checked against the approved one.** Right before deploying,
  the plugin asks the CLI for its plan again, lely checks it against what was approved
  ([005/R7](005-plan-apply-destroy.md)), and that fresh plan is what `bundle deploy --plan` is
  given — not the document from the plan file, which the CLI would refuse as stale the moment
  anything had been deployed. The CLI's own check then only has to cover the seconds in between.
  *(agreed; the design left open which of the two is handed over)*
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
  [008](008-github-actions.md)). *(agreed)*
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
  `<identity>` can see under `<path>`" — never a bare "nothing there". *(agreed — found in
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
  the plan says "and whatever else `bundle destroy` removes". *(owner; the caveat is agreed)*
- **R12** — Destroying runs `bundle destroy` for the target and nothing else: no resource is
  deleted by lely itself. *(agreed — the CLI knows the order and what it may not delete)*
- **R13** — A target with nothing deployed, as far as R9b can see, has an empty destroy plan and
  says so in R9b's words. *(agreed)*

## Not in this spec

- Running a job, pipeline or app from the bundle: that stays its own plugin, `bundle.run`
  ([010](010-command-and-bundle-run.md))
- Building artifacts, which is the bundle's own `artifacts`
- Bundle variables that aren't single values: `--var` can't carry them, and the design has a
  `TODO(verify)` on the other route
- A bundle step with a target of its own, different from `-t`: one name, said once, is what the
  person giving consent typed

## To verify on a workspace

*Written before any real run. Two were done on 2026-10-06:
[Run on a workspace](#run-on-a-workspace-2026-10-06) says what became of each point below.*

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

## Run on a workspace, 2026-10-06

One run, with the owner's token: Databricks CLI v1.19.0, an AWS workspace, a bundle with one job
and a target in development mode, the token of a workspace admin taken from the environment.
lely planned it, applied it, listed it, applied it again, applied an update from a plan file,
planned its destroy and destroyed it; the job and the bundle's folder were gone afterwards.

| | Assumed | Found |
|---|---|---|
| V1 | `bundle destroy` removes what the summary lists, and the files | **So it did**, for the one job, and the bundle's folder went with it. Whether it can remove more than the summary lists is still not known; the destroy plan keeps saying so. |
| V2 | `--auto-approve` answers when nobody can | **Yes.** Without it and with nobody to ask, `bundle destroy` refuses, exits 1 and names the flag. `deploy --plan … --auto-approve` ran unasked. Not tried: whether `deploy` without it asks before a delete. |
| V3 | the summary has an `id` and a `url` for every resource type | **For a job, yes.** Other types: only what the CLI's own recordings show (pipelines). |
| V4 | the CLI refuses a target on another workspace than the credentials reach | **No.** With a token from the environment the CLI goes to the host the bundle's target names and presents the token there. lely's own comparison of the two hosts is what stops the run — after that first call, which is the earliest it can know the bundle's host. |
| V5 | `bundle plan` speaks only of resources | **Yes.** |
| V6 | `deploy --plan` with nothing to change still uploads the files | **Yes**, and it succeeds. |
| V7 | a bundle another identity deployed looks not deployed from here | **Not tried**: one identity. The root path was seen to hold the deploying user's name. |
| V8 | `--var` reads its value as a line of CSV | **Yes.** `--var=a=1,b=2` set both variables; a pair in CSV quotes arrived whole. |

What the run found that nobody had assumed:

- **`bundle validate` is not read-only.** It creates the bundle's `files` folder in the
  workspace. lely's plan called it, so a plan left an empty folder behind — and would have
  needed credentials that can write. `bundle summary` gives the same resolved config and
  creates nothing, so the plugin asks that instead; `plan`, `status` and a destroy plan were
  then seen to leave the workspace as it was.
- **The words of a stale plan**: "plan serial 1 does not match state serial 2; the state has
  been modified since the plan was created." lely recognises a refusal by the second half.
- **The Terraform engine** (`DATABRICKS_BUNDLE_ENGINE=terraform`) answers `bundle plan -o json`
  without a `plan_version`, which is how lely tells it from the direct engine (R3). A new
  bundle was on the direct engine without being told.

Still not tried: V7; resource types other than a job; `bundle.run` (it would have run a job);
credentials that can only read; a second bundle in one project.

### A second run, later that day

After the page and GitHub were built: the same workspace and CLI, the credentials from a
`~/.databrickscfg` profile (`--profile`) this time, and a project with more in it — a `command`
step above the bundle whose plan command gives the bundle a variable, two jobs, and a `command`
step below that takes one job's id. Nothing was started; everything was destroyed again and
seen to be gone.

- **A first deploy through a file took two rounds, as designed.** `lely apply plan.json`
  created the jobs, stopped before the step that waited for a job's id (refused, exit 2), and
  wrote a record of that. The next plan showed the step ready with the real id; its file ran
  it.
- **An update through a plan file** changed one job's description — the value came from the
  step above — and the job read back from the workspace said so.
- **V3, a second resource type.** A pipeline, defined and never started, had an `id` and a
  `url` in the summary as a job has, and was planned, created, listed and destroyed like one.
- **Planning left the workspace as it was**: the folder that holds the bundles listed the same
  before and after the first plan.
- **The page** was made from a real plan, a real record and a real destroy plan (`lely ui`).
  The bundle's own view came from the real summary, and the links on a run's page led to the
  jobs.
- **The run's summary for GitHub** was written from a real plan, in a run that only said it was
  one (`GITHUB_ACTIONS=true`, a summary file, no token): Markdown as the tests have it. No
  comment was posted anywhere.
- **Destroy from a plan file** ran the lower step's destroy command first, then removed both
  jobs, the pipeline and the bundle's folder. Each was asked for by its id afterwards, and was
  not there.

Still not tried after both runs: V7 (another identity); `bundle.run`; credentials that can only
read; a second bundle in one project; a pull request in a real repository.

## Decided

- **More than one bundle in a project** (was D1): yes, from the start — R3a.
  *(owner, 2026-10-05)*
- **The overview when nothing is deployed yet** (was D2): what would exist, marked as not
  deployed — R9a. *(owner, 2026-10-05)*
- **No run on a real workspace for now:** see [To verify](#to-verify-on-a-workspace).
  *(owner, 2026-10-05. Two runs followed on 2026-10-06:
  [Run on a workspace](#run-on-a-workspace-2026-10-06).)*

## As built

2026-10-05.

- **"Files are uploaded" (R5a) is a `run`.** The spec had no word for it. A `run` already means
  "happens on every apply": a plan that holds one is never "nothing to do", and it is counted
  as a run, not as a change. So a bundle with no resource to change plans as
  `Plan: 0 changes · 1 run`.
- **Planning asks the CLI two things** — `summary` and `plan` — each with the step's `vars`. The
  summary is the resolved config with the ids of what is deployed already. Not `validate`,
  which R2's wording suggests: on a real workspace it creates a folder
  ([Run on a workspace](#run-on-a-workspace-2026-10-06)).
- **A resource this deploy replaces** is treated like one it creates: whatever id it has now is
  not the id it will have, so a step that takes it waits.
- **Which of the CLI's refusals lely recognises (R6b)** is one: a plan the state has moved on
  from, by the words "since the plan was created" in what the CLI says. That ends the run as
  refused. Any other failed deploy is a failure: running again may finish it. The words are
  read from the CLI's source, not seen live.
- **The Terraform engine (R3)** is recognised by a plan without a `plan_version`, and refused
  with a message that says so. How such a bundle really answers `bundle plan -o json` is not
  verified.
- **Another workspace (V4):** the plugin compares the host the bundle's target resolves to with
  the one the run talks to, and refuses when they differ. The CLI doesn't: it was seen to go to
  the bundle's host with whatever token the environment holds. So a bundle whose target names
  a host is trusted with the credentials the moment the CLI is asked about it — by lely or by
  hand — and lely can only stop what comes after.
- **Right after an apply (R7a)**, a resource the deploy deleted is listed too, as deleted.
- **An eighth assumption, found in review — V8.** `--var` is a list flag, which reads its
  value as a line of CSV. So a value with a comma or a quote is CSV-quoted; unquoted,
  `14,catalog=prod` from a step above would have set a second variable nobody wrote. Seen on
  the real CLI.
- **`vars` are text, passed as written.** `model_version: 3.10` goes out as `3.10`, not `3.1`,
  and `0123` isn't read as octal. A secret — a value from the environment included — and a
  list are refused where they are written, by `validate` already. A value with a line break
  isn't sent: the CLI's CSV reader and Python's don't agree on one.
- **Not held: what the bundle resolves from outside lely.** `BUNDLE_VAR_x` in the environment
  of the apply, or a variable's `lookup` answering something else than at plan, changes what
  is deployed without changing a line of the plan: the CLI's plan names the fields that
  change, not their values. A fingerprint of the resolved variables in the plan would catch
  it, at the price of refusing a plan whose variables depend on who runs it. *Not built; the
  owner's to decide.*
- **What the CLI writes while it deploys or destroys** — on stdout and on stderr — is passed
  on to the step's log a line at a time, as it comes, and kept for the error if the call
  fails; that error quotes both streams. `summary` and `plan` are answers: they are read, not
  shown. *(2026-10-07; before, only a failure showed anything, and of one stream.)*
- **A `path` that isn't a directory** is said so at plan. It used to read as "the Databricks
  CLI isn't installed".
- **What is still assumed** is a `TODO(verify)` in `src/lely/steps/bundle.py`; what was seen is
  said there too. `tests/fake_databricks.py` simulates both, and says which is which.

## Done when

- Each requirement here has a test against the fake `databricks`.
- The plugin passes the whole contract kit ([002/R25](002-plugins.md)).
- V1–V7 are each marked as unverified in the code that depends on them, and listed in the README
  as what has not been tried on a real workspace.

Not part of done, by the owner's decision, and the first thing to do afterwards: a bundle
planned, applied, listed and destroyed on a real target, end to end, settling V1–V7. *(Done
twice on 2026-10-06; V7 is still open.)*

# Running from a job

stevin applies from CI: a plan on the pull request, the apply on merge, through the
[GitHub Action](ci.md) or a lely step. Some workspaces can't be reached from a hosted
runner — Private Link, an allow-list, a network your CI isn't on. Then the plan is still
made and reviewed in CI, and the apply runs *inside* the workspace, as a job task, from
the same plan file.

## The shape

1. **CI plans.** `stevin plan -t prod -o plan.json` runs where the specs are, comments
   the plan on the pull request, and keeps `plan.json`. This needs a warehouse the
   runner can reach; if it can't reach any, planning runs in the job too, and the review
   happens on the job's output rather than the pull request — a weaker loop, named as
   such.
2. **The bundle carries the plan.** `databricks bundle deploy` syncs the project's
   files, `plan.json` among them, to the workspace.
3. **A job task applies it.** `stevin apply <path to plan.json>` as a Python wheel task
   on serverless compute, authenticated as the job's service principal, with the
   warehouse named in the target or in `DATABRICKS_WAREHOUSE_ID`.

The plan file is tied to the spec hash and to a fingerprint of the live state. If a
table moved between the plan and the job, the apply stops and says so — the job applies
exactly what was reviewed, or nothing. The history and lock tables work as anywhere:
every step's outcome is recorded, a dead run is resumed, two runs don't overlap.

## The job

```yaml title="databricks.yml"
resources:
  jobs:
    apply_tables:
      name: apply the tables
      environments:
        - environment_key: stevin
          spec:
            client: python
            environment_version: "2"
            dependencies:
              - stevin==0.4.0a1              # pin: the plan was made by this version
      tasks:
        - task_key: apply
          environment_key: stevin
          python_wheel_task:
            package_name: stevin
            entry_point: stevin
            parameters:
              - apply
              - ${workspace.file_path}/plan.json
      run_as:
        service_principal_name: ${var.deploy_principal}
```

`stevin apply` with a plan file doesn't ask; it runs the plan and refuses it if stale. A
plan with a destructive step needs `--allow-destructive` as a further parameter, so the
decision to pass it is in the reviewed `databricks.yml`, not in a notebook cell.

The task's warehouse comes from the target in `stevin.yml`
(`warehouse_id:`), which the plan file already names; the job's identity needs the
same privileges the CI principal would have had — `USE CATALOG`, `USE SCHEMA`,
`CREATE TABLE` and `MODIFY` where it creates and alters, `MANAGE` where it grants.

## The workflow

```yaml title=".github/workflows/tables.yml"
on:
  pull_request:
    paths: ["tables/**", "stevin.yml"]
  push:
    branches: [main]

jobs:
  plan:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    env:
      DATABRICKS_HOST: ${{ secrets.DATABRICKS_HOST }}
      DATABRICKS_CLIENT_ID: ${{ secrets.DATABRICKS_CLIENT_ID }}
      DATABRICKS_CLIENT_SECRET: ${{ secrets.DATABRICKS_CLIENT_SECRET }}
      DATABRICKS_WAREHOUSE_ID: ${{ secrets.DATABRICKS_WAREHOUSE_ID }}
    steps:
      - uses: actions/checkout@v4
      - uses: kostavo-oss/tools/packages/stevin@stevin-v0
        with:
          target: prod            # comments the plan; saves plan.json

  apply:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: databricks/setup-cli@main
      - run: uvx stevin plan -t prod -o plan.json   # the plan the job will apply
      - run: databricks bundle deploy -t prod       # plan.json travels with the files
      - run: databricks bundle run -t prod apply_tables
```

The `plan` here is the same plan the pull request showed, remade on `main` so its
fingerprint is current; the job refuses it if the world moved in between. Where even
the plan can't be made from the runner, drop the `plan` step and let the task run
`stevin apply -t prod --yes` instead: it plans and applies in one go inside the
workspace, and the job's log is the review.

## Not a notebook

stevin has no notebook entry point, on purpose. A notebook is run by whoever opens it,
with whatever is in its cells that morning; a plan file is a reviewed artefact and a
job task is a reviewed definition. The library is there for a host that needs it —
[As a library](sdk.md) — and a job task is one.

## Unverified

This page was written against the Databricks documentation, not run against a
workspace yet. Specifically not yet verified on a real job: that a Python wheel task on
serverless picks up the job's identity through the SDK's default authentication the way
a notebook does ([the SDK page](https://docs.databricks.com/aws/en/dev-tools/sdk-python)
describes the notebook case); that `${workspace.file_path}/plan.json` is the path the
synced file has from inside the task; and the `environments` block's current field
names ([bundle resources](https://docs.databricks.com/aws/en/dev-tools/bundles/resources)).
The live suite will take this page up; until then, try it on a dev target.

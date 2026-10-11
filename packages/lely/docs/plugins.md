# Plugins

Every step is a plugin's. `lely steps` lists the ones this project can use, with their
options, what they give, and what they can do.

## `bundle`

A Databricks Asset Bundle: planned, deployed, listed and destroyed through the Databricks
CLI. lely never reimplements what the CLI resolves — it asks.

```yaml
  - name: app
    uses: bundle
    with:
      path: .                    # where databricks.yml is; the default
      vars:
        model_version: ${steps.model.version}
```

| Option | |
| --- | --- |
| `path` | The bundle's folder, from the config's. Default `.` |
| `vars` | Bundle variables, passed as `--var`. A value may come from a step above. |

It gives the bundle's `target` and `name`, `workspace.<field>`, `var.<name>`, every
resource's own config as `resources.<type>.<key>.<field>` — known at plan — and
`resources.<type>.<key>.id` and `.url`, known once the resource exists.

Every bundle plan carries one `run`: *uploads the bundle's files*. A deploy uploads them even
when no resource changes, so a bundle step is never "nothing to do".

!!! note "The CLI trusts the bundle with your credentials"
    A bundle whose target names another host is not refused by the CLI: with a token from
    the environment it goes to that host and presents the token. lely compares the two hosts
    and stops, but only after the CLI's first call. Know whose `databricks.yml` you run.

## `bundle.run`

Runs a job, pipeline or app from a bundle step, with `databricks bundle run`.

```yaml
  - name: backfill
    uses: bundle.run
    with: {bundle: app, resource: jobs.backfill, args: ["--full"]}
```

It stands below the bundle step it names, and its plan is a `run`.

!!! warning "Not run for real yet"
    No job has been started with `bundle.run` on a workspace:
    [What has been tried](tried.md#not-yet).

## Your own

A class in a file in your repo, or one a package registers:

```yaml
  - name: model
    uses: ./ops/steps.py:LatestModel       # a class in the repo
  - name: audit
    uses: acme_deploy.steps:Audit          # a class in an installed package
```

→ [Writing a step](writing-a-step.md). A program — `dbt run`, a notification — is a
`Program`: a step in ten lines, there too.

Planning runs your project's own code — a step in the repo. On a pull request, give
`lely plan` credentials that can read and nothing more.

## `stevin`

Tables, views and the access around them, planned and applied by
[stevin](https://kostavo-oss.github.io/tools/stevin/). lely runs the `stevin` command, so
stevin has to be installed where lely runs: version 0.4.0a2 or newer. A plan from an
older stevin fails, and says which version it found.

```yaml
steps:
  - name: tables
    uses: stevin
    with:
      config: stevin.yml         # stevin's project file; the default

  - name: app
    uses: bundle
```

| Option | |
| --- | --- |
| `config` | stevin's project file, from the config's folder. Default `stevin.yml` |
| `target` | stevin's target. Default: the `-t` lely was given |
| `select` | Only these tables, views or patterns, as stevin's `--select` |
| `executable` | How to run stevin. Default `[stevin]`; `[uvx, stevin]` runs it in an environment of its own |

**The plan** has one change per table, with a line for each step stevin would run and
that step's risk class:

```text
tables  stevin
    update   main.sales.orders  rewrite
        STAGE rewritten data  [rewrite]
        REPLACE TABLE  [rewrite]
        SET NOT NULL order_id  [meta]
        ⚠ fails unless every existing row already has a value
```

`meta` and `feature` are cheap. `rewrite` rewrites the table's data, and the table's own
line says so. `destructive` loses something, and needs `lely apply --allow-destructive`;
lely passes that on to stevin only then. A risk class lely does not know is treated as
destructive.

**Apply runs the plan that was reviewed.** stevin's own plan file travels inside lely's
plan file. `lely apply` hands that file to `stevin apply`, never a new one. Two checks
stand before it:

- lely plans the step again and compares. If stevin would now do anything else than the
  reviewed file holds, lely refuses, and stevin is not run.
- stevin compares the file with the live tables. If they changed since the plan was
  made, stevin refuses the plan as stale.

Either way the run ends with 2 and nothing after the step starts. Plan again, and review
the new plan. That is also what to do after stevin failed halfway through a plan: what it
applied stays applied, and the next plan shows what is left.

lely tells a refusal from a failure by stevin's
[exit code](https://kostavo-oss.github.io/tools/stevin/cli/#exit-codes), not by what
stevin prints. A refusal ends the run with 2, and a failure with 1. Both show stevin's
own message.

**Destroy drops nothing.** A dropped table is its rows. `lely destroy` skips the step and
says so. To drop a table, take it out of stevin's specs: stevin's own rules say when it
drops one.

**Status** lists what stevin's specs describe and whether each exists. lely asks
`stevin list` for it, which makes no plan. It says whether an object is there, not
whether it matches its spec: a plan says that.

The step gives no outputs. A plan file holds stevin's statements, and names of tables,
columns and owners: keep it where the pull request's other artifacts are kept. lely
prints the names of tables and columns, the titles of stevin's steps and their warnings.
A title names the principal of a grant. No owner is printed.

!!! warning "Not run for real yet"
    The step has not run on a workspace, and not against the real `stevin` command:
    [What has been tried](tried.md#not-yet).

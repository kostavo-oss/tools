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
stevin has to be installed where lely runs: version 0.4.0a3 or newer. A plan from an
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

**The step waits for the bundle's schema.** stevin does not plan a table whose schema
the bundle declares and has not deployed yet, and it does not create that schema: it is
the bundle's. That is so on a target that was never deployed, and again whenever the
bundle gets a new schema with tables in it. stevin then plans none of its tables, also
not the ones in schemas that are there. So put the `stevin` step below the `bundle`
step. The plan shows the bundle ready and the tables waiting:

```text
app  bundle
    + schemas.sales
    ▶ uploads the bundle's files
tables  stevin
    ⏸ waiting: a schema of these tables is the bundle's and is not deployed yet; the tables are planned once it is
    stevin: dev.sales is the bundle's schema 'sales', and isn't there yet — run `databricks bundle deploy` first; stevin won't create it

Plan: 1 change · 1 run · 0 destructive · 1 waiting
```

The second line is stevin's own, and names the schema. With the `bundle` step above
the tables you do not run the deploy it speaks of: that step does.

lely does not check that a `bundle` step stands above. With the `stevin` step above
it, or with a bundle that is deployed outside lely, the plan shows the tables waiting
all the same, and every apply is refused when it reaches them, with nothing of them
applied. Move the step below the bundle, or deploy the bundle first.

- `lely apply -t dev` deploys the bundle, then plans the tables, shows them and asks.
- `lely apply plan.json` deploys the bundle and stops at the tables with 2: nobody has
  seen what stevin will do. The next `lely plan` shows the tables, and that plan
  applies them. On GitHub that is the next pull request, or an apply by hand.

Once the schema exists the step is planned as on any other day. It is a
[waiting step](plan-apply-destroy.md#apply) like any other. Any other reason stevin
cannot plan still fails the plan, with stevin's message. So does this one with a stevin
older than 0.4.0a3: it ends with 1, and lely cannot tell which stevin it was. `lely
status` and `lely destroy` work before the first deploy too: a status lists the tables
as not there, and a destroy skips the step.

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
own message. It knows that the bundle's schema is not there yet the same way: by the
exit code of `stevin plan`.

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

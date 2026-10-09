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
    `bundle.run` is tested against the fake CLI only: no job has been started with it on a
    workspace.

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

Tables, planned by [stevin](https://github.com/kostavo-oss/tools). Parked: it can plan, and
can't apply yet — `lely apply` refuses a project that uses it.

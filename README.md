# lely

**One `plan` and one `apply` for a whole Databricks deploy.**
Pre-deploy steps, the bundle, post-deploy steps — one plan you can read before anything
runs. It covers what an Asset Bundle can't deploy: tables, database migrations, and your
own steps.

> **Terraform for your platform, Asset Bundles for your code, stevin for your data model.**

> **Status: pre-alpha.** The read-only half is built: `validate`, `steps`, `plan` and
> `show`. `apply` is the next milestone — so today lely shows you a whole deploy and runs
> none of it. [docs/DESIGN.md](docs/DESIGN.md) is the source of truth.

## Named after

Cornelis Lely (1854–1929), the engineer who designed the Zuiderzee Works and, as minister,
got them built — the Afsluitdijk among them. The one who actually got big plans built.

## Install

lely isn't on PyPI yet. From a checkout:

```sh
git clone https://github.com/kostavo-oss/lely && cd lely
uv sync
uv run lely --version
```

Once it is published: `uvx lely` to run it once, `uv tool install lely` to keep it.

## Quickstart

A `lely.yml` next to your `databricks.yml` says what runs around the bundle:

```yaml
bundle: .                    # the directory holding databricks.yml

post:
  - name: tables
    uses: stevin             # plan the tables with stevin, if you use it
    with: {config: stevin.yml}
  - name: backfill
    uses: bundle.run
    with: {resource: jobs.backfill}
```

```sh
lely validate                 # config, references and step options — offline
lely steps                    # the steps installed here, and their options
lely plan -t dev              # the whole deploy as one plan; nothing is changed
lely plan -t dev -o plan.json # … or as a file, for `lely show plan.json`
```

## The plan

Every stage in one place — what the pre steps found, what the bundle will create, and
what happens after it:

```
lely plan · shop · target dev

pre
  model  ./ops/steps.py:LatestModel
    → version = 14

bundle
    + jobs.bar
    + pipelines.foo
    vars  model_version = 14

post
  tables  stevin
    ~ dev.sales.orders  destructive
        DROP COLUMN  [destructive]
  notify  command
    ⏸ decided at apply: resources.jobs.bar is created by this deploy
  backfill  bundle.run
    ▶ runs jobs.backfill

Plan: 3 changes · 1 run · 1 destructive · 1 decided at apply
```

## Steps

- **`bundle.run`** — run a job, pipeline or app from the bundle.
- **`command`** — a step as commands: an optional plan command and an apply command.
- **`stevin`** — tables, views, functions and grants, planned by
  [stevin](https://github.com/kostavo-oss/stevin). lely runs the `stevin` command, which
  you install yourself: it is not a dependency of lely, so a project without tables never
  needs it. A destructive table change shows up as destructive in the deploy's plan.
- **Your own** — a class in a file in your repo (`uses: ./ops/steps.py:LatestModel`), or a
  package that registers one under the `lely.steps` entry point.

## Where it fits

lely is one of the [Kostavo tools](https://github.com/kostavo-oss) for Databricks. Each
does one job and none needs another: Terraform sets up the platform, an Asset Bundle
deploys the code, stevin changes the data model — and lely is the one plan around the
three of them, for the part of a deploy a bundle alone can't describe.

Community project, not affiliated with or endorsed by Databricks.

## Development

```sh
mise install     # pinned Python + uv
uv sync          # .venv with deps and dev tools
mise run check   # lint + format check + types + unit tests
```

## License

[MIT](LICENSE) © Misja Pronk

# Small tools for the ugly gaps on Databricks

Databricks runs the compute, governs the catalog and deploys the code. dlt and dbt land
the data and shape it. Between them sit a handful of jobs that nobody ships a tool for,
and every team fills them the same way: a setup notebook, a shell script around the
deploy, a page of steps in a wiki. Those are the parts of a data platform that are never
reviewed, that break in the second environment, and that leave with whoever wrote them.

These are four small tools, one per gap, and a template that starts a data product with
them in place.

[Why they exist, and what they are worth →](why.md){ .md-button .md-button--primary }

## What you get

| You have to… | What most teams do | With these |
|---|---|---|
| change a table that has data in it | run a notebook and hope | a plan in the pull request that says which changes are free, which rewrite the table and which destroy something — [stevin](stevin/index.md) |
| make the tables a notebook or another system writes into, and say who may read them | a setup job nobody dares to run twice | specs in git, applied the same way in every environment, and drift reported when someone changes a table by hand — [stevin](stevin/index.md) |
| deploy a bundle and the steps around it | a shell script with no dry run | one plan for all of it, read before any of it runs, and taken down again on request — [lely](lely/index.md) |
| develop a pipeline | deploy, wait for a cluster, read the log | the same dlt pipeline on a laptop into a local file, then unchanged in a job — [leeghwater](leeghwater/index.md) |
| look after the secrets in a scope | CLI commands copied from a wiki | a page on your own machine that shows scopes, secrets and who may read them — [caland](caland/index.md) |
| depend on another team's table | find out in production | the contract they publish tested from your side, and a breaking change to a published version stopped in their pull request — [the template](https://github.com/kostavo-oss/data-product-template) |

## What every tool keeps to

- **One job, and a closed scope.** Each tool does one thing, lists what it will never
  do, and names the change in Databricks that would make it unnecessary.
- **What changes a workspace is shown first.** stevin and lely print a plan to read in
  the pull request: what will change, what it costs, what it destroys.
- **Nothing to host, nothing to sign up for.** No state file to store, no service to
  run, no account to open. The workspace is the state.
- **Your code stays yours.** The pipelines are dlt, the models are dbt, the contracts
  are an open standard. The tools are the Databricks edge around them; take one away and
  the product still runs.
- **Each works alone.** None needs another, and none needs anything from Kostavo.
- **Complete as it is.** Apache-2.0, nothing held back for a paid edition, no telemetry.

## The tools

### stevin — the data model

**stevin puts in place the tables and access that your transformation tool doesn't own.**
dbt, Lakeflow or SQLMesh own what they build. stevin owns what they read and what they
leave to a setup job: the tables notebooks and external systems write into, lookup
tables, filtered views, and who may see what. Describe them in YAML or SQL, or take
their shape from a data contract; see a plan that knows which Delta changes are free and
which rewrite 400 GB; then apply it.

[stevin →](stevin/index.md){ .md-button }

### lely — the deploy

**One plan for your whole Databricks deploy.** The bundle and everything around it, the
steps before and the steps after, reviewed before anything runs, and taken down again
when you say so.

[lely →](lely/index.md){ .md-button }

### leeghwater — the pipeline

**Your dlt pipeline, the same on your laptop and in a Databricks job.** One command to
run it, its secrets from a secret scope, and the things Databricks asks for kept out of
your code.

[leeghwater →](leeghwater/index.md){ .md-button }

### caland — the secrets

**Databricks secrets, by hand: a keyboard-driven page in your browser, served from your
own machine.** Browse scopes, secrets and grants; create, edit, move and delete; show and
copy values; put a certificate in from a file.

[caland →](caland/index.md){ .md-button }

## Starting a product

[data-product-template](https://github.com/kostavo-oss/data-product-template) is a data
product for Databricks, ready to start from: dlt lands the data, dbt shapes it, one job
runs both, the schemas are the bundle's, and the product says what it promises in a
data contract. The tools above come with it, each optional.

```sh
uvx copier copy gh:kostavo-oss/data-product-template my-product
```

## What has been tried

Every tool is early, and says so. Each keeps a page of what has run against a real
workspace and what has not: [stevin](stevin/testing.md), [lely](lely/tried.md),
[leeghwater](leeghwater/tried.md). Try them on a development catalog first.

## Named after

Dutch water engineers. Simon Stevin (1548–1620) designed sluices and introduced decimal
notation. Cornelis Lely (1854–1929) drew the plan that closed the Zuiderzee. Jan
Adriaanszoon Leeghwater (1575–1650) drained the lakes north of Amsterdam. Pieter Caland
(1826–1902) cut the Nieuwe Waterweg that gave Rotterdam its way to the sea. Precision
before action.

## Where they fit

Each does one job and none needs another: Terraform sets up the platform, an Asset Bundle
deploys the code, dbt, Lakeflow or SQLMesh build the tables they build, and these tools
take the pieces in between. Kostavo is the company behind them: it builds
[a governance platform for Databricks workspaces](https://kostavo.com), and the tools
are complete without it.

Community project, not affiliated with or endorsed by Databricks.

# Why these tools

## The gaps

Most of a data platform on Databricks is bought, not built, and what is bought is good.
What is left over is small, and it is the same in every workspace.

**The table nobody's pipeline owns.** The table a notebook appends to, the lookup table,
the table another system writes into. Someone made it once, with a `CREATE TABLE` in a
notebook. Changing it is another notebook, run by hand, once per environment, and
afterwards nobody can say what production looks like or why.

**The deploy that is more than a deploy.** `databricks bundle deploy` deploys the bundle.
The schema that has to exist first, the job that has to run once after, the table that
has to change: those are a script around it, and a script has no dry run.

**The pipeline that only runs on a cluster.** Every change is a deploy and a wait. The
secrets are in one place on a laptop and another in a job. So nobody runs the pipeline
locally, and finding a typo takes ten minutes.

**The secret you reach through an API.** Rotating a key is a command copied from a wiki,
and who may read which scope is a question nobody can answer quickly.

**The upstream table that changed.** Another team renamed a column. The job that read
it found out at night.

None of these is hard. Each is small enough that nobody builds it properly, and
important enough to hurt when it goes wrong.

## What the tools do about them

- [stevin](stevin/index.md) keeps those tables, and the access around them, as specs in
  git. A change is a plan in a pull request, and a change made by hand shows up as drift.
- [lely](lely/index.md) puts the bundle and the steps around it into one plan that is
  read before anything runs.
- [leeghwater](leeghwater/index.md) runs a dlt pipeline the same way on a laptop and in
  a job, with its secrets from one place.
- [caland](caland/index.md) is a page for the secrets, on your own machine.
- [The template](https://github.com/kostavo-oss/data-product-template) starts a product
  with all of this wired, and with a data contract for what the product promises.

## The rules they keep

**Small and closed.** A tool that grows to cover the next request becomes a platform,
and a platform needs a team. Each of these does one job and lists what it will not do.
The lists are the defence: a request outside one is a snippet in your own repository,
not a feature.

**Shown before it runs.** A change to production that nobody read is the cause of most
bad nights. Where a tool changes a workspace, it prints a plan first, and the plan says
what a reviewer needs: what changes, what it costs, what it destroys.

**No state of their own.** A state file is one more thing to store, lock and repair.
These tools ask the workspace what is there, every time.

**Your code stays yours.** The pipelines are dlt, the models are dbt and the contracts
are the Open Data Contract Standard. None of that is specific to these tools, or to
Databricks. The tools are the edge between your code and the workspace. Stop using one
and your product still runs.

**Not forever.** Each tool names the change in Databricks that would make it
unnecessary. When that change comes, use the platform's own.

## What it is worth

**To the engineer.** A change is reviewed before it runs, not explained after. The
second environment costs nothing, because it is the same specs with other names. A
pipeline can be tried on a laptop in seconds.

**To whoever answers for the platform.** Every change to production data and access is
a pull request, with a name on it and a reason. A new engineer reads a repository
instead of asking around. There is nothing to buy, host or renew, and nothing that has
to be migrated away from later.

## What they are not

Not a platform, and not a framework: none of the tools needs another, and none needs a
service. Not a replacement for Terraform, Asset Bundles, dbt or dlt: they begin where
those stop. And not finished. Each tool says what has run against a real workspace and
what has not, and that page is the place to start before trusting one with production.

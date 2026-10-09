# The ugly gaps on Databricks, and a small tool for each

Databricks does most things well. A few it leaves to you: the tables no pipeline owns and
the grants and masks around them, the steps before and after a bundle deploy, a dlt
pipeline that has to run on a laptop before it runs in a job, and the secrets in a scope
you can only reach with an API. Each of those is a setup notebook or a brittle script in
most workspaces. These are four small tools, one per gap, each with a closed scope, a
"not in this tool" list, and a line that says when Databricks will have made it
unnecessary.

Every tool is a package of its own on PyPI; none needs another. They share this
repository, one test gate and this site.

## stevin — the data model

**stevin puts in place the tables and access that your transformation tool doesn't own.**
dbt, Lakeflow or SQLMesh own what they build. stevin owns what they read and what they
leave to a setup job: the tables notebooks and external systems write into, lookup
tables, filtered views, and who may see what. Describe them in YAML or SQL, see a plan
that knows which Delta changes are free and which rewrite 400 GB, then apply it.

[stevin →](stevin/index.md){ .md-button .md-button--primary }

## lely — the deploy

**One plan for your whole Databricks deploy.** The bundle and everything around it, the
steps before and the steps after, reviewed before anything runs, and taken down again
when you say so.

[lely →](lely/index.md){ .md-button }

## leeghwater — the pipeline

**Your dlt pipeline, the same on your laptop and in a Databricks job.** One command to
run it, its secrets from a secret scope, and the things Databricks asks for kept out of
your code.

[leeghwater →](leeghwater/index.md){ .md-button }

## caland — the secrets

**Databricks secrets, by hand: a keyboard-driven page in your browser, served from your
own machine.** Browse scopes, secrets and grants; create, edit, move and delete; show and
copy values; put a certificate in from a file.

[caland →](caland/index.md){ .md-button }

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

# lely

**One plan for your whole Databricks deploy.** The bundle and everything around it — the
steps before, the steps after — reviewed before anything runs, and taken down again when you
say so.

!!! warning "Alpha"
    Everything described here is built, and has run for real a few times: on a workspace,
    and through GitHub's workflows. That is a first proof, not a track record —
    [what has been tried](tried.md) says exactly what was and wasn't. Try it on a
    development target first.

A real deploy to Databricks is an Asset Bundle and the things around it: a model version
looked up and handed to the bundle, a job that has to run once the bundle is there, a seed,
a migration. The bundle has a plan and a deploy. The things around it have a shell script.
lely replaces that script.

```
lely plan · target dev · https://dbc-example.cloud.databricks.com as jane@example.com

  model  ./ops/steps.py:LatestModel
    → version = 14
  app  bundle
    model_version = 14  ← model.version
    + jobs.bar
    ± pipelines.foo  destructive
        replaced: storage (immutable)
    ▶ uploads the bundle's files
  notify  command
    ⏸ waiting for app.resources.jobs.bar.id
  backfill  bundle.run
    bundle  ← app
    ▶ runs jobs.backfill

Plan: 2 changes · 2 runs · 1 destructive · 1 waiting
```

[Your first plan](getting-started.md){ .md-button .md-button--primary }
[What may run](safety.md){ .md-button }
[On GitHub](GITHUB.md){ .md-button }

<hr class="ly-rule">

## What it gives you

- **The whole deploy in one plan** — every step, in the order it runs, with what it takes
  from the steps above it and what it would change.
- **What one step hands the next is written down** — `${steps.<name>.<output>}`, in the
  step's own options, and checked before anything runs.
- **One rule for consent** — nothing that changes a workspace runs unasked, and nothing
  destructive without `--allow-destructive`. A reviewed plan file runs exactly what was
  reviewed, or refuses.
- **It goes both ways** — `lely destroy` plans the teardown, from the bottom up, and asks.
- **No state** — whatever lely needs to know, it asks the system it manages: for a bundle,
  the Databricks CLI.
- **Where plans get read** — as one comment on the pull request, kept current; on the run's
  page; and as [a page of its own](page.md) you can open or pass on.

## When not to use it

- **One bundle and nothing around it.** `databricks bundle deploy` is all you need.
- **Every extra step is an opaque script.** lely gives it an order, checked inputs and one
  rule for consent, but a plan that reads "runs `deploy.sh`" shows a reviewer little.
- **You need an audit trail, drift detection, or cleanup of what you stopped declaring.**
  Those need state, and lely has none: remove a step from the config and what it deployed
  stays. Destroy first, then remove the step.
- **Your CI isn't GitHub Actions**, for now.

## Where it fits

> Terraform for your platform, Asset Bundles for your code,
> [stevin](https://github.com/kostavo-oss/stevin) for your data model — and lely to deploy
> them as one.

lely borrows Terraform's words — plan, apply, destroy — because everyone knows what they
promise. The job is not the same: lely manages no resource itself and remembers nothing. It
owns the order, the review and the consent.

Named after Cornelis Lely (1854–1929), the engineer who designed the Zuiderzee Works.
Community project, not affiliated with or endorsed by Databricks.

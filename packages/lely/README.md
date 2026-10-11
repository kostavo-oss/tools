# lely

**One plan for your whole Databricks deploy.**
The bundle and everything around it — the steps before, the steps after — reviewed before
anything runs, and taken down again when you say so.

[![ci](https://github.com/kostavo-oss/tools/actions/workflows/ci.yml/badge.svg)](https://github.com/kostavo-oss/tools/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/lely.svg)](https://pypi.org/project/lely/)
[![Python](https://img.shields.io/pypi/pyversions/lely.svg)](https://pypi.org/project/lely/)
[![Docs](https://img.shields.io/badge/docs-lely-2a6f97.svg)](https://kostavo-oss.github.io/tools/lely/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/kostavo-oss/tools/blob/main/packages/lely/LICENSE)

lely replaces the script around `databricks bundle deploy`.

> **Alpha.** It is tested against a fake Databricks CLI and a fake GitHub, and has run
> for real a few times with small bundles. What was tried and what was not is in
> [What has been tried](https://kostavo-oss.github.io/tools/lely/tried/).

## Why

`databricks bundle deploy` deploys the bundle. A real deploy is more than that: the schema
that has to exist first, a model version looked up and handed to the bundle, the job that
has to run once after, the table that has to change. The bundle has a plan and a deploy.
The things around it have a shell script, and a script has no dry run.

That script fails in four ways a team feels, and lely answers each:

- **Nobody sees the whole deploy before it runs** → one plan for every step.
- **What one step hands the next is invisible** → written down in the config, and checked.
- **Nothing is guarded the same way twice** → one rule for consent and for destructive changes.
- **It only goes one way** → `lely destroy`.

lely keeps no state. Whatever it needs to know, it asks the system it manages: for a
bundle, the Databricks CLI. It borrows Terraform's words, plan, apply and destroy, because
everyone knows what they promise. The job is not the same: lely manages no resource itself
and remembers nothing. It owns the order, the review and the consent.

## Quickstart

lely is on [PyPI](https://pypi.org/project/lely/) and needs Python 3.11 or newer. In the
project that has the bundle:

```sh
uv add --dev lely
```

One ordered list of steps, in `lely.yml`. The bundle is one of them. What stands above it
runs before the deploy, what stands below runs after:

```yaml
steps:
  - name: model                  # feeds the bundle: it is above it …
    uses: ./ops/steps.py:LatestModel
    with: {model: main.ml.churn, alias: candidate}

  - name: app
    uses: bundle
    with:
      path: .
      vars:
        model_version: ${steps.model.version}     # … and the bundle says what it takes

  - name: backfill               # needs something from the bundle: it is below it …
    uses: ./ops/steps.py:Backfill
    with: {job: "${steps.app.resources.jobs.backfill.id}"}   # … and says what
```

A step takes a value from another step in one way only: `${steps.<name>.<output>}`, in its own
options, and only from a step above it. Reading a step's `with:` is enough to know everything
it depends on.

`bundle` comes with lely; the other two are yours — classes in a file in the repo.
`LatestModel` runs as it stands, and your lookup goes where the `14` is; `Backfill` is a
program as a step, one run every apply:

```python
# ops/steps.py
from dataclasses import dataclass

from lely.model import Output, StepPlan
from lely.step import Program


class LatestModel:
    """Looks up the version a serving endpoint should get. Changes nothing."""

    @dataclass(frozen=True, slots=True)
    class Options:
        model: str
        alias: str = "candidate"

    outputs = (Output("version"),)

    def plan(self, ctx):
        # a lookup changes nothing, so it belongs here; `ctx.workspace` is the
        # Databricks SDK's client, for `ctx.options.model` and `.alias`
        return StepPlan(outputs={"version": 14})

    def apply(self, ctx, plan):
        return plan.outputs  # nothing to do: what it gives was known at plan


class Backfill(Program):
    """Backfills the job this deploy made."""

    @dataclass(frozen=True, slots=True)
    class Options:
        job: str

    def command(self, ctx):
        return ["./ops/backfill.sh", ctx.options.job]
```

`bundle` comes with lely. The other two are classes in a file of the repo: `LatestModel`
runs as it stands, with your lookup where the `14` is, and `Backfill` is a program as a
step.

```sh
lely validate                    # config, options, references: offline; prints the wiring
lely plan -t dev                 # the whole deploy as one plan; nothing is changed
lely plan -t dev -o plan.json    # … as a file, to review
lely apply plan.json             # run exactly what was reviewed
lely status -t dev               # what is deployed right now
lely destroy -t dev              # take it down again: plan, show, ask, run
```

`lely validate` needs nothing but the two files above. The others need a bundle beside
`lely.yml` with a variable `model_version` and a job `backfill`, the Databricks CLI, and
a workspace to sign in to; `-t` is always given.

## The docs

How to use it is in the [docs](https://kostavo-oss.github.io/tools/lely/), and only there:

- [Your first plan](https://kostavo-oss.github.io/tools/lely/getting-started/) and [installation](https://kostavo-oss.github.io/tools/lely/installation/).
- [The config](https://kostavo-oss.github.io/tools/lely/config/): steps, references, targets, secrets.
- [Plan, apply, destroy](https://kostavo-oss.github.io/tools/lely/plan-apply-destroy/): what a plan shows, what a plan file is
  held to, and what happens when a step fails.
- [Plugins](https://kostavo-oss.github.io/tools/lely/plugins/) that come with lely, and [writing a step](https://kostavo-oss.github.io/tools/lely/writing-a-step/)
  of your own, which also runs without lely.
- [A plan as a page](https://kostavo-oss.github.io/tools/lely/page/), and [on GitHub](https://kostavo-oss.github.io/tools/lely/GITHUB/): the plan as a comment on
  the pull request, with workflows to copy.
- [What may run](https://kostavo-oss.github.io/tools/lely/safety/): consent, secrets, and what lely cannot see.
- [Commands](https://kostavo-oss.github.io/tools/lely/cli/) and exit codes, and [how it works](https://kostavo-oss.github.io/tools/lely/how-it-works/) inside.

## What has been tried

On 2026-10-06 lely ran on a real workspace twice, with small bundles, and once through
three GitHub workflows: planned, applied, updated from a plan file, listed and destroyed.
Not tried: `bundle.run`, credentials that can only read, a bundle another identity
deployed, a step run on its own, a pull request from a fork.

[What has been tried](https://kostavo-oss.github.io/tools/lely/tried/) is the record: what held, what did not, and what is
still assumed.

## When not to use it

- **One bundle and nothing around it.** `databricks bundle deploy` is all you need.
- **Every extra step is an opaque script.** lely gives it an order, checked inputs and one rule
  for consent, but a plan that reads "runs `deploy.sh`" shows a reviewer little.
- **You need an audit trail, drift detection, or cleanup of what you stopped declaring.** Those
  need state, and lely has none: remove a step from the config and what it deployed stays.
  Destroy first, then remove the step.
- **Your CI isn't GitHub Actions**, for now.

And what it will not become: a workflow engine (one ordered list, no parallel steps, no
retries), a rollback, a build tool, or a second way to do what a bundle resource can do.

## When you no longer need it

When a bundle plans its own before-and-after steps — `databricks bundle plan` shows what
runs before and after the deploy, and `bundle destroy` takes it down again — use the
bundle alone. Today `bundle plan` shows the bundle's resources and nothing around them.

## Where it fits

lely is one of the [Kostavo tools](https://github.com/kostavo-oss/tools): small tools for the ugly gaps on Databricks, one
gap each. Its gap is the deploy that is more than a deploy: the steps before and after
`databricks bundle deploy`, kept in a script with no dry run. Each works alone. Kostavo is
the company behind them: it builds
[a governance platform for Databricks workspaces](https://kostavo.com), and the tools are
complete without it.

Community project, not affiliated with or endorsed by Databricks.

## Named after

Cornelis Lely (1854–1929), the engineer who designed the Zuiderzee Works and, as minister,
got them built — the Afsluitdijk among them. The one who actually got big plans built.

## License

Apache-2.0 — see [LICENSE](https://github.com/kostavo-oss/tools/blob/main/packages/lely/LICENSE).

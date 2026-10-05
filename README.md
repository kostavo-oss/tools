# lely

**One plan for your whole Databricks deploy.**
The bundle and everything around it — the steps before, the steps after — reviewed before
anything runs, and taken down again when you say so.

lely replaces the script around `databricks bundle deploy`.

> **Terraform for your platform, Asset Bundles for your code, stevin for your data model —
> and lely to deploy them as one.**

> **Status: pre-alpha.** `plan`, `apply`, `destroy` and `status` are built, tested against a
> fake Databricks CLI, and have been run on a real workspace once, with one small bundle — see
> [what has been tried](#what-has-been-tried). That is a first proof, not a track record. [spec/](spec/README.md) says what each
> piece must do; [docs/DESIGN.md](docs/DESIGN.md) says how it is built.

## Why

A real deploy to Databricks is an Asset Bundle and the things around it: a model version
looked up and handed to the bundle, a job that has to run once the bundle is there, a seed, a
migration. The bundle has a plan and a deploy. The things around it have a shell script.

That script fails in four ways a team feels, and lely answers each:

- **Nobody sees the whole deploy before it runs** → one plan for every step.
- **What one step hands the next is invisible** → written down in the config, and checked.
- **Nothing is guarded the same way twice** → one rule for consent and for destructive changes.
- **It only goes one way** → `lely destroy`.

lely keeps no state. Whatever it needs to know, it asks the system it manages — for a bundle,
the Databricks CLI.

### When not to use it

- **One bundle and nothing around it.** `databricks bundle deploy` is all you need.
- **Every extra step is an opaque script.** lely gives it an order, checked inputs and one rule
  for consent, but a plan that reads "runs `deploy.sh`" shows a reviewer little.
- **You need an audit trail, drift detection, or cleanup of what you stopped declaring.** Those
  need state, and lely has none: remove a step from the config and what it deployed stays.
  Destroy first, then remove the step.
- **Your CI isn't GitHub Actions**, for now.

## Install

lely isn't on PyPI yet. From a checkout:

```sh
git clone https://github.com/kostavo-oss/lely && cd lely
uv sync
uv run lely --version
```

It needs the [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/install) with
the direct engine (GA in v1.3.0). `lely doctor` shows what it finds.

## Quickstart

One ordered list of steps, in `lely.yml` — or under `[tool.lely]` in `pyproject.toml`. The
bundle is one of them. What stands above it runs before the deploy, what stands below runs
after:

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
    uses: command
    with:
      apply: [./ops/backfill.sh, "${steps.app.resources.jobs.backfill.id}"]   # … and says what
```

A step takes a value from another step in one way only: `${steps.<name>.<output>}`, in its own
options, and only from a step above it. Reading a step's `with:` is enough to know everything
it depends on.

```sh
lely schema -o lely.schema.json  # for your editor: completes and checks `with:` as you type
lely validate                    # config, options, references — offline; prints the wiring
lely plan -t dev                 # the whole deploy as one plan; nothing is changed
lely plan -t dev -o plan.json    # … as a file, to review
lely apply plan.json             # run exactly what was reviewed
lely apply -t dev                # or: plan, show, ask, run
lely status -t dev               # what is deployed right now
lely destroy -t dev              # take it down again: plan, show, ask, run
```

For the editor, make `# yaml-language-server: $schema=lely.schema.json` the first line of
`lely.yml`. There is no default target: `-t` is always given. The workspace comes from `--profile`, or
from the variables the Databricks CLI already reads.

## The plan

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
Applied from a file, this stops before `notify`: a waiting step is planned once what it waits for exists.
```

Every step is **ready**, **waiting** or **skipped**. A waiting step takes something that
doesn't exist yet — here the id of a job this deploy creates — so nobody can know what it will
do, and the plan says that instead of guessing. `lely apply plan.json` stops there and asks for
a new plan, which shows the step ready: a first deploy through a reviewed file can take two
rounds, and every one after it takes one.

## What may run

- **Nothing runs unasked.** `apply` and `destroy` ask, or were given `--yes`. With no terminal
  and no `--yes` they refuse: a forgotten flag is a failed job, never an unreviewed deploy.
- **To destroy at a terminal, you type the target's name.** A saved destroy plan is run only by
  `lely destroy <file> -t <target>`.
- **Consent covers what was shown.** Each step is planned again right before it runs, and runs
  only if every change is one the approved plan showed. Fewer is fine; anything new stops the
  run.
- **Destructive changes need `--allow-destructive`.**
- **A plan file is held to what it was made for:** the workspace, the project and its steps as
  written, the values each step took, and a clean checkout of the same git tree.
- **No rollback.** The first failing step stops the run; running it again finishes it.
- **Exit codes:** 0 done · 1 something failed · 2 lely refused — plan again.

## Plugins

Every step is a plugin's. `lely steps` lists them, with their options, what they give, and
what they can do.

- **`bundle`** — an Asset Bundle: planned, deployed, listed and destroyed through the
  Databricks CLI. It gives the bundle's variables, its resources' names, and their ids and
  links once they exist.
- **`command`** — commands you give it: `apply`, and optionally `plan`, `destroy` and the
  `outputs` it gives. No shell, and no secrets in arguments.
- **`bundle.run`** — runs a job, pipeline or app from a bundle step.
- **Your own** — a class in a file in your repo (`uses: ./ops/steps.py:LatestModel`), or a
  package that registers one under the `lely.steps` entry point. `lely.testing` checks it
  against the same rules as the ones above.
- **`stevin`** — tables, planned by [stevin](https://github.com/kostavo-oss/stevin). Parked:
  it can plan, and can't apply yet.

Planning runs your project's own code — a plugin in the repo, a `command` step's plan command.
On a pull request, give `lely plan` credentials that can read and nothing more.

## What has been tried

lely is tested against a fake Databricks CLI, and has been run on a real workspace once
(2026-10-06, CLI v1.19.0): a bundle with one job, on a development target, was planned,
applied, listed, applied again, updated from a plan file, and destroyed. That run matched what
lely assumed about the CLI, with one correction and one surprise:

- **The CLI trusts the bundle with your credentials.** A bundle whose target names another
  host is not refused: with a token from the environment, the CLI goes to that host and
  presents the token. lely compares the two hosts and stops, but only after the CLI's first
  call. Know whose `databricks.yml` you run.
- **`bundle validate` writes.** It creates a folder in the workspace, so lely doesn't use it:
  `lely plan`, `status` and a destroy plan were seen to leave the workspace as it was.

What one run could not show:

1. That a bundle another identity deployed looks "not deployed" from here.
2. That every resource type has an id and a link in `bundle summary` — only a job was tried.
3. `bundle.run`: no job was run.
4. `lely plan` with credentials that can only read.
5. That `bundle destroy` never removes more than `bundle summary` lists.

`lely doctor` also can't tell whether credentials are read-only; it says so.

## Named after

Cornelis Lely (1854–1929), the engineer who designed the Zuiderzee Works and, as minister,
got them built — the Afsluitdijk among them. The one who actually got big plans built.

## Where it fits

lely is one of the [Kostavo tools](https://github.com/kostavo-oss) for Databricks. It is not
a fourth layer: it carries the layers out together. Terraform sets up the platform, an Asset
Bundle deploys the code, stevin changes the data model — and lely deploys them as one.

It borrows Terraform's words — plan, apply, destroy — because everyone knows what they promise.
The job is not the same: lely manages no resource itself and remembers nothing. It owns the
order, the review and the consent.

Community project, not affiliated with or endorsed by Databricks.

## Development

```sh
mise install     # pinned Python + uv
uv sync          # .venv with deps and dev tools
mise run check   # lint + format check + types + unit tests
```

## License

Apache-2.0 — see [LICENSE](LICENSE).

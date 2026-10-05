# 003 — config

**Status:** draft; the shape is decided. Phase one.

## Why

lely's whole job is to run what a project wrote down, so the file is the product's face. Two
things change it: it may live in `pyproject.toml`, and the bundle stops being a key of its own.

## Today

`lely.yml`, read from the working directory or from `--config`. Four keys at the top — `bundle`,
`pre`, `bundle_vars`, `post` — and four in a step: `name`, `uses`, `with`, `targets`. Unknown keys
are errors, with file, line and column.

## Requirements

- **R1 — One ordered list of steps.** `steps:` is the only key at the top. The bundle is one
  entry in it; what is written above it runs before the deploy, what is written below it runs
  after. *(owner, 2026-10-05)*

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

  A project with two bundles, or with none, is written the same way.

- **R2 — What a step takes from another is written in its own options,** as
  `${steps.<name>.<output>}`, and only steps above it can be named. The rules are
  [002/R14–R21](002-plugins.md). Reading a step's `with:` is enough to know everything it depends
  on. *(owner)*
- **R3 — A step has a name, the plugin it uses, its options, and optionally the targets it runs
  for.** Names are unique in a project: they are what a reference says. *(built)*
- **R4 — `lely.yml`,** as today. *(built)*
- **R5 — Or `[tool.lely]` in `pyproject.toml`,** with the same keys and the same meaning, so a
  Python project needs no extra file. *(owner)*

  ```toml
  [[tool.lely.steps]]
  name = "app"
  uses = "bundle"
  with = { path = ".", vars = { model_version = "${steps.model.version}" } }
  ```

- **R6 — One of the two, not both.** With both present lely stops and names the two files; it
  does not merge them and does not pick. *(proposed)*
- **R7 — Everything is checked offline by `lely validate`:** unknown keys, options against the
  plugin's, and every reference ([002/R18](002-plugins.md)). Errors point at the file, line and
  column, in either format. *(built for `lely.yml`)*
- **R8 — `lely validate` prints the wiring:** for each step, what it takes and from where, and
  what it gives ([002/R20](002-plugins.md)). For the project above:

  ```
  model     gives  version (at plan)
  app       takes  model_version ← model.version
            gives  var.*, resources.*.name (at plan) · resources.*.id, .url (after apply)
  backfill  takes  ← app.resources.jobs.backfill.id
  ```

  *(proposed)*
- **R9 — A schema for editors,** built from the plugins' own options and outputs, so a step's
  `with:` is completed and checked while it is typed. *(design; not built)*

## Decided

- **The shape** (was D1): one ordered list — R1. `pre:`, `post:`, `bundle:` and `bundle_vars:`
  go. Nothing is published, so there is no file to migrate. *(owner, 2026-10-05)*

## To decide

- **D2 — Where the file is looked for.** Today: the working directory only. stevin walks up from
  the working directory to find its project file. Same here? *(proposed: yes, for both formats)*

## Done when

- A project written in `lely.yml` and the same project written in `pyproject.toml` give the same
  plan, byte for byte.
- `lely validate` reports the same mistakes, with a position, in both.
- The README's quickstart is written as R1.

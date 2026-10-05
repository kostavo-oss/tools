# 003 — config

**Status:** draft. Phase one.

## Why

lely's whole job is to run what a project wrote down, so the file is the product's face. Two
things change it: it may live in `pyproject.toml`, and the bundle stops being a key of its own.

## Today

`lely.yml`, read from the working directory or from `--config`. Four keys at the top — `bundle`,
`pre`, `bundle_vars`, `post` — and four in a step: `name`, `uses`, `with`, `targets`. Unknown keys
are errors, with file, line and column.

## Requirements

- **R1 — `lely.yml`,** as today. *(built)*
- **R2 — Or `[tool.lely]` in `pyproject.toml`,** with the same keys and the same meaning. A
  Python project then needs no extra file. *(owner)*
- **R3 — One of the two, not both.** With both present lely stops and names the two files; it
  does not merge them and does not pick. *(proposed)*
- **R4 — The bundle is written as a step.** → [D1](#to-decide) for the shape. *(owner)*
- **R5 — A step has a name, the plugin it uses, its options, and optionally the targets it runs
  for.** *(built)*
- **R6 — Everything is checked offline by `lely validate`:** unknown keys, options against the
  plugin's, every reference in its position — and that a step only refers to steps before it.
  Errors point at the file, line and column, in either format. *(built for `lely.yml`)*
- **R7 — A schema for editors,** built from the plugins' own options, so a step's `with:` is
  completed and checked while it is typed. *(design; not built)*

## To decide

- **D1 — The shape, now that the bundle is a step.**

  *One ordered list* — "pre" and "post" are simply before and after the bundle:

  ```yaml
  steps:
    - name: model
      uses: ./ops/steps.py:LatestModel
      with: {model: main.ml.churn, alias: candidate}
    - name: app
      uses: bundle
      with:
        path: .
        vars: {model_version: "${steps.model.version}"}
    - name: tables
      uses: stevin
    - name: backfill
      uses: bundle.run
      with: {resource: jobs.backfill}
  ```

  *Or today's three parts,* where `bundle:` stays as a short way to write that one step:

  ```yaml
  pre:
    - name: model
      uses: ./ops/steps.py:LatestModel
      with: {model: main.ml.churn, alias: candidate}
  bundle: .
  bundle_vars: {model_version: "${steps.model.version}"}
  post:
    - name: tables
      uses: stevin
    - name: backfill
      uses: bundle.run
      with: {resource: jobs.backfill}
  ```

  The list is what "the bundle is just a plugin" means taken literally: a project with two
  bundles, or with none, is written the same way, and there is one thing to learn. The three
  parts read more like a deploy, and they are what is built. *(proposed: the list. Nothing is
  published, so there is nobody to migrate.)*

- **D2 — Where the file is looked for.** Today: the working directory only. stevin walks up from
  the working directory to find its project file. Same here? *(proposed: yes, for both formats)*

## Done when

- A project written in `lely.yml` and the same project written in `pyproject.toml` give the same
  plan, byte for byte.
- `lely validate` reports the same mistakes, with a position, in both.
- The README's quickstart uses the shape D1 settles on.

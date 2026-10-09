# 003 — config

**Status:** built, 2026-10-05 — see [As built](#as-built). Phase one.

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
  for.** Names are unique in a project: they are what a reference says. `targets:` is a list of
  names compared with `-t` as written; for any other target the step is skipped — in a plan, an
  apply, a destroy and `status` alike — and each says that it was. *(built for plan; the rest
  follows)*
- **R4 — `lely.yml`,** as today. *(built)*
- **R5 — Or `[tool.lely]` in `pyproject.toml`,** with the same keys and the same meaning, so a
  Python project needs no extra file. *(owner)*

  ```toml
  [[tool.lely.steps]]
  name = "app"
  uses = "bundle"
  with = { path = ".", vars = { model_version = "${steps.model.version}" } }
  ```

- **R5a — It is found from a subfolder.** lely walks up from the working directory until it
  finds a `lely.yml`, or a `pyproject.toml` with a `[tool.lely]` section; `--config` names one
  outright. A step's paths are relative to that file, not to where the command was run.
  *(owner, 2026-10-05; the last sentence is today's behaviour)*
- **R6 — One of the two, not both.** With both present lely stops and names the two files; it
  does not merge them and does not pick. *(agreed)*
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

  *(agreed)*
- **R9 — A schema for editors,** built from the plugins' own options and outputs, so a step's
  `with:` is completed and checked while it is typed. *(design; not built)*

## Decided

- **The shape** (was D1): one ordered list — R1. `pre:`, `post:`, `bundle:` and `bundle_vars:`
  go. Nothing is published, so there is no file to migrate. *(owner, 2026-10-05)*
- **Where the file is looked for** (was D2): upwards from the working directory — R5a.
  *(owner, 2026-10-05)*

## As built

2026-10-05.

- **R9, the editors' schema, is `lely schema`.** It prints a JSON Schema (draft-07) built from
  the plugins installed and the ones the project names: each plugin's options, with the words
  its author wrote above them, and what a step of it gives. An editor is pointed at it with a
  first line in `lely.yml`: `# yaml-language-server: $schema=lely.schema.json`. It says what
  `validate` says about a config's *shape*; that a reference names a step that exists, stands
  above and gives that output stays `validate`'s to check — a schema can't see one step from
  another. It is tested with a JSON Schema validator and against what lely itself accepts and
  refuses, **not in an editor**. Where the two could differ it errs towards letting a value
  through: a plugin the schema doesn't know, a boolean spelled `yes`. It covers `lely.yml`; a `[tool.lely]` section has no schema of
  its own, because a `pyproject.toml` has one schema and it isn't lely's to replace.
- **Positions in `pyproject.toml` (R7) are found again, not kept.** Python's TOML reader keeps
  no line numbers, so each key is looked up in the text in the order it was read. That is
  exact for a file written the usual way; in an unusual one a position can point at the right
  step and the wrong line.
- **R6 holds per folder.** Walking up, the first folder with a `lely.yml` or a `[tool.lely]`
  wins, and one with both is the error. `--config` names a file outright and is not checked
  against its neighbour.
- **The wiring (R8) prints what a plugin declares**, one line per "when": for a bundle,
  `resources.<type>.<key>.id (once it exists)` rather than the shorter `resources.*.id` of the
  example above.
- **"Made from" (done when) is a hash per step** of its plugin, its targets and its options as
  written. A project in `lely.yml` and the same project in `pyproject.toml` give the same plan,
  and a test holds them to it.

## Done when

- A project written in `lely.yml` and the same project written in `pyproject.toml` give the same
  plan: the same steps, changes and outputs, and the same "made from"
  ([005/R5](005-plan-apply-destroy.md)), so a plan made from one is accepted with the other.
- `lely validate` reports the same mistakes, with a position, in both.
- The README's quickstart is written as R1.

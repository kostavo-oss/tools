# The config

One ordered list of steps, in `lely.yml` — or under `[tool.lely]` in `pyproject.toml`. lely
looks for either from the current directory upwards; `-c` names one.

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

  - name: warm
    uses: command
    targets: [prod]              # only for this target; skipped, visibly, for any other
    with: {apply: [./ops/warm.sh]}
```

## A step

| Key | |
| --- | --- |
| `uses` | The plugin that does the step: a built-in (`bundle`, `command`, `bundle.run`), a class in the repo (`./path/file.py:Class`), or one in an installed package. Required. |
| `name` | What other steps call it. A plain plugin name doubles as one (`uses: bundle` is named `bundle`); a class needs a name of its own. |
| `with` | The step's options: whatever its plugin declares. `lely steps` lists them. |
| `targets` | The targets the step runs for, compared with `-t` as written. Without it, every target. |

The order is the order they run. A destroy runs it from the bottom up.

## What a step takes from another

One way only: **`${steps.<name>.<output>}`**, in the step's own `with:`, and only from a step
**above** it. Reading a step's `with:` is enough to know everything it depends on.

`lely validate` checks every reference offline: the step exists, stands above, runs for the
same targets, and gives that output. It prints the wiring — what each step takes and gives,
and when each output is known:

- **at plan** — known as soon as the step is planned;
- **once it exists** — known after the first deploy that creates it, like a job's id;
- **after every run** — known only when the step has run, every time.

A step that takes something not known yet is **waiting**: the plan says so, and the step is
planned when the run gets there.

A step can also name a whole step, where its plugin asks for one — `bundle.run` runs a
resource *of a bundle step*:

```yaml
  - name: run-backfill
    uses: bundle.run
    with: {bundle: app, resource: jobs.backfill}
```

## Values from the environment

`${env.NAME}` is the other reference. It is **always a secret**: shown as `***`, never
written to a plan file, a comment or a page, and fetched again when the step is planned at
apply. It may go where a plugin takes a secret — a `command` step's `env:`, for one — and
never into a command's arguments, which every process on the machine can see.

```yaml
  - name: seed
    uses: command
    with:
      apply: [./ops/seed.sh]
      env:
        SEED_TOKEN: ${env.SEED_TOKEN}
```

## A literal `${…}`

`${` always starts a reference. To hand a step the characters themselves — a shell's own
variable in a command — double the dollar: **`$${…}` is written out as `${…}`** and is no
reference.

```yaml
  - name: report
    uses: command
    with:
      apply: [sh, -c, 'echo "$${HOME}" > where.txt']     # the shell reads ${HOME}
```

A `${…}` that is no reference is an error, and the error says how to write it either way: as
a literal, or — where a step above gives something of that name, as a bundle's `${var.x}`
would be — as `${steps.<that step>.var.x}`.

## In `pyproject.toml`

The same list, as TOML:

```toml
[[tool.lely.steps]]
name = "model"
uses = "./ops/steps.py:LatestModel"
with = { model = "main.ml.churn" }

[[tool.lely.steps]]
name = "app"
uses = "bundle"
with = { vars = { model_version = "${steps.model.version}" } }
```

## What lely does not have

- **No default target.** `-t` is always given, and each plugin reads it its own way — for the
  bundle it is the bundle's target.
- **No state.** Remove a step from the config and what it deployed stays; destroy first, then
  remove the step.
- **No variables of its own, no includes, no conditions** beyond `targets:`. What differs per
  target belongs in the bundle, or in a step's own options.

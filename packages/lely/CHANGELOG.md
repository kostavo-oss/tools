# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **The `stevin` step waits for the bundle's schema, where the plan failed.** A table
  whose schema the bundle declares cannot be planned before the bundle has deployed
  that schema. On a target that was never deployed, `lely plan` stopped at the
  `stevin` step with stevin's refusal, and a new repository's first pull request got
  no plan. The step is now *waiting*: the plan succeeds, shows the bundle, and says
  why the tables wait. `lely apply -t <target>` deploys the bundle, then plans the
  tables, shows them and asks. `lely apply plan.json` stops at the tables with 2, and
  the next plan shows them. The same happens when the bundle later gets a new schema
  with tables in it. Any other failure of `stevin plan` fails the plan as before. Put
  the `stevin` step below the `bundle` step: lely does not check that.
- **The `stevin` step needs stevin 0.4.0a3 or newer**, where it needed 0.4.0a2. It is
  the first stevin whose `plan` says with an exit code that the bundle has not
  deployed a schema yet. A plan file an older stevin wrote fails the plan and names
  both versions. Before the schema is there an older stevin writes no file: the plan
  fails with stevin's own message, as it did.
- **A step that still waits when a run reaches it is no longer told to plan again.**
  The refusal says that no step above brought about what it waits for. A step `--from`
  passes over that could not be planned in full says so, where it said "planned".

### Added

- **The docs say how a plugin makes its step wait**: `plan` answers a `StepPlan` whose
  `waiting` says why. lely holds such a step as it holds one that waits for an output.
  The field was there; what a run does with it was not written down.

## [0.4.0] - 2026-10-11

### Added

- **The `stevin` step applies.** `lely apply` hands stevin the plan file that was
  approved, not a new one, and passes `--allow-destructive` on only when it was given. A
  plan stevin refuses as stale ends the run with 2 and says to plan again. `lely status`
  lists the tables stevin's specs describe. `lely destroy` leaves them alone and says so:
  a dropped table is its rows. It has not run on a workspace yet.
- **The `stevin` step needs stevin 0.4.0a2 or newer.** It reads stevin's exit codes to
  tell a refusal from a failure, and no longer stevin's words. `lely status` asks
  `stevin list`, so it makes no plan. A plan from an older stevin fails and names both
  versions.
- **A plugin can run what was reviewed.** In `apply`, `ctx.approved` is the step's plan
  as it was approved, payload and all. A plugin without a destroy can say why in
  `nothing_to_destroy`.

- **`lely.testing` has `check_no_state` and `check_only_its_own`**, for the rules it
  had no check for: no state, only what its options name, only its own. Every check takes the plugin's class too, and then makes each
  call on a new instance, as lely does; `check` on a step's own command line does so.
  The docs say what the kit cannot see: a write through the SDK or by another program.
- **A step on its own shows what it gives.** `plan` prints the outputs it knows and names
  the ones that come later; `apply` prints what the step returned. A `Secret` is `***`.
- **A step on its own can plan its destroy**: `plan --destroy -o gone.json`, then
  `destroy --plan-file gone.json`.

### Changed

- **`check --live` says what it is about to do before it does it**: apply and destroy, on
  which target and workspace, and as whom. Without `--live`, `check` no longer speaks of
  a destroy for a step that has none.
- **A flag takes `$${` for a literal `${`**, as a config file does. It was refused as a
  reference.
- **`lely doctor` is no longer meant to say whether credentials are read-only.** It
  never could. It says whether the identity is a workspace admin, and that it cannot
  tell what the credentials may change. For an admin it said "these credentials can
  change anything", which nobody had checked: that claim is gone.
- **A plan made from `lely.yml` is accepted with the same project in `pyproject.toml`,
  whatever the spelling.** What a step is made from is now each option as its plugin is
  handed it: `1.10` and `yes` in YAML are `1.10` and `true` in TOML for a number or a
  yes or no, and `"1.10"` and `"yes"` for text. A plan file saved by 0.3.1 for a step
  with a number or a boolean in its options is refused once by the next release: the
  refusal names both versions and says to plan again.

- **A secret written out is not in what the plan file keeps of a step's options.** A
  `Secret` option given in the config, or as a flag of a step on its own, was part of
  the hash the plan file keeps of each step. Its text is left out now, and so is text
  written beside a reference in such an option. lely no longer notices that either
  changed between plan and apply; it never did for a value from the environment.
- **An output that holds what a `Secret` option was given is a secret**, also when the
  step gives it as plain text. It was in the plan file and in `-f json` as it came. It is
  `***` and a marker now, and a step below can take it only into a `Secret` option, and
  whole: no field of it.
- **The order of a mapping's entries counts.** A plugin is handed them in the order
  written, so a plan file is refused when they were moved since.
- **A plan file saved by 0.3.1 is refused once** in three cases, and says to plan again.
  A step has a `Secret` option that holds written-out text. A step has a mapping whose
  keys are not in sorted order, capitals first. Or a step takes an output that is a
  secret now and was text in the file: that one is refused when the run reaches the
  step, after the steps above it have run.
- **A refusal for a value that is a secret on one side says neither value.** It printed
  the one that was not a secret.

- **A stevin plan shows every step with its risk class**, and a table that is rewritten
  says so in its own line. A risk class lely does not know is destructive; it was read as
  an update.

- **The README is short, and how to use lely is in the docs only.** The docs' design
  page is now "How it works" and says what the code does today. The `spec/` folder is
  gone: what must be true of lely is in `RULES.md`, and why in `DECISIONS.md`.

### Fixed

- **A flag for `Mapping[str, int]`** (or a decimal number, or true and false) reads the
  value of `key=value` as that type. Such a step started, and then refused every value.
- **A value from the environment is refused wherever it is no `Secret`**: in an option
  that takes anything (`object`), which took the secret into the plan, and as a list or
  a mapping given whole, which `lely validate` let through and the plan then refused.
- **A list or a mapping given whole by one reference is read by element.** A
  `tuple[Secret, ...]` got plain text and a `tuple[int, ...]` got whatever came. Each
  element is now what the option declares, or an error.
- **The editors' schema takes a list or a mapping given whole by one reference**, as
  `lely validate` does: `tags: ${steps.model.tags}` is no longer marked as a mistake.
  Write the schema again with `lely schema -o lely.schema.json`.

## [0.3.1] - 2026-10-10

Nothing lely plans or applies has changed. This is the first release from its new home.

### Changed

- **lely lives in `kostavo-oss/tools`**, one repository for the four Kostavo tools. The
  package, its name on PyPI and its command are what they were. The links on PyPI point
  at the new place, and the docs are at `kostavo-oss.github.io/tools/lely/`. From this
  release on a tag is `lely-v<version>`.
- **The README says what lely will not do and when you no longer need it**: the day a
  bundle plans its own before-and-after steps.
- **The page has the look of the other Kostavo pages, and they have its.** The colours and
  what they mean, the type, a table, a badge and a block of code are now one style sheet
  that caland's page and stevin's use too; lely's page was the reference, so it reads as
  it did. Three things differ: a column's heading is a little less heavy, a `pre` or a
  `kbd` in a plugin's view is drawn as the page's own, and what the keyboard is on has a
  blue ring. The page is still one file with its style sheet inline, no script, and
  nothing fetched.

## [0.3.0] - 2026-10-08

A breaking release: the `command` plugin is gone, and a step runs on its own.

### Added

- **A step on its own** (`spec/011`). A step that inherits `lely.step.Step` and ends with
  `Step.main()` is a command of its own: `plan`, `apply`, `destroy`, `status` and `check`,
  its options as flags, with no `lely.yml`. A plan it writes is a one-step lely plan:
  `lely apply plan.json` takes it, and the same checks are made before anything runs.
  `check` holds the step to the rules from the command line; `--live` applies and destroys
  on the target.
- **`Program`**: a program as a step, in ten lines — one `run` every apply, destructive if
  it says so, outputs from the JSON on its last line. What `command` did, under the rules.

### Removed

- **`command`**: a program is a `Program` (ten lines, see Writing a step); a config that
  names `command` is told by `lely validate` that no plugin of that name is installed.
  → [011](https://github.com/kostavo-oss/tools/blob/main/packages/lely/spec/011-a-step-on-its-own.md)

## [0.2.0] - 2026-10-07

### Added

- **`$${…}` writes a literal `${…}`.** `apply: [sh, -c, 'echo $${HOME}']` hands the shell
  `${HOME}`; before, there was no way to write one. The error for a `${…}` that is no
  reference says so, and names a step only when one above gives a value of that name.

### Changed

- **What a step's program says is shown while it runs.** `bundle deploy`, `bundle destroy`,
  `bundle run` and a `command` step's apply and destroy commands are passed on a line at a
  time, as they come, on stderr — what they write to stdout and to stderr. Before, a deploy
  or a long job run was silent until it ended, and a warning from a program that succeeded
  was never shown.
- **The source package holds the code, its tests and the files that say what it is.** It
  also carried the docs site, the specs, the workflows and the lock file, and was five times
  the wheel's size. The wheel is as it was.

### Removed

- `lely.step.StderrLog` and `lely.planfile.outputs_json`: nothing used them.

### Fixed

- **A program that fails is quoted on both of its streams**, each under its name. One that
  gave its reason on stdout and a notice on stderr was quoted for the notice alone.
- **The README's quickstart can be followed**: it shows the plugin file its config names. A
  test checks every whole config in the README and the docs the way `lely validate` does.
- **`lely doctor` looks for git**, as the docs said it did: git missing or refusing the
  checkout, in a repository, is a failed check — `lely plan` fails there. It compares the
  Databricks CLI's version with v1.3.0 and says when it is older, and says what bundles
  need only to a project with a step that runs the CLI.
- **`lely doctor` doesn't fail for a Databricks CLI no step runs.** In a project of
  commands a missing CLI is said, and is no failed check.
- **Why a run's record couldn't be written is shown, not obeyed**: the error's own words
  went into the line as markup.
- **`lely doctor` says a plugin that fails in one line**, with the step and the plugin, and
  checks the rest. A plugin whose `programs` raised ended it in a traceback.
- **A traceback never shows local values.** With a typer below 0.23, an error lely didn't
  expect printed every frame's locals, and the frames of `plan` and `apply` hold the run's
  token and the environment.
- **`lely apply` with neither a plan file nor `-t` is refused at once**, with 2. It reached
  the workspace first, so without credentials it failed with 1 instead.
- **Every `--help` names `[tool.lely]` again.** It read "a pyproject.toml with . Found from
  here up": the brackets were taken for markup. So did what `lely schema -o` says of a
  `pyproject.toml`.
- **lely asks for a typer it works with**: `typer>=0.17.5`, where 0.1.0 said `>=0.12`. With
  an older one every `--help` could end in a traceback, or a command given no `-t` could run
  without one. CI now runs the tests on the oldest version of every dependency.

## [0.1.0] - 2026-10-07

The first release, as alpha: this is what is built.

### Added

- **One plan for a whole deploy.** `lely.yml`, or `[tool.lely]` in `pyproject.toml`, lists
  steps in the order they run; each is done by a plugin. A step takes what a step above it
  gives (`${steps.<name>.<output>}`) and values from the environment (`${env.NAME}`, always a
  secret). `lely validate` checks all of it offline and prints the wiring.
- **`lely plan`** plans every step and changes nothing. Each step is ready, waiting — it
  takes something that doesn't exist yet — or skipped, and the plan says which and why.
  `--destroy` plans a teardown, from the bottom up.
- **`lely apply` and `lely destroy`** run a plan: a reviewed file (`lely plan -o plan.json`),
  or planned on the spot with `-t`. Nothing runs unasked — a terminal to answer at, or
  `--yes` — and a destructive change needs `--allow-destructive`. Every step is planned
  again right before it runs, and may do nothing the approved plan didn't show.
- **A plan file is held to what it was made for**: the workspace, the steps as written, and
  the git tree of a clean checkout. It keeps no secret.
- **`lely status`** lists what exists because of each step, with links; `lely show` shows a
  saved plan; `lely doctor` says which tools and which workspace lely finds.
- **Plugins.** `bundle` deploys a Databricks Asset Bundle with the Databricks CLI's direct
  engine; `command` runs commands you give it, with an optional plan and destroy command;
  `bundle.run` runs a job or pipeline of a bundle step. A class in the repo
  (`./ops/steps.py:Class`) or in an installed package is a plugin too. `lely steps` lists
  them, `lely schema` writes a JSON Schema of the config for editors, and `lely.testing`
  holds a plugin to the contract.
- **GitHub.** With `--github`, in a GitHub Actions run, the plan is one comment on the pull
  request, kept current, and the run's page says what was planned or done. `-f md` prints
  the same Markdown. `docs/GITHUB.md` has workflows to copy.
- **A page.** `lely ui plan.json` makes one HTML file of a plan — or of a run's record,
  written by `apply -o` and `destroy -o` — with nothing to fetch and nothing that runs. A
  plugin can give its plan a view of its own; the bundle shows every resource by type.

### Known limits

- Tried on a real workspace and on GitHub a few times, with small bundles: a first proof,
  not a track record. `README.md`, "What has been tried", says what was and wasn't.
- The `stevin` plugin plans and can't apply yet.

# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

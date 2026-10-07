# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **What a step's program says is shown while it runs.** `bundle deploy`, `bundle destroy`,
  `bundle run` and a `command` step's apply and destroy commands are passed on a line at a
  time, as they come, on stderr — what they write to stdout and to stderr. Before, a deploy
  or a long job run was silent until it ended, and a warning from a program that succeeded
  was never shown.

### Fixed

- **A program that fails is quoted on both of its streams**, each under its name. One that
  gave its reason on stdout and a notice on stderr was quoted for the notice alone.
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

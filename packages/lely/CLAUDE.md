# CLAUDE.md

`lely`: one plan for a whole Databricks deploy. It plans, applies and destroys an ordered
list of steps, each done by a plugin, and keeps no state. The Asset Bundle is one of
those plugins.

## Where a fact lives

One place per fact. Write a fact where it lives, and link to it from anywhere else.

| The fact | Its one place |
|---|---|
| What lely is for, when not to use it, when it is no longer needed | `README.md` |
| What must be true of the code | `RULES.md`: numbered rules, each with the tests that hold it |
| Why it is so, and what was tried or left behind | `DECISIONS.md`: a log, appended to and never edited |
| What ran on a real workspace and on GitHub, and what did not | `docs/tried.md` |
| How to use it, and how it works inside | `docs/`, and only there: the README has a quickstart and links |
| What changed for a user, per release | `CHANGELOG.md` |
| What the Databricks CLI or GitHub does that the code leans on | the docstring of the code that leans on it (`src/lely/steps/bundle.py`, `src/lely/github.py`) |
| An idea that is wanted and not built | a GitHub issue |
| How it came to be | git |

There is no `spec/` folder, and none comes back.

## Rules of working

- **A change to behaviour changes its rule, in the same pull request.** Find the rule in
  `RULES.md`, change it or add one with the next number of its area, and name the tests
  that hold it under `Held by:`. Each of those tests cites the identifier. A number is
  never reused. `tests/test_rules.py` at the root of the repository fails when a
  citation, a rule and a test disagree.
- **A rule is checked against the code before it is written, and states the whole
  promise.** What the code does not keep yet gets an issue, and the rule says
  `Not kept yet:` with its number.
- **A decision goes into `DECISIONS.md` only with its reason**, or with the alternative
  that was rejected. No entry is edited: a new one names the one it supersedes.
- **A run on a workspace or on GitHub is recorded in `docs/tried.md`**, with its date,
  and nothing under "Not yet" there is written about as if it had run.
- The core does no I/O of its own: I/O is at the edges (the table in
  `docs/how-it-works.md`). No module outside `src/lely/steps/` imports a plugin (PLG-1).
- The bundle is the Databricks CLI's: the plugin asks it and never works out what it
  resolves, and never calls `bundle validate` (BDL-2). If a bundle resource can manage
  something, no plugin does.
- Nothing that changes a workspace runs unasked (ASK-1). A refusal is a `Refused`, exit
  2; a failure is any other `LelyError`, exit 1 (CLI-1).
- A plan holds no secret (SEC-1), and what a plan says is shown, never obeyed (SEC-3,
  GH-8, PAGE-9). `show` and `ui` load no plugin (PLAN-9, PAGE-4).
- A new place that prints goes through `cli._hide`, and a new place that shows a plan
  through `cli._holds_no_token` (GH-7). A file is written with `cli._write` (CLI-7).
- No raw invisible character in any file: write its escape (PKG-2).
- Every assumption about what Databricks or GitHub does gets a test, and a link to the
  docs in its docstring. If unsure, say so and add a `TODO(verify)`: do not guess.
- The `stevin` plugin runs the `stevin` command and imports nothing of stevin. It applies
  the plan file that was approved (STV-4) and drops nothing (STV-10). What it assumes of
  stevin's command line is numbered S1 to S10 in `tests/fake_stevin.py`; it has not run on
  a workspace. It needs stevin 0.4.0a3 or newer (STV-14). It waits, and does not fail,
  when `stevin plan` exits 5: the bundle has not deployed a schema yet (STV-16).
- `render/base.css` is in three packages, byte for byte (PKG-4): change all three in one
  pull request. After a change to `render/html.py`, run `uv run pytest tests/browser`
  and remake the pictures in `docs/assets/` when the page looks different.
- Some files decide what may run, or handle what is not trusted: `approval.py`,
  `running.py`, `source.py`, `planfile.py`, `cli.py`, `github.py` and the renderers. A
  change there is reviewed by someone who did not write it before the pull request is
  opened.
- A link out of `docs/` goes to the repository by its full address: the site has only
  what is in `docs/`. The README is the PyPI page: every link in it is absolute.
- Small pull-request-sized commits, conventional commit messages. A change to `version`
  in `pyproject.toml`, merged to `main`, publishes to PyPI: a release is a pull request
  of its own, opened when the owner says.

## Layout

```
src/lely/config.py, refs.py, options.py    the config, references, a step's options (CFG, REF)
src/lely/registry.py, step.py, model.py    finding a plugin, the contract, what lely talks in (PLG, PROG)
src/lely/planning.py                       check and plan, and the Session that walks the list (PLAN, WAIT)
src/lely/approval.py, running.py           what may run; apply, destroy, status (APL, DST)
src/lely/planfile.py, source.py            the plan file, and the git tree it is held to (PLAN)
src/lely/cli.py                            the commands, consent, exit codes, writing files (ASK, CLI)
src/lely/solo.py, flags.py                 a step on its own (SOLO)
src/lely/steps/                            the plugins lely ships (BDL, BRUN, STV)
src/lely/render/                           the terminal, Markdown, the page (SEC, PAGE, GH)
src/lely/github.py                         the comment and the run's page (GH)
src/lely/testing.py                        the contract as checks a test can run (PLG-9)
src/lely/databricks.py, process.py         the Databricks CLI, any other program
tests/unit/test_<module>.py                the tests of that module
tests/fake_*.py, tests/project.py          the stand-ins, and the scenario most tests share
tests/fixtures/                            the CLI's own recorded outputs, and stevin's plan files
tests/browser/                             a plugin's view, as Chrome reads it
docs/                                      the pages of the site, listed in mkdocs.yml
```

The recorded plans in `tests/fixtures/stevin-*.json` carry `deltaplan.managed`: that is
the property stevin writes onto tables, and it kept its name on purpose.

## Commands

uv, ruff and ty, as in every package of this repository. Never pip, black or mypy.

```sh
uv sync                              # once, anywhere in the repository
uv run pytest tests/unit             # from packages/lely: its tests
uv run pytest tests/browser          # from packages/lely: needs Chrome, skips without it
uv run ty check                      # from packages/lely: its types
uv run ruff check . && uv run ruff format --check .   # from the root: every package
uv run pytest tests                  # from the root: the rules file, and what holds across packages
uv run --group docs mkdocs build --strict             # from the root: the site
```

`mise run check` at the root runs the gate for every package. `ruff format` also
formats the Python in Markdown code blocks. A pipe hides a failing test: read the exit
code of the test run, not of `tail`.

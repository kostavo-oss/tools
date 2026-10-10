# CLAUDE.md

`leeghwater`: a package a dlt project imports, to run its pipelines the same way on a
laptop and in a Databricks job. A command line for the project, dlt's secrets from
Databricks secret scopes, and what Databricks needs before dlt can be imported.

## Where a fact lives

One place per fact. Write a fact where it lives, and link to it from anywhere else.

| The fact | Its one place |
|---|---|
| What leeghwater is for, when not to use it, when it is no longer needed | `README.md` |
| What must be true of the code | `RULES.md`: numbered rules, each with the tests that hold it |
| Why it is so, and what it replaced | `DECISIONS.md`: a log, appended to and never edited |
| What ran on a real workspace, and what did not | `docs/tried.md` |
| How a project uses it | `docs/`, and the README in short |
| What changed for a user, per release | `CHANGELOG.md` |
| What dlt or Databricks does that the code leans on | the docstring of the code or the test that leans on it |
| An idea that is wanted and not built | a GitHub issue |
| How it came to be | git |

There is no `spec/` folder, and none comes back.

## Rules of working

- **A change to behaviour changes its rule, in the same pull request.** Find the rule in
  `RULES.md`, change it or add one with the next number of its area, and name the tests
  that hold it under `Held by:`. Each of those tests cites the identifier in its
  docstring. A number is never reused. `tests/test_rules.py` at the root of the
  repository fails when a citation, a rule and a test disagree.
- **A rule is checked against the code before it is written.** What the code does not
  keep is a bug to report or not a rule; it is not written down as if it held.
- **A decision is appended to `DECISIONS.md`, with its date and its reason.** No entry is
  edited: a new one names the one it supersedes. Where the reason is not known, the
  entry says "reason not recorded".
- **Nothing under "Not yet" in `docs/tried.md` is written about as if it had run.** A
  run on a workspace is recorded there, with its date, and nowhere else.
- dlt stays dlt: patch nothing in it (DLT-1). A call into dlt beyond its documented API
  goes in `src/leeghwater/_dlt.py`, with a test in `tests/test_dlt.py` (DLT-2).
- Examples and docs make a pipeline with `leeghwater.create_pipeline` and run it with
  `leeghwater.run`, never with `dlt.pipeline()` or `pipeline.run()` (RUN-8).
- No secret's value is printed, logged, written to a file or put in the environment
  (SEC-9). A test that reads a secret looks for its value in what was printed.
- Every assumption about what Databricks or dlt does gets a test, and a link to the docs
  or the source in its docstring. If unsure, say so and add a `TODO(verify)`: do not
  guess.
- It is installed on compute it does not own: few dependencies, low lower bounds, one
  upper bound (DLT-3).
- Small pull-request-sized commits, conventional commit messages. A release is a pull
  request of its own, opened when the owner says.

## Layout

```
src/leeghwater/__init__.py   what a project imports; importing it does not import dlt
src/leeghwater/_app.py       App and @pipeline: the command line (APP)
src/leeghwater/_pipeline.py  create_pipeline and run (RUN)
src/leeghwater/_report.py    the report of a load (RUN-6)
src/leeghwater/_prepare.py   prepare() and the Setup it returns (PRE, DST)
src/leeghwater/_where.py     on a laptop or on Databricks (DBX-1)
src/leeghwater/_hook.py      the name `dlt` on Databricks (DBX-2 to DBX-4)
src/leeghwater/secrets.py    the providers for secret scopes (SEC); imports dlt
src/leeghwater/keyvault.py   the provider for an Azure Key Vault (SEC-13 to SEC-15); imports dlt
src/leeghwater/_dlt.py       every call into dlt beyond its documented API (DLT-2); imports dlt
tests/test_<module>.py       the tests of that module
tests/conftest.py            a clean process for every test, and a stand-in workspace
tests/my_ingest/             a small project that uses leeghwater
tests/my_ingest_odd/         pipelines that go wrong, each in its own way
docs/                        the pages of the site, listed in mkdocs.yml
```

## Commands

uv and ruff, as in every package of this repository. Never pip, black or mypy.

```sh
uv sync                          # once, anywhere in the repository
uv run pytest                    # from packages/leeghwater: its tests
uv run ty check                  # from packages/leeghwater: its types
uv run ruff check . && uv run ruff format --check .   # from the root: every package
uv run pytest tests              # from the root: the rules file, and what holds across packages
uv run --group docs mkdocs build --strict             # from the root: the site
```

`mise run check` at the root runs the gate for every package. `ruff format` also formats
the Python in Markdown code blocks.

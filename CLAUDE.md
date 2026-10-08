# CLAUDE.md

`leeghwater`: a package a dlt project imports, to run its pipelines the same way on a laptop
and in a Databricks job. A command line for the project, dlt's secrets from Databricks secret
scopes, and what Databricks needs before dlt can be imported.

**Phase one is built:** the runner, what it does on Databricks, and the secrets. The scaffold
(phase two) was built and then moved to a bundle template, a repository of its own; the
skills (phase three) are not built. `spec/` says *what* each piece must deliver and
when it is done; read `spec/README.md` first. It also says who decided what — the owner, or
the writer on the owner's "you decide" — and what was run on a real workspace on 2026-10-07
and what could not be. Don't write as if something under "To verify" in `spec/002` had been
run.

## Rules

Each is from the spec, and as open as the requirement it comes from.

- dlt stays dlt: go through what dlt offers (a registered provider, the config it reads from
  the environment, the arguments of `dlt.pipeline`) and patch nothing in it. `spec/000`, R8.
- A project's pipeline calls `leeghwater.create_pipeline` and `leeghwater.run`, never
  `dlt.pipeline()` or `pipeline.run()`: where a run loads is the run's to say. Examples and
  docs show it that way. `spec/001`, R2.
- Importing `leeghwater` changes nothing and does not import dlt: everything happens in
  `prepare()`. `spec/002`, R2. `leeghwater.secrets`, `leeghwater.keyvault` and
  `leeghwater._dlt` are the modules that import dlt at their top.
- A run's options live in the `Setup` that `prepare()` returns, and `create_pipeline`
  sets them on the dlt destination it makes. Only `DATABRICKS_CONFIG_PROFILE`,
  `DLT_PROJECT_DIR`, `RUNTIME__LOG_LEVEL` and `--set` go through the environment, because
  dlt or the SDK read them there. No other global state. `spec/002`, R5.
- Every place leeghwater reaches into dlt beyond its documented API is in
  `src/leeghwater/_dlt.py`, with a canary test in `tests/test_dlt.py`. Add there, never
  elsewhere.
- A secret is read through the client's `dbutils`, never the SDK's secrets API: only the
  first is redacted in a job's output. `spec/003`, R2.
- No secret's value is printed, logged, written to a file or put in the environment.
  `spec/003`, R8.
- Whatever is set up for a run is said in its first lines. `spec/000`, R9.
- Every assumption about what Databricks or dlt does gets a test and a link to the docs or the
  source in its docstring. If unsure, say so and add a `TODO(verify)` — do not guess. What was
  read in dlt is listed in `spec/README.md`, "Read, not assumed".
- It is installed on compute it doesn't own: few dependencies, low lower bounds, and one upper
  bound, `dlt<2`. `spec/002`, R11.
- Small PR-sized commits, conventional commit messages.
- A release is a pull request of its own, opened when the owner says.

## Commands

The Astral stack, as in `stevin`, `lely` and `caland`: uv and ruff. Never pip, black or mypy.

```sh
uv sync
uv run pytest && uv run ruff check && uv run ruff format --check .
```

`ruff format` also formats the Python in Markdown code blocks, so the check covers `spec/`.

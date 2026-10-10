# Decisions

Why leeghwater is the way it is: a log, oldest first.

**An entry is never edited.** A decision that changes gets a new entry at the end, and
the new entry names the one it supersedes by its number. The old entry stays as it was
written. What must be true of the code is in [RULES.md](RULES.md); this file says why,
and what was there before.

An entry has a number, a date, what was decided and by whom, why, and what it replaced
if it replaced something. "The writer" is whoever built it, on the owner's "you decide".

## 1. 2026-10-06 — A package a dlt project imports, beside dlt

Decided by the owner. leeghwater is imported by a project; it wraps nothing of dlt but
the two calls of decision 4. Sources, `secrets.toml`, dlt's config and the `dlt` command
stay dlt's.

Why: every team that runs dlt on Databricks writes the same wrapper, a `main.py` that
reads its own arguments, copies `dbutils.secrets` into environment variables and builds
the pipeline by hand. It works on Databricks and nowhere else. leeghwater is that
wrapper, written once and tested.

## 2. 2026-10-06 — One command, on a laptop and as a job's entry point

Decided by the owner. The project's console script is what a developer types and what a
wheel task calls, and the project adds its own commands to it.

Why: a job needs an entry point and a developer needs a command. When they are two
things, what was tried on the laptop is not what runs at night.

## 3. 2026-10-06 — dlt's secrets come from secret scopes, through a config provider

Decided by the owner.

Why: a Databricks team keeps its secrets in secret scopes, and dlt has no provider for
those. The usual way around it, `dbutils.secrets.get` copied into an environment
variable at the top of a pipeline, runs on Databricks and nowhere else, is written again
for each secret, and puts the value in the environment of everything the process starts.

## 4. 2026-10-07 — leeghwater makes the pipeline

Decided by the owner. A project's pipeline calls `leeghwater.create_pipeline` and
`leeghwater.run`, and never `dlt.pipeline()` or `pipeline.run()`.

Why: where a run loads is not the code's to say. The same code loads into a local file
on a laptop, into one developer's schema in development and into the real one in
production. Those two dlt calls are where the destination and the schema are named, so
they are the two the run has to reach.

## 5. 2026-10-07 — A laptop run loads into a local DuckDB file

Decided by the owner. Without a profile a run on a laptop loads locally and reads no
secret scope; with `--profile` it loads into that workspace.

Why: the first run then needs nothing but Python, and it tries the source, not the
destination.

## 6. 2026-10-07 — A secret is named by dlt's path, joined with `-`

Decided by the writer. A secret that exists under another name can be pointed at, in
the app or per run.

Why: it is how dlt's Google provider names a secret, and the name can be copied from
dlt's error into the scope. The pointer is for a team whose scope was filled by somebody
else, and per run so that dev and prod can point at different scopes from the bundle.

## 7. 2026-10-07 — A scope is listed once, before anything is read from it

Decided by the writer.

Why: dlt tries several paths for every value and most do not exist. Listing first keeps
a run at one list per scope and one read per secret used, and keeps a trail of failed
reads out of the workspace's audit log.

## 8. 2026-10-07 — A secret is read through the client's `dbutils`

Decided by the writer, after the run on a workspace of that day. It replaced a read
through the SDK's secrets API.

Why: redaction. In a serverless wheel task a value read through the API and then
printed stood in the task's output as it is. Read through `dbutils`, every print of it
came out as `[REDACTED]`. leeghwater prints no value, but a project's own `print` might.

## 9. 2026-10-07 — A run into Databricks names its warehouse, and a schema its staging schema

Decided by the writer. A run that does not is stopped, with the lines of the job that
are missing.

Why: dlt would load through the first warehouse on the workspace's list. And dlt
derives its staging schema as `<name>_staging`, a schema the bundle never made and so
never grants or cleans up.

## 10. 2026-10-07 — A yes or no parameter takes a word, not a flag

Decided by the writer.

Why: a job's parameter comes from a bundle variable, and a variable can set a word.

## 11. 2026-10-07 — A project may import dlt wherever it likes

Decided by the writer, after the run on a workspace of that day. It replaced the rule
"keep `import dlt` out of the app's module".

Why: in a serverless wheel task a plain `import dlt` at the top of a project's module
got dltHub's dlt. The import hook is there, and so is Databricks' own `dlt`, but its
folder is not on the path. The workaround still runs on Databricks and does no harm. A
notebook and a classic cluster were not tried.

## 12. 2026-10-07 — A run's options are set on the destination, in the call

Decided by the writer, after a review. `create_pipeline` sets the catalog, the
warehouse, the staging schema and the normalization switch on the destination it makes.
It replaced handing them to dlt as environment variables.

Why: the environment left state behind between calls of `prepare()`. It also reached a
plain `dlt.pipeline()` with the run's names but without its `--limit`, which was lost
silently. Since the change a plain `dlt.pipeline()` gets nothing from the run, and
because nothing in dlt is patched it cannot be stopped either: so a run whose pipeline
made no load with `leeghwater.run()` fails.

## 13. 2026-10-07 — Starting a project is a template's job, not leeghwater's

Decided by the owner. It replaced `leeghwater init <name>`, which wrote a project with a
bundle and a job, and which was built and run on a workspace the same day. The command
and its files left leeghwater that day, for a template in a repository of its own.

Why: the owner's reason was that starting a project is a bundle template's job, with
dlt and dbt both. So leeghwater has no command that writes a project. The same command
inside dlt's own command line was left out as well: it needs dlt and leeghwater
installed first, which is not when a scaffold is wanted.

## 14. 2026-10-08 — An Azure Key Vault can be read directly

Decided by the owner. Asked whether that meant a Key Vault-backed Databricks scope or
the vault itself, the owner chose the vault itself. It is an extra, `keyvault`, and a
vault is asked after the scopes.

Why: a Key Vault-backed scope is a scope and needed nothing new. Why the vault is read
directly as well: decided, reason not recorded.

## 15. 2026-10-11 — One place per fact, and no spec folder

Decided by the owner. It replaced the `spec/` folder: seven files that each held rules,
decisions, a record of runs and the story of how the tool came to be. The rules are in
`RULES.md`, the decisions here, the record of runs in `docs/tried.md`, the scope in the
README, and the story in git.

Why: an audit of the folder against the code found 59% of the checked statements true
as written, and about 12 of the 42 citations in code and tests named a rule that had
moved or did not exist. A fact written in five places goes stale in four.

One spec was not carried over: skills for coding agents, a draft that was never agreed
and that rested on `leeghwater init` (decision 13).

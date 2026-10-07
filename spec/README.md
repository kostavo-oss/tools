# spec

What leeghwater has to do, and how we know that it does.

Written on 2026-10-06, the day the owner described the tool and named it. Built on 2026-10-07,
and run on a workspace the same day.

**Phases one and two are built:** the runner, what it does on Databricks, the secrets and the
scaffold. **Phase three, the skills, is not.** What was run for real, and what could not be,
is under [Run on a workspace](#run-on-a-workspace).

## The specs

The numbers are names, not an order; the order of work is in
[000, Phases](000-what-leeghwater-is.md#phases).

| Spec | What it covers | Phase | Status |
|---|---|---|---|
| [000 — what leeghwater is](000-what-leeghwater-is.md) | Why it exists, where it stands, what it does and doesn't | — | agreed |
| [001 — the runner](001-the-runner.md) | The project's command line: one command on a laptop and in a job | 1 | built; run as a serverless wheel task |
| [002 — on Databricks](002-on-databricks.md) | What it knows about where it runs, and what it does about it | 1 | built; run on serverless, not on a cluster or in a notebook |
| [003 — secrets](003-secrets.md) | dlt's secrets, from Databricks secret scopes | 1 | built; read from a real scope, in a job and from a laptop |
| [004 — the scaffold](004-the-scaffold.md) | A project and a job to start from | 2 | superseded: moved to [vierlingh](https://github.com/kostavo-oss/vierlingh) |
| [005 — for agents](005-for-agents.md) | Skills for coding agents | 3 | draft, not built; the owner said "maybe" |

## How a spec is written

- **Status** — draft, agreed, built, parked, superseded.
- **Why** — the problem, in a few lines.
- **Requirements** — numbered (`R1`, `R2`, …), each one a thing you can check. Refer to one as
  `003/R4`. Each says where it comes from:
  - *(owner)* — the owner said it;
  - *(decided)* — the writer's answer to a question the owner handed over on 2026-10-07 with
    "you decide". It stands until the owner says otherwise;
  - *(dlt)* — read in dlt's source or docs. Where is in [Read, not assumed](#read-not-assumed);
  - *(run)* — it was run on a workspace on 2026-10-07 and held;
  - *to verify* — it leans on something Databricks does that has not been tried.
- **Not in this spec** — what was left out on purpose, and where it went.
- **Done when** — the checks that close the spec.

## Decided

**By the owner, on 2026-10-06,** in their words:

- **What it is:** "a cli package for dlt to make it easy for devs to run it in databricks" —
  "in essence its a package they import that handles some of the databricks idiotic things; it
  knows if its running in databricks or not".
- **An entry point, and theirs to extend:** "a entry point for running in databricks, a cli that
  people can extend". → [001](001-the-runner.md)
- **It fits dlt:** "fit it nicely with dlt". → [000/R8](000-what-leeghwater-is.md#what-it-does)
- **Secrets:** "a custom secrets provider for databricks secrets". → [003](003-secrets.md)
- **Who uses it:** "developers in databricks, to build and run ingestion within databricks".
- **A scaffold:** "it should also be able to scaffold a job to get people started".
  → [004](004-the-scaffold.md)
- **For agents:** "maybe have skills and other things to help agentic development".
  → [005](005-for-agents.md)
- **The name:** leeghwater, after Jan Adriaanszoon Leeghwater, the millwright who drained the
  Beemster. A person, like stevin, lely and caland.

**By the owner, on 2026-10-07:**

- **leeghwater makes the pipeline.** Asked what a pipeline function is, the owner chose
  "leeghwater makes it": a project calls `leeghwater.create_pipeline(...)` and
  `leeghwater.run(...)`, and never `dlt.pipeline()` or `pipeline.run()` itself.
  → [001/R2](001-the-runner.md#requirements)
- **A laptop run loads into a local DuckDB file** unless a profile is given.
  → [002/R6](002-on-databricks.md#requirements)
- **Build it, and try it for real:** "you decide get to work make it good", and later "you
  have permisions to create a job and test this".

**By the writer, on the owner's "you decide"** — each stands until the owner says otherwise:

- A secret is named by dlt's path joined with `-`, and one under another name can be pointed
  at. → [003](003-secrets.md)
- A run's options are set on the destination `create_pipeline` makes, in the call; only
  what dlt or the SDK read from the environment goes there. Nothing in dlt is patched.
  → [002/R5](002-on-databricks.md#requirements)
- Every reach into dlt beyond its documented API lives in one module with one canary test
  each: `src/leeghwater/_dlt.py`, `tests/test_dlt.py`. *(after a review on 2026-10-07)*
- On Databricks a run stops without a named warehouse, and a schema needs its staging schema.
  → [002/R7 and R10](002-on-databricks.md#requirements)
- A yes or no parameter takes a word (`--full true`), so a bundle variable can set it.
  → [001/R4](001-the-runner.md#requirements)
- The scaffold was `leeghwater init`, until the owner moved it to a bundle template of its
  own on 2026-10-07. → [004](004-the-scaffold.md)
- The first line, and the Kostavo line left as it is. → [000](000-what-leeghwater-is.md)

## Run on a workspace

On 2026-10-07, on the owner's test workspace: a project made by `leeghwater init`, deployed
as a bundle to a development target, with a job of serverless wheel tasks; and the same
project run from a laptop with a profile. A throwaway scope, secret, job and schemas were
made and removed again.

| What | Held? |
|---|---|
| The scaffolded bundle validates, deploys and destroys | yes |
| The job's entry point is the project's console script, with the words as its arguments | yes |
| `DATABRICKS_RUNTIME_VERSION` says where it runs; on serverless it was `client.2.5` | yes |
| The job is told the deployed names of the bundle's schemas (`dev_<user>_…`) by reference | yes |
| The wheel's `.dlt/config.toml` is found from a job's working directory | yes |
| dlt's working files can be written: the home directory is writable, and is the working directory | yes |
| A pipeline that raises fails its task | yes |
| A plain `import dlt` in a serverless wheel task is dltHub's dlt, hook or no hook | yes |
| A scope is listed and read as the job's identity; a real source gets its secret | yes |
| A secret read by leeghwater is redacted in the task's output | yes — through `dbutils`; **not** through the SDK's secrets API |
| From a laptop with a profile: `doctor`, the scope, and a load into Unity Catalog | yes |
| A schema with two underscores is loaded into as named, and the named staging schema is used; no third schema | yes |
| A load from the serverless job into Unity Catalog | **no — not on this workspace**: see below |

**What did not hold, and why.** dlt's Databricks destination uploads its files to a volume
before it copies them into a table, and the upload goes to
`<region>.storage.cloud.databricks.com`. From this workspace's serverless compute that
connection is refused: its outbound network is limited to a list of hosts. The same load
from a laptop works. So a full load from a job is still *to verify*, on a workspace with
ordinary outbound access.

**What it changed:**

- Secrets are read through the client's `dbutils`, for the redaction. → [003/R2](003-secrets.md#requirements)
- The scaffold asks for `dlt[databricks,parquet]`: off Databricks nothing brings pyarrow, and
  dlt needs it to write the files it loads from. → [004/R2](004-the-scaffold.md#requirements)
- The scaffolded task turns serverless' own retry off: a failed task was run a second time
  without being asked. → [004/R4](004-the-scaffold.md#requirements)
- The rule "keep `import dlt` out of the app's module" is gone. → [002/R3](002-on-databricks.md#requirements)

## Still open

1. **A full load from a job,** on a workspace whose serverless compute can reach its storage.
2. **A notebook and a classic cluster.** Nothing was run on either; the name `dlt` is where
   they differ from a wheel task. → [002, To verify](002-on-databricks.md#to-verify)
3. **A first release.** The name was free on PyPI on 2026-10-06. Until then a job installs
   leeghwater from a wheel beside the project's own. The owner's word, as for lely.
4. **Phase three:** whether the skills are wanted, and for which agents.
   → [005](005-for-agents.md)
5. **Where the scaffold's command also lives:** inside dlt's own command, as a plugin.
   → [004](004-the-scaffold.md#not-in-this-spec)

## Read, not assumed

What the specs say about dlt was read in dlt 1.30.0 on 2026-10-06 and in 1.31.0 on 2026-10-07.

| What | Where |
|---|---|
| Plugins are found by the entry-point group `dlt`. Three hooks: `plug_run_context` (one plugin wins), `plug_cli`, `plug_mcp`. | `dlt/common/configuration/plugins.py` |
| Config providers: environment, `secrets.toml`, `config.toml`; vaults for Google, AWS and Airflow. None for Databricks. | `dlt/common/configuration/providers/` |
| `VaultDocProvider` asks for `dlt_secrets_toml` first, then for the fragments `sources`, `sources.<name>`, `destination`, `destination.<name>` — each also under the pipeline's name — then for the value itself. With `list_secrets` it lists the vault once and skips what isn't there. A subclass gives `_look_vault`, `_list_vault` and the name of a key; Google's joins the path with `-`. | `…/providers/vault.py`, `…/providers/google_secrets.py` |
| A fragment is merged at the root of the document, not under the key it was read from. | `…/providers/doc.py`, `set_fragment` |
| `dlt.secrets.register_provider` adds a provider after all the others. | `dlt/common/configuration/accessors.py` |
| dlt looks for `.dlt/` in the working directory, or in `DLT_PROJECT_DIR`. Its working files go under the home directory; as root under `/var/dlt`; in a temporary directory when the home directory can't be written. | `dlt/common/runtime/run_context.py` |
| `dlt.pipeline` takes `dataset_name` and the destination from config when the call leaves them out, and from the call when it names them. | `dlt/pipeline/__init__.py`, `dlt/pipeline/configuration.py` |
| A dataset name is normalized unless `enable_dataset_name_normalization` is off. The staging dataset is `staging_dataset_name_layout`, `%s_staging` by default; a layout without `%s` is taken as the whole name. | `dlt/common/destination/client.py` |
| A failed load job raises: `raise_on_failed_jobs` is `True` unless a project sets it otherwise. With it off, the package is marked loaded with the failed job recorded. | `dlt/load/configuration.py`, `dlt/load/load.py` |
| dlt makes its logger from its runtime config, which holds `log_level`. | `dlt/common/runtime/init.py` |
| The Databricks destination makes its own `WorkspaceClient()` and takes its default sign-in. Without an `http_path` it takes the notebook's cluster, then `DATABRICKS_WAREHOUSE_ID`, then the first warehouse on the list. | `dlt/destinations/impl/databricks/configuration.py` |
| The Databricks destination uploads a local file with `PUT … INTO` a volume named `_dlt_staging_load_volume` in the schema it loads into, then copies from it. | `dlt/destinations/impl/databricks/databricks.py` |
| Two workarounds for the name `dlt`: on serverless, take the import hook out while importing; on a cluster, an init script or a snippet. The docs call the snippet fragile. | docs, *Databricks → Troubleshooting* |

The names dlt reads a run's options by, as environment variables, are tried in the tests:
`DESTINATION_TYPE`, `DATASET_NAME`, `DESTINATION__ENABLE_DATASET_NAME_NORMALIZATION`,
`DESTINATION__STAGING_DATASET_NAME_LAYOUT`, `DESTINATION__DATABRICKS__CREDENTIALS__CATALOG`
and `…__HTTP_PATH`, `RUNTIME__LOG_LEVEL`.

From the Databricks SDK: it decides that it runs on Databricks by `DATABRICKS_RUNTIME_VERSION`
(`databricks/sdk/credentials_provider.py`), and a client's `dbutils` is the runtime's own on
Databricks and a stand-in over the REST API elsewhere (`databricks/sdk/dbutils.py`).

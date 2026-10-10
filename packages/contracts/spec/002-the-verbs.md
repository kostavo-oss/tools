# 002 — the verbs

**Status:** draft, 2026-10-10. Nothing is built.

Marks: *(owner)*, *(proposed)*, *(standard)*, *(cli)* as in [000](000-positioning.md);
*to verify* where it leans on something that has not been run.

## Why

Three moments in a consumer's life need a command: when it starts reading a port, before
each run, and after a run. `pull`, `check`, `evaluate`.

## Every verb

- **R1 — Run from a product's folder.** Each verb finds `dataproduct.yaml` and
  `contracts.yml` by walking up from where it is run. *(proposed)*
- **R2 — Three exit codes**, lely's: **0** done; **1** something failed — a repository
  that can't be reached, a file that can't be read, the evaluator crashing, a warehouse
  that doesn't answer; **2** refused — a rule in this spec said no. A warning is exit 0.
  *(owner)*
- **R3 — `--json`** on every verb: what was read, done, warned about and refused, as
  one document. Without it, a few lines a person can read. *(proposed)*
- **R4 — One seam to the Data Contract CLI.** Everything asked of it goes through one
  interface with three calls: *test* a contract against a server, say whether a change
  between two contracts *breaks*, and *export* a contract to a format. One
  implementation runs the CLI; a fake stands in for it in tests ([004](004-testing.md)).
  The rest of the package never names the CLI. *(owner: behind one seam)*
- **R4a — The CLI is run as a command, not installed beside this package.** As lely
  runs stevin. Its Databricks extra brings `ibis-framework[databricks]`,
  `databricks-sql-connector` and `databricks-sdk<0.143.0`
  ([pyproject.toml](https://github.com/datacontract/datacontract-cli/blob/main/pyproject.toml),
  v1.2.4), and it needs Python below 3.15. As a dependency that cap would hold back
  whatever is installed beside this package, in a project and in this repository's one
  lock file. As a command, at a version this package names, it holds back nothing. The
  owner hasn't been asked: [README](README.md#still-open), 7. *(proposed)*
- **R5 — Who resolves which `${…}`.** Written down because three tools spell a variable
  the same way.
  - In a **stevin spec** and in `stevin.yml`: stevin, from the target's variables.
    stevin never substitutes inside a contract, and `from_contract` does not read a
    contract's `servers` at all.
  - In a **bundle file**: the Databricks CLI.
  - In a **contract** or a **product file**: tooling, says the standard
    ([001, Variables](001-the-files.md#variables)). Which tool is the owner's to choose
    ([README](README.md#still-open), 2). The proposal: this package resolves nothing,
    and the Data Contract CLI resolves a contract's variables from the environment when
    it tests (it has code for this, `datacontract/config/variables.py`; *to verify* that
    it follows RFC 0050's rules for unset variables and defaults).
  - In **`contracts.yml`**: nobody. It holds none ([001/R12](001-the-files.md)).

  *(proposed)*
- **R6 — `context` and `synonyms` are passed over.** *(proposed)*
- **R7 — Nothing is written outside the product's folder**, except the one table
  `evaluate` is told to write to. *(proposed)*
- **R8 — Which ports.** No argument means every input port. A port's name as an
  argument means that one. *(proposed)*

## pull

When a consumer starts reading a port, and again when it moves to another version.

```
contracts pull [PORT] [--as dbt-sources|dlt] [--out PATH]
```

- **R9 — A port that names no contract is refused.** For each input port: no
  `contractId` — exit 2, "the input port *x* names no contract: there is nothing to
  fetch". No `version` — exit 2, "the input port *x* names no version: a snapshot needs
  one to be called by". ODPS v1.1.0 allows both to be left out
  ([001/R3](001-the-files.md)); this package does not. *(proposed)*
- **R10 — Fetch by id and version.** From the port's source in `contracts.yml`, the
  file under `contracts/output/` whose `id` is the port's `contractId` and whose
  `version` is the port's `version`. None, or more than one, is refused naming the
  source and what was looked for. A `repo` is fetched with git, at `ref`, with whatever
  credentials git already has. *(proposed)*
- **R11 — Write a snapshot.** To `src/input_ports/<port>/<version>.odcs.yaml`, the
  producer's bytes unchanged ([001/R9](001-the-files.md)). The same bytes already there:
  nothing to do, exit 0. Different bytes for the same version: refused, because a
  published version does not change — the message says to look at what the producer
  did, and `--force` takes the new file. The snapshot is committed: a pull request
  shows what the consumer now depends on. *(proposed)*
- **R12 — Render it, when asked.** After the snapshot is written:
  - `--as dbt-sources` — the CLI's export to `dbt-sources`
    ([export formats](https://github.com/datacontract/datacontract-cli/blob/main/datacontract/export/exporter.py)),
    written to `--out`. Nothing of this package's own. *(cli)*
  - `--as dlt` — a dlt import schema for a pipeline that loads this port's data: one
    `<name>.schema.yaml` with the contract's objects as tables and their properties as
    columns (`data_type`, `nullable`, `primary_key`), for the folder a pipeline names as
    `import_schema_path`
    ([dlt: adjust a schema](https://dlthub.com/docs/walkthroughs/adjust-a-schema)).
    leeghwater's `create_pipeline` passes `import_schema_path` on to dlt as it is. The
    types map as stevin's `from_contract` maps them, to dlt's names; a property with no
    dlt type is refused, naming it. *(proposed)*
  - With it, the schema is frozen: dlt's `schema_contract: freeze` raises on a new
    table, a new column or a changed type instead of evolving
    ([dlt: schema contracts](https://dlthub.com/docs/general-usage/schema-contracts)).
    dlt's docs set it on a resource, a source or `pipeline.run`. *To verify:* whether an
    import schema file can carry it. If it can't, `pull --as dlt` prints the one line
    to put on `run`.
- **R13 — No test.** `pull` reads files. It needs no workspace. *(proposed)*

## check

The first task of a consumer's job, and a step in its CI.

```
contracts check [PORT] --server NAME
```

It answers one question: *is what I am about to read still what I pulled?* For each
input port, in this order. The first refusal ends that port; the other ports are still
checked, so one run reports everything.

- **R14 — The port names a contract and has a snapshot.** As R9; and no snapshot for
  the port's version is refused with "run `contracts pull`". *(proposed)*
- **R15 — The producer still serves this version.** Read the producer's current
  `dataproduct.yaml` from the port's source, and find the output port entry with this
  `contractId` and `version` ([001/R1](001-the-files.md)).
  - There, not deprecated: pass.
  - There, `deprecated: true`: **a warning**, naming the port and any newer version of
    the same port the producer lists. Exit 0.
  - **Gone: refused**, exit 2.
  - The producer's product itself `deprecated`, or its `status` `deprecated` or
    `retired`: a warning.

  This is the whole compatibility window: a consumer pinned to a version passes for as
  long as the producer lists it. A producer that wants to move its consumers lists v2
  beside v1, marks v1 deprecated, and removes it when the warnings have been read.
  *(proposed)*
- **R16 — The contract is still the one that was pulled.** Compare the snapshot with
  the producer's current file for the same `id` and `version` (R10).
  - The same bytes: pass.
  - Different, and the CLI's `breaking` says the change breaks
    ([commands](https://docs.datacontract.com/commands)): **refused**.
  - Different, and it doesn't break: a warning, "the producer changed a published
    version", with the CLI's changelog. `contracts pull --force` takes it.

  *(proposed)*
- **R17 — Say what is on its way out.** Every schema object and property that the
  producer's current contract marks `deprecated` (ODCS v3.2.0) is a warning, by name. A
  consumer does not say which properties it uses, so every one is named. *(proposed)*
- **R18 — Test it now.** Ask the evaluator to test the **snapshot** against the server
  `--server` names: the contract's schema, its quality rules, and its service levels
  where it states any, against the producer's live table. Run by the consumer, at the
  start of the consumer's run, with the consumer's credentials: producer and consumer
  are not on one clock, so a result from the producer's last run says little about now.
  - Every check passes: pass.
  - A check fails: **refused**, exit 2, with the failed checks.
  - The test could not run: exit 1.

  *(owner: pull-based; the consumer tests)*
- **R19 — "The pulled version still tests clean" is the rule.** R15 to R18 together.
  Nothing else decides. In particular, no clock of this package's own: freshness is
  checked when the contract states it and not otherwise
  ([README](README.md#still-open), 4). *(proposed)*
- **R20 — `--server` is required.** A contract can list several servers; guessing one
  is how dev gets tested and prod gets read. *(proposed)*
- **R21 — `--no-test`** does R14 to R17 and skips R18, for a pull request where no
  warehouse is at hand. It says that it skipped. *(proposed)*

## evaluate

The last task of a job. Optional: a product can use `pull` and `check` and never run
this.

```
contracts evaluate [PORT] --server NAME [--to CATALOG.SCHEMA.TABLE | --to FILE.duckdb] [--inputs]
```

- **R22 — Test what the product promises.** For each **output** port: the evaluator
  tests the contract in `contracts/output/` against the server named, which is the
  product's own table. "Did we deliver what we promised." With `--inputs`, the input
  ports' snapshots as well, as `check` does. A port without `contractId` or `version`
  is refused as in R9. *(owner)*
- **R23 — One row per contract tested**, appended to one table. Nothing is updated or
  deleted, ever.

  | column | |
  |---|---|
  | `product_id`, `product_version` | whose run this was |
  | `port`, `direction` | the port's name; `output` or `input` |
  | `contract_id`, `contract_version` | what was tested |
  | `server` | the name given to `--server` |
  | `run_id` | the job run's id when there is one, else a new one |
  | `started_at`, `finished_at` | UTC |
  | `passed` | every check held |
  | `results` | the evaluator's result, as JSON text |
  | `evaluated_by`, `evaluator` | who ran it; the CLI's version |

  *(owner: one table; the columns are proposed)*
- **R24 — Where the table is.** `--to catalog.schema.table`: Unity Catalog, written
  through a SQL warehouse with the Statement Execution API and the SDK's default
  sign-in. `--to file.duckdb`: a local file, the same columns. Without `--to`, nothing
  is written and the results are only printed. The table is made when it isn't there;
  a team that wants its grants and owner reviewed declares it in stevin instead, and the
  docs show that spec. *(owner: Unity Catalog or DuckDB; the rest proposed)*
- **R25 — The row is written before the verdict.** A failed test writes its row and
  then exits 2. A row that can't be written is exit 1, after the results are printed.
  *(proposed)*
- **R26 — Nobody is told.** A consumer that wants to start when a producer has
  evaluated uses Databricks' own trigger on a table update, on this table. That is a
  page in the docs and no code here. *(owner)*
- **R27 — Two sign-ins, one identity — to verify.** The CLI reads
  `DATACONTRACT_DATABRICKS_SERVER_HOSTNAME`, `DATACONTRACT_DATABRICKS_HTTP_PATH` and
  `DATACONTRACT_DATABRICKS_TOKEN`
  ([docs](https://docs.datacontract.com/testing/databricks)), and needs a running SQL
  warehouse or cluster. The row is written with the SDK's default sign-in. In a job
  run by a service principal there is no token in the environment. Whether the
  evaluator can hand the CLI what the SDK has — and what it takes — is not known until
  it is tried on a workspace. *to verify*

## Not in this spec

- A verb that publishes anything, anywhere.
- `status`, `search`, `show`, `list`.
- Testing with anything other than the Data Contract CLI.
- Deciding which *properties* a consumer may rely on. A consumer is pinned to a whole
  contract version.
- Waiting, retrying, or polling for a producer.
- Access: whether the consumer may read the table is Unity Catalog's answer, and it
  arrives as a failed test.

## Done when

- Each requirement has a test against the fake evaluator, and R10, R18, R24 and R27
  have run on the test workspace ([004](004-testing.md)).
- The *to verify* marks in R5, R12 and R27 are each replaced by what was found.
- `check` on the two-product scenario passes, then refuses after the producer's table
  loses a column, then refuses after the producer removes the port version.

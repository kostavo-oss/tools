# 000 — what this is

**Status:** draft, 2026-10-10. Nothing is built. The shape is the owner's, decided on
2026-10-09 after two outside reviews; what is still theirs to answer is in the
[README](README.md#still-open).

Requirements are marked *(owner)* where the owner chose them, *(proposed)* where the
writer proposes and the owner has not answered, *(standard)* where a Bitol standard says
it, and *(cli)* where the Data Contract CLI's docs or source say it.

## In one line

> **A consumer's gate for data contracts on Databricks.**
> Pull the contract of what you read, and check it before every run.

## Why it exists

A data product reads another product's output. The producer has written down what that
output looks like, in a data contract. Three things still go wrong, and each is quiet:

1. **The consumer never had the contract.** It read the table, guessed the shape, and
   wrote its models against the guess.
2. **The producer changed something.** A column went, a type widened, a version was
   retired. The consumer finds out when its run fails halfway, or worse, when it
   doesn't fail.
3. **Nobody can say afterwards who kept their promise.** The test ran in someone's CI
   and the result is gone.

The standards for writing the contract down exist, and so does a tool that tests one.
What is missing is the small piece between a consumer's repository and its job: fetch
the contract of what I read, keep it beside my code, and stop my run when what I read
is no longer what I pulled.

## What exists, and is not rebuilt

Checked on 2026-10-09 and 2026-10-10.

- **The standards.** Bitol's
  [Open Data Contract Standard](https://github.com/bitol-io/open-data-contract-standard)
  (ODCS, contracts) and
  [Open Data Product Standard](https://github.com/bitol-io/open-data-product-standard)
  (ODPS, products). Both published their newest version on 2026-09-08: ODCS
  [v3.2.0](https://github.com/bitol-io/open-data-contract-standard/releases/tag/v3.2.0)
  and ODPS
  [v1.1.0](https://github.com/bitol-io/open-data-product-standard/releases/tag/v1.1.0).
  "ODPS" here always means Bitol's. opendataproducts.org publishes another
  specification under the same four letters; it is not this one.
- **The test.** The [Data Contract CLI](https://github.com/datacontract/datacontract-cli)
  (MIT, v1.2.4 on 2026-10-06) lints a contract, tests it against Databricks, DuckDB and
  others, says whether a change between two contracts breaks, exports dbt sources, and
  builds an HTML catalog ([commands](https://docs.datacontract.com/commands)). It is
  maintained by Entropy Data.
- **The store.** Entropy Data has a free self-hosted Community edition
  ([pricing](https://entropy-data.com/pricing)). Dataminded's
  [Data Product Portal](https://github.com/conveyordata/data-product-portal) is
  Apache-2.0 and has access requests. OpenMetadata and DataHub read ODCS. A team that
  wants a registry, a page to browse and a workflow for access installs one of those.
- **The page.** `datacontract catalog` builds a static site from the contracts in git.
  On Databricks, Unity Catalog's own discovery pages do the browsing.
- **The table's shape.** stevin reads a contract for a table's shape itself
  ([`from_contract`](https://kostavo-oss.github.io/tools/stevin/spec/)), so this package
  renders no stevin spec.

## Where it stands

- **Git is the truth.** Contracts and product files live in repositories. This package
  keeps no registry, no index and no server. *(owner)*
- **Beside the Data Contract CLI, not instead of it.** Every test, every comparison of
  two contracts and every export is the CLI's. This package decides *which* contract,
  *when*, and what a result means for a run. *(owner)*
- **A gate that pulls, not a bus that pushes.** A consumer asks before it runs. Nothing
  is sent to anyone when a producer finishes. *(owner)*
- **Databricks first, the files agnostic.** The files are the standards' and work
  anywhere. What is Databricks' is where the test runs and where the one optional table
  is written. *(owner)*
- **Not a store, and it works next to one.** It reads files, so it sits beside Entropy
  Data or the Data Product Portal without knowing they are there. *(owner)*

### When not to use it

- **You only produce.** `datacontract lint` on a pull request and `datacontract test`
  after your pipeline are all you need, and the
  [data product template](https://github.com/kostavo-oss/data-product-template) wires
  both in ([003](003-in-the-template.md)).
- **You want to browse, request access, or approve.** That is a store's job; see above.
- **Your contracts are not ODCS.** Nothing else is read.

## Who it is for

Honestly: today, nobody outside this repository. The first user is a producer and a
consumer made from the data product template, run on the test workspace
([004](004-testing.md)). Until a client's two products use it, it is a worked example
of data contracts on Databricks without a service to run, and it is sized as one: three
verbs, a few hundred lines.

It is for a team with more than one data product on Databricks, each in a repository of
its own, where one reads another's tables and nobody wants to host anything to keep
them honest.

## What it does

- **R1 — Three verbs.** `pull`, `check` and `evaluate`, and nothing else.
  [002](002-the-verbs.md). *(owner)*
- **R2 — A plain command line.** Each verb runs on its own, on a laptop, in CI and in a
  job. It does not need lely, and lely does not need to know it. A project that deploys
  with lely wraps a verb in a step of its own. *(owner)*
- **R3 — The standards' files, as they are.** It reads ODPS for a product's ports and
  ODCS for a contract, checks by hand the few fields it uses, and never models the whole
  standard. A file from a newer minor version reads for what it has. *(owner)*
- **R4 — One file of its own.** `contracts.yml` says where each input port's contract is
  fetched from. [001](001-the-files.md). *(proposed)*
- **R5 — One optional table.** `evaluate` appends each test result to one table, in
  Unity Catalog or in a local DuckDB file. Nothing else is stored anywhere. *(owner)*
- **R6 — It becomes unnecessary** when the Data Contract CLI checks a product's input
  ports itself, or when Databricks ships data contracts with a consumer-side check. The
  README says so. *(proposed)*

## Not in this spec

Left out on purpose, by the owner on 2026-10-09 unless marked.

- A registry, an API, a server, a hosted or multi-tenant mode.
- Tables for products, ports or runs; search; a page or UI.
- Events, webhooks, queues.
- Access requests, agreements, approvals, a workflow.
- A stevin renderer: stevin reads the contract.
- A SQLMesh renderer.
- A lely plugin or step packaging.
- A Postgres backend.
- Quality checks of its own, and owning the ODCS or ODPS schema.
- Writing contracts: `datacontract init` and `datacontract import` do that. *(proposed)*

## Done when

- The owner has answered the [Still open](README.md#still-open) list.
- 001 to 004 are agreed.
- The package has its name and the folder carries it.

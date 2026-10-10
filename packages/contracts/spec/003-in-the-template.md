# 003 — in the data product template

**Status:** draft, 2026-10-10. Nothing is built, here or in the template.

## Why

The verbs are only worth having inside a product that has the files. The
[data product template](https://github.com/kostavo-oss/data-product-template) is where a
team gets a product from, so it is where the files, the checks and the three verbs are
wired in once. A producer needs none of this package: the first half of this spec is the
Data Contract CLI alone.

## What every product gets

Needs only the Data Contract CLI.

- **R1 — The files.** `dataproduct.yaml` at the root and one contract per output port
  version under `contracts/output/<port>/<version>.odcs.yaml`
  ([001](001-the-files.md)), written in ODPS v1.1.0 and ODCS v3.2.0. *(owner)*
- **R2 — Lint on a pull request.** `datacontract lint` on every contract the pull
  request touches. *(owner)*
- **R3 — Test after the pipeline.** The job's last task runs `datacontract test` on each
  output port's contract against the product's own tables — or `contracts evaluate`,
  which does the same and keeps the result ([002/R22](002-the-verbs.md#evaluate)).
  *(owner)*
- **R4 — A page from git.** The docs job runs `datacontract catalog` over
  `contracts/output/` and publishes the result beside the product's docs. That page is
  the catalog; there is no other. *(owner)*

## What a consumer gets

Needs this package.

- **R5 — `contracts.yml`**, one source per input port ([001/R10](001-the-files.md)),
  asked for when the project is made and editable after. *(proposed)*
- **R6 — Snapshots under `src/input_ports/`**, committed. The template's first commit
  has none; `contracts pull` makes them. *(owner)*
- **R7 — `check` first.** The job's first task is `contracts check --server <target>`.
  A refusal fails the task, so nothing downstream reads. In CI, on a pull request,
  `contracts check --no-test`. *(owner: the gate is the first task)*
- **R8 — `evaluate` last, when the product opts in.** A template question, off by
  default, that asks for the table. *(proposed)*
- **R9 — Sources for dbt.** With dbt in the product, `contracts pull --as dbt-sources`
  writes the sources file dbt reads, and CI fails when it is stale. *(proposed)*
- **R10 — A frozen schema for dlt.** With a dlt pipeline that loads another product's
  port, `contracts pull --as dlt` writes the import schema
  ([002/R12](002-the-verbs.md#pull)). *(proposed)*

## The stevin variant

In the template's variant with stevin in dbt's place, the producer's tables take their
shape from its own output contracts:

```yaml
table: ${catalog}.gold.transactions
from_contract: ../contracts/output/transactions/2.0.0.odcs.yaml
grants:
  - {principal: analysts, privileges: [SELECT]}
```

stevin reads the contract ([stevin: shape from a data contract](https://kostavo-oss.github.io/tools/stevin/spec/)).
This package renders nothing for it. The contract says the shape, the spec says who may
see it, and each is said once. *(owner)*

- **R11 — `${catalog}` there is stevin's**, from the target. It is not a contract
  variable and nothing in this package touches it ([002/R5](002-the-verbs.md#every-verb)).

## With lely

A product that deploys with lely wraps a verb in a step of its own, a few lines in the
product's repository. This package ships no step and does not import lely
([000/R2](000-positioning.md)). *(owner)*

## Not in this spec

- Making the template's changes: that is a pull request in the template's repository,
  after 001 and 002 are agreed.
- Sharing a table with the consumer: grants are stevin's or the bundle's.
- A contracts repository for a whole organisation. A source can point at one
  ([001/R11](001-the-files.md)); the template does not make it.

## Done when

- A producer made from the template lints, tests and publishes its catalog with no
  trace of this package.
- A consumer made from the template pulls, and its job refuses to run when the
  producer breaks its promise ([004](004-testing.md), the two-product run).

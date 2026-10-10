# contracts

**A consumer's gate for data contracts on Databricks.** Pull the contract of what you
read, and check it before every run.

!!! warning "A spec, and nothing else"
    No command exists yet, and the name is a working one. What this will do is written
    down in the
    [spec](https://github.com/kostavo-oss/tools/tree/main/packages/contracts/spec),
    with the questions that are still open.

## The gap

One data product reads another's tables. The producer has written down what those tables
look like, in a data contract. The standards for that exist —
[ODCS](https://github.com/bitol-io/open-data-contract-standard) for contracts,
[ODPS](https://github.com/bitol-io/open-data-product-standard) for products — and so
does a tool that tests a contract, the
[Data Contract CLI](https://github.com/datacontract/datacontract-cli). What a consumer
still does by hand is fetch the contract, keep it beside its code, and stop its own run
when what it reads is no longer what it pulled.

## What it will be

Three verbs, a plain command line, no server and no registry.

- **`pull`** fetches the contract of every input port from the producer's repository
  into your own, as a snapshot you commit. It can render the contract as dbt sources,
  or as a frozen dlt schema.
- **`check`** is the first task of your job. Does the producer still serve the version
  you pulled, is the contract unchanged, and does the live table pass it right now.
- **`evaluate`** is optional. It tests what you promise after your run and appends the
  result to one table.

## Not in this tool

A registry, a catalog page, search, access requests, approvals, events, quality checks
of its own. A table's shape from a contract is [stevin](https://kostavo-oss.github.io/tools/stevin/)'s.

It becomes unnecessary when the Data Contract CLI checks a product's input ports itself,
or when Databricks ships data contracts with a consumer-side check.

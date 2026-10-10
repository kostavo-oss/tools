# contracts

**A consumer's gate for data contracts on Databricks.**
Pull the contract of what you read, and check it before every run.

> **Status: a spec, and nothing else.** No command exists yet. [`spec/`](spec/README.md)
> says what this will do; the owner has ten questions to answer there before anything is
> built. `contracts` is a working name: it is someone else's project on PyPI, and this
> package is not published under it.

## The gap

One data product reads another's tables. The producer has written down what those tables
look like, in a data contract. The standards for that exist
([ODCS](https://github.com/bitol-io/open-data-contract-standard) for contracts,
[ODPS](https://github.com/bitol-io/open-data-product-standard) for products), and so
does a tool that tests a contract, the
[Data Contract CLI](https://github.com/datacontract/datacontract-cli). What a consumer
still does by hand is fetch the contract, keep it beside its code, and stop its own run
when what it reads is no longer what it pulled.

## What it will be

Three verbs, a plain command line, no server and no registry.

- **`pull`** — fetch the contract of every input port from the producer's repository
  into your own, as a snapshot you commit. Render it as dbt sources, or as a frozen dlt
  schema.
- **`check`** — the first task of your job. Does the producer still serve the version
  you pulled, is the contract unchanged, and does the live table pass it right now.
  Exit 0 to run, 2 to stop.
- **`evaluate`** — optional. Test what you promise after your run, and append the
  result to one table.

The contracts and product files stay in git, in the standards' own formats. The testing
is the Data Contract CLI's.

## Not in this tool

A registry, a catalog page, search, access requests, approvals, events, quality checks
of its own. For a store, see Entropy Data's Community edition or the Data Product
Portal; this works beside either. For a table's shape from a contract, see
[stevin](https://kostavo-oss.github.io/tools/stevin/).

**It becomes unnecessary** when the Data Contract CLI checks a product's input ports
itself, or when Databricks ships data contracts with a consumer-side check.

## License

Apache-2.0 — see [LICENSE](LICENSE). Community project, not affiliated with or endorsed
by Databricks.

# 001 — the files

**Status:** draft, 2026-10-10. Nothing is built.

## Why

Three kinds of file are involved and two of them are someone else's standard. This spec
says which file is which, where each lives in a product's repository, and exactly which
fields this package reads. Everything it does not read, it leaves alone.

Examples are written in the newest versions, ODPS v1.1.0 and ODCS v3.2.0. ODPS v1.0.0
and ODCS v3.1.0 are read too. *(proposed; the choice of versions is the owner's, see the
[README](README.md#still-open))*

## A product's repository

```
dataproduct.yaml                       the product, in ODPS
contracts.yml                          this package's own file: where input contracts come from
contracts/output/<port>/<version>.odcs.yaml    what this product promises, one file per port version
src/input_ports/<port>/<version>.odcs.yaml     what it reads, as pulled: a snapshot, committed
```

The layout is the one the data product template gives a project
([003](003-in-the-template.md)). Entropy Data's
[Databricks template](https://github.com/entropy-data/dataproduct-builder-databricks)
uses nearly the same folders, which is on purpose: a team that moves between the two
finds its files.

## The product file

`dataproduct.yaml` is ODPS. Read from it, and nothing else:

| field | read for |
|---|---|
| `apiVersion`, `kind` | that it is a `DataProduct`, in a version that is read |
| `id`, `name`, `version`, `status`, `deprecated` | messages, and a warning when a producer's product is deprecated or retired |
| `inputPorts[].name`, `.version`, `.contractId`, `.deprecated` | what this product reads |
| `outputPorts[].name`, `.version`, `.contractId`, `.deprecated` | what it promises |
| `outputPorts[].inputContracts[].id`, `.version` | see the [README](README.md#still-open), 3 |

- **R1 — A port is one name and one version.** ODPS says of an output port's `version`:
  "For each version, a different instance of the output port is listed. The combination
  of the name and version is the key."
  ([schema v1.1.0](https://github.com/bitol-io/open-data-product-standard/blob/main/schema/odps-json-schema-v1.1.0.json),
  `OutputPort.version`.) So a producer that serves v1 and v2 side by side lists two
  entries with one name, each naming its own contract through `contractId` and
  `version`. A consumer is pinned to one of them. *(standard)*
- **R2 — A port has no place of its own.** There is no catalog, schema or table on a
  port. Those are in the `servers` block of the contract the port names. Finding the
  data behind a port always means resolving `contractId` first. *(standard)*
- **R3 — What ODPS 1.1 made optional, this package still needs.** In v1.0.0 an input
  port required `name`, `version` and `contractId`, and an output port `name` and
  `version`. In v1.1.0 both require only `name`
  ([changelog](https://github.com/bitol-io/open-data-product-standard/blob/main/CHANGELOG.md):
  "`inputPorts` and `outputPorts` now require only `name`; `version` and `contractId`
  are optional"). A port without a `contractId` names nothing to fetch or test, and one
  without a `version` gives a snapshot no name. Both are refused by `pull` and `check`
  ([002/R9](002-the-verbs.md#pull)). *(proposed)*
- **R4 — `inputContracts` stayed strict.** On an output port, each `inputContracts`
  entry still requires `id` and `version` in v1.1.0 (`InputContract`, same schema). What
  this package does with it is the owner's to choose. *(standard)*
- **R5 — `context` and `synonyms` are not read.** They are for catalogs and AI tools.
  Neither changes what is fetched or tested. *(proposed)*

A producer, serving two versions of one port and retiring the older:

```yaml
apiVersion: v1.1.0
kind: DataProduct
id: 5d7e7f3a-2f4c-4b8e-9a51-1c2f3d4e5f60
name: payments
version: 2.1.0
status: active
outputPorts:
  - name: transactions
    version: 1.0.0
    contractId: c2798941-1b7e-4b03-9e0d-955b1a872b32
    deprecated: true
  - name: transactions
    version: 2.0.0
    contractId: c2798941-1b7e-4b03-9e0d-955b1a872b32
```

A consumer, still on the older one:

```yaml
apiVersion: v1.1.0
kind: DataProduct
id: 0b1c2d3e-4f50-4a61-8b72-93a4b5c6d7e8
name: revenue
version: 0.4.0
status: active
inputPorts:
  - name: transactions
    version: 1.0.0
    contractId: c2798941-1b7e-4b03-9e0d-955b1a872b32
outputPorts:
  - name: revenue_by_day
    version: 1.0.0
    contractId: 7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d
    inputContracts:
      - id: c2798941-1b7e-4b03-9e0d-955b1a872b32
        version: 1.0.0
```

## A contract

An ODCS file. Read from it by this package, and nothing else:

| field | read for |
|---|---|
| `apiVersion`, `kind` | that it is a `DataContract`, in a version that is read |
| `id`, `version` | that the file is the contract the port names |
| `status` | a warning when it is `deprecated` or `retired` |
| `schema[].name`, `.deprecated`, `.properties[].name`, `.properties[].deprecated` | the deprecation warning ([002/R17](002-the-verbs.md#check)) |
| `schema[]` and `properties[]`, whole | `pull --as dlt` only ([002/R12](002-the-verbs.md#pull)) |

Everything else in a contract — `servers`, `quality`, `slaProperties`, the rest — is
read by the Data Contract CLI when it tests, not by this package.

- **R6 — A contract is its `id` and its `version`.** The file a port names is the one
  whose `id` equals the port's `contractId` and whose `version` equals the port's
  `version`. A fetched file that says otherwise is refused. *(proposed)*
- **R7 — A published version does not change.** A snapshot is the bytes of the
  producer's file, committed. If the producer later changes the file without changing
  its version, `check` says so ([002/R16](002-the-verbs.md#check)). *(proposed)*
- **R8 — `deprecated` is the standard's way to retire something.** ODCS v3.2.0 adds a
  `deprecated` flag on schema objects and properties, and ODPS v1.1.0 on the product
  and its ports ([ODCS release notes](https://github.com/bitol-io/open-data-contract-standard/releases/tag/v3.2.0),
  [ODPS changelog](https://github.com/bitol-io/open-data-product-standard/blob/main/CHANGELOG.md)).
  It is the signal a consumer gets before something goes. *(standard)*

A contract, cut to what matters here:

```yaml
apiVersion: v3.2.0
kind: DataContract
id: c2798941-1b7e-4b03-9e0d-955b1a872b32
name: transactions
version: 1.0.0
status: active
schema:
  - name: transactions
    physicalType: table
    properties:
      - name: transaction_id
        logicalType: string
        required: true
        primaryKey: true
      - name: amount
        logicalType: number
        physicalType: decimal(18,2)
      - name: channel
        logicalType: string
        deprecated: true
servers:
  - server: prod
    type: databricks
    host: ${DATABRICKS_HOST}
    catalog: ${PAYMENTS_CATALOG:-payments}
    schema: gold
```

## Variables

Both standards now allow `${VAR_NAME}`, and `${VAR_NAME:-default}`, in any string value,
"resolved at runtime by tooling"
([ODCS](https://github.com/bitol-io/open-data-contract-standard/blob/main/docs/variables.md),
[ODPS](https://github.com/bitol-io/open-data-product-standard/blob/main/docs/variables.md),
RFC 0050). Tools must not put an empty string where a variable is unset, and must write
unresolved tokens back unchanged.

That spelling is also the one stevin uses for a target's variables in its own specs,
and the one an Asset Bundle uses. Three tools, one spelling, three different sets of
values: which tool resolves which file has to be written down, and it is
[002/R5](002-the-verbs.md#every-verb). Who resolves a contract's variables is the
owner's to choose ([README](README.md#still-open), 2).

- **R9 — A snapshot keeps its variables.** `pull` writes the producer's bytes. A
  `${VAR_NAME}` in the producer's contract is a `${VAR_NAME}` in the snapshot, whoever
  resolves it later. *(standard: round-trip)*

## This package's own file

`contracts.yml`, beside `dataproduct.yaml`. It says where an input port's contract comes
from, because ODPS gives a port an id to look for and no place to look.

```yaml
sources:
  transactions:                 # an input port's name
    repo: https://github.com/acme/payments
    ref: main                   # a branch, a tag or a commit; main when left out
  customers:
    path: ../customers          # a checkout beside this one
```

- **R10 — One entry per input port, by the port's name.** `repo` with an optional
  `ref`, or `path`. Not both. *(proposed)*
- **R11 — A source is a product's repository**, laid out as above: its
  `dataproduct.yaml` at the root and its contracts under `contracts/output/`. A team
  that keeps every contract in one repository points every port at it; the lookup is by
  `id` and `version`, not by folder ([002/R10](002-the-verbs.md#pull)). *(proposed)*
- **R12 — No variables in this file.** It names repositories and paths, which are the
  same in every environment. What differs per environment is in the contract's
  `servers` and is chosen with `--server`. *(proposed)*
- **R13 — Unknown keys are an error**, with the file, line and key. *(proposed)*

## Not in this spec

- Validating a whole file against the standard's JSON schema: `datacontract lint` does.
- The Data Contract Specification (the CLI's older format) and ODCS v2: not read.
- Management ports, SBOMs, teams, support channels, pricing: not read.
- A place for a consumer to say which properties it uses. A consumer is pinned to a
  contract version, whole.

## Done when

- A producer and a consumer written as above are read, and every field in the two
  tables is used by a verb or removed from the tables.
- One valid and one invalid fixture per version read (ODPS 1.0, 1.1; ODCS 3.1, 3.2),
  each invalid one refused with the file, the line and the field ([004](004-testing.md)).

# spec

What this package has to do, and how we will know that it does.

Written on 2026-10-10, before any code, as the owner asked. **Nothing is built.** The
package under `src/` holds a version number and nothing else.

The owner described the need on 2026-10-09: data mesh has its standards and Databricks
has no tooling for them; contracts should be kept somewhere, a product that consumes an
output port should be able to do something useful with its contract, contracts should
be evaluated and the results kept, and a completed run should be something another
product can build on. A first design was a store with five tables. Two outside reviews
the same day showed that the store already exists, free, three times over, and that the
one piece nobody ships is small: a consumer's gate that needs no server. The owner chose
the small piece.

## The specs

The numbers are names, not an order.

| Spec | What it covers | Status |
|---|---|---|
| [000 — what this is](000-positioning.md) | Why it exists, what is not rebuilt, who it is for | draft |
| [001 — the files](001-the-files.md) | The product file, a contract, a snapshot, `contracts.yml`; which fields are read | draft |
| [002 — the verbs](002-the-verbs.md) | `pull`, `check`, `evaluate`; the exit codes; the one seam to the Data Contract CLI | draft |
| [003 — in the data product template](003-in-the-template.md) | The files, the CI and the job a product gets | draft |
| [004 — how we know it works](004-testing.md) | The fake evaluator, the fixtures, the two-product run | draft |

## How a spec is written

As lely's and leeghwater's are.

- **Status** — draft, agreed, built, parked, superseded.
- **Why** — the problem, in a few lines.
- **Requirements** — numbered (`R1`, `R2`, …), each a thing you can check. Refer to one
  as `002/R15`. Each says where it comes from:
  - *(owner)* — the owner said it, or chose it from options put to them;
  - *(proposed)* — the writer proposes it. Not the owner's yet;
  - *(standard)* — read in ODCS or ODPS, with the link;
  - *(cli)* — read in the Data Contract CLI's docs or source, with the link;
  - *to verify* — it leans on something that has not been run.
- **Not in this spec** — what was left out on purpose.
- **Done when** — the checks that close the spec.

## Decided

By the owner, on 2026-10-09, each chosen from options after the reasoning was laid out.

- **No store.** No tables for products, ports or runs, no search, no registry, no API.
  **Git is the truth.** → [000](000-positioning.md#where-it-stands)
- **One small package: `pull`, `check`, and an optional `evaluate`** that writes to one
  table. → [002](002-the-verbs.md)
- **The Data Contract CLI does the testing**, at a version this package names, behind
  one seam. It is maintained by Entropy Data, whose product is the nearest thing to a
  competitor; the seam is why that is acceptable. → [002/R4](002-the-verbs.md#every-verb)
- **A gate that pulls.** The consumer checks before it runs. No events, no webhooks, no
  queue; Databricks' own table-update trigger is documented for anyone who wants a
  push. → [002/R18](002-the-verbs.md#check), [002/R26](002-the-verbs.md#evaluate)
- **A plain command line, with no tie to lely.** → [000/R2](000-positioning.md#what-it-does)
- **No stevin renderer.** stevin reads a contract for a table's shape itself, and says
  who may see the table in its own spec. → [003](003-in-the-template.md#the-stevin-variant)
- **Bitol's ODPS**, not the specification opendataproducts.org publishes under the same
  letters. → [000](000-positioning.md#what-exists-and-is-not-rebuilt)
- **No page.** `datacontract catalog` and Unity Catalog's own pages do the browsing.
  **No access requests or agreements.** → [000](000-positioning.md#not-in-this-spec)
- **The data product template adopts the files and the Data Contract CLI's lint, test
  and catalog**, whether or not a product uses this package.
  → [003](003-in-the-template.md)
- **The evaluation table is in Unity Catalog, or in DuckDB on a laptop.**
  → [002/R24](002-the-verbs.md#evaluate)

## Still open

Each is the owner's to answer. Each has a proposal, and the specs are written to the
proposals so they can be read as a whole. None of them is decided.

1. **The name.** `contracts` is a working name and somebody else's project on
   [PyPI](https://pypi.org/project/contracts/), so the package can't be published under
   it. Free on PyPI on 2026-10-10:
   - **`cruquius`** — after Nicolaus Cruquius (1678–1754), the surveyor who measured and
     recorded water levels and weather day after day, for decades, before anyone built
     on the numbers. A person, like the other four. *The proposal.*
   - **`odcsgate`** — says what it is, and nothing else does that. No namesake.

   The folder, the module and the command are renamed with it.
2. **Who resolves `${VAR}` inside a contract.** Both standards now allow it in any
   string ([001, Variables](001-the-files.md#variables)).
   - **(a) This package resolves nothing.** The Data Contract CLI resolves a contract's
     variables from the environment when it tests. Costs: a variable that is unset is
     reported by the CLI, in the CLI's words; and `pull --as dlt` and `--as dbt-sources`
     render whatever text the contract holds, so a variable in a table's or a column's
     name would reach the rendered file unresolved. (A variable in `servers` never
     reaches them.) *The proposal:* variables belong in `servers`, and a render that
     meets one elsewhere refuses, naming it.
   - **(b) This package resolves them** before it hands a contract to the evaluator or
     renders it. Costs: a second implementation of RFC 0050 that can disagree with the
     CLI's about order and defaults; a decision about where values come from (the
     environment, a `.env`, a secret scope); and resolved secrets in memory, and in any
     file that is written from them.

   Either way a snapshot keeps its variables as written, which the standard requires,
   and stevin never substitutes inside a contract.
3. **Where `check` reads a consumer's dependencies from.**
   - **(a) The input ports**, refusing any without `contractId` and `version`. Simple,
     and every consumer has input ports. It asks for more than ODPS v1.1.0 requires.
   - **(b) `inputContracts` on the output ports**, which the standard still keeps
     strict: `id` and `version` are both required there. Exact, but a product with no
     output port — a dashboard, a model — has none, and nothing names the port to store
     a snapshot under.
   - **(c) Both.** The input ports are what is pulled and tested, as in (a). Where an
     output port lists `inputContracts`, every entry must be an input port's contract
     and version, and a disagreement is refused. *The proposal:* the product file then
     can't say two things about what it is built from.
4. **Freshness when a contract states no service level.** *The proposal:* none. `check`
   tests what the contract says and has no clock of its own; freshness is checked when
   the contract states it. An earlier draft had "within 24 hours"; a default like that
   refuses runs for a promise nobody made.
5. **Where a contract is fetched from.** *The proposal:* the producer's own repository,
   named per input port in `contracts.yml` as a git URL with a ref, or a path
   ([001/R10](001-the-files.md#this-packages-own-file)). One contracts repository for a
   whole organisation works the same way, since the lookup is by id and version.
6. **Which versions are read.** *The proposal:* read ODCS 3.1 and 3.2 and ODPS 1.0 and
   1.1; document and write examples in the newest. Not ODCS 3.0 or 2.x, and not the
   Data Contract Specification.
7. **The Data Contract CLI as a command, not a dependency.** *The proposal:* run it as
   lely runs stevin, at a named version. Its Databricks extra caps `databricks-sdk`
   below 0.143 and brings ibis; installed beside this package it would hold back
   everything else in a project's environment, and in this repository's one lock file
   ([002/R4a](002-the-verbs.md#every-verb)). The cost is a first run that fetches it.
8. **Is `evaluate` in the first build.** *The proposal:* yes, last, and optional to use.
   It is the part with the least proof that anyone needs it.
9. **Where it lives first.** *The proposal:* here, as this package. A folder in the
   data product template would be less to maintain, but a consumer that was not made
   from the template could not install it.
10. **A port with a contract and no version.** ODPS v1.1.0 allows it. *The proposal:*
    refuse it ([002/R9](002-the-verbs.md#pull)); the alternative is "whatever the
    producer has today", which is the dependency a contract is meant to end.

## Not yet known

Three things only a run can say. They are marked *to verify* where they stand.

- Whether the Data Contract CLI and the Databricks SDK can sign in as one identity in a
  job. → [002/R27](002-the-verbs.md#evaluate)
- Whether the CLI resolves a contract's variables as RFC 0050 says.
  → [002/R5](002-the-verbs.md#every-verb)
- Whether a dlt import schema file can carry `schema_contract: freeze`.
  → [002/R12](002-the-verbs.md#pull)

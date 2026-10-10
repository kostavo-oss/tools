# 004 — how we know it works

**Status:** draft, 2026-10-10. Nothing is built.

## Why

Most of this package is deciding what a result means. That can be tested without a
workspace, as long as what the Data Contract CLI would have answered can be put in by
hand. The few things that can't are listed, so nobody reads a green run as more than it
is.

## Without a workspace

- **R1 — A fake evaluator.** The one seam ([002/R4](002-the-verbs.md#every-verb)) has a
  fake that answers *test*, *breaks* and *export* with what a test tells it to. Every
  rule in 002 is tested against it. The fake is loud: a call a test did not prepare
  fails, it does not pass. *(proposed)*
- **R2 — Fixtures per version.** For each version read — ODPS v1.0.0 and v1.1.0, ODCS
  v3.1.0 and v3.2.0 — one valid file and one invalid one, the valid ones taken from the
  standards' own examples where there is one. An invalid file is refused with the
  file, the line and the field. *(owner)*
- **R3 — Sources on disk.** `path` sources are folders in a temp directory; `repo`
  sources are git repositories made there, so `ref` is tested with real branches and
  tags and no network. *(proposed)*
- **R4 — The table in DuckDB.** `evaluate --to file.duckdb` is the real writer, read
  back in the test. *(proposed)*
- **R5 — The exit codes**, one test per code per verb. *(proposed)*
- **R6 — The CLI's answers are pinned.** The real evaluator is tested against recorded
  output of the CLI version this package names, for a passing test, a failing one, a
  breaking change and a harmless one. Naming a new CLI version means recording again.
  *(proposed)*

## With the real CLI, and no workspace

- **R7 — DuckDB end to end.** The CLI tests DuckDB. One suite runs the real CLI against
  a DuckDB file that plays the producer's table: `check` passes, the table loses a
  column, `check` refuses. It is slow and needs the network once, to fetch the CLI;
  it runs in CI on a change to this package and nightly. *(proposed)*

## On the test workspace

Needs the `databricks-test` environment, as stevin's live suite does.

- **R8 — Two products.** A producer and a consumer made from the data product template,
  each in a scratch schema that is dropped afterwards:
  1. the producer deploys, runs, and `evaluate` writes a row;
  2. the consumer pulls, and `check` passes;
  3. a column is dropped from the producer's table by hand: `check` refuses, exit 2;
  4. the column is put back and the producer marks the port version deprecated:
     `check` warns, exit 0;
  5. the producer removes the port version: `check` refuses, exit 2.

  A script, not a session by hand. *(owner)*
- **R9 — What only the workspace can say:** that the CLI and the SDK can sign in as one
  identity in a job ([002/R27](002-the-verbs.md#evaluate)); that the CLI resolves a
  contract's variables there ([002/R5](002-the-verbs.md#every-verb)); that the table is
  written through a warehouse; that the table-update trigger starts a consumer.

## Not in this spec

- Testing the Data Contract CLI: its checks are its own.
- Load, timing, or many products at once.
- Private repositories as sources: git's own credentials are trusted to work.

## Done when

- R1 to R6 run in this repository's gate, on every Python it supports.
- R7 runs in CI.
- R8 has run once on the test workspace, and what it showed is written here under
  "Run on a workspace", with what it could not show.

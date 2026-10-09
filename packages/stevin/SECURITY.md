# Security Policy

## How stevin handles your workspace

- **No credentials are stored.** Authentication is delegated entirely to the
  Databricks SDK's unified auth (`~/.databrickscfg` profiles, OAuth token cache, or
  `DATABRICKS_*` environment variables). stevin never writes a token anywhere.
- **No state file.** Unity Catalog is the state. There is no local artefact holding
  a copy of your schema, and nothing to leak or drift.
- **Plans are inert, and three commands write.** `stevin plan` only reads
  (`information_schema`, `DESCRIBE DETAIL`, `DESCRIBE HISTORY`, `SHOW CREATE TABLE`,
  `SHOW TBLPROPERTIES`), and so do `drift`, `import`, `adopt` and `doctor`. A
  statement that changes one of your tables is executed by `apply` and nowhere
  else: from a saved plan that was reviewed first, or — without a plan file — from
  a plan it makes on the spot, shows, and asks about before it runs (`--yes` skips
  the question, so then nobody has read it). `apply` also keeps its run history
  and its lock in the `history_schema`, where `force-unlock` can release the lock.
  `verify` writes too, in a scratch schema of its own and nowhere else: it creates
  the schema, makes tables, views and functions in it, and drops it.
- **Identifiers are always quoted.** SQL is never assembled by concatenating raw
  identifiers; one `quote_ident()` helper handles every name that reaches a
  statement.
- **Safe by default.** Only tables stevin created (`deltaplan.managed = true`) can
  ever be drop candidates; everything else is reported as unmanaged and left
  untouched. Destructive steps require `--allow-destructive`, and `apply` refuses a
  stale plan whose state fingerprint no longer matches the live tables.

Plans and the history tables record the SQL that was run, including column names and
table comments. Treat plan JSON as you would a schema dump — it can contain
business-sensitive names. The one kind of data in it is a seed's rows: they are in the
plan as they are in your repository.

## Supported versions

The latest released version on PyPI is supported. Please upgrade before reporting an
issue.

## Reporting a vulnerability

Please report security issues **privately**:

- Open a [GitHub Security Advisory](https://github.com/kostavo-oss/tools/security/advisories/new), or
- email **info@kostavo.com**.

Do not open a public issue for security reports. You'll get an acknowledgement as
soon as possible, and we'll coordinate a fix and disclosure with you.

# Troubleshooting

- **Deleting the DuckDB file does not start a pipeline over.** dlt keeps a pipeline's state
  outside the database, under `~/.dlt/pipelines/<name>/`. Delete that folder too.
- **`import dlt` gives Delta Live Tables.** Databricks has a module of its own named `dlt`.
  In a serverless job a plain `import dlt` gets the right one. In a notebook or on a
  cluster, call `leeghwater.prepare()` before `import dlt`. The first lines of a run say
  what was done about the name.
- **The pipeline and its schema have the same name, and DuckDB refuses.** DuckDB names its
  database after the file, `<pipeline>.duckdb`, and can't tell a schema of that name from
  it. Locally, give the schema another name or leave it out.
- **A load from a job is refused a connection to `…storage.cloud.databricks.com`.** dlt
  uploads its files to a volume before it copies them into a table. A workspace whose
  serverless compute has a limited outbound network refuses that upload.
- **`ingest doctor`** says where a run would load and checks the sign-in, each secret scope
  and the warehouse, without running anything. `--json` for a machine.

# Tried, and not yet

On 2026-10-07 a project made by `leeghwater init` was deployed to a workspace as a bundle
and run, and the same project was run from a laptop with a profile.

Held, for real:

- a bundle made from the former `leeghwater init` validates, deploys and destroys, and the
  job's entry point is the project's own command;
- the job is told the deployed names of the bundle's schemas, and finds the `config.toml`
  its wheel carries;
- a pipeline that raises fails its task;
- a secret scope is read as the job's identity and from a laptop, and a secret is redacted
  in the job's output;
- from a laptop, a load into Unity Catalog; and with schemas named with two underscores, a
  load into exactly those, with no third schema made.

Not yet:

- **a full load from a serverless job.** The workspace it was tried on limits the outbound
  network of serverless compute, and dlt's upload to storage was refused. Everything before
  the upload ran;
- a notebook and a classic cluster, which is where the name `dlt` is said to bite;
- the job's `ingest` task with leeghwater installed from PyPI, which 0.1.0 makes possible.

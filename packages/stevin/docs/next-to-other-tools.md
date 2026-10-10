# Next to other tools

stevin puts in place the tables and access that your transformation tool doesn't own.
That sentence has a line in it, and this page draws it once per tool: what the other
tool builds is the other tool's; what it reads, and what it leaves to a setup job, is
stevin's. The [project file](spec.md#whose-tables-are-whose) is where you tell stevin
which is which.

## dbt

**dbt's tables are dbt's: models, seeds, snapshots.** stevin's are the tables dbt reads —
raw, landing, reference — and whatever dbt leaves alone.

- A spec for a table dbt builds is refused, at `validate` and at `plan`, with the file
  and line. Not governed, not shaped: dbt's own `grants` config replaces the grants it
  doesn't list, its `databricks_tags` add tags, and a `table` materialisation recreates
  the table, which drops a mask or a row filter stevin set. Two writers would fight every
  run, so there is one.
- Grants and tags on dbt's tables go in dbt's config. Masks on dbt's tables go in a
  schema-level ABAC policy, which keys off tags and survives a recreate —
  [a recipe](access-recipes.md#pii-columns-by-tag).
- Tell stevin what dbt builds by pointing at the manifest, and it reads the names of
  every model, seed and snapshot (`database.schema.alias`); ephemeral models are skipped,
  sources are never owners:

  ```yaml
  dbt:
    manifest: ../analytics/target/manifest.json   # relative to stevin.yml
  owned_elsewhere:
    ${catalog}.silver.*: dbt                        # or say it by pattern
  ```

  An exact name from the manifest wins over a pattern. A manifest that isn't there is an
  error naming the path: run dbt first.
- **Order in CI:** `stevin apply` before `dbt run`, because the sources have to exist.
- `import` skips dbt's tables and says so; `drift` and a plan list them as *dbt's*, not
  as unmanaged.

## dlt, and leeghwater

**A dlt pipeline's landing tables are dlt's.** stevin never shapes them, and can govern
them.

- A schema that holds dlt's own `_dlt_loads` and `_dlt_version` tables is a dlt dataset,
  every table in it. That is a heuristic — a schema someone copied `_dlt_loads` into
  would pass — and `owned_elsewhere` can override it for a name.
- The PII in a landing table gets its tags, grants, masks and row filter from a
  [governance-only spec](spec.md#a-governance-only-spec): the columns by name, no types.
  stevin lays it over the live table, changes governance only, and never claims,
  reshapes or drops the table. A column or table the spec names that isn't there yet
  stops the plan: the pipeline makes it first.
- `import` writes that spec for you, with what the table already carries.
- [leeghwater](https://kostavo-oss.github.io/tools/leeghwater/) runs the same dlt
  pipeline on a laptop and in a Databricks job; the tables it lands are read by what
  comes next, which is where stevin starts.

## Lakeflow Declarative Pipelines

**A pipeline owns its streaming tables and materialized views.** stevin owns the tables
the pipeline reads, and ordinary tables a sink writes into.

- Streaming tables and materialized views are listed as skipped and never managed;
  `import` passes them over.
- Name them in `owned_elsewhere` with the pipeline as the owner, so `drift` and a plan say
  whose they are rather than *unmanaged*. stevin has no detector for a pipeline's tables
  (there is an issue for one, not built).
- A pipeline that streams from a stevin table needs it first: `stevin apply`, then the
  bundle deploy, then the pipeline update. Enabling column mapping on a table — a rename
  needs it — breaks streaming readers, and the plan says so where it happens; the
  pipeline needs a full refresh after that apply.
- Expectations, `AUTO CDC`, and a pipeline table's own properties live in the pipeline's
  code, not in a spec.

## SQLMesh

No manifest is read. Name what SQLMesh builds in `owned_elsewhere` by pattern, with
`sqlmesh` as the owner, and stevin refuses to shape those names and reports them as
SQLMesh's. Governance-only specs work on them as on any owned table; whether SQLMesh's
own materialisation keeps a mask across a rebuild is SQLMesh's documentation to answer.

## Asset Bundles

**What the bundle declares is the bundle's**: catalogs, schemas, volumes. stevin takes the
bundle's targets, workspaces and variables, names things the way a deploy would, and
leaves the declared containers alone — a spec for one is an error.
[With an Asset Bundle](bundles.md) has the whole story.

## Terraform

**The platform is Terraform's**: catalogs, groups and service principals, governed tags,
and ABAC policies. stevin doesn't create any of those. A spec names principals Terraform
or your identity provider made, and tags whose keys an account admin governs.

ABAC policies are written in Terraform or SQL, never by stevin. Reading them — the
policies that apply to a table, shown in the plan, in `drift`, and in an access report —
is planned, not built.

## Data contracts

A producer who wrote an [ODCS](https://bitol-io.github.io/open-data-contract-standard/)
contract has already said what the table looks like; a spec can take its shape from the
contract and add only governance and layout:
[Shape from a data contract](spec.md#shape-from-a-data-contract). stevin reads the
contract for the shape and nothing else. Testing live data against a contract, and
telling a breaking change from a safe one, is what the
[Data Contract CLI](https://github.com/datacontract/datacontract-cli) does; stevin
doesn't, and the two meet at the file.

## Notebooks

The tables a notebook writes into are exactly what stevin is for: declared once, created
by stevin, written by the notebook, their drift seen nightly and adopted on purpose.
[Tables your notebooks write](tables-your-notebooks-write.md) walks through that loop.

## The order of a deploy

1. `databricks bundle deploy` — the containers, the code, the jobs.
2. `stevin apply` — the tables and access, from a plan that was reviewed.
3. The jobs: dbt, the pipeline, the notebooks.

In CI that is the [GitHub Action](ci.md) or a [lely](https://kostavo-oss.github.io/tools/lely/)
step. Where CI can't reach the workspace, step 2 runs as a job task from the same plan
file: [Running from a job](running-from-a-job.md).

## What stevin refuses

The sentences, as the code says them:

- A spec for a dbt table: *`<name>` is dbt's: put grants and tags in dbt's config, and
  use a schema-level policy for masks*.
- A spec with types for a table someone else owns: *`<name>` is dlt's: leave the
  columns' types out to govern it (tags, grants, masks, a row filter), or take it out of
  owned_elsewhere*.
- A spec without types for a table nobody owns: *`<name>` has no columns' types, so it
  governs a table another tool makes — but nothing says whose it is: say the columns, or
  name the owner in owned_elsewhere*.
- A function spec nothing names: *a function spec is only for a column mask or row
  filter; general SQL functions belong to your transformation tool*.
- A spec for a schema, catalog or volume the bundle declares: see
  [what stevin won't touch](bundles.md#what-stevin-wont-touch).

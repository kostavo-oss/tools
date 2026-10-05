# 000 — what lely is

**Status:** draft. Everything below except [To decide](#to-decide) restates `docs/DESIGN.md`
(Why, Goals, Non-goals); the scope itself is waiting on a decision.

## In one line

One `plan` and one `apply` for a whole Databricks deploy: the steps before the bundle, the bundle,
and the steps after it.

## Who it is for

A team that deploys with a Declarative Automation Bundle (`databricks.yml`) and has things a
bundle can't deploy: table schemas, what is inside a database, a job that has to run between two
other things, a lookup the bundle needs as a variable. Today those live in shell scripts around
`bundle deploy`, and nobody reviews them before they run.

## What it does

- **R1 — One plan.** Every step's changes and the bundle's own, in one plan that can be read in a
  terminal, saved as a file, and posted as one pull-request comment. *(design: Goals)*
- **R2 — One apply.** Pre steps, then `bundle deploy`, then post steps, in the order written.
  What a step produces is available to the steps after it. *(design: Goals)*
- **R3 — Nothing changes at plan time.** `plan` can run on every pull request. *(design: step
  rules)*
- **R4 — A destructive change is named, and refused unless allowed.** Deleting, replacing or
  dropping data shows as destructive in the plan, and `apply` won't do it without
  `--allow-destructive`. *(design: step rules)*
- **R5 — A second apply finishes an interrupted one.** There is no rollback and no history; each
  system a step touches is its own state. *(design: Failure model)*
- **R6 — A step is small and yours to write.** A Python class in the repo, an installed package,
  or a pair of commands — all under the same rules as the built-in steps. *(design: The step
  interface)*
- **R7 — The bundle stays the bundle.** lely asks the Databricks CLI what a bundle resolves to and
  never works it out itself. Pre steps feed the bundle variables, nothing else. *(design: Goals,
  Non-goals)*
- **R8 — Tables are stevin's.** The built-in `stevin` step runs the `stevin` command and reads its
  plan file. stevin is not a dependency: a project without tables never installs it. *(design:
  Built-in steps)*

## What it does not do

From the design's non-goals, unchanged:

- anything a bundle resource can manage — when a resource type appears, the step that covered it
  is retired
- generate YAML for the bundle to include
- be a workflow engine: three ordered lists, no DAG, no parallel steps, no retries
- roll back
- build artifacts
- keep a state file or a run history
- support the Terraform engine — the direct engine is required
- `bundle destroy` and teardown, in v1
- CI systems other than GitHub Actions, in v1

## v1

Three milestones, in order: [read-only](001-read-only.md) (built), [apply](002-apply.md),
[CI](003-ci.md). After v1, and only written down so v1 doesn't block them: Lakebase schemas and
MLflow steps (design: Later).

## To decide

- **D1 — Is this still the product?** The setup plan for the Kostavo tools (2026-10-05) describes
  lely as "better Databricks Asset Bundle deployments", says to *port the existing bundle tooling*
  into it with anything client-specific replaced by config, and calls it done at "feature parity
  with the old tooling for the generic parts". The design above was written a week earlier, under
  the name sluis, without that tooling in view — and the tooling isn't in this repository or next
  to it, so nothing here says what it does.

  Three ways this can go:

  1. *The design is the product.* The old tooling was the motivation, not a feature list. Nothing
     changes here.
  2. *The design, plus specific things the old tooling does.* Each becomes a requirement here, or
     a built-in step with its own spec.
  3. *The old tooling is the product* and the design bends to it. Then 002 and 003 wait until this
     spec is rewritten.

  Until this is answered, 002 is written against the design.

- **D2 — What comes right after v1?** The design lists Lakebase schemas and three MLflow steps as
  "later" without an order. Which one is first decides what 002 must not close off.

## Done when

D1 is answered and this page says, without a "to decide", what lely is for.

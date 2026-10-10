# One product, end to end

On 10 October 2026 a data product was made from
[the template](https://github.com/kostavo-oss/data-product-template), pushed to a
repository of its own, deployed to a Databricks workspace from a reviewed plan, broken on
purpose, and taken down again. Nothing in it was edited by hand. This page says what
happened at each step, in the tools' own output, and what did not hold.

It is one run, in one private repository, against a test workspace. It is evidence, not a
benchmark.

## What was made

```sh
uvx copier copy --defaults gh:kostavo-oss/data-product-template data-product-proof
```

With the defaults that is a Databricks Asset Bundle with three schemas and one job; a dlt
pipeline that lands the data, run by [leeghwater](leeghwater/index.md); a dbt model that
shapes it; a data contract for the table the product promises; and three GitHub
workflows: one that checks every change, one where [lely](lely/index.md) plans the deploy
on a pull request, and one that applies that plan on merge.

The repository then got three settings, and nothing else: the workspace's address and a
warehouse id as variables, and a token as a secret.

## 1. The first push

The product's own check ran on a clean GitHub runner and passed:

- the tools were installed as the product lists them;
- the lint, the format check and the contract lint passed;
- the example pipeline ran into a local database file, with no workspace involved.

One workflow failed, and was meant to. `apply` only applies a plan that was reviewed on a
pull request, and a first push comes from none:

```text
This commit came from no pull request: no plan was reviewed.
```

That is the rule working. It is also a red cross on a product's first day, so the
product's README now says so, and that the first pull request puts it right.

## 2. A pull request, and the plan on it

The first pull request changed one file. lely planned the deploy of the `dev` target and
posted the plan as a comment:

```diff
lely plan · target dev

4 changes · 1 run · 0 destructive

  bundle  bundle
+     create   jobs.data_product_proof
+     create   schemas.raw
+     create   schemas.raw_staging
+     create   schemas.silver
      run      uploads the bundle's files
```

A reviewer reads that before anything exists: one job, three schemas, nothing destroyed.

## 3. The merge, and the same plan applied

On merge, the `apply` workflow found the pull request the commit came from, fetched the
plan that was made for its last commit, and applied that file. It did not plan again.
What ran is what was read.

The job and the three schemas were then in the workspace.

## 4. A promise broken on purpose

The product's contract says its table has three columns. A second pull request removed
one of them from the published version of the contract, as someone would who renames a
column and forgets who reads it.

The check failed, with the reason and the remedy:

```text
contracts/output/squares/v1.odcs.yaml: a breaking change needs a new version,
v2.odcs.yaml beside it: a published version is not edited.

│ ERROR │ Removed │ schema.squares.properties.root │ Removed property root │

contracts/output/squares/v1.odcs.yaml: breaking
```

The comparison itself is the
[Data Contract CLI](https://github.com/datacontract/datacontract-cli)'s. The product only
knows which files to compare, and that a published version is never edited. The pull
request was closed without merging.

## 5. Taken down again

A destroy is a plan too. lely showed it, and then ran it:

```text
lely destroy plan · target dev

    - jobs.data_product_proof  destructive
    - schemas.raw  destructive
    - schemas.raw_staging  destructive
    - schemas.silver  destructive

Destroy plan: 4 changes · 0 runs · 4 destructive
```

Nothing was left in the workspace.

## What did not hold, and what was not tried

- **The job was not started.** Its first task loads data through dlt, and on the test
  workspace that cannot finish: serverless compute there is refused the connection to
  the storage address the load uploads to. Everything up to the deploy held; the run of
  the job itself is still to be shown on a workspace without that rule.
- **Not tried:** the `prod` target, and keeping a source's secret in a scope with
  [caland](caland/index.md).
- **Found by doing it:** the product's ignore file did not cover `.env`, where a
  developer keeps a token for local commands. It showed as an untracked file, one
  careless command away from being committed. The template ignores it now.

## What it shows

Nobody wrote a deploy script, a setup notebook or a workflow for this product. The plan
was read before it ran, the thing that ran was the thing that was read, a broken promise
was caught before it merged, and the whole of it could be removed again by name. Those
are the gaps [the tools are for](why.md), closed by answering a few questions.

What a team would do next is theirs: real sources in place of the example, real models,
and a contract that says what they promise. The template's own record of what has been
tried, and what has not, is in its
[spec](https://github.com/kostavo-oss/data-product-template/blob/main/spec/README.md).

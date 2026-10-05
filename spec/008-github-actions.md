# 008 — GitHub Actions

**Status:** draft; its scope is decided. Phase two.

## Why

A plan is reviewed where code is reviewed: on the pull request. Until lely puts its plan there —
and keeps it current as the branch changes — the one plan for the whole deploy is something
people have to go and fetch from a log.

## Requirements

The owner's "a way to update GitHub Actions" means: **update what GitHub shows** (decided
2026-10-05). So:

- **R1** — `lely plan -f md` and `lely show plan.json -f md` render a plan as Markdown, from the
  same plan the terminal, the JSON file and the page show. A destroy plan renders the same way.
  *(design)*
- **R2 — The pull request is kept up to date.** On a pull request, the plan is posted as one
  comment that covers every step, and that comment is *updated* on later pushes instead of
  another being added. One comment per target. *(owner)*
- **R3 — The run's page is kept up to date.** The plan goes to the job summary; after an apply,
  so does what each step did and the overview of what now exists
  ([004/R7](004-asset-bundle.md)), with links into the workspace. A run can be read without
  opening its log. *(owner)*
- **R4 — lely does this itself.** A project adds it to the workflow it already has; there is
  nothing separate to install or to keep in step with lely's version. How it is asked for is
  [D4](#to-decide). *(follows from the owner's answer: no ready-made Action was asked for)*
- **R5** — Outside a GitHub Actions run, or without permission to comment, it says what it
  couldn't do and why, and the plan itself still succeeds or fails on its own merits.
  *(proposed)*
- **R6** — The token is never printed and never written to a plan, a comment or a summary.
  *(proposed)*
- **R7 — The docs carry a workflow to copy:** plan on a pull request, apply on merge, destroy
  only when started by hand with the target named — with the `concurrency:` group that keeps two
  runs for one target from overlapping, and with no input pasted into a script as text.
  *(design, as an example instead of an Action)*

## Not in this spec

Asked on 2026-10-05, and not chosen:

- **Writing the workflow files.** lely does not generate or rewrite `.github/workflows/…`.
- **A ready-made Action** (`uses: kostavo-oss/lely@v1`) with a moving version tag.

Also not here: CI systems other than GitHub Actions; a lock of lely's own.

## Decided

- **What "update GitHub Actions" means** (was D1): what GitHub shows — the pull-request comment
  and the job summary. *(owner, 2026-10-05)*

## To decide

- **D4 — How a project asks for it.** A flag on the commands it already runs
  (`lely plan -t dev --github`), or on by itself whenever lely notices it is inside a GitHub
  Actions run? *(proposed: the flag. Something that posts to a pull request shouldn't happen
  because of where a command was run.)*
- **D2 — Which plan does `apply` run on merge,** in the workflow the docs show? The file the pull
  request produced, kept as an artifact — so what runs is exactly what was reviewed, and a stale
  one is refused — or a new plan made on `main` with `--yes`? With the file, a first deploy that
  has a waiting step takes two runs ([005/R22](005-plan-apply-destroy.md)); with `--yes`, one
  ([005/R23](005-plan-apply-destroy.md)).
- **D3 — A pull request from a fork** has no credentials. Skip quietly, or say so in the job
  summary?

## Done when

- R1–R7 each have a test; posting and updating a comment is tested against a fake GitHub, the way
  stevin tests its own.
- A pull request in a real repository has carried a plan comment that changed in place, and a
  merge has left a summary of what was created.
- D2–D4 are answered here.

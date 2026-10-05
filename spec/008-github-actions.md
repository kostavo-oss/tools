# 008 — GitHub

**Status:** agreed, 2026-10-05, except one question ([D2](#to-decide)); not started. Phase two.

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
  another being added. One comment per target. lely finds its own comment by a marker it puts
  in it — the memory is GitHub's, not lely's. *(owner; the marker is how stevin does it)*
- **R3 — The run's page is kept up to date.** The plan goes to the job summary; after an apply,
  so does what each step did and the overview of what now exists
  ([004/R7](004-asset-bundle.md)), with links into the workspace. A run can be read without
  opening its log. *(owner)*
- **R4 — lely does this itself, when asked.** A project adds `--github` to the commands its
  workflow already runs (`lely plan -t dev --github`); there is nothing separate to install or to
  keep in step with lely's version. It is never on just because of where a command was run.
  *(follows from the owner's answer: no ready-made Action was asked for; the flag is agreed)*
- **R4a — A pull request from a fork gets no plan, and is told so.** It has no credentials and
  must not be given any: its code would run with them. The job summary says the plan was
  skipped, and why. *(agreed)*
- **R5** — Outside a GitHub Actions run, or without permission to comment, it says what it
  couldn't do and why, and the plan itself still succeeds or fails on its own merits.
  *(agreed)*
- **R6** — The token is never printed and never written to a plan, a comment or a summary.
  *(agreed)*
- **R7 — The docs carry a workflow to copy:** plan on a pull request, apply on merge, destroy
  only when started by hand with the target named — with the `concurrency:` group that keeps two
  runs for one target from overlapping, with no input pasted into a script as text, and with
  the plan job given credentials that can only read — planning runs the pull request's own code
  ([002/R13a](002-plugins.md)). *(design, as an example instead of an Action; the last part was
  found in review)*

## Not in this spec

Asked on 2026-10-05, and not chosen:

- **Writing the workflow files.** lely does not generate or rewrite `.github/workflows/…`.
- **A ready-made Action** (`uses: kostavo-oss/lely@v1`) with a moving version tag.

Also not here: CI systems other than GitHub Actions; a lock of lely's own.

## Decided

- **What "update GitHub Actions" means** (was D1): what GitHub shows — the pull-request comment
  and the job summary. *(owner, 2026-10-05)*
- **How a project asks for it** (was D4): a `--github` flag — R4.
  *(owner, 2026-10-05: go with the proposals)*
- **A pull request from a fork** (was D3): no plan, and the job summary says so — R4a.
  *(owner, 2026-10-05: go with the proposals)*

## To decide

- **D2 — Which plan does `apply` run on merge,** in the workflow the docs show? The file the pull
  request produced, kept as an artifact — so what runs is exactly what was reviewed, and a stale
  one is refused — or a new plan made on `main` with `--yes`? With the file, a first deploy that
  has a waiting step takes two runs ([005/R27](005-plan-apply-destroy.md)); with `--yes`, one
  ([005/R28](005-plan-apply-destroy.md)).

## Done when

- R1–R7 each have a test; posting and updating a comment is tested against a fake GitHub, the way
  stevin tests its own.
- A pull request in a real repository has carried a plan comment that changed in place, and a
  merge has left a summary of what was created.
- D2 is answered here.

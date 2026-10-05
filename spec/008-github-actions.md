# 008 — GitHub Actions

**Status:** draft. Phase two. Its first question, [D1](#to-decide), decides what this spec is.

## Why

A plan is reviewed where code is reviewed: on the pull request. And a deploy that only runs from
a laptop isn't a deploy process. The owner's direction names "a way to update GitHub Actions";
what follows is the part of that which the design already had, with the open reading kept open.

## Requirements

- **R1** — `lely plan -f md` and `lely show plan.json -f md` render a plan as Markdown, from the
  same plan the terminal, the JSON file and the UI show. *(design)*
- **R2** — A GitHub Action, in this repository, that runs `plan`, `apply` or `destroy` for a
  target. *(design, with destroy added)*
- **R3 — It keeps the pull request up to date.** On a pull request, `plan` posts one comment that
  covers every step, and *updates* that comment on later pushes instead of adding another. One
  comment per target. *(design)*
- **R4 — It keeps the run's page up to date.** The plan, and after an apply the overview of what
  was created ([004/R7](004-asset-bundle.md)), go to the job summary, so a run can be read
  without opening its log. *(proposed)*
- **R5** — On merge, `apply` runs. Which plan it runs is [D2](#to-decide).
- **R6** — `destroy` never runs on its own: only when someone starts the workflow by hand and
  names the target. *(proposed)*
- **R7** — No input is put into a script as text: values reach it through the environment, and a
  test enforces that, as in stevin. *(design)*
- **R8** — The Action installs lely from its own checkout, so the Action and the tool are always
  the same version. *(proposed — it is how stevin's does it)*
- **R9** — The docs show the `concurrency:` group that keeps two runs for one target from
  overlapping. *(design)*

## To decide

- **D1 — What "update GitHub Actions" means.** Three readings, and they are different pieces of
  work:
  1. *Update what GitHub shows* — the pull-request comment and the job summary. That is R3 and
     R4 above.
  2. *Update the workflow files* — lely writes `.github/workflows/…` for a project from its
     config, and rewrites them when the config changes: a `lely ci` command, say. Then adding a
     step or a target never means editing YAML by hand.
  3. *Keep the Action itself current* — a moving `v1` tag, as stevin has `v0`, so `uses:
     kostavo-oss/lely@v1` follows releases.

  This spec covers 1 and assumes 3. If 2 is what was meant, it is a spec of its own: say so and
  it becomes 010.
- **D2 — Which plan does `apply` run on merge?** The file the pull request produced, kept as an
  artifact — so what runs is exactly what was reviewed, and a stale one is refused — or a new
  plan made on `main`? The first is stricter and has to find the artifact again; the second is
  simpler and runs something nobody looked at.
- **D3 — A pull request from a fork** has no credentials. Skip quietly, or say so in the job
  summary?

## Not in this spec

- CI systems other than GitHub Actions
- A lock of lely's own

## Done when

- R1–R9 each have a test; the Action's script is tested the way stevin's is, with the commands
  stubbed.
- A pull request in a real repository has carried a plan comment that changed in place, and a
  merge has applied it.
- D1–D3 are answered here.

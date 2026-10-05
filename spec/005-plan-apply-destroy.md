# 005 — plan, apply, destroy

**Status:** draft. Phase one. `plan` is built; `apply` and `destroy` are not started — every
plugin's `apply` raises "apply is milestone 2" today.

## Why

This is the half of lely that changes a workspace, so it is where the safety rules stop being
promises and become code. And `destroy` is the one verb that can't be taken back.

## Requirements

### `plan`

- **R1** — `lely plan -t <target>` plans every step in order and changes nothing. It can be
  written to a file with `-o`. *(built)*
- **R2** — A plan file records what it was made from: lely's version, and a hash of the config
  and of every step's resolved options. *(built)*

### `apply`

- **R3** — `lely apply plan.json` runs a plan that was saved and reviewed. `lely apply -t
  <target>`, without a file, plans, shows the plan, asks, and then runs. `--yes` skips the
  question. *(design)*
- **R4** — A plan file is refused when the config, or any step's resolved options, differ from
  what it was planned with. The message says which, and to plan again. *(design)*
- **R5** — Steps run in the order written. A step whose `targets:` leaves this target out is
  skipped, and the result says so. *(design)*
- **R6 — The approval check.** Each step is planned again immediately before it runs. It may run
  only if every change in the new plan matches an approved one, and none has become destructive.
  Fewer changes is fine — someone else did part of the work. Anything new stops the run and asks
  for a new plan. *(design)*
- **R7** — `apply` refuses a destructive change without `--allow-destructive`. Where the plan
  already shows one, the refusal comes before anything runs. *(design)*
- **R8** — When it is done, `apply` shows what each step did and, from every plugin that can, the
  overview of what now exists ([002/R6](002-plugins.md)). *(owner)*

### `destroy`

- **R9** — `lely destroy -t <target>` plans the destroy, shows it, asks, and then runs. The plan
  lists, per step, what would be removed. *(owner)*
- **R9a — At a terminal, the answer is the target's name.** Not `y`: the name, typed, so that
  `prod` is never destroyed by a reflex. *(owner, 2026-10-05)*
- **R9b — Without a terminal, consent is given in the command.** `lely destroy -t <target> --yes`
  runs without asking — for a pipeline, where nobody can. It needs the target spelled out with
  `-t`; there is no default target to destroy. *(owner, 2026-10-05)*
- **R10** — Steps are destroyed in the reverse of the order they are applied in: what was made
  last goes first. *(proposed)*
- **R11** — A step with nothing to destroy — one that only runs something — is listed as
  skipped, with the reason. *(proposed; see [002/D3](002-plugins.md#to-decide))*
- **R12** — The approval check of R6 holds for a destroy as well: each step is planned again
  before it is destroyed, and anything that wasn't in the approved plan stops the run.
  *(proposed)*
- **R13** — Destroying a target that has nothing deployed does nothing, and says so. *(proposed)*

### Consent

- **R13a — Nothing that changes a workspace runs unasked.** `apply` and `destroy` either ask, or
  were given `--yes` in the command. With no terminal and no `--yes` they refuse, and the message
  names the flag: a forgotten flag is a failed job, never an unreviewed deploy.
  *(owner, 2026-10-05, for destroy; the same rule is applied to apply)*

### When something fails — apply and destroy alike

- **R14** — The first failing step stops the run. Nothing after it starts. The result names what
  ran, what failed and what never started, and the exit code is not zero. *(design)*
- **R15** — Running the same command again finishes the job: a step that already did its work
  plans as nothing to do. `--from <step>` starts at a named step, for getting past one that
  *runs* something every time. Resuming is always asked for, never inferred. *(design)*
- **R16** — There is no rollback. A failure half-way leaves what was done, done, and the result
  says so in those words. *(design)*

### On demand

- **R17** — A command that changes nothing and shows the overview of every step for a target —
  what is deployed right now, in detail. *(proposed, from the owner's "detailed overview"; the
  name is [D5](#to-decide))*
- **R18** — `lely doctor` reports whether each plugin's tool is installed and usable (the
  Databricks CLI and its engine, a `command` step's executable) and whether the target
  can be reached. It changes nothing. An error message in the code already points at it.
  *(design)*

### Secrets

- **R19** — A secret in a step's outputs is never written anywhere and never printed; it is
  fetched again when it is needed. *(built for plan)*

## Not in this spec

- What each plugin does when applied or destroyed → [004](004-asset-bundle.md)
- Markdown output, the pull-request comment → [008](008-github-actions.md)
- A lock against two runs at once: for now a CI concurrency group does that job

## Decided

- **No terminal and no `--yes`** (was D1): refuse — R13a. *(owner, 2026-10-05)*
- **What it takes to destroy** (was D2): at a terminal, typing the target's name; headless,
  `--yes` in the command with the target spelled out — R9a and R9b. No flag in the config, and
  `--allow-destructive` plays no part in a destroy: everything in one is destructive.
  *(owner, 2026-10-05)*

## To decide

- **D3 — A destroy plan as a file.** For apply there is `plan -o` and `apply plan.json`, so that
  what runs is what was reviewed. The same for destroy — `lely plan --destroy -o plan.json`, then
  `lely apply plan.json` — or is destroy always run in one go? *(proposed: the same; one file
  format, and a destroy can be reviewed in a pull request like anything else)*
- **D4 — A step that could only be planned at apply.** It was approved as "decided at apply",
  without its changes. When it is finally planned: run it straight away, or — when there is a
  terminal — show that part and ask once more?
- **D5 — The name of R17.** `lely status`, `lely overview`, `lely show -t <target>`?
- **D6 — Exit codes.** *(proposed)* 0 done; 1 a step failed; 2 refused before or between steps —
  a stale plan, a change that wasn't approved, a destructive change that wasn't allowed. A
  pipeline can then tell "plan again" from "something broke".
- **D7 — What has to be proven on a workspace.** lely has no live tests, and this is the first
  work that changes anything. Which of these must have run for real before this is called done:
  a first deploy, a second apply after a failure, a refused stale plan, a destroy, a destroy
  after a failed destroy? And on which workspace — stevin's test workspace is the obvious one,
  and its token has expired.

## Done when

- R1–R19 each have a test, against fake tools.
- Whatever D7 names has run on a workspace.
- The README no longer says lely "shows you a whole deploy and runs none of it".
- D3–D7 are answered here.

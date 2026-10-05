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
- **R11** — A step with nothing to destroy — one that only runs something — is listed in the
  destroy plan as skipped, with the reason, and the rest is destroyed.
  *(owner, 2026-10-05; [002/R8a](002-plugins.md))*
- **R11a — A destroy can be saved and reviewed first, like an apply.**
  `lely plan -t <target> --destroy -o destroy.json` writes it, `lely show` renders it, and
  `lely apply destroy.json` runs exactly that. One file format for both; a destroy can go through
  a pull request. *(owner, 2026-10-05)*
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

### A step that can't be planned yet

*A plan reaches as far as lely can see, and consent covers what was shown.*

- **R20 — Ready or waiting.** A step whose inputs are all known is *ready*: the plan shows its
  changes, and approving the plan approves them. A step that takes something that doesn't exist
  yet is *waiting*: the plan shows the step and names what it waits for
  (`app.resources.jobs.backfill.id`), and shows no changes, because nobody can know them.
  *(owner, 2026-10-05; the showing is built, as "decided at apply")*
- **R21 — One rule, wherever the step stands.** A step waits when it takes something an earlier
  step only has after it is applied — below the bundle or above it. In practice that is narrow:
  the first deploy of something a later step needs the id or link of. The second time it exists,
  and the step is ready. *(owner, 2026-10-05)*
- **R22 — A reviewed file runs what was reviewed.** `lely apply plan.json` stops at a waiting
  step and says to plan again; the next plan shows that step, now ready. So a first deploy through
  a reviewed file can take two rounds, and every deploy after it takes one.
  *(owner, 2026-10-05)*
- **R23 — `--yes` without a file runs it.** `lely apply -t <target> --yes` plans a waiting step
  when it gets there and runs it: nobody reviewed a plan in that run, and `--yes` said not to
  ask. *(owner, 2026-10-05)*
- **R24 — At a terminal, lely asks again.** `lely apply -t <target>` shows the waiting step's
  plan when it gets there, and asks once more before running it. *(proposed — the same consent,
  given at the moment it can be)*
- **R25 — Never out of order, and never past the other rules.** Apply doesn't skip a waiting step
  to reach the ones below it. A destructive change in a step that was waiting needs
  `--allow-destructive` like any other. A destroy has no waiting steps: everything it removes
  exists. *(proposed)*

### How a run ends

- **R26 — Three exit codes.** 0: done. 1: a step failed. 2: lely refused, before or between
  steps — a plan that went stale, a waiting step in a reviewed file, a change that wasn't
  approved, a destructive change that wasn't allowed, no consent. A pipeline can tell "plan
  again" from "something broke" without reading the message. *(owner, 2026-10-05)*

### On demand

- **R17 — `lely status -t <target>`** changes nothing and shows the overview of every step for
  that target — what is deployed right now, in detail. *(owner, 2026-10-05)*
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

- **A destroy plan as a file** (was D3): yes, the same as for apply — R11a.
  *(owner, 2026-10-05)*
- **The command that shows what is deployed** (was D5): `lely status` — R17.
  *(owner, 2026-10-05)*
- **What has to be proven on a workspace** (was D7): nothing, for now. This work is tested against
  fake tools only, and everything it assumes about the real Databricks CLI stays marked as
  unverified — in the code, and in the README where a user would rely on it — until a real run
  is done. The list of what is assumed is [004, To verify](004-asset-bundle.md#to-verify-on-a-workspace).
  *(owner, 2026-10-05)*
- **A step that can't be planned yet** (was D4): ready or waiting, by what a step takes and not by
  where it stands; a reviewed file stops there and asks for a new plan; `--yes` without a file
  runs it — R20 to R25. *(owner, 2026-10-05)*
- **Exit codes** (was D6): 0 done, 1 failed, 2 refused — R26. *(owner, 2026-10-05)*

## Done when

- R1–R26 each have a test, against fake tools.
- The README no longer says lely "shows you a whole deploy and runs none of it" — and says
  instead that apply and destroy have not yet been run against a real workspace.
- R24 and R25, the two still marked as proposed here, are agreed or changed.

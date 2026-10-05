# 005 — plan, apply, destroy

**Status:** draft. Phase one. `plan` is built; `apply` and `destroy` are not started — every
plugin's `apply` raises "apply is milestone 2" today.

## Why

This is the half of lely that changes a workspace, so it is where the safety rules stop being
promises and become code. And `destroy` is the one verb that can't be taken back.

Two sentences carry most of what follows: **a plan reaches as far as lely can see**, and
**consent covers what was shown.**

## Requirements

### `plan`

- **R1** — `lely plan -t <target>` plans every step in order and changes nothing. It can be
  written to a file with `-o`. *(built)*
- **R2 — A plan file says what it is.** Its format version; lely's version; the target; whether
  it is a plan to apply or a plan to destroy; and a hash of the config and of every step's
  resolved options. *(built, except the kind)*
- **R3** — A plan file in a format this lely doesn't read is refused, with a message that names
  both versions and says to plan again. *(built, for `show`)*

### `apply`

- **R4** — `lely apply plan.json` runs a plan that was saved and reviewed. `lely apply -t
  <target>`, without a file, plans, shows the plan, asks, and then runs. *(design)*
- **R5** — A plan file is refused when the config, or any step's resolved options, differ from
  what it was planned with. The message says which, and to plan again. *(design)*
- **R6** — Steps run in the order written. A step whose `targets:` leaves this target out is
  skipped, and the result says so. *(design)*
- **R7 — The approval check.** Each step is planned again immediately before it runs. It may run
  only if every change in the new plan matches an approved one, and none has become destructive.
  Fewer changes is fine — someone else did part of the work. Anything new stops the run and asks
  for a new plan. What "matches" means is [D9](#to-decide). *(design)*
- **R8** — `apply` refuses a destructive change without `--allow-destructive`. Where the plan
  already shows one, the refusal comes before anything runs. *(design)*
- **R9** — A plan with nothing to do runs nothing, says so, and ends as done. *(proposed)*
- **R10** — When it is done, `apply` shows what each step did and, from every plugin that can, the
  overview of what now exists ([002/R6](002-plugins.md)). *(owner)*

### `destroy`

- **R11** — `lely destroy -t <target>` plans the destroy, shows it, asks, and then runs. The plan
  lists, per step, what would be removed. *(owner)*
- **R12** — Steps are destroyed in the reverse of the order they are applied in: what was made
  last goes first. *(proposed)*
- **R13** — A step with nothing to destroy — one that only runs something — is listed in the
  destroy plan as skipped, with the reason, and the rest is destroyed.
  *(owner, 2026-10-05; [002/R8a](002-plugins.md))*
- **R14 — A destroy can be saved and reviewed first, like an apply.**
  `lely plan -t <target> --destroy -o destroy.json` writes it, `lely show` renders it, and
  `lely apply destroy.json` runs exactly that. One file format for both; a destroy can go through
  a pull request. *(owner, 2026-10-05)*
- **R15** — The approval check holds for a destroy as well: each step is planned again before it
  is destroyed, and anything that wasn't in the approved plan stops the run. *(proposed)*
- **R16** — Destroying a target that has nothing deployed does nothing, says so, and ends as
  done. *(proposed)*

### Consent

- **R17 — Nothing that changes a workspace runs unasked.** `apply` and `destroy` either ask, or
  were given `--yes` in the command. With no terminal and no `--yes` they refuse, and the message
  names the flag: a forgotten flag is a failed job, never an unreviewed deploy.
  *(owner, 2026-10-05, for destroy; the same rule is applied to apply)*
- **R18 — To destroy at a terminal, the answer is the target's name.** Not `y`: the name, typed,
  so that `prod` is never destroyed by a reflex. *(owner, 2026-10-05)*
- **R19 — Without a terminal, consent is given in the command.** `lely destroy -t <target> --yes`
  runs without asking — for a pipeline, where nobody can. It needs the target spelled out with
  `-t`; there is no default target to destroy. *(owner, 2026-10-05)*
- **R20 — A file is asked about too.** Applying a saved plan at a terminal shows what is in it
  and asks before running; `--yes` answers. A saved *destroy* plan is a destroy: it asks for the
  target's name as in R18, and `--allow-destructive` plays no part in it — everything in a
  destroy is destructive, and the command already says so. *(proposed — otherwise the file route
  of R14 would be a way around R18)*

### When something fails — apply and destroy alike

- **R21** — The first failing step stops the run. Nothing after it starts. The result names what
  ran, what failed and what never started. *(design)*
- **R22** — Running the same command again finishes the job: a step that already did its work
  plans as nothing to do. *(design)*
- **R23** — `--from <step>` starts at a named step, for getting past one that *runs* something
  every time. In a destroy it names where to start going *up* the list. Resuming is always asked
  for, never inferred from a record. *(design; the destroy half is proposed)*
- **R24** — There is no rollback. A failure half-way leaves what was done, done, and the result
  says so in those words. *(design)*

### A step that can't be planned yet

- **R25 — Ready or waiting.** A step whose inputs are all known is *ready*: the plan shows its
  changes, and approving the plan approves them. A step that takes something that doesn't exist
  yet is *waiting*: the plan shows the step and names what it waits for
  (`app.resources.jobs.backfill.id`), and shows no changes, because nobody can know them.
  *(owner, 2026-10-05; the showing is built, as "decided at apply")*
- **R26 — One rule, wherever the step stands.** A step waits when it takes something an earlier
  step only has after it is applied — below the bundle or above it. In practice that is narrow:
  the first deploy of something a later step needs the id or link of. The second time it exists,
  and the step is ready. *(owner, 2026-10-05)*
- **R27 — A reviewed file runs what was reviewed.** `lely apply plan.json` stops at a waiting
  step and says to plan again; the next plan shows that step, now ready. So a first deploy through
  a reviewed file can take two rounds, and every deploy after it takes one.
  *(owner, 2026-10-05)*
- **R28 — `--yes` without a file runs it.** `lely apply -t <target> --yes` plans a waiting step
  when it gets there and runs it: nobody reviewed a plan in that run, and `--yes` said not to
  ask. *(owner, 2026-10-05)*
- **R29 — At a terminal, lely asks again.** `lely apply -t <target>` shows the waiting step's
  plan when it gets there, and asks once more before running it. *(proposed — the same consent,
  given at the moment it can be)*
- **R30 — Never out of order, and never past the other rules.** Apply doesn't skip a waiting step
  to reach the ones below it. A destructive change in a step that was waiting needs
  `--allow-destructive` like any other. A destroy has no waiting steps: everything it removes
  exists. *(proposed)*

### How a run ends

- **R31 — Three exit codes.** 0: done, including "nothing to do". 1: a step failed. 2: lely
  refused, before or between steps — a plan that went stale, a waiting step in a reviewed file,
  a change that wasn't approved, a destructive change that wasn't allowed, no consent. A pipeline
  can tell "plan again" from "something broke" without reading the message.
  *(owner, 2026-10-05)*

### On demand

- **R32 — `lely status -t <target>`** changes nothing and shows the overview of every step for
  that target — what is deployed right now, in detail. A step whose plugin has nothing to list
  is shown with those words; one skipped for this target is shown as skipped.
  *(owner, 2026-10-05; the last sentence is proposed)*
- **R33** — `lely doctor` reports whether each plugin's tool is installed and usable (the
  Databricks CLI and its engine, a `command` step's program) and whether the workspace can be
  reached. It changes nothing. An error message in the code already points at it. *(design)*

### Secrets

- **R34** — A secret in a step's outputs is never written anywhere and never printed — not in a
  plan file, a page, a comment or a summary. It is fetched again when it is needed.
  *(built for plan)*

## Not in this spec

- What each plugin does when applied or destroyed → [004](004-asset-bundle.md),
  [010](010-command-and-bundle-run.md)
- Markdown output, the pull-request comment → [008](008-github-actions.md)
- A lock against two runs at once: for now a CI concurrency group does that job, and the bundle
  holds its own lock while it deploys

## Decided

All by the owner, on 2026-10-05.

- **No terminal and no `--yes`** (was D1): refuse — R17.
- **What it takes to destroy** (was D2): at a terminal, typing the target's name; headless,
  `--yes` in the command with the target spelled out — R18 and R19. No flag in the config.
- **A destroy plan as a file** (was D3): yes, the same as for apply — R14.
- **A step that can't be planned yet** (was D4): ready or waiting, by what a step takes and not by
  where it stands; a reviewed file stops there and asks for a new plan; `--yes` without a file
  runs it — R25 to R30.
- **The command that shows what is deployed** (was D5): `lely status` — R32.
- **Exit codes** (was D6): 0 done, 1 failed, 2 refused — R31.
- **What has to be proven on a workspace** (was D7): nothing, for now. This work is tested against
  fake tools only, and everything it assumes about the real Databricks CLI stays marked as
  unverified — in the code, and in the README where a user would rely on it — until a real run
  is done. The list of what is assumed is
  [004, To verify](004-asset-bundle.md#to-verify-on-a-workspace).

## To decide

Found when the spec was reviewed on 2026-10-05; numbered on from the ones above.

- **D8 — Is `-t` always needed?** Today it may be left out, and the bundle's own default target
  is used. With the target now a bare name handed to every step ([002/R23](002-plugins.md)),
  there is no one place a default could come from. Always require `-t` for anything that touches
  a workspace — `plan`, `apply`, `destroy`, `status` — or keep a default for everything but
  `destroy`? *(proposed: always require it. One more word to type, and no deploy to a target
  nobody named.)*
- **D9 — How strict is "matches" in the approval check (R7)?** The design matches a change by its
  key alone: `jobs.backfill` was approved, so `jobs.backfill` may run — even if what changes in
  it is no longer what the reviewer saw. Stricter: the key *and* what kind of change it is
  (create, update, delete, replace, run), so an approved update can't turn into a replace.
  Strictest: the whole change, so any difference at all needs a new plan. *(proposed: key and
  kind. The strictest makes every reviewed plan stale the moment anything moves; the design's is
  the one that lets an unreviewed change through.)*

## Done when

- R1–R34 each have a test, against fake tools.
- The README no longer says lely "shows you a whole deploy and runs none of it" — and says
  instead that apply and destroy have not yet been run against a real workspace.
- Every requirement still marked *(proposed)* here is agreed or changed, and D8 and D9 are
  answered.

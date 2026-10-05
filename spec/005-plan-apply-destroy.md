# 005 — plan, apply, destroy

**Status:** agreed, 2026-10-05. Phase one. `plan` is built; `apply` and `destroy` are not started — every
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
- **R2 — A plan file says what it is, and holds what was shown.** At the top: its format
  version; lely's version; the target; the workspace and the identity it was planned as (R35);
  whether it is a plan to apply or a plan to destroy; and what it was made from (R5, R36). Then,
  for every step in order: its name and plugin; whether it is ready, waiting (and for what) or
  skipped (and why); what it takes and from where; its changes, each with its key, its kind,
  whether it is destructive, and the lines that were shown for it; the outputs known at plan; and
  whatever the plugin itself needs to carry — for a bundle step, the CLI's own plan.
  *(built in part: no kind, no workspace, and the bundle's plan sits outside the steps)*
- **R3** — A plan file in a format this lely doesn't read is refused, with a message that names
  both versions and says to plan again. *(built, for `show`)*

### `apply`

- **R4** — `lely apply plan.json` runs a plan that was saved and reviewed. `lely apply -t
  <target>`, without a file, plans, shows the plan, asks, and then runs. `apply` runs plans to
  apply: handed a destroy plan, it refuses and names the command that takes one (R14).
  *(design; the last sentence is agreed)*
- **R5** — A plan file is refused when the project's steps, or any step's options, differ from
  what it was planned with. What is compared is the config as lely reads it — not the file's
  text, so an unrelated edit to `pyproject.toml` doesn't make a plan stale — with values from the
  environment compared by name, and without the values that couldn't be known when planning. The
  message says which step differs, and to plan again. *(design; today the file's text is hashed)*
- **R6** — Steps run in the order written. A step whose `targets:` leaves this target out is
  skipped, and the result says so. *(design)*
- **R7 — The approval check.** Each step is planned again immediately before it runs. It may run
  only if every change in the new plan is one that was shown and approved: the same thing, the
  same kind of change, the same lines. Fewer changes is fine — someone else did part of the
  work, or an earlier run did. Anything new, or anything that reads differently, stops the run
  and asks for a new plan: a reviewed plan goes stale when the workspace moves under it, which
  is what a reviewed plan should do. *(design, made stricter on 2026-10-05: the design matched a
  change by its name alone)*
- **R8** — `apply` refuses a destructive change without `--allow-destructive`. Where the plan
  already shows one, the refusal comes before anything runs. *(design)*
- **R9** — A plan with nothing to do runs nothing, says so, and ends as done. (A project with a
  bundle step always has something to do: [004/R5a](004-asset-bundle.md).) *(agreed)*
- **R10** — When it is done, `apply` shows what each step did and, from every plugin that can, the
  overview of what now exists ([002/R6](002-plugins.md)). *(owner)*

### `destroy`

- **R11** — `lely destroy -t <target>` plans the destroy, shows it, asks, and then runs. The plan
  lists, per step, what would be removed. *(owner)*
- **R12** — Steps are destroyed in the reverse of the order they are applied in: what was made
  last goes first. *(agreed)*
- **R13** — A step with nothing to destroy — one that only runs something — is listed in the
  destroy plan as skipped, with the reason, and the rest is destroyed. So is a step that needs
  something that isn't there ([002/R21](002-plugins.md)).
  *(owner, 2026-10-05; [002/R8a](002-plugins.md))*
- **R14 — A destroy can be saved and reviewed first, like an apply.**
  `lely plan -t <target> --destroy -o destroy.json` writes it, `lely show` renders it, and
  `lely destroy destroy.json -t <target>` runs exactly that. One file format for both; a destroy
  can go through a pull request. The file is handed to `destroy`, with the target said again: a
  command that destroys always has both words in it. *(owner, 2026-10-05; that it is `destroy`
  and not `apply` that takes the file is a change made in review — see R20)*
- **R15** — The approval check holds for a destroy as well: each step is planned again before it
  is destroyed, and anything that wasn't in the approved plan stops the run. *(agreed)*
- **R16** — Destroying a target that has nothing deployed does nothing, says so, and ends as
  done. *(agreed)*

### Consent

- **R17 — Nothing that changes a workspace runs unasked.** `apply` and `destroy` either ask, or
  were given `--yes` in the command. With no terminal and no `--yes` they refuse, and the message
  names the flag: a forgotten flag is a failed job, never an unreviewed deploy.
  *(owner, 2026-10-05, for destroy; the same rule is applied to apply)*
- **R18 — To destroy at a terminal, the answer is the target's name.** Not `y`: the name, typed,
  so that `prod` is never destroyed by a reflex. *(owner, 2026-10-05)*
- **R19 — Without a terminal, consent is given in the command.** `lely destroy -t <target> --yes`
  runs without asking — for a pipeline, where nobody can. It needs the target spelled out with
  `-t`, with or without a file; there is no default target to destroy, and a file made for
  another target is refused. *(owner, 2026-10-05)*
- **R20 — A file is asked about too, and can't smuggle a destroy.** Applying a saved plan at a
  terminal shows what is in it and asks before running; `--yes` answers. A destroy plan is run
  only by `lely destroy`, which asks for the target's name as in R18. `--allow-destructive`
  plays no part in a destroy: everything in one is destructive, and the command says so.
  *(agreed — as first written, `lely apply destroy.json --yes` would have destroyed a target
  with neither "destroy" nor its name on the command line)*

### When something fails — apply and destroy alike

- **R21** — The first failing step stops the run. Nothing after it starts. The result has three
  lists — what ran, what failed, what never started — in the terminal and as JSON. *(design)*
- **R22** — After a *failure*, running the same command again finishes the job: a step that
  already did its work plans as nothing to do. After a *refusal* — a stale plan, a waiting step
  in a reviewed file — the same file will be refused again: it takes a new plan. The exit code
  says which of the two it was (R31). *(design; the distinction is new)*
- **R23** — `--from <step>` starts at a named step, for getting past one that *runs* something
  every time. In a destroy it names where to start going *up* the list. The steps it passes over
  are still planned, for what they give to the others; they are not applied or destroyed.
  Resuming is always asked for, never inferred from a record. *(design; the destroy half and the
  third sentence are agreed)*
- **R24** — There is no rollback. A failure half-way leaves what was done, done, and the result
  says "nothing was rolled back" in those words. *(design)*

### A step that can't be planned yet

- **R25 — Ready or waiting.** A step whose inputs are all known is *ready*: the plan shows its
  changes, and approving the plan approves them. A step that takes something that doesn't exist
  yet is *waiting*: the plan shows the step and names what it waits for
  (`app.resources.jobs.backfill.id`), and shows no changes, because nobody can know them. A
  plugin can also say that part of its *own* plan has to wait; that step is treated the same way
  for the part that waits. *(owner, 2026-10-05; the showing is built, as "decided at apply")*
- **R26 — One rule, wherever the step stands.** A step waits when it takes something an earlier
  step doesn't have yet — below the bundle or above it. How often depends on what it takes
  ([002/R14](002-plugins.md)): something that exists *once it exists* makes a step wait on the
  first deploy and never again; something produced *after every run* makes it wait on every
  deploy. *(owner, 2026-10-05; the second sentence corrects an earlier "in practice this is
  narrow", which was only true of the first kind)*
- **R27 — A reviewed file runs what was reviewed.** `lely apply plan.json` stops at a waiting
  step and says to plan again; the next plan shows that step, now ready. So a first deploy through
  a reviewed file can take two rounds, and every deploy after it takes one. `plan` says so before
  anyone is surprised: a plan with a waiting step ends with "applied from a file, this stops
  before `<step>`" — and, where the step waits on every deploy, that a file can never take it
  further. *(owner, 2026-10-05; the warning is agreed)*
- **R28 — `--yes` without a file runs it.** `lely apply -t <target> --yes` plans a waiting step
  when it gets there and runs it: nobody reviewed a plan in that run, and `--yes` said not to
  ask. This is lely's unreviewed way of running, and the docs call it that. *(owner, 2026-10-05)*
- **R29 — At a terminal, lely asks again.** `lely apply -t <target>` shows the waiting step's
  plan when it gets there, and asks once more before running it. *(agreed — the same consent,
  given at the moment it can be)*
- **R30 — Never out of order, and never past the other rules.** Apply doesn't skip a waiting step
  to reach the ones below it. A destructive change in a step that was waiting needs
  `--allow-destructive` like any other. *(agreed)*

### How a run ends

- **R31 — Three exit codes.** 0: done, including "nothing to do". 1: something failed — a step,
  or lely itself. 2: lely refused, before or between steps — a plan that went stale, a waiting
  step in a reviewed file, a change that wasn't approved, a destructive change that wasn't
  allowed, no consent, a command it couldn't make sense of. A pipeline can tell "plan again" from
  "something broke" without reading the message. `plan`, `status`, `validate` and `doctor` end
  with 0 or 1 by the same rule. *(owner, 2026-10-05; today every error ends with 1)*

### Naming the target

- **R37 — `-t <target>` is always given** to a command that touches a workspace: `plan`, `apply`,
  `destroy`, `status`. There is no default target. With a plan file the target is the file's,
  and for a destroy it is said again (R19). *(owner, 2026-10-05: go with the proposals; today
  the bundle's own default target is used when `-t` is left out)*

### On demand

- **R32 — `lely status -t <target>`** changes nothing and shows the overview of every step for
  that target — what is deployed right now. To find it, it resolves each step's inputs from the
  top down, the way a plan does. A step whose plugin has nothing to list is shown with those
  words; one skipped for this target is shown as skipped; and a bundle step says whose view it
  is ([004/R9b](004-asset-bundle.md)). *(owner, 2026-10-05; the detail is agreed)*
- **R33** — `lely doctor` reports whether each plugin's tool is installed and usable (the
  Databricks CLI and its engine, a `command` step's program), whether the workspace can be
  reached and as whom, and whether the credentials at hand can do more than read
  ([002/R13a](002-plugins.md)). It changes nothing. An error message in the code already points
  at it. *(design; the last check is agreed)*

### What is never shown, and what always is

- **R34 — Secrets.** A value a plugin marks as secret, and any value that came from the
  environment (`${env.…}`), is never printed and never written — not in a plan file, a page, a
  comment or a summary — wherever it flows. It is not kept for apply either: the step that gives
  it is planned again, and gives it again. A pull-request comment, a job summary and the page's
  first view show a step's changes; they never show a plugin's raw data, such as the CLI's own
  plan, which can hold whatever the bundle's config holds. *(built for values marked secret; the
  rest is the design's promise, and found unkept in review)*
- **R35 — The workspace is named.** Every plan, every question lely asks, and every plan file
  says which workspace it is about and as whom: the host and the identity. A plan file made
  against one workspace is refused on another. Consent is given to a target *on a workspace*,
  not to a name that could mean anything. *(agreed — found in review: the target is typed, but
  the workspace comes from the environment)*
- **R36 — What was reviewed is what is deployed.** A plan file records which version of the
  project it was made from — in a git repository, the tree it was planned on, and whether
  anything was uncommitted. `apply` and `destroy` refuse the file on a different tree, and say
  so. Without it, a plan approved for one commit can be applied on another, and a bundle's
  notebooks and wheels are in no plan at all ([004/R5a](004-asset-bundle.md)). Outside a git
  repository nothing is recorded, and the plan says that it couldn't be. *(agreed — found in
  review)*

## Not in this spec

- What each plugin does when applied or destroyed → [004](004-asset-bundle.md),
  [010](010-command-and-bundle-run.md)
- Markdown output, the pull-request comment → [008](008-github-actions.md)
- A lock against two runs at once: for now a CI concurrency group does that job, and the bundle
  holds its own lock while it deploys
- Finding what the config no longer names: a step that was removed or renamed, a target taken
  out of `targets:`. Without state lely can't see it ([000](000-what-lely-is.md#what-it-does-not-do))

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
- **Whether `-t` is always needed** (was D8): yes — R37. *(go with the proposals)*
- **How strict the approval check is** (was D9): every change in the new plan must be one that
  was shown; changes that are gone are fine — R7. *(go with the proposals)*

## Done when

- Each requirement here has a test, against fake tools.
- The README no longer says lely "shows you a whole deploy and runs none of it" — and says
  instead that apply and destroy have not yet been run against a real workspace.

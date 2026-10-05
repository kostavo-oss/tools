# 002 — apply

**Status:** draft — not started. Written against `docs/DESIGN.md`; waits on
[000/D1](000-what-lely-is.md#to-decide) only if that changes what lely is.

## Why

Today lely shows a whole deploy and runs none of it. Every built-in step's `apply` raises
"apply is milestone 2". This spec is the half that changes a workspace, so it is also where the
safety rules stop being promises and become code.

## Requirements

### The command

- **R1** — `lely apply plan.json` runs a plan that was saved and reviewed. *(design: CLI)*
- **R2** — `lely apply -t <target>`, without a file, plans, shows the plan, asks, and then runs —
  the way `stevin apply` does. `--yes` skips the question. *(design: CLI)*
- **R3** — A plan file is refused when `lely.yml`, or any step's resolved options, differ from the
  ones it was planned with. The message says which, and to plan again. *(design: the approval
  check; the hashes are already in the file, [001/R10](001-read-only.md))*
- **R4** — A plan with nothing to do runs nothing and says so. *(proposed)*

### The order

- **R5** — Pre steps in the order written, then the bundle, then post steps in the order written.
  A step whose `targets:` leaves this target out is skipped, and the summary says it was.
  *(design: Pipeline)*
- **R6** — The bundle is deployed with `databricks bundle deploy --plan`, with `bundle_vars` from
  the pre steps passed as `--var`. *(design: Pipeline, Milestones)*
- **R7** — After the bundle deploys, `bundle summary -o json` is read, so a post step can use the
  id and url of what was just created. *(design: Pipeline)*
- **R8** — What a step returns from `apply` is available to every later step as
  `${steps.<name>.<output>}`. *(design: Config)*

### The approval check

- **R9** — Each step is planned again immediately before it runs. It may run only if every change
  in the new plan matches an approved one by `key`, and none has become destructive. Fewer
  changes is fine — someone else did part of the work. Anything new stops the run and asks for a
  new plan. *(design: the approval check)*
- **R10** — The bundle gets the same check, by resource key and action; `delete`, `recreate` and
  `update_id` count as destructive. The CLI's own check (`bundle deploy --plan` refuses a plan
  whose state has moved on) is left to do its part and its refusal is reported as it is.
  *(design: the approval check)*
- **R11** — A step that was *decided at apply* in the plan is planned for the first time here,
  with the values it was waiting for. What happens between that plan and running it is
  [D2](#to-decide).

### Destructive changes

- **R12** — `apply` refuses a destructive change without `--allow-destructive` — a step's or the
  bundle's. Where the plan already shows one, the refusal comes before anything runs.
  *(design: step rules)*
- **R13** — The `stevin` step passes `--allow-destructive` to stevin only when lely was given it.
  *(design: Built-in steps)*

### When something fails

- **R14** — The first failing step stops the run. Nothing after it starts. The summary names what
  ran, what failed, and what never started, and the exit code is not zero. *(design: Failure
  model)*
- **R15** — Running `apply` again finishes the job: steps that converge plan again and do what is
  left. `--from <step>` starts at a named step, for getting past a step that *runs* something
  every time. Resuming is always asked for, never inferred from a record. *(design: Failure
  model)*
- **R16** — There is no rollback. A failure after the bundle deployed leaves it deployed, and the
  summary says so in those words. *(design: Failure model)*

### The built-in steps

- **R17** — **`command`** runs its `apply` command with the environment it has at plan time
  (`LELY_TARGET`, `LELY_STEP`, `LELY_PHASE`) plus `LELY_PLAN`, a file holding the step's approved
  plan, and `LELY_OUTPUTS`, a file the command writes its outputs to. This closes
  [001/G2](001-read-only.md): the design names three of the five, the code another three.
  *(design: Built-in steps; the union is proposed)*
- **R18** — **`stevin`** writes the plan it was approved with back to a file and runs
  `stevin apply <file> --yes`. A stale plan is stevin's to refuse; lely reports the refusal.
  *(design: Built-in steps)*
- **R19** — **`bundle.run`** runs `databricks bundle run <key>` with its `args`. It runs on every
  apply. *(design: Built-in steps)*
- **R20** — A step written as a Python class gets the same `apply(ctx, plan) -> Outputs` and the
  same rules. *(design: The step interface)*

### Secrets

- **R21** — A `Secret` in a step's outputs is never written anywhere and never printed. It is
  fetched again at apply. *(design: step rules)*

### `doctor`

- **R22** — `lely doctor` reports the Databricks CLI's version and whether the bundle uses the
  direct engine, whether the target can be reached with the credentials at hand, and whether each
  step's tool is on PATH (`stevin`, a `command` step's executable). It changes nothing.
  *(design: CLI, Non-goals)* Closes [001/G1](001-read-only.md).

### For people writing a step

- **R23** — The apply half of the contract kit in `lely.testing`: `plan`, then `apply`, then
  `plan` again gives an empty plan for a step that converges; `apply` does nothing the plan
  didn't say; no `Secret` reaches a file. Every built-in step passes it. *(design: Testing)*

## Not in this spec

- Markdown output and the GitHub Action → [003](003-ci.md)
- A lock against two applies at once: v1 leans on a CI concurrency group (design: Failure model,
  Open questions)
- Bundle variables that aren't single values: `--var` can't carry them, and the design has a
  `TODO(verify)` on the other route
- `bundle destroy`, Lakebase, MLflow

## To decide

- **D1 — No terminal and no `--yes`.** `apply -t prod` in a pipeline has nobody to ask. Refuse
  with a message that names `--yes` *(proposed — it is what keeps a forgotten flag from becoming
  an unreviewed deploy)*, or run?
- **D2 — A step that could only be planned at apply.** It was approved as "decided at apply",
  without its changes. When it is finally planned: run it straight away, or — when there is a
  terminal — show that part and ask once more? Either way [R12](#destructive-changes) holds: a
  destructive change in it needs `--allow-destructive`.
- **D3 — Exit codes.** *(proposed)* 0 done; 1 a step failed; 2 refused before or between steps —
  a stale plan, a change that wasn't approved, a destructive change that wasn't allowed. A
  pipeline can then tell "plan again" from "something broke".
- **D4 — `bundle deploy` and its own questions.** The design carries a `TODO(verify)`: does the
  CLI ask before deleting or recreating, and fail when it can't? This decides which flags
  [R6](#the-order) passes, and it can only be settled on a workspace.
- **D5 — What has to be proven live.** lely has no live suite, and this is the first milestone
  that changes a workspace. Which of these must run against a real one before 002 is called done:
  a first deploy, a second apply after a failure, a refused stale plan, a destructive change
  refused and then allowed, `bundle.run`? And on which workspace — stevin's test workspace is the
  obvious one, and its token has expired.

## Done when

- R1–R23 each have a test, against the fake `databricks` and the fake `stevin`.
- Every built-in step passes the whole contract kit.
- The README's "today lely shows you a whole deploy and runs none of it" is no longer true, and
  is rewritten.
- Whatever D5 names has run on a workspace, and what it found is written down next to the
  assumption it settled.
- D1–D4 are answered in this file, and `docs/DESIGN.md` says the same.

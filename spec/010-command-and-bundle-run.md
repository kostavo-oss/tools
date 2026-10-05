# 010 — the small plugins: `command` and `bundle.run`

**Status:** built, 2026-10-05 — see [As built](#as-built). Phase one. `bundle.run`'s apply is
tested against a fake CLI only.

## Why

A bundle step on its own is `bundle deploy` with more ceremony. lely earns its place with the
steps *around* the bundle, and these are the two every project can use on day one: run my
script, and run that job. Without at least `command`, phase one can deploy a bundle and nothing
else.

Their plan halves are built. A step written as a Python class in the repo needs nothing from
this spec: it goes through the contract of [002](002-plugins.md) like any plugin.

**An honest limit, said here once.** A `command` step without a plan command tells a reviewer
one thing: that it runs. lely still gives such a step its place in the order, its inputs written
down, and one rule for consent — but it can't show what a script it has never run will do. A
project whose every extra step is an opaque script gets less from lely than one whose steps can
plan.

## Requirements

### `command`

- **R1** — Options: `apply`, the command to run; and optionally `plan`, `destroy`, `outputs` and
  `env`. Each command is a list — a program and its arguments — and is never passed through a
  shell. *(built, except `destroy` and `outputs`: owner, 2026-10-05)*
- **R2 — Plan.** With a `plan` command: it is run, and what it prints on stdout — a plan, as JSON
  — is the step's plan. Without one: the plan is a single line that shows the command, saying it
  runs on every apply. *(built)*
- **R3 — Apply.** The `apply` command is run from the project's directory. A non-zero exit is a
  failed step, and what it printed is shown. *(design)*
- **R4 — What the command is given.** The environment lely was run in, the step's own `env`, and
  `LELY_TARGET` and `LELY_STEP`; on apply also `LELY_PLAN`, a file holding the plan that was
  approved for this step, and `LELY_OUTPUTS`, a file the command writes its outputs to, one
  `name=value` to a line. `LELY_PHASE`, which the code sets today, goes: it said "pre" or "post",
  and there are no phases any more. This settles [001/G2](001-what-is-built.md). *(the first
  two built; the rest design)*
- **R5 — What it gives, and when.** An output the plan command prints is known *at plan*. An
  output the apply command writes to `LELY_OUTPUTS` is known only *after every run* — so a step
  that takes it waits on every deploy ([002/R19](002-plugins.md)). A command that feeds the
  bundle should therefore give its value from its plan command: a lookup changes nothing, and
  planning is where a lookup belongs. *(follows from [002/R14](002-plugins.md))*
- **R6 — Destroy.** With a `destroy` command: the destroy plan shows that command line in full,
  marked destructive, and destroy runs it. lely can't vouch for what it removes
  ([002/R11](002-plugins.md)). Without one: the step is skipped, visibly
  ([002/R8a](002-plugins.md)). *(owner, 2026-10-05)*
- **R7 — Status.** A command has nothing lely can list. `lely status` shows the step with the
  words "runs a command; nothing to list". *(agreed)*
- **R8 — No secrets, for now.** A `command` step can't be handed a secret in its arguments —
  they would be visible to every process on the machine — and can't give one. A step that has to
  handle a secret is written as a Python class. *(built)*

### `bundle.run`

- **R9** — Options: `bundle`, the name of the bundle step it belongs to; `resource`, the key of a
  job, pipeline or app in that bundle (`jobs.backfill`); and `args`. The bundle is always named,
  even when a project has only one: what a step depends on is read in its options
  ([002/R15](002-plugins.md)). *(`resource` and `args` built; `bundle` is agreed)*
- **R10 — Plan.** One line: it runs that resource. It runs on every apply, so it is never
  "nothing to do". *(built)*
- **R11 — Apply.** `databricks bundle run <key>`, with its `args`, waiting for it to finish. A
  failed run is a failed step. *(design)*
- **R12 — It stands below the bundle step it names,** because it needs that bundle deployed — the
  same rule as any reference ([002/R16](002-plugins.md)). `lely validate` says so otherwise.
  *(agreed)*
- **R13 — Destroy and status.** Nothing to destroy: skipped, visibly. Nothing to list.
  *(owner, 2026-10-05, as [002/R8a](002-plugins.md))*
- **R14 — It gives nothing, for now.** What a run produced — a run id, a result — is not an
  output in phase one. *(agreed — it would be an "after every run" output, and nothing needs
  it yet)*

## Decided

- **How a `command` step says what it gives** (was D1): the step lists them — `outputs:
  [version]` in its options. `lely validate` can then check references to them, and a name it
  lists and gives in neither way is a failed step. *(owner, 2026-10-05: go with the proposals)*

## As built

2026-10-05.

- **When a `command` step's outputs are known (R5).** Without a plan command they are all
  *after every run*, and `validate` warns about a step that takes one. With a plan command lely
  can't know before running it which of the listed names it prints, so they are declared *once
  it exists*: known at plan if the plan command prints them, otherwise after the apply command
  writes them. A step that takes one the plan command never prints waits on every deploy all
  the same — and `validate` can't warn about that.
- **A step that gives something only by running plans a run.** With a plan command and a listed
  output it doesn't print, the apply command is the only thing that can give that output — so
  every plan of the step shows a `run` for it, "to give `<name>`", beside its other changes.
  Without it the step had nothing to do, never ran, and the step below it failed on every
  deploy; and with it only once the other changes were gone, a run that failed further down
  couldn't be finished from the same file.
- **One value, written two ways.** The plan command prints JSON and the apply command writes
  text. An output both give with the same value keeps the plan's type — `14`, not `"14"` — so
  a step below that took it still takes it.
- **An argument is passed as it was written**: `1.10` stays `1.10`.
- **`LELY_PLAN` (R4)** holds the plan made right before the command runs, which was checked
  against the approved one.
- **What a command prints (R3)** is shown when it fails, and logged line by line when it
  succeeds.
- **`env` may hold a secret (R8)**; arguments may not, a value from the environment included.
- **`bundle` on `bundle.run` (R9)** is an option that names a step — see
  [002, As built](002-plugins.md#as-built).
- **`bundle run <key> -- <args>` (R11):** that arguments after `--` reach the job, and that a
  failed run exits non-zero, are from the CLI's docs and not seen live.

## Done when

- Each requirement here has a test, with a script standing in for the command and the fake
  `databricks` for the run.
- Both plugins pass the parts of the contract kit that apply to them
  ([002/R25](002-plugins.md)).
- A project with a `command` above a bundle, feeding it a variable from its plan command, and a
  `bundle.run` below it plans, applies and is destroyed in tests, end to end.

# 010 — the small plugins: `command` and `bundle.run`

**Status:** draft. Phase one — found missing when the spec was reviewed: nothing said what these
two do on apply, on destroy or in `status`.

## Why

A bundle step on its own is `bundle deploy` with more ceremony. lely earns its place with the
steps *around* the bundle, and these are the two every project can use on day one: run my
script, and run that job. Without at least `command`, phase one can deploy a bundle and nothing
else.

Their plan halves are built. A step written as a Python class in the repo needs nothing from
this spec: it goes through the contract of [002](002-plugins.md) like any plugin.

## Requirements

### `command`

- **R1** — Options: `apply`, the command to run; and optionally `plan`, `destroy` and `env`. Each
  command is a list — a program and its arguments — and is never passed through a shell.
  *(built, except `destroy`: owner, 2026-10-05)*
- **R2 — Plan.** With a `plan` command: it is run, and what it prints on stdout — a plan, as JSON
  — is the step's plan. Without one: the plan is a single line saying the command runs, on every
  apply. *(built)*
- **R3 — Apply.** The `apply` command is run from the project's directory. A non-zero exit is a
  failed step, and what it printed is shown. *(design)*
- **R4 — What the command is given.** The environment lely was run in, the step's own `env`, and
  `LELY_TARGET`, `LELY_STEP`, `LELY_PHASE`; on apply also `LELY_PLAN`, a file holding the plan that
  was approved for this step, and `LELY_OUTPUTS`, a file the command writes its outputs to. This
  settles [001/G2](001-what-is-built.md): the design named three of these, the code another
  three. *(the first three built; the last two design)*
- **R5 — Destroy.** With a `destroy` command: the destroy plan shows one line saying it runs,
  marked destructive, and destroy runs it. Without one: the step is skipped, visibly
  ([002/R8a](002-plugins.md)). *(owner, 2026-10-05)*
- **R6 — Status.** A command has nothing lely can list. `lely status` shows the step with the
  words "runs a command; nothing to list". *(proposed)*

### `bundle.run`

- **R7** — Options: `resource`, the key of a job, pipeline or app in a bundle (`jobs.backfill`);
  `args`; and `bundle`, the name of the bundle step it belongs to — needed only when a project
  has more than one. *(built, except `bundle`: proposed, since several bundles are now allowed)*
- **R8 — Plan.** One line: it runs that resource. It runs on every apply, so it is never "nothing
  to do". *(built)*
- **R9 — Apply.** `databricks bundle run <key>`, with its `args`, waiting for it to finish. A
  failed run is a failed step. *(design)*
- **R10 — It stands below the bundle step it names,** because it needs that bundle deployed — the
  same rule as any reference ([002/R16](002-plugins.md)). `lely validate` says so otherwise.
  *(proposed)*
- **R11 — Destroy and status.** Nothing to destroy: skipped, visibly. Nothing to list.
  *(owner, 2026-10-05, as [002/R8a](002-plugins.md))*

## To decide

- **D1 — How a `command` step says what it gives.** [002/R14](002-plugins.md) asks every plugin
  to declare its outputs, but a command's outputs are whatever a script writes. So the step has
  to list them itself — `outputs: [version]` in its options — or `command` steps can't feed
  other steps at all. *(proposed: the step lists them; a name it lists and doesn't write is a
  failed step)*
- **D2 — Does a `destroy` command count as destructive consent enough?** It runs whatever the
  project wrote, on a target that is being taken down. Covered by destroy's own consent
  ([005/R18](005-plan-apply-destroy.md)), or should the plan also show the command line in full?
  *(proposed: covered, and the plan shows the command line in full)*

## Done when

- R1–R11 each have a test, with a script standing in for the command and the fake `databricks`
  for the run.
- Both plugins pass the parts of the contract kit that apply to them
  ([002/R25](002-plugins.md)).
- A project with a `command` above a bundle, feeding it a variable, and a `bundle.run` below it
  plans, applies and is destroyed in tests, end to end.

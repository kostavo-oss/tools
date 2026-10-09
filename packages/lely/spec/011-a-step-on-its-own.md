# 011 — a step on its own

**Status:** built, 2026-10-08, the same day — the owner said "sound good build the thing"
after reading it; see [As built](#as-built). `command` was removed the same day, in the
change after.

Markers: *(owner)* the owner said it or chose it on 2026-10-08; *(proposal)* the writer's,
not yet decided; *(002)* already the contract of [002](002-plugins.md).

## Words

- A **step** is a plugin's class with its options: what [002](002-plugins.md) calls a
  plugin. This spec uses *step* for the class people write.
- **On its own** means run from a terminal, without `lely.yml` and without `lely`'s
  commands — the package is installed, as the base the step imports.
- The **base** is `lely.step.Step`: what a step inherits to get its command line.

## Why

A step written for lely is only useful inside lely: it needs a `lely.yml`, a target and
`lely plan` before anyone sees it do anything. The owner's direction: *"steps should be
single script typer apps that import the base so that someone can run a custom step even
without lely."* A step that runs on its own can be tried before a config exists, shipped
to a team that doesn't use lely, and debugged with a `--help`.

The one thing not to lose is the contract. If lely talked to a step as a *program* — its
stdout, its exit code — the step would be the `command` plugin again: a box lely can't hold
to [002's rules](002-plugins.md#rules-every-plugin-follows). So the class stays the
contract, and the command line is derived from it: lely imports the class in-process,
every check applies, and the same file runs alone because the base gives it a command line
for free.

## Requirements

### The step is the class; the command line comes with it

- **R1 — A step is what 002 says it is**: `Options`, `outputs`, `plan`, `apply`, and the
  optional `overview`, `plan_destroy`, `destroy`. Nothing in this spec changes that
  contract or its rules. *(002)*
- **R2 — A step inherits `lely.step.Step`, and `Step.main()` is its command line.** One
  line at the bottom of the file:

  ```python
  # ops/scope.py
  # /// script
  # dependencies = ["lely"]
  # ///
  from dataclasses import dataclass

  from lely.model import Change, Output, StepPlan
  from lely.step import Context, Step


  class SecretScope(Step):
      """Makes the product's secret scope."""

      @dataclass(frozen=True, slots=True)
      class Options:
          #: The scope's name.
          name: str

      outputs = (Output("name"),)

      def plan(self, ctx: Context) -> StepPlan: ...

      def apply(self, ctx: Context, plan: StepPlan) -> dict: ...


  if __name__ == "__main__":
      SecretScope.main()
  ```

  Under lely the same file is `uses: ./ops/scope.py:SecretScope`, unchanged. *(owner for
  the direction; the shape is proposal)*
- **R3 — One file, run with nothing installed.** The inline metadata above (PEP 723) is
  enough for `uv run ops/scope.py plan -t dev --name shop_data`. The docs show that first.
  *(owner: "single script")*
- **R4 — Five commands, the same for every step.** *(proposal)*

  | Command | Does |
  |---|---|
  | `plan -t <target> [options] [-o plan.json]` | Plans, shows the plan, changes nothing. Writes the plan file when asked. |
  | `apply <plan.json>` | Applies a plan made earlier, after the same checks lely makes. |
  | `apply -t <target> [options]` | Plans, shows, asks, applies — as `lely apply -t` does. `--yes` skips the asking. |
  | `destroy -t <target> [options]` | Plans the destroy, shows, asks, destroys. A step without `plan_destroy` says so and stops. |
  | `status -t <target> [options]` | The step's `overview`: what exists because of it. |
  | `check [-t <target> [options]]` | Holds the step to the rules: see R9. |

  `--json` on any of them answers as data; `--profile` picks the workspace (R6).
- **R5 — The step's options are its flags.** Each field of `Options` is `--<name>`, with
  the field's type, default and description (its `#:` comment). Text, whole and decimal
  numbers, yes/no as a word, dates and times in ISO format; a list field takes the flag
  more than once; a mapping takes `--<name> key=value`. A value that does not parse is
  refused by the flag's name. This is the machinery leeghwater already has for a pipeline's
  parameters, lifted into `lely.step` so there is one copy: leeghwater imports it back in a
  later release. *(owner: the base lives in lely and leeghwater imports it later)*

### What a step alone is given

- **R6 — The workspace is whatever already signs the Databricks CLI in, and `--profile`
  picks one** — the rule leeghwater and caland follow. `ctx.workspace` connects on first
  use; `ctx.databricks` runs the CLI found on the PATH with the same sign-in. *(owner)*
- **R7 — The rest of `ctx` is built the same way lely builds it**: `ctx.target` from `-t`,
  `ctx.name` the class's name in lower case, `ctx.root` the working directory, `ctx.env`
  the environment, `ctx.log` to stderr, `ctx.purpose` from the command. One `Context`
  class, two builders; a step cannot tell which built it. *(proposal)*
- **R8 — A reference has nothing to point at, and is refused.** An option value that looks
  like `${steps.<name>.<output>}` is refused before anything runs, with: *run it under lely,
  or pass the value*. *(proposal)*

### The same plan, the same checks

- **R9 — A step's plan file is a one-step lely plan.** `plan -o plan.json` writes what
  `lely plan -o` writes for a config of that one step: the same header (format, lely's
  version, purpose, target, workspace, identity, git tree), the same step entry. So
  `lely apply plan.json` and `ops/scope.py apply plan.json` are interchangeable, and both
  make the same approval check before applying. A step's `apply` refuses a plan file that
  holds another step, or more than one. *(owner: one format)*
- **R10 — `check` holds the step to the rules, with and without a workspace.** Alone,
  `check [options]` runs what `lely.testing` can run offline: `plan` behind a CLI that
  refuses anything but a read, the plan through a plan file and back, outputs as declared.
  `check --live -t <target> [options]` adds `check_apply` and, when the step can,
  `check_destroy`: it makes and removes things on that target, and says so first.
  *(proposal; the checks are built)*
- **R11 — Outputs are shown, secrets are not.** `plan` prints the outputs it knows and
  names the ones known later; `apply` prints what the step returned. A `Secret` is shown
  as a secret, never as its value, as the page shows it. *(002/R13; proposal for the
  console)*

### What goes, and what replaces it

- **R12 — `command` is retired.** A program that wants in writes a class, and the base
  gives it the command line; lely has one mechanism to document, test and hold to the
  rules. It goes in the release that ships this spec, with a line in the changelog and
  [010](010-command-and-bundle-run.md) marked superseded for its `command` half;
  `bundle.run` stays. *(owner: "retire it")*
- **R13 — A `Program` base for the run-only case.** A program as a single `run` change:

  ```python
  from lely.step import Program


  class Notify(Program):
      """Tells the channel the deploy is done."""

      command = ["./ops/notify.sh", "deployed"]
      destructive = False
  ```

  Its plan is one `run`, declared destructive or not; its outputs are what the program
  prints as JSON on its last line, if it declares any; it has no destroy, because a run has
  nothing to take down, and `lely destroy` skips it visibly. Ten lines in place of what
  `command` did, under the rules. *(owner: "yes, a Program base")*
- **R14 — lely's own steps keep their own command lines.** `bundle` alone is the
  Databricks CLI; `stevin` alone is stevin. The base is for steps people write. *(owner)*

### Docs

- **R15 — "Writing a plugin" becomes "Writing a step"**, and starts with the step run on
  its own: the file, `uv run`, the five commands, then `uses:` in a config. The
  `SecretScope` step is the example throughout, and the data product template's first step of its own.
  *(proposal)*

## Not in this spec

- **A registry or discovery** beyond the `lely.steps` entry point that exists.
- **A command line for `bundle`, `bundle.run` and `stevin`.** R14.
- **Changing the rules of 002**, or the plan file's content beyond what R9 names.
- **lely itself running without a config.** A step alone is a step alone; lely stays the
  thing that orders several.

## Decided

All on 2026-10-08, by the owner, by question form unless quoted.

- The direction, in their words: "steps should be single script typer apps that import the
  base so that someone can run a custom step even without lely".
- `command`: **retire it**.
- Sign-in on its own: **the SDK's default, plus `--profile`**.
- The base lives **in lely; leeghwater imports it later**.
- The plan file: **one format**, a standalone plan is a one-step lely plan.
- Built-ins: **custom steps only** get the command line.
- The run-only case: **a `Program` base**.
- Timing: **spec now, build later**.

## To decide

- **D1 — Option types beyond R5's list.** An `Options` field of another type is refused
  when the step starts, with the list; the writer proposes that and no more.
- **D2 — `Program`'s outputs.** JSON on the last line of stdout (proposed), or a file the
  program writes. The first needs no convention beyond `print(json.dumps(...))`.
- **D3 — `apply -t` without a plan file asks**, and `--yes` skips it (proposed, as
  `lely apply -t` does); or a step alone always wants a plan file first.

## Done when

With the `SecretScope` step from the docs, in the tests against a fake workspace:

- `uv run ops/scope.py plan -t dev --name x` shows one change and the output `name`, and
  changes nothing; `-o plan.json` writes a file `lely show` reads and `lely apply` accepts.
- `apply plan.json` applies it; `apply -t dev --name x` plans, asks and applies; planned
  again, nothing changes.
- `status` lists the scope; `destroy` takes it down; a step without `plan_destroy` is
  skipped and says why.
- `check` passes for it and fails for a step whose `plan` writes.
- A `${steps.x.y}` value is refused with the message of R8.
- `uses: ./ops/scope.py:SecretScope` in a `lely.yml` runs it under lely with the same plan.
- A `Program` step plans one `run`, applies it, and gives the outputs it printed.
- `command` is gone from `lely steps`, the docs and the config schema; the changelog says
  so.

And on a workspace: the step run alone, then under lely, on the owner's test workspace.

## As built

In `src/lely/step.py` (`Step`, `Program`), `src/lely/flags.py` (options as flags, and back
into a config block) and `src/lely/solo.py` (the five commands); tested in
`tests/unit/test_solo.py` and `tests/unit/test_step_program.py`.

- **A step alone is a config of one step.** The flags become the `with:` block a `lely.yml`
  would hold, and everything goes through lely's own `planning`, `running`, plan file and
  approval. So R9 costs nothing: a standalone plan *is* a one-step lely plan, and a plan file
  that holds other steps is refused by name.
- **A flag not given is left out of the block**, so the option's own default applies and
  `made_from` agrees with a config that doesn't write it. The default is said in the help.
- **`check` is not offline** (R10's first half): `plan` needs the target to read, so `check`
  takes `-t` and runs behind a Databricks CLI that refuses anything but a read, with the
  workspace reached as it is. `--live` runs the cycle plan–apply–destroy–plan when the step
  destroys, or plan–apply–plan when it doesn't. What a step does through the SDK is its own:
  `check` cannot see a write made there, and the docs say so.
- **The plan file is given as `--plan-file`**, not as a positional argument: a step's own
  flags are positional-free, and a file beside `-t` was ambiguous.
- **The step's name on its own** is the class's, in lower case (R7).
- **`command` is removed, 2026-10-08**, in the change after this one, so this one stays
  readable: the plugin, its entry point, its docs and its tests are gone, and the shared
  test scenario's programs are `Program` steps. A config that still names `command` is told
  by `lely validate` that no plugin of that name is installed. The changelog says so under
  Removed, and [010](010-command-and-bundle-run.md) is superseded for its `command` half.
  Two things that change found in `Program`: `lely doctor` asks `programs` of the class, so
  it is a classmethod; and what the program prints is logged under the step's name.
- **D1, D2, D3 as proposed**: an option of another type is refused with the list; a
  `Program`'s outputs are the JSON on the last line; `apply -t` asks, `--yes` skips.
- **Not run on a workspace yet.** The marker step of the tests makes a file; a step that
  makes a secret scope on the owner's test workspace is the next proof.

# 001 — read-only

**Status:** built (milestone 1, 2026-09-29). 125 unit tests; no live run against a workspace yet.

## Why

Before lely may change anything, it has to be able to say exactly what it would change — for the
bundle and for every step around it — without touching a workspace.

## What is built

Each line names where it is tested, under `tests/unit/`.

- **R1 — `lely validate`** checks `lely.yml` offline: unknown keys, each step's `with:` block
  against that step's options, and every `${…}` reference in its position. Errors carry
  file:line:column. (`test_config`, `test_options`, `test_refs`)
- **R2 — `lely steps`** lists the installed steps and their options. (`test_registry`, `test_cli`)
- **R3 — `lely plan -t <target>`** plans the pre steps, the bundle (`bundle plan -o json`, with
  pre-step outputs as `--var`), and the post steps, and changes nothing. (`test_planning`,
  `test_bundle`, `test_databricks`)
- **R4 — Two formats.** Rich for a terminal, JSON with `-f json` or `-o plan.json`.
  (`test_render_rich`, `test_planfile`)
- **R5 — `lely show plan.json`** renders a saved plan without a workspace. (`test_cli`)
- **R6 — A step is found** by registered name (entry-point group `lely.steps`), by
  `package.module:Class`, or by `./file.py:Class` in the repo. (`test_registry`)
- **R7 — Three built-in steps, plan half:** `stevin`, `bundle.run`, `command`.
  (`test_step_stevin`, `test_step_bundle_run`, `test_step_command`)
- **R8 — What isn't known yet is said, not guessed.** A step whose options need something this
  deploy creates is shown as *decided at apply*. (`test_planning`, `test_refs`)
- **R9 — No secret reaches a plan file.** A `Secret` output is `***` on screen and a marker in the
  file. (`test_planfile`)
- **R10 — The plan file knows what it was made from:** a format version, the tool version, and
  hashes of `lely.yml` and of every step's resolved options. (`test_planfile`, `test_planning`)
- **R11 — The plan half of the contract kit**, `lely.testing`, for anyone writing a step.

## Where the code and the design disagree

Found while writing this; none is fixed yet. Each is small, and each needs one of the two changed.

- **G1 — `doctor` is mentioned and doesn't exist.** An error in `bundle.py` tells the user to
  "check `lely doctor`". It arrives with [002](002-apply.md).
- **G2 — What a `command` step is given.** The design promises `LELY_TARGET`, `LELY_PLAN` and
  `LELY_OUTPUTS`. The code sets `LELY_TARGET`, `LELY_STEP` and `LELY_PHASE`. Settled in
  [002/R17](002-apply.md).
- **G3 — How stevin is called.** The design says `stevin plan -t <target> -o <tmp> -f json`. The
  code spells the flags out and adds `--config` and `--select`. The code is right; the design
  needs the line updated.
- **G4 — `py.typed` was promised by the package's classifiers and missing** until 2026-10-05.
  Fixed; listed so nobody looks for it.

## Not in this spec

- Markdown output (`-f md`) → [003](003-ci.md)
- `apply`, `doctor`, the apply half of the contract kit → [002](002-apply.md)
- Live probes: every assumption about the Databricks CLI here was settled from its source and its
  recorded tests, not from a workspace → [002/D5](002-apply.md#to-decide)

## Done when

Already done, except: G1–G3 are closed by the specs they point to.

# 001 — what is built

**Status:** built (the design's milestone 1, 2026-09-29). 125 unit tests; no live run against a
workspace yet. Built under the earlier shape — pre steps, *the bundle*, post steps — so some of
it moves; see [What changes](#what-changes).

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
  "check `lely doctor`". It arrives with [005/R33](005-plan-apply-destroy.md).
- **G2 — What a `command` step is given.** The design promises `LELY_TARGET`, `LELY_PLAN` and
  `LELY_OUTPUTS`. The code sets `LELY_TARGET`, `LELY_STEP` and `LELY_PHASE`. Settled in
  [010/R4](010-command-and-bundle-run.md): four of the five; `LELY_PHASE` goes with the phases.
- **G3 — How stevin is called.** The design says `stevin plan -t <target> -o <tmp> -f json`. The
  code spells the flags out and adds `--config` and `--select`. The code is right; the design
  needs the line updated.
- **G4 — `py.typed` was promised by the package's classifiers and missing** until 2026-10-05.
  Fixed; listed so nobody looks for it.

## Words that change

The spec says *waiting* for a step whose inputs aren't known yet. The code has four names for
it — `deferred`, `Unresolved`, `Unknown`, and "decided at apply" on screen — and the README shows
the last. They become one word when [005/R25](005-plan-apply-destroy.md) is built. Likewise a
plugin's kinds of change have no word yet for "files are uploaded"
([004/R5a](004-asset-bundle.md)).

## What the review found in the built half

Small, and listed so they are fixed on the way rather than rediscovered:

- A step is handed every earlier step's outputs and the whole bundle, not only what its options
  name ([002/R22](002-plugins.md)).
- Only values marked as secret are kept out of plan files; values from the environment and the
  CLI's whole plan are not ([005/R34](005-plan-apply-destroy.md)).
- The plan file's "made from" is a hash of the config file's text ([005/R5](005-plan-apply-destroy.md)).
- Every error ends with exit code 1 ([005/R31](005-plan-apply-destroy.md)).
- `lely steps` lists installed plugins, not the ones a project's config names
  ([002/R2](002-plugins.md)).
- The workspace's host is taken from the bundle's target ([002/R24](002-plugins.md)).

## What changes

The owner's direction of 2026-10-05 ([000](000-what-lely-is.md)) keeps all of the above as
behaviour and moves some of it:

- **The bundle leaves the core.** Asking the CLI to validate, plan and summarise a bundle, and
  turning its plan into changes, becomes the `bundle` plugin ([004](004-asset-bundle.md)). R3 and
  R8 then hold for any plugin, not for the bundle by name.
- **The config loses its bundle keys.** `pre:`, `post:`, `bundle:` and `bundle_vars:` become one
  list of steps, the bundle one of them with `vars` among its options ([003/R1](003-config.md)).
- **References to the bundle become a step's outputs** ([002/R14](002-plugins.md)), and the
  short spellings go ([002/R15a](002-plugins.md)).
- **The plan file's format changes with it,** so its format version goes up. Nothing is
  published, so no old plan file has to be read.

What stays as it is: finding plugins (R6), options checked offline (R1), the two formats (R4),
secrets (R9), and the `stevin`, `bundle.run` and `command` plugins' plan halves (R7).

## Not in this spec

- Markdown output (`-f md`) → [008](008-github-actions.md)
- `apply`, `destroy`, `doctor` → [005](005-plan-apply-destroy.md)
- Live checks: every assumption about the Databricks CLI here was settled from its source and its
  recorded tests, not from a workspace, and stays that way for now
  → [004, To verify](004-asset-bundle.md#to-verify-on-a-workspace)

## Done when

Already done, except: G1–G3 are closed by the specs they point to, and "What changes" is carried
out by [002](002-plugins.md)–[004](004-asset-bundle.md) without losing a test.

One more thing changes for anyone who used it as built: `-t` may stop having a default
([005, To decide](005-plan-apply-destroy.md#to-decide)); today it falls back to the bundle's own
default target.

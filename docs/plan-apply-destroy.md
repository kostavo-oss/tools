# Plan, apply, destroy

## Plan

```sh
lely plan -t dev                  # the whole deploy as one plan; nothing is changed
lely plan -t dev -o plan.json     # … as a file, to review
lely plan -t dev --destroy        # the teardown instead
```

Every step is planned in order, each given what the steps above it give. A plan changes
nothing — for the bundle, lely asks the Databricks CLI for its plan and its summary and
reads them.

Each change is one of five kinds:

| | |
| --- | --- |
| `+` create | something new |
| `~` update | something changed in place |
| `±` replace | removed and made again — **destructive** |
| `-` delete | removed — **destructive** |
| `▶` run | something that happens on every apply: a command, a job run, the bundle's upload |

and each step is **ready**, **waiting** or **skipped** — see
[your first plan](getting-started.md#3-plan).

## Apply

```sh
lely apply -t dev                 # plan, show, ask, run
lely apply plan.json              # run exactly what was reviewed
lely apply plan.json --yes        # … without a terminal to ask at
```

- **Nothing runs unasked.** `apply` asks, or was given `--yes`. With no terminal and no
  `--yes` it refuses: a forgotten flag is a failed job, never an unreviewed deploy.
- **Consent covers what was shown.** Each step is planned again right before it runs, and
  runs only if every change is one the approved plan showed — the same thing, the same kind
  of change, the same lines. Fewer is fine: someone else did part of the work. Anything new
  stops the run.
- **Destructive changes need `--allow-destructive`**, and are refused before anything runs
  where the plan already shows one.
- **A waiting step** is planned once what it waits for exists. Run in one go, lely shows that
  step's plan then and asks about it. Run from a file, it stops there: nobody has seen what
  the step will do. The next plan shows it ready.
- **`--from <step>`** starts at a step; the ones before it are planned, for what they give,
  and not run.

### When a step fails

The first step that fails stops the run. Nothing after it starts, and **nothing is rolled
back**. The result says which steps ran, which failed and which never started; running it
again finishes the job.

Exit codes: **0** done · **1** something failed · **2** lely refused — plan again.

## What a plan file is held to

A plan file is what was reviewed, so `lely apply plan.json` runs it only where it still
means the same thing:

- **the workspace** it was made against;
- **the project**: the same steps, written the same way;
- **the values** each step took from the steps above it — the plan showed
  `model_version = 14`, and 15 was never approved;
- **the git tree**: a clean checkout of the tree it was made on, for the same project of the
  repository. A bundle's notebooks are in no plan at all; this is what ties them to the
  review. A plan made with uncommitted changes says so, and is not run from a file.

A plan file holds no secret. It does hold the plan each plugin made — for the bundle, the
Databricks CLI's own — so treat it like the config it was made from.

## Destroy

```sh
lely destroy -t dev                              # plan the teardown, show it, ask, run
lely plan -t dev --destroy -o destroy.json       # … or review it first
lely destroy destroy.json -t dev
```

A destroy runs from the bottom of the list up. Each plugin removes only what it can show is
its own, and a step whose plugin has nothing to remove is skipped, with the reason.

To destroy at a terminal, the answer is the target's name. A saved destroy plan is run only
by `lely destroy <file> -t <target>`, never by `apply`.

## Status

```sh
lely status -t dev
```

lists what exists because of each step, as its plugin can show it — for the bundle, every
resource it declares, deployed or not, with its id and a link.

## Other ways to read a plan

`-f json` and `-f md` print a plan, a result or a status as JSON or Markdown, with stdout
holding that and nothing else. [`lely ui`](page.md) makes a page of a plan file.

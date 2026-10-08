# What may run

lely's job is the order, the review and the consent. These are the rules it keeps.

## Consent

- **Nothing runs unasked.** `apply` and `destroy` ask, or were given `--yes`. With no
  terminal and no `--yes` they refuse: a forgotten flag is a failed job, never an unreviewed
  deploy.
- **To destroy at a terminal, you type the target's name.** A saved destroy plan is run only
  by `lely destroy <file> -t <target>`.
- **Consent covers what was shown.** Each step is planned again right before it runs, and
  runs only if every change is one the approved plan showed. Fewer is fine; anything new
  stops the run.
- **Destructive changes need `--allow-destructive`.**
- **A plan file is held to what it was made for**: the workspace, the project and its steps
  as written, the values each step took, and a clean checkout of the same git tree.
- **No rollback.** The first failing step stops the run; running it again finishes it.

## Secrets

- A value from the environment (`${env.NAME}`) and a value a plugin marks secret are never
  printed and never written — not to a plan file, a comment, a summary or a page.
- A plan file holds no secret. It does hold each plugin's own plan, so treat it like the
  config it was made from.
- With `--github`, lely knows the run's token, and no line it says holds it. A plan that
  holds the token is shown by no command.

## What a plan says is shown, never obeyed

A plan is made from the project's own files, and a plan file can be written by hand. So
nothing in one is trusted where it is shown:

- **in a terminal**, control characters and characters that reorder text are made visible;
- **on GitHub**, every word that isn't lely's own stands in a code block or a code span — a
  resource named `@everyone` notifies nobody;
- **on the page**, everything is escaped, and a plugin's view is written again from a short
  list of elements.

## Planning runs your code

A step in the repo runs when a plan is made: its `plan`, and whatever that does. So:

- **On a pull request, give `lely plan` credentials that can read and nothing more.**
- **A pull request from a fork gets no plan**: with `--github`, lely sees where the pull
  request comes from, makes none, and says so. → [On GitHub](GITHUB.md)
- **Showing a plan runs nothing.** `lely show` and `lely ui` load no plugin and reach no
  workspace: a plan file from anywhere is safe to open.

## What lely can't see

- **Files git doesn't track** are not part of the tree a plan is held to: a new, unadded
  notebook is deployed without the plan knowing.
- **What the bundle resolves from outside** — a `BUNDLE_VAR_x` set at apply, a variable
  looked up in the workspace — can change what is deployed without changing a line of the
  plan.
- **Whether credentials are read-only.** `lely doctor` says what it can see: which workspace,
  as whom, and whether that is a workspace admin.
- **What a `Program`'s program really does.** The plan shows its command line.
- **What a step's program prints.** A deploy, a job run and a step's program are passed on
  while they run. lely hides the run's GitHub token in what they print and knows no other
  secret there: a program that prints a secret it was given prints it to the log.

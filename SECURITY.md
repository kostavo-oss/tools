# Security Policy

## How lely handles your workspace

- **No credentials are stored.** The workspace comes from `--profile`, or from the
  variables the Databricks CLI and SDK already read (`~/.databrickscfg`, `DATABRICKS_*`).
  lely hands them on to the programs a step runs and never writes a token anywhere.
- **No state.** lely keeps nothing between runs: whatever it needs to know, it asks the
  system it manages — for a bundle, the Databricks CLI.
- **Nothing that changes a workspace runs unasked.** Only `apply` and `destroy` change one,
  and they ask, or were given `--yes`; with no terminal and no `--yes` they refuse. To
  destroy at a terminal, the answer is the target's name.
- **Consent covers what was shown.** Each step is planned again right before it runs, and
  runs only if every change is one the approved plan showed. A destructive change needs
  `--allow-destructive`. A plan file is held to the workspace, the project and its steps as
  written, the values each step took, and a clean checkout of the git tree it was made on.
- **Secrets stay out of what is shown and kept.** A value from the environment
  (`${env.NAME}`) and a value a plugin marks secret are never printed and never written —
  not to a plan file, a comment, a summary or a page. With `--github` lely knows the run's
  token: it is sent to GitHub over https only, and no line lely says holds it.
- **What a plan says is shown, never obeyed.** A plan file can be written by hand, so
  nothing in one is trusted where it is shown: a terminal has control characters made
  visible, GitHub gets a code block or a code span, the page is escaped.

A plan file holds no secret. It does hold each plugin's own plan — for a bundle, the
Databricks CLI's — so treat it like the config it was made from.

## What lely does not protect you from

- **Planning runs your project's own code**: a plugin in the repo, a `command` step's plan
  command. On a pull request, give `lely plan` credentials that can read and nothing more.
  A pull request from a fork gets no plan: with `--github`, lely makes none and says so.
  `lely show` and `lely ui` load no plugin and reach no workspace: a plan file from
  anywhere is safe to open.
- **The Databricks CLI trusts the bundle with your credentials.** A bundle whose target
  names another host is not refused by the CLI: with a token from the environment, it goes
  to that host and presents the token. lely compares the two hosts and stops, but only
  after the CLI's first call. Know whose `databricks.yml` you run.
- **What a step's program prints is shown.** A deploy, a job run and a step's command are
  passed on while they run. lely hides the run's GitHub token in what they print and knows
  no other secret there: a command that prints a secret it was given prints it to the log.
- **lely can't tell whether credentials are read-only**, and can't see what a `command`
  step's commands really do: the plan shows the command line.

More in [the docs](https://kostavo-oss.github.io/lely/safety/).

## Supported versions

The latest released version on PyPI is supported. Please upgrade before reporting an
issue.

## Reporting a vulnerability

Please report security issues **privately**:

- Open a [GitHub Security Advisory](https://github.com/kostavo-oss/lely/security/advisories/new), or
- email **info@kostavo.com**.

Do not open a public issue for security reports. You'll get an acknowledgement as soon as
possible, and we'll coordinate a fix and disclosure with you.

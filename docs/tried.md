# What has been tried

lely is tested against a fake Databricks CLI and a fake GitHub, which simulate what lely
*believes* those do. It has also run for real, a few times, all on 2026-10-06. This page says
what those runs showed and what they couldn't — a first proof, not a track record.

## On a workspace

Twice, with Databricks CLI v1.19.0 on an AWS workspace, as a workspace admin.

**First**, a bundle with one job on a development target: planned, applied, listed, applied
again, updated from a plan file, and destroyed.

**Then**, a project with a step above the bundle that gives it a variable, two jobs, a
pipeline that was never started, and a step below that takes a job's id: a first deploy
through a plan file in its two rounds, an update, the page made from the real plan and the
real run, and a destroy from a plan file. Everything was asked for by its id afterwards, and
was gone.

The runs matched what lely assumed about the CLI, with one correction and one surprise:

- **The CLI trusts the bundle with your credentials.** A bundle whose target names another
  host is not refused: with a token from the environment, the CLI goes to that host and
  presents the token. lely compares the two hosts and stops, but only after the CLI's first
  call.
- **`bundle validate` writes.** It creates a folder in the workspace, so lely doesn't use it:
  `lely plan`, `status` and a destroy plan were seen to leave the workspace as it was.

## On GitHub

Once through all three workflows, in a private repository with one job in its bundle:

- **A plan that failed left a comment that said so**, as `github-actions[bot]`.
- **The comment was kept current**: the same comment became the plan, and after another push
  the plan of that push.
- **The merge applied the plan that was reviewed**, and the job was read back from the
  workspace.
- **A destructive change was refused on merge**, and applied when started by hand with the
  allow box ticked.
- **A destroy started by hand** removed everything.

→ [On GitHub](GITHUB.md#what-has-been-tried) has the detail.

## What those runs could not show

1. That a bundle another identity deployed looks "not deployed" from here — and a plan made
   by one identity, applied by another.
2. That every resource type has an id and a link in `bundle summary`: a job and a pipeline
   were tried.
3. `bundle.run`: no job was started.
4. `lely plan` with credentials that can only read.
5. That `bundle destroy` never removes more than `bundle summary` lists.
6. On GitHub: signing in with GitHub's own identity, environments and the pause for a
   reviewer, a pull request from a fork.

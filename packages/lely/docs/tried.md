# What has been tried

lely is tested against a fake Databricks CLI and a fake GitHub, which simulate what lely
*believes* those do. It has also run for real, a few times, all on 2026-10-06, before the
first release. This page is the one record of those runs: what they showed, and what they
could not. A first proof, not a track record.

## On a workspace

Twice, with Databricks CLI v1.19.0 on an AWS workspace, as a workspace admin.

**First**, with a token from the environment, a bundle with one job on a development
target: planned, applied, listed, applied again, updated from a plan file, and destroyed.
The job and the bundle's folder were gone afterwards.

**Then**, with a profile from `~/.databrickscfg`, a project with a step above the bundle
that gives it a variable, two jobs, a pipeline that was never started, and a step below
that takes a job's id. Nothing was started.

| What | Held? |
|---|---|
| A first deploy through a plan file takes two rounds: the file stops before the waiting step with exit 2, the next plan shows it ready | yes |
| An update through a plan file, with the value from the step above | yes: the job read back from the workspace said so |
| `lely plan`, `status` and a destroy plan leave the workspace as it was | yes: the folder that holds the bundles listed the same before and after |
| `bundle destroy` removes what `bundle summary` lists, and the bundle's files | yes, for these; each thing was asked for by its id afterwards and was gone |
| `--auto-approve` answers for `deploy` and `destroy`; without it and nobody to ask, `destroy` refuses and names the flag | yes |
| `bundle summary -o json` has an `id` and a `url` for a resource | yes, for a job and a pipeline |
| `bundle plan` speaks only of resources, and `deploy --plan` with nothing to change still uploads the files | yes |
| `--var` reads its value as a line of CSV | yes: `--var=a=1,b=2` set both variables |
| The page from a real plan, a real run and a real destroy plan, with links that lead to the jobs | yes |
| The CLI refuses a bundle whose target names another workspace than the credentials are for | **no** |
| `bundle validate` only reads | **no** |

**What did not hold, and what lely does about it.**

- **The CLI trusts the bundle with your credentials.** A bundle whose target names another
  host is not refused: with a token from the environment, the CLI goes to that host and
  presents the token. lely compares the two hosts and stops, but only after the CLI's
  first call. Know whose `databricks.yml` you run.
- **`bundle validate` writes.** It creates the bundle's `files` folder in the workspace,
  so lely does not call it and asks `bundle summary` instead.

Seen besides: a plan the state has moved on from is refused by the CLI with "plan serial
1 does not match state serial 2; the state has been modified since the plan was created."
On the Terraform engine, `bundle plan -o json` has no `plan_version`. A new bundle was on
the direct engine without being told.

## On GitHub

Once through the three workflows of [On GitHub](GITHUB.md), in a private repository with
one job in its bundle. Two things differed from the workflows as they stand there: the
workspace was reached with a token kept as a secret, not with GitHub's own identity, and
there were no environments.

- **A plan that failed left a comment that said so.** The first run had no credentials
  for the workspace: lely posted "The plan could not be made, so there is none to
  review", with a link to the run, as `github-actions[bot]`.
- **The comment was kept current.** With credentials the same comment became the plan,
  and after another push the plan of that push. One comment throughout, by the run's own
  token.
- **The merge applied the plan that was reviewed.** The apply job found the pull request
  of the merged commit and fetched the plan its last run had kept. lely took it for the
  tree on `main`: a merge commit has the tree the pull request was planned on. The job
  was created, and read back from the workspace.
- **A destructive change was refused on merge.** A pull request that removed a deployed
  job carried a comment that opened with it. Its merge was not applied: lely ended with
  2 and said to pass `--allow-destructive`. Started by hand with that box ticked, the
  same change was planned and applied.
- **A destroy started by hand** planned, then removed the job; it was asked for
  afterwards and was not there.

## Not yet

1. **A bundle another identity deployed**: that it looks "not deployed" from here, and a
   plan made by one identity and applied by another, which is what the workflows do.
2. **Other resource types** than a job and a pipeline: that each has an id and a link in
   `bundle summary`.
3. **`bundle.run`**: no job was started. That arguments after `--` reach the job and
   that a failed run exits non-zero are from the CLI's docs.
4. **`lely plan` with credentials that can only read.**
5. **That `bundle destroy` never removes more than `bundle summary` lists**, and whether
   `deploy` without `--auto-approve` asks before a delete.
6. **A second bundle in one project.**
7. **A step run on its own** (`Step.main()`) against a workspace, and `check --live`:
   what it says first, and what a step prints of its outputs, were seen against the
   stand-ins only.
8. **On GitHub**: signing in with GitHub's own identity, environments and the pause for a
   reviewer, a pull request from a fork, a merge after `main` moved, a first deploy with
   a waiting step.
9. **Any release from PyPI**: every run was before 0.1.0 of 2026-10-07.
10. **The `stevin` step**: it has not run on a workspace, and lely itself has not run
    the real `stevin` command: its tests run a fake of it, written from stevin's source.
    What was seen, on 2026-10-11, is stevin's own command against its in-memory
    warehouse, with the flags the step passes and plan files that had been through
    lely's plan file and back. Such a file was read and applied. A destructive one ended
    with exit 1 without `--allow-destructive` and was applied with it. A plan whose
    tables had changed ended with exit 1 and the words the step looks for. Two plans made
    one after the other, with nothing changed between them, held the same steps. None of
    that says what a warehouse does.
11. **What `lely doctor` says of an identity.** That a workspace admin is listed in the
    group `admins` is from the docs, and was not seen for an admin who is one through
    another group. Whether credentials are read-only is not said at all: no call is
    known that answers it.

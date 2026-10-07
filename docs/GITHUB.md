# lely on GitHub

A plan is reviewed where code is reviewed. With `--github`, a command that runs in GitHub
Actions keeps two things current:

- **the pull request**: the plan as one comment, updated in place on every push;
- **the run's page**: the plan, and after an apply what each step did and what exists now,
  with links into the workspace.

```sh
lely plan -t dev --github             # the comment, and the run's page
lely show plan.json --github          # the same, for a plan made earlier
lely apply plan.json --yes --github   # what was done and what exists, on the run's page
```

It is never on because of where a command runs: without `--github`, a run on GitHub posts
nothing. Outside a run, or without permission to comment, lely says what it couldn't do and
why, and the command ends as it would have without the flag.

`-f md` prints the same Markdown, for anywhere else it is wanted.

> **These workflows have run once, on a private repository, on 2026-10-06** — with two
> differences from what stands here: the workspace was reached with a token kept as a secret,
> not with GitHub's own identity, and there were no environments. What that run showed, and
> what it couldn't, is under [What has been tried](#what-has-been-tried). Read the workflows
> before you copy them.

## What lely needs from the workflow

| For | Give the job |
| --- | --- |
| the comment | `permissions: pull-requests: write`, and the step `env: GITHUB_TOKEN: ${{ github.token }}` |
| the run's page | nothing |
| the workspace | the variables the Databricks CLI reads — below, signing in with GitHub's own identity, so no secret is stored |

Signing in to Databricks from GitHub Actions without a stored secret:
<https://docs.databricks.com/aws/en/dev-tools/auth/provider-github>

The workflows below assume lely is a development dependency of the project
(`uv add --dev lely`), so that the lock file says which lely plans and applies, and run it
with `uv run`.

## Three rules these workflows keep

1. **The plan job can only read the workspace.** Planning runs the pull request's own code —
   a plugin in the repo, a `command` step — so it gets credentials that can't change the
   workspace: a service principal of its own, in a GitHub environment of its own
   (`dev-plan`). **The environment with the credentials that can change it (`dev`) must be
   limited to the `main` branch** in the repository's settings ("deployment branches").
   Without that, a pull request names `dev` in its own copy of a workflow and has them.
2. **What is applied is what was reviewed.** The merge applies the plan file the pull request
   made. lely refuses it if the project, the workspace or the git tree is not what it was
   made on.
3. **One run at a time for a target**, and no input pasted into a script: what a person types
   reaches a script as an environment variable, never as text of the script.

## Plan on a pull request

```yaml
# .github/workflows/plan.yml
name: plan

on:
  pull_request:

permissions:
  contents: read
  pull-requests: write # the plan's comment
  id-token: write # to sign in to Databricks

concurrency:
  group: plan-${{ github.event.pull_request.number }}
  cancel-in-progress: true # a new push makes the last plan stale

jobs:
  plan:
    runs-on: ubuntu-latest
    environment: dev-plan # credentials that can only read
    env:
      DATABRICKS_HOST: ${{ vars.DATABRICKS_HOST }}
      DATABRICKS_AUTH_TYPE: github-oidc
      DATABRICKS_CLIENT_ID: ${{ vars.DATABRICKS_CLIENT_ID }}
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false # no token left behind for later steps
      - uses: astral-sh/setup-uv@v7
      - uses: databricks/setup-cli@v1.19.0
      - run: uv sync --locked
      - run: uv run lely plan -t dev -o plan.json --github
        env:
          GITHUB_TOKEN: ${{ github.token }}
      - uses: actions/upload-artifact@v4
        if: hashFiles('plan.json') != ''
        with:
          name: lely-plan-dev
          path: plan.json
```

The checkout is GitHub's default for a pull request: the branch merged into `main`. That is
the tree the plan records, and the tree `main` has after the merge — as long as `main` didn't
move in between.

**A pull request from a fork gets no plan.** It has no credentials and must not be given any:
its code would run with them. `lely plan --github` sees where the pull request comes from,
makes no plan, loads nothing of the project, says so on the run's page and ends with 0. Don't
use `pull_request_target` to get a fork's plan. A run that is about a pull request and isn't
told where it comes from — one started by a comment on it (`issue_comment`) — is treated the
same way: lely can't tell that it isn't a fork's.

### What the comment is worth

The comment is written by a workflow that the pull request itself can change, in a job that
runs the pull request's code. It is there to help a reviewer read the change. It is not
evidence: someone who can push to the repository can make it say anything, and the reviewer
is reading that person's diff as well.

What is applied does not rest on the comment. `lely apply plan.json` plans every step again
and refuses any change the file doesn't hold — and it runs on `main`, with the workflow as
it is on `main`, and credentials no pull request can reach.

## Apply on merge

```yaml
# .github/workflows/apply.yml
name: apply

on:
  push:
    branches: [main]

permissions:
  contents: read
  actions: read # to fetch the plan the pull request made
  pull-requests: read # to find that pull request
  id-token: write

concurrency:
  group: lely-dev # one run at a time for the target, apply or destroy
  cancel-in-progress: false

jobs:
  apply:
    runs-on: ubuntu-latest
    environment: dev
    env:
      DATABRICKS_HOST: ${{ vars.DATABRICKS_HOST }}
      DATABRICKS_AUTH_TYPE: github-oidc
      DATABRICKS_CLIENT_ID: ${{ vars.DATABRICKS_CLIENT_ID }}
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false # no token left behind for later steps
      - uses: astral-sh/setup-uv@v7
      - uses: databricks/setup-cli@v1.19.0
      - run: uv sync --locked
      - name: Fetch the plan that was reviewed
        env:
          GH_TOKEN: ${{ github.token }}
          REPO: ${{ github.repository }}
          COMMIT: ${{ github.sha }}
        run: |
          head=$(gh api "repos/$REPO/commits/$COMMIT/pulls" --jq '.[0].head.sha // empty')
          if [ -z "$head" ]; then
            echo "This commit came from no pull request: no plan was reviewed."
            exit 1
          fi
          run=$(gh run list --repo "$REPO" --workflow plan.yml --event pull_request \
            --commit "$head" --status success --limit 1 \
            --json databaseId --jq '.[0].databaseId // empty')
          if [ -z "$run" ]; then
            echo "No plan was made for the pull request's last commit ($head)."
            exit 1
          fi
          gh run download "$run" --repo "$REPO" --name lely-plan-dev
      - run: uv run lely apply plan.json --yes --github
```

`--yes` is the consent: the merge is the approval, and the file is what was approved.

What this does not do, and what to do then:

- **`main` moved between the plan and the merge.** The tree is another one and lely refuses
  the plan (exit 2). Require branches to be up to date before merging, or use a merge queue,
  and it doesn't happen.
- **A push that came from no pull request** has no reviewed plan: the fetch stops the job,
  and nothing is applied.
- **A plan with a destructive change** is refused without `--allow-destructive`. Apply it by
  hand, below, where someone says so.
- **A first deploy with a waiting step** stops before that step, as the plan said it would.
  The next plan shows the step ready.
- **A step that waits on *every* deploy** — it takes what only a run produces — can never be
  applied from a file, by a merge or by hand: only `lely apply -t <target> --yes` runs it,
  which plans and applies in one go, so nobody reads that step's plan before it runs. Whether
  that is acceptable is the project's to decide; these workflows don't do it.

## Apply or destroy by hand

For what a merge doesn't cover, and for every destroy. The run plans, stops, and applies that
plan once someone has read it and approved. The second job runs in an environment of its own,
`<target>-by-hand`: the same credentials as `<target>`, limited to `main`, and with
**required reviewers** in the repository's settings — so it waits for one of them. (Required
reviewers on `<target>` itself would make every merge wait too.)

```yaml
# .github/workflows/by-hand.yml
name: by hand

on:
  workflow_dispatch:
    inputs:
      action:
        type: choice
        options: [apply, destroy]
      target:
        description: The target, typed out
        type: string
        required: true
      allow_destructive:
        description: Apply changes the plan marks destructive
        type: boolean
        default: false

permissions:
  contents: read
  id-token: write

concurrency:
  group: lely-${{ inputs.target }}
  cancel-in-progress: false

env:
  DATABRICKS_HOST: ${{ vars.DATABRICKS_HOST }}
  DATABRICKS_AUTH_TYPE: github-oidc
  DATABRICKS_CLIENT_ID: ${{ vars.DATABRICKS_CLIENT_ID }}
  # what was typed and ticked reaches a script as a variable, never as its text
  TARGET: ${{ inputs.target }}
  ACTION: ${{ inputs.action }}
  DESTROY: ${{ inputs.action == 'destroy' && '--destroy' || '' }}
  ALLOW: ${{ inputs.allow_destructive && '--allow-destructive' || '' }}

jobs:
  plan:
    runs-on: ubuntu-latest
    environment: ${{ inputs.target }}-plan # credentials that can only read
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false # no token left behind for later steps
      - uses: astral-sh/setup-uv@v7
      - uses: databricks/setup-cli@v1.19.0
      - run: uv sync --locked
      - run: uv run lely plan -t "$TARGET" $DESTROY -o plan.json --github
      - uses: actions/upload-artifact@v4
        with:
          name: lely-plan
          path: plan.json

  run:
    needs: plan
    runs-on: ubuntu-latest
    environment: ${{ inputs.target }}-by-hand # required reviewers: the plan is read first
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false # no token left behind for later steps
      - uses: astral-sh/setup-uv@v7
      - uses: databricks/setup-cli@v1.19.0
      - run: uv sync --locked
      - uses: actions/download-artifact@v4
        with:
          name: lely-plan
      - run: |
          if [ "$ACTION" = destroy ]; then
            uv run lely destroy plan.json -t "$TARGET" --yes --github
          else
            uv run lely apply plan.json --yes --github $ALLOW
          fi
```

A target that was mistyped names an environment with no credentials: nothing can sign in,
and nothing runs.

## What has been tried

One run through all three workflows, on 2026-10-06, in a private repository with one job in
its bundle and a `command` step above it:

- **A plan that failed left a comment that said so.** The first run had no credentials for the
  workspace: lely posted "The plan could not be made, so there is none to review", with a link
  to the run, as `github-actions[bot]`.
- **The comment was kept current.** With credentials, the same comment became the plan; after
  another push it was the plan of that push. One comment throughout, by the run's own token.
- **The merge applied the plan that was reviewed.** The apply job found the pull request of
  the merged commit, fetched the plan its last run had kept, and lely took it for the tree on
  `main` — a merge commit has the tree the pull request was planned on. The job was created,
  and read back from the workspace.
- **A destroy started by hand** planned, then removed the job; it was asked for afterwards and
  was not there.

- **A destructive change was refused on merge.** A pull request that removed a deployed job
  carried a comment that opened with it — "Destructive: `app: jobs.second`". Its merge was
  not applied: lely ended with 2 and said to pass `--allow-destructive`, and the job was
  still there. Started by hand with that box ticked, the same change was planned and applied.

Not tried in that run: signing in with GitHub's own identity (a token secret was used);
environments, and the pause for a reviewer in the by-hand workflow (a private repository on a
free plan has none); a pull request from a fork; a merge after `main` moved; a first deploy
with a waiting step.

## What is not known yet

- **A plan made by one identity and applied by another.** The plan job and the job that
  applies sign in as different service principals. lely holds a plan to the workspace's host,
  not to who made it. Whether the Databricks CLI plans the same changes for both has not been
  tried on a real workspace ([004](https://github.com/kostavo-oss/lely/blob/main/spec/004-asset-bundle.md), V7); a development target,
  whose bundle lives under the deploying user's own folder, will not. Use a target whose
  `root_path` doesn't depend on who runs.
- **Whether credentials are read-only** is nothing lely can check; `lely doctor` says what it
  can see.
- **The comment with a run's own token.** lely only updates a comment it could have written:
  one by whoever the token is, or — for a run's own token, which is nobody's — one by a bot,
  any app's bot. With a run's own token it found its comment and updated it, twice.

## What is posted, and what never is

- Nothing a plan says is Markdown where it is shown: a resource named `@everyone`, or a link,
  or an image, is text in a block, and can't end the block it is in.
- A plan that couldn't be made takes the place of the last plan's comment, so an old plan
  doesn't stand there as the new one. So does a plan that was made and can't be shown —
  GitHub won't take it. What went wrong is on the run's page, which hides a run's secrets;
  the comment links there and repeats none of it. If GitHub can't be reached at all, the
  last comment stays: its last line names the commit it was made for.
- The token is sent to GitHub's API over https and nowhere else, and not along with a
  redirect. What is posted is searched for it first — as it is written, and as
  `actions/checkout` keeps it — which catches a step that prints its environment, not every
  spelling of a token. A plan that holds the token is not written at all: `lely plan
  --github` fails and says which step printed it.
- A comment too long for GitHub is told shorter — without each change's details, then as
  counts — and says so. The counts and the destructive changes are always there.

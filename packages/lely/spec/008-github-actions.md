# 008 — GitHub

**Status:** built, and run once through the three workflows on a real repository, 2026-10-06
([Done when](#done-when)).
Phase two.

## Why

A plan is reviewed where code is reviewed: on the pull request. Until lely puts its plan there —
and keeps it current as the branch changes — the one plan for the whole deploy is something
people have to go and fetch from a log.

## Requirements

The owner asked for a way to update GitHub Actions. That means: **update what GitHub shows**
(decided 2026-10-05). So:

- **R1** — `lely plan -f md` and `lely show plan.json -f md` render a plan as Markdown, from the
  same plan the terminal, the JSON file and the page show. A destroy plan renders the same way.
  *(design)*
- **R2 — The pull request is kept up to date.** On a pull request, the plan is posted as one
  comment that covers every step, and that comment is *updated* on later pushes instead of
  another being added. One comment per target. lely finds its own comment by a marker it puts
  in it — the memory is GitHub's, not lely's. *(owner; the marker is how stevin does it)*
- **R3 — The run's page is kept up to date.** The plan goes to the job summary; after an apply,
  so does what each step did and the overview of what now exists
  ([004/R7](004-asset-bundle.md)), with links into the workspace. A run can be read without
  opening its log. *(owner)*
- **R4 — lely does this itself, when asked.** A project adds `--github` to the commands its
  workflow already runs (`lely plan -t dev --github`); there is nothing separate to install or to
  keep in step with lely's version. It is never on just because of where a command was run.
  *(follows from the owner's answer: no ready-made Action was asked for; the flag is agreed)*
- **R4a — A pull request from a fork gets no plan, and is told so.** It has no credentials and
  must not be given any: its code would run with them. The job summary says the plan was
  skipped, and why. *(agreed)*
- **R5** — Outside a GitHub Actions run, or without permission to comment, it says what it
  couldn't do and why, and the plan itself still succeeds or fails on its own merits.
  *(agreed)*
- **R6** — The token is never printed and never written to a plan, a comment or a summary.
  *(agreed)*
- **R7 — The docs carry a workflow to copy:** plan on a pull request, apply on merge, destroy
  only when started by hand with the target named — with the `concurrency:` group that keeps two
  runs for one target from overlapping, with no input pasted into a script as text, and with
  the plan job given credentials that can only read — planning runs the pull request's own code
  ([002/R13a](002-plugins.md)). *(design, as an example instead of an Action; the last part was
  found in review)*

## Not in this spec

Asked on 2026-10-05, and not chosen:

- **Writing the workflow files.** lely does not generate or rewrite `.github/workflows/…`.
- **A ready-made Action** (`uses: kostavo-oss/lely@v1`) with a moving version tag.

Also not here: CI systems other than GitHub Actions; a lock of lely's own.

## Decided

- **What "update GitHub Actions" means** (was D1): what GitHub shows — the pull-request comment
  and the job summary. *(owner, 2026-10-05)*
- **How a project asks for it** (was D4): a `--github` flag — R4.
  *(owner, 2026-10-05: as proposed)*
- **A pull request from a fork** (was D3): no plan, and the job summary says so — R4a.
  *(owner, 2026-10-05: as proposed)*

- **Which plan `apply` runs on merge** (was D2): the file the pull request produced, kept as
  an artifact — what runs is exactly what was reviewed, and a stale one is refused. A first
  deploy with a waiting step takes two runs ([005/R27](005-plan-apply-destroy.md)).
  *(decided by the owner, 2026-10-06, as the builder proposed: the reviewed file)*

## To decide

Nothing.

## As built

Built on 2026-10-06. `docs/GITHUB.md` is what a project reads. The builder's calls where the
spec left room — none is the owner's yet:

- **`--github` is on `plan`, `show`, `apply` and `destroy`.** `show plan.json --github` posts
  a plan made earlier. `plan` and `show` write the comment and the run's page; `apply` and
  `destroy` write the run's page only: the comment is the plan's.
- **`-f md` is on `status`, `apply` and `destroy` as well** as on `plan` and `show` (R1).
- **Nothing a plan says is Markdown.** A plan is made from the pull request's own files, so a
  resource named `@everyone` or `![](https://…)` must not notify anyone or load anything.
  Every word that isn't lely's own stands in a fenced block or a code span, each longer than
  any run of backticks inside it. Checked against GitHub's own renderer.
- **The marker names the kind, the target and the project** (`<!-- lely:plan:dev:team-a -->`):
  one comment per target (R2), and also one for a destroy plan and one per project of a
  repository with several.
- **Only a comment lely could have written is updated**: by whoever the token is, or by a bot
  when the token is a run's own. Anyone can write a comment that starts with the marker, and
  could change the plan in it afterwards. *This is more than stevin does.*
- **A plan that could not be made takes the last plan's place** in the comment, with a link
  to the run and none of the error: what a failing program printed is on the run's page,
  where GitHub hides a run's secrets, and not in a comment, where nothing does.
- **A fork (R4a) is told before anything of the project is loaded,** and `lely plan` ends
  with 0. A pull request whose origin lely can't read is treated as a fork. `apply` and
  `destroy` with `--github` refuse one (exit 2) — the spec spoke only of the plan.
- **The token (R6)** is read from `GITHUB_TOKEN`, or `GH_TOKEN`; sent only over https and not
  along with a redirect; and whatever is posted is searched for it first.
- **A comment has a size.** One too long for GitHub is told shorter — without each change's
  details, then as counts per step — and says so; the counts and the destructive changes are
  always there. The run's page takes the whole plan.
- **The workflows (R7) are three**: plan on a pull request, apply on merge, and one started
  by hand for a destroy and for whatever a merge doesn't cover — which plans, waits for an
  approval on the environment, and runs that plan.

**Found in review, 2026-10-06** (the fifth, of this branch alone; each has a test):

- A run of 80 backticks in a name, or a line of 255 in a block, ended the code span or the
  block it stood in — GitHub stops counting there — and the rest of the plan was Markdown.
  Seen on GitHub's own renderer. No run of backticks longer than 16 is shown as it is now.
- A plan lely couldn't write down (half a character in a change's name) or GitHub wouldn't
  take left the last plan standing under a green run. A note that there is a new plan now
  takes its place.
- A token pasted with its line break was repeated on stderr, in the words of an error.
- `show --github` posted a fork's plan file; a run started by a comment on a pull request, or
  by another run, was not placed and so not treated as a fork's.
- A plan that holds the run's token was written to the plan file and to stdout. With
  `--github`, `lely plan` now fails instead, and names the step (R6).
- One failed request made a second comment that was never updated again.

Left as it is, and said: with a run's own token, a comment by *any* app's bot that starts
with the marker is taken for lely's. And the comment is written by a workflow the pull
request can change, so it is an aid to the reviewer and not evidence — `docs/GITHUB.md`,
"What the comment is worth".

Not known, and said in `docs/GITHUB.md`: a plan made by one identity and applied by another
([004](004-asset-bundle.md), V7), which is what the workflows do; and that a run's own token
can't ask who it is, which decides how lely finds its comment.

## Done when

- R1–R7 each have a test; posting and updating a comment is tested against a fake GitHub, the way
  stevin tests its own. **Done** — R7 is a document: its workflows are read, not run.
- A pull request in a real repository has carried a plan comment that changed in place, and a
  merge has left a summary of what was created. **Done, 2026-10-06**, in a private repository
  made for it: the comment was a failed plan, then the plan, then the plan of the next push —
  one comment, by the run's own token; the merge applied the plan that was reviewed and the
  job was read back from the workspace; a destroy started by hand removed it. What that run
  differed in and didn't try is in `docs/GITHUB.md`, "What has been tried".
- D2 is answered here. **Done.**

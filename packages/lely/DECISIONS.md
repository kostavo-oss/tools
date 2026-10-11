# Decisions

Why lely is the way it is: a log, oldest first. What must be true of the code is in
[RULES.md](RULES.md); this file says why, and what was tried or left behind.

**An entry is never edited.** A decision that changes gets a new entry at the end, which
names the one it supersedes by its number. An entry is here only when it says something
the rule and the code do not: a reason, or an alternative that was rejected.

## 1. 2026-09-29 — The direct engine is required

`bundle deploy --plan` exists on the direct engine only, and a reviewed plan is what
lely hands the CLI. A bundle on the Terraform engine is refused.

## 2. 2026-09-29 — A bundle is fed variables, nothing else

A step never writes YAML for the bundle to include, so everything a bundle deploys can
be read in its own files. Rejected: a `preinit` script that writes an included file,
which is the only way the bundle's own scripts get a value back in.

## 3. 2026-10-05 — The bundle is a plugin, and the config is one list

The core then does one thing, run steps in order through one contract, and what the
bundle needs every plugin can have. A project with two bundles or with none is written
the same way. It replaced a fixed middle: `pre:`, `bundle:`, `bundle_vars:`, `post:`.

## 4. 2026-10-05 — `destroy` is the third verb

A deploy script only goes one way, so development and pull-request environments are
made and never removed. It replaced "teardown is a non-goal".

## 5. 2026-10-05 — No state, and what that costs

A plugin reads what it needs from the system it manages; the Databricks CLI knows what
a bundle deployed. The price is known: lely cannot see what the config no longer names.
A step that is removed or renamed, or a target taken out of `targets`, leaves what it
deployed. Destroy first, then remove the step.

## 6. 2026-10-05 — One spelling for a reference, and declared outputs

Every reference names the step its value comes from. The short `${var.…}`,
`${bundle.…}`, `${workspace.…}` and `${resources.…}`, from when the bundle was built
in, went. A plugin declares what it gives and when each is known, because without that
a name could not be checked until it was used.

## 7. 2026-10-05 — `-t` is always given

A command that destroys has both words in it, the verb and the target, and an empty
`-t` would be read by the Databricks CLI as "the default target". It replaced falling
back to the bundle's own default target. A target no step runs for is refused for the
same reason: no plugin would be asked about it, and it used to end "Nothing to do".

## 8. 2026-10-05 — Consent is asked, or given in the command

With no terminal and no `--yes` lely refuses: a forgotten flag is a failed job, never
an unreviewed deploy. To destroy, the answer is the target's name, so that `prod` is
never destroyed by a reflex. Rejected: a flag in the config that allows a destroy.

## 9. 2026-10-05 — A saved destroy plan is run by `lely destroy`, not by `lely apply`

As first written, `lely apply destroy.json --yes` would have destroyed a target with
neither "destroy" nor its name on the command line.

## 10. 2026-10-05 — The approval check compares what was shown

A change in the fresh plan must be one the approved plan showed: the same key, action
and lines. It replaced matching a change by its name alone. A reviewed plan goes stale
when the workspace moves under it, which is what a reviewed plan should do.

## 11. 2026-10-05 — A saved plan stops at a waiting step

Nobody has seen what a waiting step will do, so a file is refused there and the next
plan shows the step ready: a first deploy through a file can take two rounds. `--yes`
without a file runs the step, and is called lely's unreviewed way of running. Rejected:
guessing the value, and going past the step to the ones below.

## 12. 2026-10-05 — Three exit codes

So a pipeline can tell "plan again" (2) from "something broke" (1) without reading the
message. Before, every error ended with 1.

## 13. 2026-10-05 — A plan file is held to the config as lely reads it, and to its inputs

It replaced a hash of the config file's text, which made a plan stale on an unrelated
edit to `pyproject.toml`. The values a step took are compared too, because the bundle's
own changes read the same with `model_version` 14 as with 15.

## 14. 2026-10-05 — A plan file is for a clean checkout

A bundle's notebooks and wheels are in no plan, so the git tree is what ties them to
the review. The tree and not the commit, so a merge that changes nothing keeps a plan
valid. The whole repository, because a step can reach outside the config's folder.
Without the plan file itself, so a plan committed for review does not refuse itself.
Tried and dropped for a plan made with uncommitted changes: holding it to nothing, and
holding it to the exact contents of the files. Each let something through. Since
2026-10-06 a sparse checkout counts as the tree of what is checked out: it read as the
whole checkout, so a plan ran where a step would find files missing.

## 15. 2026-10-05 — A value from the environment is a `Secret`

It is the one way to keep it out of every plan, file and line of output wherever it
flows.

## 16. 2026-10-05 — A bundle step always deploys, and its upload is a `run`

`bundle plan` speaks only of resources. Without the `run`, a plan that says nothing
changes would be followed by a deploy that ships new notebooks and wheels.

## 17. 2026-10-05 — Apply hands the CLI a fresh plan

The plan from the plan file would be refused by the CLI as stale the moment anything
had been deployed. So the step is planned again, lely checks that plan against the
approved one, and the fresh one goes to `bundle deploy --plan`.

## 18. 2026-10-05 — An option can name a whole step

`bundle.run` has to run the CLI as its bundle step does, with the same directory and
`--var`s, and a step is given nothing but its options. On 2026-10-06 holding everything
a plugin reads from the named step to the plan was tried and backed out: a bundle step
gives who is running, so a plan made by one identity and applied by CI was refused for
nothing.

## 19. 2026-10-06 — `bundle summary`, not `bundle validate`

On a real workspace `bundle validate` created the bundle's `files` folder. A plan then
left a folder behind and needed credentials that can write. `summary` gives the same
resolved config and creates nothing.

## 20. 2026-10-06 — lely compares the bundle's host itself

The CLI was assumed to refuse a bundle whose target names another workspace. It does
not: with a token from the environment it goes to that host and presents the token.
lely can only stop what comes after the CLI's first call.

## 21. 2026-10-06 — A step is told what it is planned for

The bundle held back the id of a pipeline the next deploy would replace. That is right
for a deploy; for a destroy it skipped the step that had to take down what it had made
for that pipeline.

## 22. 2026-10-05 — The page is one HTML file that only shows

It can be opened from disk, passed on, and hold a plugin's own view. Rejected: a
terminal app, and a button that applies. A plugin's view is made when the step is
planned and kept in the plan file, so the page needs no plugin, project or workspace
and a plan file from anywhere is safe to open.

## 23. 2026-10-06 — A plugin's view is written again, and keeps no `div`

A plan file can be written by hand, so a view is not trusted. Counting tags was not
enough: a browser closes elements its own way, and a view with a `div` or a `details`
in it ended the frame, the step and the list of steps in Chrome. A view now keeps no
element the page around it is built from. Rejected: an `<iframe>`.

## 24. 2026-10-06 — GitHub is a flag on the commands

`--github` on the commands a workflow already runs: nothing separate to install or to
keep in step with lely's version. Asked for and not chosen: writing the workflow files,
and a ready-made Action with a moving version tag.

## 25. 2026-10-06 — What a comment may hold, and which comment is lely's

Only a comment by the token's own identity, or by a bot for a run's own token, is
updated: anyone can write a comment that starts with the marker and change the plan in
it afterwards. A plan that failed puts a link in the comment and none of the error: the
run's page hides a run's secrets, a comment does not.

## 26. 2026-10-06 — A merge applies the plan the pull request made

The file is kept as an artifact, so what runs is what was reviewed, and a stale one is
refused.

## 27. 2026-10-06 — A file is written beside its place and moved there

`lely ui` wrote through a link standing where the page goes, and over an unrelated
`plan.html`. What is no file is written to as it is: writing beside it broke
`-o /dev/null`.

## 28. 2026-10-07 — `$${` writes a literal `${`

`${` always starts a reference, so a shell's own `${HOME}` in a command could not be
written at all. The escape is the one Terraform and Compose use.

## 29. 2026-10-07 — A program is heard while it changes something

A deploy or a long job run was silent until it ended, and a warning from a program that
succeeded was never shown.

## 30. 2026-10-08 — A step runs on its own, and `command` is removed

A step is useful before a config exists and to a team that does not use lely. The class
stays the contract and the command line is derived from it: had lely talked to a step
as a program, by its stdout and exit code, the step would be the `command` plugin
again, a box lely cannot hold to the rules. So `command` went, and a program is a
`Program`. `check` takes `-t` and is not offline, because `plan` needs the target to
read. The plan file is `--plan-file`, because a positional file beside `-t` was
ambiguous.

## 31. 2026-10-11 — The flags of a step are lely's own copy

On 2026-10-08 the flag machinery was to live in lely and be imported back by
leeghwater. The tools now share a repository whose rule is that no package imports
another, so each keeps its own.

## 32. 2026-10-11 — One place per fact

The `spec/` folder and the design document held rules, decisions, runs and history
together, and a third of what they said had gone stale. Rules are in `RULES.md`,
reasons here, what ran for real in `docs/tried.md`, how lely works in the docs.

## 33. 2026-10-11 — The `stevin` step applies the plan that was reviewed

The step could plan and not apply (kostavo-oss/tools#41). Four things were settled.

**The reviewed file is what runs.** stevin's plan file is the step's payload, and
`apply` hands the approved one to `stevin apply`. Rejected: planning again at apply,
comparing, and applying the new plan, which is what the bundle step does (entry 17 has
why it must). lely's lines for a stevin plan are titles and risk classes; the statements
are in the file. Two plans can read the same in lely and run different SQL, and only
the reviewed file is known to be what the reviewer saw. stevin also holds its own file
to the live tables as they were at review, which a plan made a second ago cannot do.
Until now nothing in a plan file was kept for apply. So a plugin is handed the approved
plan beside the fresh one (`Context.approved`). Rejected: keeping stevin's file beside
lely's plan file, which a workflow would have to carry along and nothing would tie to
what was approved.

**The reviewed file is still held to a fresh plan.** A plan file is an artifact that
passes between jobs, and lely does not obey what one says. So the step runs the
approved file only when its steps are the ones stevin would run now. Rejected: trusting
the file as stevin's own workflow does. The cost: a plan stevin applied in part is not
gone on with from the same file, where `stevin apply` on its own would resume it. A
table applied in part reads differently in a fresh plan, so lely's own check refuses
that file in most cases already.

**A destroy drops nothing.** A dropped table is its rows, and no later apply brings
them back. Rejected: dropping for targets that say so. There is no option, so no
config can make a destroy cost data.

**A risk class lely does not know is destructive.** It was read as an update. A newer
stevin may add a class that loses data; lely would rather ask than wave through what it
cannot read, as the bundle step does for an action it does not know.

stevin gives a stale plan no exit code of its own, so the step knows the refusal by
stevin's words (kostavo-oss/tools#65).

## 34. 2026-10-11 — What a step is made from is what its plugin is handed

The hash counted how a `lely.yml` spelled a number or a boolean (`1.10`, `yes`), and a
`pyproject.toml` has no spelling to count: the same project hashed differently in the
two files, and a plan made from one was refused with the other. The spelling was there
for a reason, which stays: an option that wants text is handed `1.10` as written, so
`1.10` edited to `1.1` is another step. So the hash now follows the option's type. Text
counts as the text the plugin gets, anything else as its value.

Rejected: hashing the value alone, as the issue put it. `1.10` edited to `1.1` in a
bundle variable would then pass a plan file unseen, outside git. Rejected: keeping a
number's spelling from TOML too, so both files hash a spelling. Where a TOML value was
written is found by scanning the text, which may land on a comment: good enough for a
position in a message, not for a value.

The cost: the hash of a step with a number or a boolean in its options changes, so a
plan file 0.3.1 saved for one is refused once. The file's format number stays, because
a new one would refuse every saved plan, also in `lely show`. A plan file names the
lely that made it, so the refusal says that the versions differ and that this may be
why.

## 35. 2026-10-11 — `lely doctor` does not say whether credentials are read-only

The promise is given up. `doctor` was to say whether the credentials at hand can do
more than read, so a pull request's plan is not run with ones that can write. No call
of Databricks is known that answers that: what an identity may do is granted per
object, and nothing we know of sums it up. So `doctor` says
the one thing it can read off, whether the identity is a workspace admin, and for
anyone else that it cannot tell.

Rejected: a guess, such as trying a harmless write or reading a few grants. A wrong
"read-only" is worse than none: it would be taken as a check that was made, on the one
question where being wrong lets a pull request change a workspace. Rejected: leaving
the rule open until an API turns up, which keeps a promise in the rules that nobody is
working on. The rule had the number 6 of the `CLI` area; what `doctor` does say is `CLI-8`.

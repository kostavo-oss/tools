# How it works

What lely does inside when a command runs, for someone who reads or changes the code.
How to use it is on the other pages. What must be true of the code is in
[RULES.md](https://github.com/kostavo-oss/tools/blob/main/packages/lely/RULES.md), and
why it is so in
[DECISIONS.md](https://github.com/kostavo-oss/tools/blob/main/packages/lely/DECISIONS.md).

## A run, from the config to a plan

```
lely.yml  or  pyproject.toml [tool.lely]
        │
        ▼
   config ──▶ check ──▶ for each step, top to bottom:
   (one list)  (offline)   resolve its options from what the steps above give
                           ├─ all known  → the plugin plans it          (ready)
                           └─ something missing → no plan, by name      (waiting)
                                   │
                                   ▼
                              Plan ──▶ terminal · Markdown · JSON file · page

apply:    top to bottom, each step planned again, checked against what was approved, applied
destroy:  options resolved top to bottom, then bottom to top: planned again, checked, destroyed
status:   options resolved top to bottom, each plugin asked what exists
```

`config` reads the file into located nodes, so every value keeps its file, line and
column. `planning.check` is what `lely validate` runs: it finds every plugin, reads
every step's options and checks every reference where it stands, with no workspace.
Finding a plugin imports its module, so `validate` runs the project's own code.

`planning.plan` then walks the list once, in a `Session`. For each step it resolves the
options from what the steps above have given so far. When every value is known the
plugin is asked for its plan and the step is ready. When one is not, the plugin is not
called with half its options: the step is waiting, and the plan names the output it
waits for. `apply`, `destroy` and `status` in `running` use the same `Session`, so each
resolves options the same way.

## The modules

The core does no I/O of its own. References, options, the approval check, the plan
file, the schema and the renderers are pure: values in, values out. I/O is at the
edges.

| Module | Does |
|---|---|
| `config` | `lely.yml` or `pyproject.toml` into one list of steps, every value located. `find` and `load` read the disk; `load_text` is pure. |
| `refs` | `${steps.<name>.<output>}` and `${env.<NAME>}`: their shape, where one may stand, what it answers |
| `options` | a step's `with:` into the plugin's `Options` dataclass, strictly |
| `registry` | `uses:` into a plugin class. An edge: it imports the plugin's module. |
| `step` | the contract, what a step is given, and the bases `Step` and `Program` |
| `model` | plans, changes, outputs, overviews, results: frozen dataclasses |
| `planning` | `check` and `plan`, and the `Session` that walks the list |
| `approval` | what may run: a plan file against the project, a fresh plan against the approved one |
| `running` | `apply`, `destroy`, `status` |
| `planfile` | a plan and a run's result, to JSON and back |
| `schema` | the config's shape as JSON Schema, built from the plugins |
| `render/` | the terminal (`rich`), Markdown, the page (`html`), and the words they share (`words`) |
| `steps/` | the plugins lely ships: `bundle`, `bundle.run`, `stevin` |
| `solo`, `flags` | the command line of a step run on its own, and its options as flags |
| `testing` | the contract as checks a test can run |
| `databricks`, `source`, `process`, `github` | edges: the Databricks CLI, git, any other program, GitHub's API |
| `cli` | the commands, consent, exit codes, and writing files |

No module outside `steps/` imports a plugin. What the core knows is the Databricks CLI
itself, which is not a plugin: `testing.READS` lists the calls that only read, and
`cli` knows which version brought the direct engine.

## What a step gives, and what the next one takes

A plugin declares its outputs, each with when it is known: at plan, once it exists, or
after every run. A name that depends on the project is declared as a shape, such as
`resources.<type>.<key>.id`. `refs.match` finds the declared output a reference names:
the most literal declaration wins, and what is left of the reference walks into the
value.

A plugin's plan may leave out an output that exists only after apply and name it in
`later`. A reference to a name that is neither given nor in `later` is an error at
plan. A reference to one that is in `later`, or to an output of a run, answers
`Unknown`, and the step that holds it waits.

An option of type `Linked` names a whole step. The plugin is handed that step's
resolved options and its outputs; `bundle.run` uses it to open the bundle exactly as
its bundle step does.

## What is checked before a step runs

A plan file is read strictly and then held to three things by `approval`: the
workspace's host, the project, and the git tree. "The project" is each step's name and
plugin and a hash of its plugin, targets and options (`planning.made_from`). An
option counts as its plugin is handed it, with a reference as it was written
(`options.handed`): the value, not how a file spells it. `source.read` asks git for the tree of `HEAD`, the project's
folder in the repository and whether anything differs from `HEAD`. When the plan file
is tracked, or the checkout is sparse, the tree is made in an index and an object
store of its own, in a temporary folder.

`running.apply` then goes down the list. For each step it resolves the options and
compares every value the step takes with the value the plan recorded
(`approval.same_inputs`), asks the plugin for a fresh plan, and lets the step run only
if every change in it is one the approved plan showed (`approval.approved_changes`). A
step that was waiting when the plan was made has no approved changes: `running` asks
the command line what to do there, through `at_waiting`.

`running.destroy` first walks down, resolving options and planning each step for what
it gives the others, and compares inputs. Only then does it walk up, asking each plugin
for its destroy plan and checking it the same way.

A refusal is a `Refused`, any other problem a `LelyError`. The command line ends with 2
for the first and 1 for the second.

## The plan file

JSON, format 4 (`planfile.FORMAT_VERSION`). A step's plan is written by
`step_plan_to_json` and read back by `step_plan_from_json`. What a plugin hands back is
made plain JSON at the moment it is planned (`planfile.normalised`), so the approved
plan and the fresh one compare the same whether or not a file came between them. A
secret output is written as `{"$secret": true}` and read back as a `Secret` without a
value. Nothing in the file is used at apply but to compare: every step is planned
again and gives its values again.

A run's record, written by `apply -o` and `destroy -o`, is the result as JSON with a
`result_format` of 1. `lely ui` is the only thing that reads one.

## The plugins lely ships

**`bundle`** asks the Databricks CLI. To plan it calls `bundle summary` and
`bundle plan`, each with `-o json` and the step's `vars` as `--var`. The summary is the
resolved config with the `id` and `url` of what is deployed; it gives the step's
outputs. The plan gives the changes, and is kept as the step's payload. To apply, the
fresh payload is written to a temporary file and handed to
`bundle deploy --plan <file> --auto-approve`. The overview and the destroy plan come
from `bundle summary`; destroying is `bundle destroy --auto-approve`. What the plugin
assumes of the CLI, and what was seen of it on a workspace, is in the docstring of
`src/lely/steps/bundle.py`.

**`bundle.run`** runs `databricks bundle run <key>` in the directory and with the
`--var`s of the bundle step it names.

**`stevin`** runs the `stevin` command and imports nothing of stevin. To plan it runs
`stevin plan --target <t> --config <c> --output <tmp> --format json` and turns stevin's
plan file into one change per table, with a line per step. The file is kept whole as the
step's payload. To apply, the payload of the approved plan is written to a temporary file
and handed to `stevin apply <file> --config <c>`, with `--allow-destructive` when the
plan lely let through holds a destructive change. Before that the approved file is
compared with the plan made right before, every step and the changes it carries out: the core hands a plugin both,
the fresh plan as `plan` and the approved one as `ctx.approved`. stevin exits 1 for a
refusal and for a failure alike, so a stale plan is known by stevin's words. The overview
is the `tables` of a `stevin plan`. It has no destroy. What the plugin assumes of
stevin's command line is numbered in `tests/fake_stevin.py`.

**`Program`** is no plugin lely ships but a base in `lely.step`: a class with a
`command`. It runs the program with `process.run`, never through a shell, and reads
its outputs from the JSON object on the last line the program printed.

A program that changes something is heard while it runs: `process.run` takes `said`,
which is given each line from both streams as it comes. The plugins pass it to the
step's log, which is the command line's, so a line a program wrote is cleaned and
searched for the run's token like any other line lely prints.

## A step on its own

`Step.main()` calls `solo.main`. `flags` turns each field of the step's `Options` into
a flag, and what the flags gave back into the same config nodes a `lely.yml` would
hold. `solo` makes a config of that one step, named as a config in the working
directory would name it (`./path/file.py:Class`), and goes through `planning`,
`running`, `planfile` and `approval` like any project. That is why a plan a step writes
is a one-step lely plan.

A plan keeps a step's outputs that have a plain name and the ones another step takes,
and a run's result keeps none. So `planning.plan` and `running.apply` take a `given` to
fill with what each step gives, whole, and `solo` prints the step's own from it.

## Showing a plan

`render/words.py` holds what every renderer says the same way: the counts, the
warnings, which outputs are shown, how a run ended. `clean` there makes control
characters and invisible characters visible.

- `render/rich.py` is the terminal.
- `render/markdown.py` writes Markdown in which every word that is not lely's own
  stands in a fenced block or a code span. Its first line is a marker,
  `<!-- lely:plan:<target> -->` or `<!-- lely:destroy:<target> -->`, with the project's
  folder added in a repository with several.
- `render/html.py` writes the page: one document with its style sheet inline and a
  content policy that allows nothing else. `framed` takes a plugin's view apart with an
  HTML parser and writes it again from the elements it keeps.

`github` is the edge for `--github`. It reads the run's environment and its event
file, appends to the summary file, and talks to GitHub's API through one function that
tests replace. It finds its comment by the marker. Nothing in it decides how a command
ends.

## The tests

There is no Databricks CLI, workspace or GitHub in the unit suite.

- `tests/fake_databricks.py` is the CLI as a fake, as a program and in process. It
  answers from recordings, or simulates a bundle in a workspace kept in a folder:
  `plan`, `deploy`, `summary`, `destroy`, `run`. A call it cannot answer fails.
- `tests/fixtures/cli/` holds the CLI's own outputs, from its acceptance tests; the
  README there says where each came from.
- `tests/fake_github.py` is a pull request's comments in memory, and a run's
  environment.
- `tests/fixtures/stevin-*.json` are plan files stevin wrote against its own fake
  warehouse. `tests/fake_stevin.py` is the `stevin` command as a fake: it plans from one
  of them, applies a plan file, refuses a stale one in stevin's words, and fails on a
  command line it does not know.
- `tests/project.py` is the scenario most tests share.
- `tests/browser/` asks Chrome whether a plugin's view stays in its frame. It skips
  without Chrome.

What has run against the real things is on [What has been tried](tried.md).

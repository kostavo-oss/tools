# Writing a step

A step is a class with an `Options` dataclass, the outputs it gives, and two methods — and
up to three more. Inherit `Step`, add one line at the bottom, and the file is a command of
its own as well: it runs before any `lely.yml` exists, and for a team that doesn't use lely.

```python
# ops/scope.py
# /// script
# dependencies = ["lely"]
# ///
from dataclasses import dataclass

from lely.model import Change, Item, Output, Overview, Skip, StepPlan
from lely.step import Context, Step


class SecretScope(Step):
    """Makes the product's secret scope. One line: `lely steps` shows it."""

    @dataclass(frozen=True, slots=True)
    class Options:
        #: The scope's name. A comment like this one is the option's description.
        name: str

    outputs = (Output("name"),)

    def plan(self, ctx: Context) -> StepPlan:
        # reads only: a plan changes nothing
        if self._exists(ctx):
            return StepPlan(outputs={"name": ctx.options.name})
        return StepPlan(
            changes=(
                Change(
                    key=ctx.options.name,
                    action="create",
                    summary=f"makes scope {ctx.options.name}",
                ),
            ),
            outputs={"name": ctx.options.name},
        )

    def apply(self, ctx: Context, plan: StepPlan) -> dict:
        for change in plan.changes:  # do what the plan said, and no more
            ctx.workspace.secrets.create_scope(change.key)
        return {"name": ctx.options.name}

    # The optional three: what exists because of the step, and how it goes.

    def overview(self, ctx: Context) -> Overview | Skip:
        if not self._exists(ctx):
            return Skip("no scope yet")
        name = ctx.options.name
        return Overview((Item("secret scope", name, name, deployed=True),))

    def plan_destroy(self, ctx: Context) -> StepPlan | Skip:
        if not self._exists(ctx):
            return Skip("no scope to remove")
        name = ctx.options.name
        return StepPlan(changes=(Change(name, "delete", f"removes scope {name}"),))

    def destroy(self, ctx: Context, plan: StepPlan) -> None:
        for change in plan.changes:
            ctx.workspace.secrets.delete_scope(change.key)

    def _exists(self, ctx: Context) -> bool:
        scopes = ctx.workspace.secrets.list_scopes()
        return any(scope.name == ctx.options.name for scope in scopes)


if __name__ == "__main__":
    SecretScope.main()
```

## On its own

The inline metadata at the top is enough for `uv run` on a machine with nothing installed:

```sh
uv run ops/scope.py plan -t dev --name shop_data              # shows the plan; changes nothing
uv run ops/scope.py plan -t dev --name shop_data -o plan.json
uv run ops/scope.py apply --plan-file plan.json --name shop_data
uv run ops/scope.py apply -t dev --name shop_data             # plan, show, ask, apply
uv run ops/scope.py destroy -t dev --name shop_data
uv run ops/scope.py status -t dev --name shop_data
uv run ops/scope.py check -t dev --name shop_data [--live]
```

The fields of `Options` are the flags, with their types and their `#:` comments as help.
`-t` is the target; `--profile` picks a workspace from `~/.databrickscfg`, and without it
whatever already signs the Databricks CLI in is used. `-f json` answers as data; `--yes`
gives consent in the command, as it does for `lely apply`.

A plan the step writes is a one-step lely plan: the same file, the same checks before it
runs — the workspace, the project, the git tree — and `lely apply plan.json` takes it, given
a config that names the step the same way. The step refuses a plan file that holds other
steps: `lely apply` runs those.

What a flag can carry: text, whole and decimal numbers, `true`/`false` as a word, a
`Secret`, one of a `Literal`'s values, a list (the flag more than once), a mapping
(`--name key=value`, more than once), and `T | None`. An option of another type is refused
when the step starts, and a `${steps.…}` reference too: on its own, a step has no step
above to take it from.

`check` holds the step to the rules below: `plan` behind a Databricks CLI that refuses
anything but a read, the plan through a plan file and back, outputs as declared, and
`overview` reading only. `--live` adds the cycle — plan, apply, destroy, plan again — on the
target, and says so first. What a step does through the SDK is its own: `check` cannot see a
write made there.

## Under lely

```yaml
steps:
  - name: scope
    uses: ./ops/scope.py:SecretScope
    with: {name: shop_data}
  - name: app
    uses: bundle
    with:
      vars:
        secret_scope: ${steps.scope.name}
```

A class in an installed package is named as `package.module:Class`, or by a short name the
package registers under the `lely.steps` entry point — which is how `bundle` is found. The
step is imported in-process either way: lely holds it to the contract, and never talks to
it as a program.

## What a step is given

`ctx` is everything a step gets, and nothing else — not the other steps' outputs, and not
the bundle: what a step depends on is in its options.

| | |
| --- | --- |
| `ctx.options` | The step's `with:`, as the `Options` dataclass, references resolved. |
| `ctx.target` | `-t`, as it was typed. Each step reads it its own way. |
| `ctx.name` | The step's own name: in a config, the `name:`; on its own, the class's, in lower case. |
| `ctx.root` | The project's directory: where the config file is, or where the step was run. |
| `ctx.workspace` | The workspace, through the Databricks SDK. Connects on first use. |
| `ctx.databricks` | Runs the Databricks CLI with this run's credentials. |
| `ctx.host`, `ctx.env` | The workspace's address; the environment for a program the step runs. |
| `ctx.log` | `ctx.log.info("…")` for a line of progress. |
| `ctx.purpose` | What the step is planned for: `apply`, `destroy` or `status`. |

## What it answers

**`plan`** returns a `StepPlan`:

- `changes` — each a `Change(key, action, summary, destructive=False, detail=())`. The `key`
  is the change's identity across plans; `action` is `create`, `update`, `replace`, `delete`
  or `run`. A delete and a replace are always destructive; anything else that loses
  something says so with `destructive=True`.
- `outputs` — what the step knows now, by declared name. `later` names the ones that exist
  only once the step has been applied.
- `waiting` — why part of the plan can't be made yet.
- `notes` — lines shown with the plan that are not changes.
- `payload` — the step's own data, carried through the plan file. No secret in it.
- `view` — its own picture of the plan for [the page](page.md), as HTML.

**`apply`** does what the plan says and returns the outputs.

The optional three: **`overview`** says what exists because of the step (`Overview` of
`Item(kind, key, name, deployed, id, url)`), for `lely status` and after an apply.
**`plan_destroy`** and **`destroy`** take it down again; a step without them is skipped by
`lely destroy`, with the reason.

## A program as a step

For the run-only case — `dbt run`, a notification — `Program` is a step in ten lines:

```python
from lely.model import Output
from lely.step import Program


class Notify(Program):
    """Tells the channel the deploy is done."""

    command = ["./ops/notify.sh", "deployed"]
    destructive = False
    outputs = (Output("sent", known="run"),)
```

Its plan is one `run`, destructive if it says so. `apply` runs the program in the project's
directory, never through a shell, with the environment lely was given and `LELY_TARGET`
and `LELY_STEP`; a failing program fails the step. Outputs, when it declares any, are what
the program prints as JSON on its last line. A run has nothing to take down, so a `Program`
has no destroy and `lely destroy` skips it visibly. A secret goes in `env`, never in the
arguments: every process on the machine can see those.

## Outputs, and when they are known

```python
outputs = (
    Output("version"),  # known at plan
    Output("id", known="exists"),  # once it exists: after the first deploy that makes it
    Output("rows", known="run"),  # after every run
)
```

A step that takes an output not known yet is waiting, and the plan says so. Declaring it is
what lets `lely validate` say that before anything runs. A value nobody may see is a
`Secret`.

## The rules, and how to hold your step to them

- **No state.** `plan` and `apply` may run on different machines, days apart; only the
  `StepPlan` passes between them, through the plan file.
- **`plan` changes nothing**, and neither does `overview`.
- **`apply` does what the plan says and no more.** Planning again right after it gives no
  changes, unless they are `run`s.
- **Only what the options name.** Anything else is not its own, never changed.
- **It destroys only what it can show is its own.**
- **Destructive is declared** on the change.
- **Outputs are as declared.**
- **No secrets in plans.**

`lely.testing` turns each into a check a test can run, and `check` runs them from the
command line:

```python
from lely.testing import check_apply, check_plan, context


def test_plans_the_scope():
    ctx = context(SecretScope.Options(name="shop_data"), target="dev")
    plan = check_plan(SecretScope(), ctx)
    assert [change.key for change in plan.changes] == ["shop_data"]
```

`check_plan` runs the plan with a Databricks CLI that refuses anything but a read, and
checks the plan survives a plan file. `check_apply` plans, applies, and plans again;
`check_destroy` applies and takes it down; `check_overview` lists.

## A view for the page

`StepPlan.view` is HTML, as text. The page shows it under lely's own list of the step's
changes, never in place of it, and rewrites it from a short list of elements: tables, lists,
headings (`h4`–`h6`), paragraphs and inline text. No script, style, link or image comes
through, and no `div`. A few classes are styled: `create`, `update`, `delete`, `replace`,
`run`, `destructive`, `unchanged`, `dim`, `num`, `key`.

Escape what you write into it (`html.escape`), and put nothing secret there: it is kept in
the plan file.

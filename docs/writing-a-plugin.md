# Writing a plugin

A plugin is a class with an `Options` dataclass, the outputs it gives, and two methods — and
up to three more.

```python
from dataclasses import dataclass

from lely.model import Change, Output, StepPlan
from lely.step import Context


class WarmCache:
    """Warms a table's cache. One line: `lely steps` shows it."""

    @dataclass(frozen=True, slots=True)
    class Options:
        #: The table to warm. A comment like this one is the option's description.
        table: str
        rows: int = 1000

    outputs = (Output("rows", known="run"),)

    def plan(self, ctx: Context) -> StepPlan:
        # reads only: a plan changes nothing
        return StepPlan(
            changes=(
                Change(
                    key=ctx.options.table,
                    action="run",
                    summary=f"warms {ctx.options.table}",
                ),
            )
        )

    def apply(self, ctx: Context, plan: StepPlan) -> dict:
        warmed = ...  # do what the plan said, and no more
        return {"rows": warmed}
```

```yaml
steps:
  - name: warm
    uses: ./ops/steps.py:WarmCache
    with: {table: main.sales.orders}
```

A class in an installed package is named as `package.module:Class`, or by a short name the
package registers under the `lely.steps` entry point — which is how `bundle` and `command`
themselves are found.

## What a step is given

`ctx` is everything a step gets, and nothing else — not the other steps' outputs, and not
the bundle: what a step depends on is in its options.

| | |
| --- | --- |
| `ctx.options` | The step's `with:`, as the `Options` dataclass, references resolved. |
| `ctx.target` | `-t`, as it was typed. Each plugin reads it its own way. |
| `ctx.name` | The step's own name. |
| `ctx.root` | The project's directory, where the config file is. |
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
- `payload` — the plugin's own data, carried through the plan file. No secret in it.
- `view` — its own picture of the plan for [the page](page.md), as HTML.

**`apply`** does what the plan says and returns the outputs.

The optional three: **`overview`** says what exists because of the step (`Overview` of
`Item(kind, key, name, deployed, id, url)`), for `lely status` and after an apply.
**`plan_destroy`** and **`destroy`** take it down again; a plugin without them is skipped by
`lely destroy`, with the reason.

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

## The rules, and how to hold your plugin to them

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

`lely.testing` turns each into a check a test can run:

```python
from lely.testing import check_apply, check_plan, context


def test_plans_the_warm_up():
    ctx = context(WarmCache.Options(table="main.sales.orders"), target="dev")
    plan = check_plan(WarmCache(), ctx)
    assert [change.key for change in plan.changes] == ["main.sales.orders"]
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

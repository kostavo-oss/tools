# Your first plan

You have a Databricks Asset Bundle — a `databricks.yml` — and something that happens before
or after `bundle deploy`. This puts both in one plan.

## 1. Write the steps

`lely.yml`, beside `databricks.yml`:

```yaml
steps:
  - name: app
    uses: bundle

  - name: backfill               # needs something from the bundle: it stands below it
    uses: command
    with:
      apply: [./ops/backfill.sh, "${steps.app.resources.jobs.backfill.id}"]
```

The bundle is one step among the others. What stands above it runs before the deploy, what
stands below runs after. `backfill` takes the id of a job the bundle deploys, and says so in
its own options — that is the only way a step takes anything from another.

## 2. Check it, offline

```sh
lely validate
```

```
✓ lely.yml: 2 steps

  app       gives  target, name, workspace.<field>, var.<name>, resources.<type>.<key>.<field> (at plan)
            gives  resources.<type>.<key>.id, resources.<type>.<key>.url (once it exists)
  backfill  takes  ← app.resources.jobs.backfill.id
```

No workspace is asked: this checks the config, each step's options, and that every reference
points at a step above and at something that step gives.

## 3. Plan

```sh
lely plan -t dev
```

There is no default target: `-t` is always given. Nothing is changed. Each step is one of:

- **ready** — lely knows what it would do, and shows it;
- **waiting** — it takes something that doesn't exist yet, like the id of a job this deploy
  creates, so nobody can know what it will do; the plan says that instead of guessing;
- **skipped** — it has `targets:` and this isn't one of them.

## 4. Apply

```sh
lely apply -t dev
```

plans, shows the plan, asks, and runs — step by step, each one planned again right before it
runs. A step that was waiting is planned once what it waits for exists, shown, and asked
about on its own.

Or review first:

```sh
lely plan -t dev -o plan.json    # a file, to read and to pass on
lely ui plan.json                # … as a page
lely apply plan.json             # runs exactly what was reviewed, or refuses
```

A first deploy through a file can take two rounds: the file stops before a waiting step,
because nobody has seen what that step will do. The next plan shows it ready.

## 5. Look, and take it down again

```sh
lely status -t dev     # what exists because of each step, with links
lely destroy -t dev    # the teardown: planned from the bottom up, shown, asked
```

To destroy at a terminal, the answer is the target's name — not `y`.

## Next

- [The config](config.md): references, targets, secrets.
- [Plan, apply, destroy](plan-apply-destroy.md): what a plan file is held to, and what
  happens when a step fails.
- [On GitHub](GITHUB.md): the plan as a comment on the pull request.

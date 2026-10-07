# Commands

```
lely validate                 config, options, references: offline; prints the wiring
lely steps                    plugins: options, outputs, what each can do
lely schema [-o file]         a JSON Schema of the config, for editors
lely plan -t <target>         plan every step; changes nothing
lely show plan.json           show a saved plan
lely apply [plan.json]        run a reviewed plan — or, with -t, plan, show, ask and run
lely destroy -t <target>      take a target down again
lely status -t <target>       what is deployed right now, per step
lely ui <file>                a plan, or a run's record, as a page
lely doctor                   the tools, the workspace, the identity
```

`-t` is always given to a command that touches a workspace: there is no default target. The
workspace comes from `--profile`, or from the variables the Databricks CLI and SDK already
read.

## Options

| Option | On | |
| --- | --- | --- |
| `-t`, `--target` | `plan` `apply` `destroy` `status` | The target. No default. |
| `-c`, `--config` | all but `show`, `ui` | `lely.yml`, or a `pyproject.toml` with `[tool.lely]`. Found from here up when not given. |
| `-p`, `--profile` | `plan` `apply` `destroy` `status` `doctor` | A `~/.databrickscfg` profile, for the CLI and for plugins. |
| `-o`, `--output` | `plan` | Write the plan to a file. |
| | `apply` `destroy` | Write a record of the run to a file. |
| | `schema` `ui` | Where to write the schema, or the page. |
| `-f`, `--format` | `plan` `show` `apply` `destroy` `status` | `rich` (the default), `json` or `md`. With the last two, stdout holds that and nothing else. |
| `--destroy` | `plan` | Plan a teardown instead. |
| `--yes` | `apply` `destroy` | Don't ask: consent is given in the command. |
| `--allow-destructive` | `apply` | Apply changes marked destructive. |
| `--from <step>` | `apply` `destroy` | Start at this step; the ones passed over are planned, not run. |
| `--github` | `plan` `show` `apply` `destroy` | In a GitHub Actions run, keep the pull request's comment and the run's page current. → [On GitHub](GITHUB.md) |
| `--open` / `--no-open` | `ui` | Open the page in a browser. |

## Exit codes

| | |
| --- | --- |
| **0** | Done. |
| **1** | Something failed. |
| **2** | lely refused: nothing more will come of trying again — plan again. Or the command line is one lely can't make sense of. |

`plan`, `status`, `validate` and `doctor` change nothing, so they have nothing to refuse:
what goes wrong in them ends with 1.

A command line lely can't make sense of ends with 2 whatever the command — a missing or an
empty `-t`, an option it doesn't know, `lely apply` with neither a plan file nor `-t` — and
before the project's config is read or a workspace reached. So 2 from `plan` or `status` is
always that.

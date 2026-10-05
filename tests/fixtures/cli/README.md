# Databricks CLI outputs

What `databricks bundle … -o json` prints, taken from the CLI's own acceptance
tests at [`e41a5c8`](https://github.com/databricks/cli/tree/e41a5c87436a5b8fa81ce192e2aac77675d4b4c2/acceptance/bundle).
The tests replace real values with placeholders (`[PLAN_VERSION]`, `[FOO_ID]`,
`[USERNAME]`, …), some of them unquoted; these files put plausible values back.
Nothing else is changed except where a note below says so.

| File | Source |
|---|---|
| `plan-create.json` | `resource_deps/pipelines_recreate/out.plan_create.direct.json` |
| `plan-update-recreate.json` | `resource_deps/pipelines_recreate/out.plan_update.direct.json` (the `deployment` blocks of `new_state` / `remote_state` trimmed) |
| `plan-delete-update.json` | `resource_deps/job_id_delete_bar/out.plan_delete.direct.json` (same trim) |
| `validate-default-python.json` | `templates/default-python/integration_classic/out.validate.dev.json` — recorded on a real workspace; `workspace.current_user` restored from `validate/job-references/output.txt`, the job's task list shortened to one task |
| `summary-default-python.json` | the same test's validate → summary diff: each resource gains `id` and `url` |

Most of these were recorded against the CLI's in-process test server; the
default-python files against a real workspace. Replace them with transcripts of
a live run when the live suite exists.

These are for *reading* the CLI's answers. What `bundle deploy`, `destroy` and `run` do is not
recorded anywhere: `tests/fake_databricks.py` simulates them, from what lely assumes
(`spec/004-asset-bundle.md`, To verify).

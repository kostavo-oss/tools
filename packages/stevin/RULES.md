# Rules

What must be true of stevin: the promises a user or a reviewer relies on. Why a rule is
so is in [DECISIONS.md](DECISIONS.md), how stevin works in
[docs/how-it-works.md](docs/how-it-works.md), what a spec may say in `docs/`.

## How this file is kept

- A rule has an identifier, an area and a number such as `OWN-2`. Code, tests and docs
  cite a rule by it. A new rule takes the next number of its area, and a number is
  never reused.
- `Held by:` names tests that hold the rule, as `tests/<folder>/<file>.py::<test>`. Each
  of them cites the identifier, as `# RULES.md: OWN-2.`, and no other test does. A rule
  no test can hold says `Not tested:` and why.
- A rule states the whole promise. Where the code does not keep all of it, the rule says
  `Not kept yet: #12 — what the code does`, with the issue that tracks it.
- A change to behaviour changes its rule and its test in the same pull request.
  `tests/test_rules.py` at the root of the repository checks all of this.

Areas: `OWN` what stevin may touch, `RISK` what a step may cost, `PLAN` how a plan is
made, `APL` what `apply` promises, `RW` a rewrite, `SQL` the statements, `ACC` access,
`SPEC` what a spec may say, `DBX` what is assumed of Databricks, `TEST` the tests
themselves, `NAME` the names from when this was deltaplan, `ACT` the GitHub Action.

## OWN — what stevin may touch

- **OWN-1** — There is no state file. That stevin made a table or a view is a property
  on it, `deltaplan.managed = true`, set when it is created. A spec cannot remove it.
  Held by: `tests/unit/test_planning.py::test_a_new_table_needs_no_claim`,
  `tests/unit/test_removals.py::test_the_ownership_marker_cannot_be_removed`.
- **OWN-2** — stevin drops only what it made: a table or a view that carries the marker,
  that no spec describes, in a schema whose mode is `strict`. In an `additive` schema,
  the default, it stays and is listed. A table without the marker is reported as
  unmanaged and left alone in every mode. A plan made with `--select` drops nothing.
  Held by: `tests/unit/test_planning.py::test_additive_keeps_orphans_and_says_so`,
  `tests/unit/test_planning.py::test_strict_drops_orphans_and_only_orphans`,
  `tests/unit/test_cli_apply.py::test_a_selection_never_drops_what_it_leaves_out`.
- **OWN-3** — A spec for a live table or view without the marker plans a claim: a step
  of its own, shown in the plan, that sets the marker.
  Held by: `tests/unit/test_planning.py::test_a_spec_for_someone_elses_table_claims_it`,
  `tests/unit/test_views.py::test_someone_elses_view_is_claimed`.
- **OWN-4** — A schema, a volume and a function are never dropped, in any mode.
  Held by: `tests/unit/test_schema_specs.py::test_a_schema_is_never_dropped`,
  `tests/unit/test_functions.py::test_a_function_without_a_spec_is_left_alone_even_in_a_strict_schema`.
- **OWN-5** — What a live object has and its spec does not mention is left as it is and
  reported as unmanaged, never diffed away: a property, a tag, a constraint, a grant to
  a principal the spec does not name, a mask, a row filter, partitioning, an owner, and
  what the model does not cover.
  Held by: `tests/unit/test_differ.py::test_nothing_unmodelled_is_diffed_away`,
  `tests/unit/test_masks_and_filters.py::test_an_undeclared_control_is_never_removed`.
- **OWN-6** — A table another tool owns is never claimed, reshaped or dropped, whatever
  the mode, and a plan reports it as theirs. The owner is known from `owned_elsewhere:`
  in the project file, from a dbt manifest, and from dlt's own tables in the schema.
  Held by: `tests/unit/test_owned_elsewhere.py::test_owned_tables_are_theirs_not_unmanaged`,
  `tests/unit/test_owned_elsewhere.py::test_the_project_file_says_who_owns_what`.
  Not kept yet: #42 — `owned_elsewhere` cannot name a schema that a bundle deploys under
  another name: a key with a `${resources.schemas.<key>.name}` reference is refused.
- **OWN-7** — A spec for a table dbt builds is refused, at `validate` and at `plan`. A
  table of any other owner may be governed and never shaped: a spec without column
  types puts tags, grants, masks, a row filter and an owner on it and plans no claim. A
  spec with types for such a table is refused, and so is a governance-only spec for a
  table nobody is said to own or that is not there yet.
  Held by: `tests/unit/test_owned_elsewhere.py::test_even_a_governance_only_spec_for_dbts_table_is_refused`,
  `tests/unit/test_owned_elsewhere.py::test_a_governance_only_spec_governs_a_dlt_table`,
  `tests/unit/test_owned_elsewhere.py::test_a_shape_spec_for_a_dlt_table_is_refused`.

## RISK — what a step may cost

- **RISK-1** — Every step carries one risk class: `meta`, `feature`, `rewrite` or
  `destructive`. A step that can lose data is `destructive`: dropping a column, a table
  or a view, a rewrite that leaves out a column, loading a seed over rows that are
  there. What a change needs first, such as column mapping, is a step of its own.
  Held by: `tests/unit/test_planner.py::test_dropping_a_column_is_destructive_and_needs_column_mapping`,
  `tests/unit/test_seeds.py::test_loading_over_rows_that_are_there_is_destructive`,
  `tests/unit/test_planner.py::test_a_rename_inserts_column_mapping_first`.
- **RISK-2** — `apply` refuses a plan that holds a destructive step unless it is told
  `--allow-destructive`, before any statement runs and before it asks.
  Held by: `tests/unit/test_executor.py::test_a_destructive_plan_needs_the_flag`,
  `tests/unit/test_cli_apply.py::test_a_destructive_plan_is_refused_before_asking`.
- **RISK-3** — stevin does not invent a statement. A change it cannot write the SQL for
  is a step without SQL that says what it needs, and `apply` refuses a plan that holds
  one. A conversion between nested types is written by field name, never by position.
  Held by: `tests/unit/test_executor.py::test_a_step_stevin_cannot_generate_is_refused`,
  `tests/unit/test_planner.py::test_the_projection_refuses_rather_than_inventing`.

## PLAN — how a plan is made

- **PLAN-1** — `differ.py` and `planner.py` do no I/O: no SDK, no clock, no environment,
  no file. The model is frozen, slotted dataclasses that hold tuples, and nothing in
  stevin imports Pydantic or msgspec.
  Held by: `tests/unit/test_pure_middle.py::test_the_differ_and_the_planner_import_nothing_that_reaches_outside`,
  `tests/unit/test_pure_middle.py::test_the_model_is_frozen_slotted_and_holds_tuples`.
- **PLAN-2** — A plan is made from the specs and the live objects and nothing else: the
  same two give the same plan in every workspace. What `stevin verify` finds about a
  runtime is not read by a plan.
  Held by: `tests/unit/test_pure_middle.py::test_planning_reads_nothing_of_what_a_workspace_accepts`.
- **PLAN-3** — A plan is one object. The terminal, the Markdown comment, the page and
  the JSON file are renderings of it, and a plan file reads back as the plan it was.
  Held by: `tests/unit/test_planfile.py::test_a_busy_plan_round_trips`,
  `tests/unit/test_cli.py::test_the_plan_file_is_the_plan_whatever_the_screen_shows`.
- **PLAN-4** — One name has one spec, and objects are planned each after what it names.
  Two specs for one name and a cycle are errors, found by `validate`, which needs no
  workspace and never runs the Databricks CLI.
  Held by: `tests/unit/test_one_name_one_spec.py::test_validate_refuses_two_files_naming_one_table`,
  `tests/unit/test_plan_order.py::test_the_whole_chain_lands_in_one_order`.

## APL — what `apply` promises

DDL is not transactional across statements, so there is no rollback. There is this.

- **APL-1** — Nothing runs from a stale plan. A fresh run reads again every object the
  plan was made from, holding the lock, and refuses when anything differs. A plan that
  already ran is refused, and so is a plan file another version of stevin saved.
  Held by: `tests/unit/test_executor.py::test_a_stale_plan_is_refused`,
  `tests/unit/test_executor.py::test_staleness_is_settled_under_the_lock`.
- **APL-2** — A step whose change is already true of the live object is skipped. With a
  history schema every step's outcome is recorded, and the next `apply` of the same
  plan goes on from the step that failed.
  Held by: `tests/unit/test_executor.py::test_steps_already_applied_are_skipped`,
  `tests/unit/test_executor.py::test_a_failed_run_resumes_where_it_stopped`.
- **APL-3** — With a history schema one run at a time changes a target. The lock is
  taken before any table is read, runs out after an hour, and is renewed before every
  step and through a long one. A run that lost it stops before its next step.
  Held by: `tests/unit/test_executor.py::test_a_locked_target_is_refused_before_anything_is_read`,
  `tests/unit/test_executor.py::test_a_run_that_loses_its_lock_stops_before_the_next_step`.
- **APL-4** — Before every rewrite and every destructive step the table's Delta version
  is recorded, so `RESTORE` is one command. When it cannot be read the step still runs,
  and its line says it ran without a restore point.
  Held by: `tests/unit/test_executor.py::test_a_rewrite_records_a_restore_point`,
  `tests/unit/test_executor.py::test_a_destructive_step_records_a_restore_point`.
- **APL-5** — A project that names no history schema applies anyway, and nothing is
  written outside the objects its specs describe. There is then no lock and no resume,
  and `apply` says so.
  Held by: `tests/unit/test_no_history.py::test_nothing_is_created_and_the_change_is_made`,
  `tests/unit/test_no_history.py::test_a_risky_step_still_takes_a_restore_point`.
- **APL-6** — A step has no time limit. No statement is reported as failed while it
  still runs: one that outlives a limit is cancelled first. Ctrl-C asks the warehouse
  to cancel, releases the lock and leaves the run resumable, and `apply` never says a
  statement was stopped when it may still be running.
  Held by: `tests/unit/test_long_steps.py::test_reads_have_a_budget_and_apply_has_none`,
  `tests/unit/test_long_steps.py::test_a_statement_that_outlives_its_budget_is_cancelled_before_it_is_reported`,
  `tests/unit/test_long_steps.py::test_ctrl_c_before_the_statement_had_an_id_does_not_claim_a_cancel`.
- **APL-7** — `apply` without a plan file shows the plan and asks before it changes
  anything. No answer is no: a closed stdin, as in CI, applies nothing.
  Held by: `tests/unit/test_cli_apply.py::test_apply_plans_shows_and_asks`,
  `tests/unit/test_cli_apply.py::test_no_answer_is_no`.

## RW — a rewrite

- **RW-1** — A table that needs a rewrite is replaced from a query in one statement. It
  is never dropped and made again, so it keeps its identity and its Delta history.
  Held by: `tests/unit/test_planner.py::test_replace_table_sql`,
  `tests/unit/test_executor.py::test_a_rewrite_runs_and_converges`.
- **RW-2** — A rewrite that converts values writes them to a staging table first and
  checks it before the table is touched: every row is there, and no converted column
  has more NULLs. When the check fails the table is as it was and the copy is kept. A
  rewrite that converts no value has no staging table and writes the data once.
  Held by: `tests/unit/test_rewrite_safety.py::test_staging_is_checked_for_lost_rows_and_values`,
  `tests/unit/test_rewrite_safety.py::test_lost_values_stop_the_run_before_the_table_is_touched`.
- **RW-3** — A rewrite loses nothing the spec did not ask to lose. What a replace does
  not carry is put back, and what nobody declared survives: properties, constraints,
  tags, grants, the owner, partitioning.
  Held by: `tests/unit/test_rewrite_safety.py::test_properties_nobody_declared_survive_a_rewrite`,
  `tests/unit/test_rewrite_safety.py::test_tags_grants_and_an_owner_survive_a_rewrite_without_a_step`.
- **RW-4** — A table is not rewritten when a rewrite would lose what a query cannot
  carry, or would copy its data to where its protection does not reach: a table with an
  identity or generated column, with something the model does not cover, or whose data
  is masked or filtered, by a mask or row filter of its own or by an ABAC policy. The
  plan holds a step without SQL that says why (RISK-3), also when the project hands
  masks to another tool.
  Held by: `tests/unit/test_generation.py::test_a_table_with_identity_is_never_rewritten`,
  `tests/unit/test_masks_and_filters.py::test_a_protected_table_is_never_rewritten`,
  `tests/unit/test_manage.py::test_handing_something_over_does_not_make_stevin_blind`.
  Not kept yet: #50 — a table under an ABAC policy is staged and replaced like any
  other, with no warning: the copy holds what the applying principal reads, outside
  the policy.

## SQL — the statements

- **SQL-1** — Every identifier in a statement goes through `quote_ident()`, which always
  quotes, and every string through `quote_literal()`.
  Held by: `tests/unit/test_planner.py::test_identifiers_are_always_quoted`,
  `tests/unit/test_grants.py::test_principals_are_quoted`.
  Not kept yet: #51 — a nested field's name inside a type, as in `STRUCT<select:INT>`,
  goes through `maybe_quote_ident()`, which leaves a plain word bare.

## ACC — access

- **ACC-1** — A principal a spec names gets exactly the privileges the spec lists, by
  grants and revokes that are steps in the plan. A principal no spec names is left
  alone, and a grant inherited from a schema or a catalog is not the table's.
  Held by: `tests/unit/test_grants.py::test_a_named_principal_is_managed_exactly`,
  `tests/unit/test_grants.py::test_inherited_grants_are_not_the_tables_to_manage`.
- **ACC-2** — A mask or a row filter a spec declares is set, and one it does not declare
  is never removed. A new table is created with them in the same statement. A step that
  sets one is refused before it runs when its function is not there.
  Held by: `tests/unit/test_masks_and_filters.py::test_declared_controls_are_set`,
  `tests/unit/test_masks_and_filters.py::test_a_new_table_is_never_unprotected`.
- **ACC-3** — ABAC policies are read and never written. A policy in scope of a table is
  a fact in the plan and never a change or a step: no plan holds a statement that
  creates, alters or drops a policy.
  Held by: `tests/unit/test_policies.py::test_policies_are_facts_and_never_a_step_or_a_change`,
  `tests/unit/test_policies.py::test_the_fake_knows_the_statements_stevin_reads_with_and_no_other`.
- **ACC-4** — `stevin verify` creates no policy unless it is asked to with
  `--create-policy`. A plain run leaves out the probes that would and says so.
  Held by: `tests/unit/test_probes.py::test_a_probe_that_creates_a_policy_runs_only_when_asked`,
  `tests/unit/test_probes.py::test_the_command_creates_no_policy_unless_asked`.
- **ACC-5** — A policy that arrives, goes or changes between `plan` and `apply` makes
  the plan stale. A policy is not drift. Where a spec's own mask or row filter sits
  beside a policy of the same kind, the plan warns. A workspace that will not list
  policies does not fail a plan: it says so once and goes on.
  Held by: `tests/unit/test_policies.py::test_a_policy_that_arrives_after_the_plan_makes_it_stale`,
  `tests/unit/test_policies.py::test_drift_lists_them_as_not_stevins_and_stays_in_sync`.
- **ACC-6** — What a project hands to another tool with `manage:` cannot reach a plan:
  its key is refused in a spec and it is not asked of the workspace. stevin still reads
  what it needs to keep from destroying it (RW-4).
  Held by: `tests/unit/test_manage.py::test_a_handed_over_key_is_refused_in_a_spec`,
  `tests/unit/test_manage.py::test_the_workspace_is_not_even_asked_about_grants`.
- **ACC-7** — `stevin access` reads and changes nothing, reads grants and policies
  whatever `manage:` says, and says in its output what it does not decide.
  Held by: `tests/unit/test_access.py::test_it_writes_nothing`,
  `tests/unit/test_access.py::test_the_reader_asks_for_grants_whatever_the_project_manages`.

## SPEC — what a spec may say

- **SPEC-1** — A spec is checked where it is read. An unknown key is an error, and every
  error names its file, line and column.
  Held by: `tests/unit/test_loader.py::test_spec_errors`,
  `tests/unit/test_loader.py::test_errors_carry_file_line_and_column`.
- **SPEC-2** — stevin runs no SQL of the user's around a change and keeps no function
  of its own: `hooks:` is refused, and a function spec is valid only when a mask or a
  row filter in the project names it.
  Held by: `tests/unit/test_backfills.py::test_a_spec_with_hooks_is_refused_with_the_key_named`,
  `tests/unit/test_functions_are_for_masks.py::test_validate_refuses_a_function_nothing_names`.
- **SPEC-3** — A spec with `from_contract:` takes its table's shape from the contract
  and from nowhere else. The contract is read and never written, and `adopt` refuses to
  put live state over it.
  Held by: `tests/unit/test_from_contract.py::test_a_spec_cannot_say_the_shape_twice`,
  `tests/unit/test_from_contract.py::test_adopt_refuses_to_write_over_a_contract`.

## DBX — what is assumed of Databricks

- **DBX-1** — What stevin assumes Databricks does is a probe in `probes.PROBES`, with
  the page of the Databricks docs it rests on. The live suite and `stevin verify` run
  that one list. An assumption no workspace has settled is marked `TODO(verify)`.
  Held by: `tests/unit/test_probes.py::test_every_probe_says_what_it_is_and_what_rests_on_it`,
  `tests/integration/test_live_assumptions.py::test_the_assumption_holds`.

## TEST — the tests themselves

- **TEST-1** — A unit test reaches no workspace, and the stand-ins fail loudly: the fake
  warehouse raises on a statement it does not know, and so does a replayed transcript.
  Held by: `tests/unit/test_offline.py::test_every_unit_test_runs_that_way`,
  `tests/unit/test_executor.py::test_the_fake_refuses_statements_it_does_not_know`.
- **TEST-2** — Every terminal picture in the docs is what the CLI prints today.
  Held by: `tests/unit/test_screens.py::test_the_docs_pictures_match_what_the_cli_prints`.
- **TEST-3** — A live run keeps to its budget of tables: 60 for the whole suite, 15 for
  `smoke`. A session over its budget fails, and one that does not fit under the
  metastore's quota does not start.
  Held by: `tests/unit/test_table_budget.py::test_the_budgets_are_the_ones_the_docs_promise`,
  `tests/unit/test_table_budget.py::test_a_session_over_its_budget_fails_with_one_line`.
- **TEST-4** — The live suite runs only when somebody starts it: never on a schedule
  and never on a pull request.
  Not tested: the trigger is in `.github/workflows/integration.yml`, outside this
  package; it has `workflow_dispatch` and nothing else.

## NAME and ACT

- **NAME-1** — The four names written onto tables are the ones deltaplan wrote:
  `deltaplan.managed`, `deltaplan.seed`, `__deltaplan_rewrite` and `__deltaplan_backup`.
  `formerly.py` is the only module that spells the old name.
  Held by: `tests/unit/test_formerly.py::test_what_is_written_on_tables_kept_its_name`,
  `tests/unit/test_formerly.py::test_only_formerly_spells_the_old_name`.
- **ACT-1** — The Action puts no input into a script: `${{ }}` never stands inside a
  `run:`. `command: plan` never applies.
  Held by: `tests/unit/test_action.py::test_no_input_is_interpolated_into_a_script`,
  `tests/unit/test_action.py::test_plan_never_applies`.

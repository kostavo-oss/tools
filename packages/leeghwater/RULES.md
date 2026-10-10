# Rules

What must be true of leeghwater. Each rule is one or two sentences in the present tense,
and names the tests that hold it. Why a rule is so is in [DECISIONS.md](DECISIONS.md);
what ran on a real workspace is in [docs/tried.md](docs/tried.md).

## How this file is kept

- A rule has an identifier: an area and a number, such as `APP-3`. Code, tests and docs
  cite a rule by that identifier and by nothing else.
- A new rule takes the next number in its area. A number is never reused: a rule that is
  dropped leaves a gap, and a rule that changes its meaning gets a new number.
- Under each rule stands `Held by:` with the tests that hold it, each as
  `tests/<file>.py::<test>`. Each of those tests cites the identifier, and no other test
  does.
- A rule no test can hold says `Not tested:` and why, in place of `Held by:`.
- A change to behaviour changes its rule and its test in the same pull request.
  `tests/test_rules.py` at the root of the repository checks all of the above.

The areas: `APP` the command line, `RUN` the pipeline of a run, `PRE` what `prepare()`
does, `DBX` what Databricks needs, `DST` where a run loads, `SEC` secrets, `DLT` how
leeghwater stands beside dlt.

## APP — the command line

- **APP-1** — The app is the project's console script. The words a wheel task gives it
  run the same pipeline as the same words typed by a developer.
  Held by: `tests/test_app.py::test_the_same_words_run_the_same_pipeline_as_a_console_script`.
- **APP-2** — A pipeline is a function marked `@pipeline` in the module or package the
  app names, and the app imports that package itself. A pipeline is named after its
  function unless the mark names it, and two of one name are refused when the app starts.
  Held by: `tests/test_app.py::test_list_names_the_pipelines_and_their_parameters`,
  `tests/test_app.py::test_what_else_is_refused_at_the_start`.
- **APP-3** — A pipeline's parameters are options of its command, with the type the
  function gives: text, a whole or a decimal number, a date or a date and time in ISO
  format, or a yes or no. A value that does not parse is refused and the pipeline is not
  called.
  Held by: `tests/test_app.py::test_run_runs_a_pipeline_and_its_parameters_arrive_typed`,
  `tests/test_app.py::test_a_parameter_keeps_its_default_and_its_type`,
  `tests/test_app.py::test_a_wrong_option_is_refused_by_name`.
- **APP-4** — A yes or no takes a word (`true`, `1`, `yes`, `y`, or `false`, `0`, `no`,
  `n`) and is not a flag.
  Held by: `tests/test_app.py::test_run_runs_a_pipeline_and_its_parameters_arrive_typed`,
  `tests/test_app.py::test_a_parameter_keeps_its_default_and_its_type`,
  `tests/test_app.py::test_a_wrong_option_is_refused_by_name`.
- **APP-5** — A parameter keeps its own name and its capitals, whatever the app calls
  its own arguments, and a parameter before a `/` is given by its place.
  Held by: `tests/test_app.py::test_a_parameter_may_have_a_name_the_app_uses_itself`,
  `tests/test_app.py::test_a_parameter_keeps_its_capitals_and_its_place`.
- **APP-6** — A parameter of another type, a `*args` or a `**kwargs`, and a parameter
  named like an option of every run or like `help` are refused when the app starts, not
  when the pipeline runs.
  Held by: `tests/test_app.py::test_a_parameter_named_like_an_option_of_every_run_is_refused_at_the_start`,
  `tests/test_app.py::test_what_else_is_refused_at_the_start`.
- **APP-7** — A `--schema` or a `--staging-schema` that is given but empty is refused,
  not taken for one left out.
  Held by: `tests/test_app.py::test_an_empty_option_from_a_bundle_is_refused_not_skipped`,
  `tests/test_prepare.py::test_what_is_refused`.
- **APP-8** — `list` names the pipelines and their parameters, and answers as JSON when
  asked.
  Held by: `tests/test_app.py::test_list_names_the_pipelines_and_their_parameters`,
  `tests/test_app.py::test_list_answers_as_json`.
- **APP-9** — `doctor` says what a run would set up. For a run that would load into
  Databricks it checks the sign-in, each secret scope, each pointed-at secret and the
  warehouse, and ends with 1 when a check fails. It runs no pipeline, reads no secret's
  value, and answers as JSON when asked.
  Held by: `tests/test_app.py::test_doctor_on_a_laptop_says_it_would_load_locally`,
  `tests/test_app.py::test_doctor_checks_the_identity_the_scopes_and_the_warehouse`,
  `tests/test_app.py::test_doctor_fails_by_name_and_answers_as_json`.
- **APP-10** — A command the project adds with `@app.command()` is prepared as a
  pipeline is, with the app's own settings, and finds the same secrets.
  Held by: `tests/test_app.py::test_a_command_the_project_added_runs_and_finds_a_secret`.
- **APP-11** — Off Databricks an error of leeghwater's own is one line and exit 1, and
  any other error is raised as it came. On Databricks an error of leeghwater's own is
  raised too, so the task fails with it.
  Held by: `tests/test_app.py::test_on_a_laptop_an_error_of_leeghwaters_is_one_line`,
  `tests/test_app.py::test_a_pipeline_that_raises_ends_the_run_with_its_own_error`,
  `tests/test_app.py::test_on_databricks_a_run_without_a_warehouse_stops_before_the_pipeline`.

## RUN — the pipeline of a run

- **RUN-1** — `create_pipeline` returns dlt's own pipeline, with the destination and
  the schema the run decided. A run's `--schema` wins over the call's `schema=`, which is
  for a run that names none.
  Held by: `tests/test_pipeline.py::test_the_pipeline_is_dlts_own_with_what_the_run_named`,
  `tests/test_pipeline.py::test_the_run_wins_over_the_schema_in_the_code`,
  `tests/test_pipeline.py::test_the_schema_in_the_code_is_for_a_run_that_names_none`.
- **RUN-2** — A `destination` or a `dataset_name` in the call of `create_pipeline` is
  refused. Anything else `dlt.pipeline` takes is passed on.
  Held by: `tests/test_pipeline.py::test_what_is_the_runs_to_say_is_refused_in_the_call`,
  `tests/test_pipeline.py::test_other_arguments_of_dlt_pipeline_are_passed_on`.
- **RUN-3** — `create_pipeline` and `run` go by the last `prepare()` in the process.
  `create_pipeline` refuses when there was none, and takes a `setup=` in its place.
  Held by: `tests/test_pipeline.py::test_without_prepare_it_refuses`,
  `tests/test_pipeline.py::test_a_setup_can_be_given_instead_of_the_last_one`.
- **RUN-4** — `run` is `pipeline.run`: it returns dlt's own load info, and anything else
  `pipeline.run` takes is passed on.
  Held by: `tests/test_pipeline.py::test_run_loads_reports_and_returns_dlts_load_info`,
  `tests/test_pipeline.py::test_arguments_of_pipeline_run_are_passed_on`.
- **RUN-5** — `run` applies the run's limit with dlt's `add_limit`: at most that many
  pages from each resource, and 0 for all. A limit below 0 is refused, and so is a run
  with a limit whose data dlt cannot limit.
  Held by: `tests/test_pipeline.py::test_a_limit_is_so_many_pages_from_each_resource`,
  `tests/test_pipeline.py::test_a_limit_needs_something_dlt_can_limit`,
  `tests/test_app.py::test_a_limit_reaches_the_pipeline`.
- **RUN-6** — `run` prints one report of the load: each package with its state, each
  finished job with its table, file format, size and seconds, each failed job with its
  table and one line of why. Then the destination, the schema, the start and the end,
  and whether it was the pipeline's first run.
  Held by: `tests/test_report.py::test_a_report_names_each_job_and_where_it_went`,
  `tests/test_report.py::test_a_second_run_is_not_a_first_run`,
  `tests/test_report.py::test_sizes_read_like_sizes`,
  `tests/test_report.py::test_a_failed_job_is_one_line_not_a_traceback`,
  `tests/test_pipeline.py::test_run_loads_reports_and_returns_dlts_load_info`.
- **RUN-7** — A load job that failed fails the run, also when the project told dlt not
  to raise on one.
  Held by: `tests/test_pipeline.py::test_a_failed_load_job_is_raised_even_when_dlt_was_told_not_to`,
  `tests/test_app.py::test_a_failed_load_job_ends_with_1_even_when_dlt_was_told_not_to_raise`.
- **RUN-8** — A run through the app whose pipeline made no load with `leeghwater.run()`
  fails, and the error says that a plain `dlt.pipeline()` gets nothing from the run.
  Held by: `tests/test_app.py::test_a_pipeline_that_calls_dlt_itself_is_not_a_green_run`,
  `tests/test_app.py::test_a_pipeline_that_ran_nothing_is_not_a_green_run`.
- **RUN-9** — Loading into DuckDB, a schema named like its pipeline is refused: DuckDB
  names its database after the pipeline's file.
  Held by: `tests/test_pipeline.py::test_duckdb_cannot_have_a_schema_named_like_its_file`.

## PRE — what `prepare()` does

- **PRE-1** — Importing `leeghwater` does not import dlt. What is set up for dlt is set
  up in `prepare()`, which the app calls and a notebook calls itself.
  Held by: `tests/test_where.py::test_importing_leeghwater_does_not_import_dlt`.
- **PRE-2** — A second `prepare()` with the same arguments changes nothing: not the
  environment, not dlt's providers, not the first lines.
  Held by: `tests/test_prepare.py::test_a_second_call_changes_nothing`.
- **PRE-3** — Each `prepare()` decides the destination, the schemas, the warehouse and
  the limit anew, from its own arguments.
  Held by: `tests/test_prepare.py::test_a_later_call_decides_again_from_scratch`.
- **PRE-4** — What `prepare()` sets in the environment is what dlt or the Databricks SDK
  read there: `DATABRICKS_CONFIG_PROFILE`, `DLT_PROJECT_DIR`, `RUNTIME__LOG_LEVEL`, and
  what `--set` names.
  Held by: `tests/test_prepare.py::test_with_a_profile_a_laptop_loads_into_the_workspace`,
  `tests/test_prepare.py::test_a_wheels_config_is_found_where_the_working_directory_has_none`,
  `tests/test_prepare.py::test_the_log_level_is_dlts_and_stays_after_dlt_makes_its_logger_again`,
  `tests/test_prepare.py::test_a_catalog_and_any_config_value_reach_dlt`,
  `tests/test_app.py::test_set_gives_dlt_any_config_value`,
  `tests/test_app.py::test_the_log_level_is_still_the_level_after_dlt_has_run`.
- **PRE-5** — The first lines of a run, and `doctor`, say what was set up: where it runs
  and on which runtime, the workspace, the destination, the catalog, the schemas, the
  warehouse, what was done about the name `dlt`, where dlt's config and its working
  files are, and the scopes, the pointed-at secrets and the vaults by name.
  Held by: `tests/test_prepare.py::test_the_first_lines_say_everything_and_no_secret`,
  `tests/test_keyvault.py::test_prepare_names_the_vaults_and_reads_them_on_a_laptop_too`,
  `tests/test_app.py::test_a_secret_from_a_scope_reaches_a_pipeline`.

## DBX — what Databricks needs

- **DBX-1** — leeghwater runs on Databricks when `DATABRICKS_RUNTIME_VERSION` is set,
  and on serverless when its value starts with `client.`. Nothing else is read to decide.
  Held by: `tests/test_where.py::test_a_laptop_is_where_the_variable_is_not_set`,
  `tests/test_where.py::test_a_cluster_and_serverless_are_told_apart_by_the_runtime`,
  `tests/test_where.py::test_it_reads_the_process_environment_when_given_none`.
- **DBX-2** — On Databricks, `prepare()` makes `import dlt` dltHub's: what Databricks had
  loaded under the name is dropped, and the import hook is taken out for that one import.
  Held by: `tests/test_hook.py::test_with_the_hook_in_the_way_import_dlt_is_still_dlthubs`,
  `tests/test_hook.py::test_what_databricks_had_loaded_under_the_name_is_dropped_and_said`,
  `tests/test_hook.py::test_dlthubs_dlt_is_told_from_databricks_own`,
  `tests/test_hook.py::test_a_hook_is_known_by_the_names_in_dlts_docs`.
- **DBX-3** — The hook is put back after the import and no entry of `sys.path` is moved.
  Off Databricks nothing is touched.
  Held by: `tests/test_hook.py::test_with_the_hook_in_the_way_import_dlt_is_still_dlthubs`,
  `tests/test_hook.py::test_without_a_hook_it_goes_on_and_says_what_it_got`,
  `tests/test_hook.py::test_on_a_laptop_nothing_is_touched`.
- **DBX-4** — Every step taken about the name `dlt` is a line among the first lines of
  the run. That no hook was found, that the import is not dltHub's after all, and which
  modules hold Databricks' own `dlt` are said too, and the run goes on.
  Held by: `tests/test_hook.py::test_without_a_hook_it_goes_on_and_says_what_it_got`,
  `tests/test_hook.py::test_what_databricks_had_loaded_under_the_name_is_dropped_and_said`,
  `tests/test_hook.py::test_the_modules_that_hold_a_dlt_are_named`.
- **DBX-5** — `--profile` is handed on as `DATABRICKS_CONFIG_PROFILE`, where the SDK
  and dlt's Databricks destination read it, and is refused on Databricks.
  Held by: `tests/test_prepare.py::test_with_a_profile_a_laptop_loads_into_the_workspace`,
  `tests/test_prepare.py::test_a_profile_is_refused_on_databricks`.
- **DBX-6** — leeghwater reads no token and passes none: whoever the Databricks SDK
  finds reads the secrets and loads the data.
  Not tested: it is an absence, and no test can show that no path reads a token.
- **DBX-7** — When the app's package carries a `.dlt/config.toml`, the working directory
  has no `.dlt/` and `DLT_PROJECT_DIR` is not set, `prepare()` points dlt at the package.
  Held by: `tests/test_prepare.py::test_a_wheels_config_is_found_where_the_working_directory_has_none`,
  `tests/test_prepare.py::test_a_config_in_the_working_directory_is_left_to_dlt`,
  `tests/test_prepare.py::test_a_project_dir_that_was_set_is_left`,
  `tests/test_prepare.py::test_a_project_that_is_not_installed_is_no_error`.
- **DBX-8** — A package that carries a `.dlt/secrets.toml` is refused on Databricks, by
  name, before anything is read from it.
  Held by: `tests/test_prepare.py::test_a_wheel_with_a_secrets_toml_is_refused_on_databricks`.

## DST — where a run loads

- **DST-1** — On Databricks, or with a profile, a run loads into the app's `destination`,
  which is Databricks unless the app says otherwise, and the secret scopes are read. On a
  laptop without a profile it loads into `local_destination`, a DuckDB file unless the
  app says otherwise, no scope is read, and the first lines say so.
  Held by: `tests/test_prepare.py::test_on_a_laptop_it_loads_locally_and_reads_no_scope`,
  `tests/test_prepare.py::test_with_a_profile_a_laptop_loads_into_the_workspace`,
  `tests/test_prepare.py::test_on_databricks_it_loads_into_databricks_and_reads_the_scopes`.
- **DST-2** — A destination of `None` leaves the destination to dlt's own config.
  Held by: `tests/test_prepare.py::test_no_destination_leaves_it_to_dlt`,
  `tests/test_pipeline.py::test_no_destination_leaves_it_to_dlt`.
- **DST-3** — The catalog, the warehouse and the staging schema a run names, and the
  switch that turns dlt's normalizing off, are set on the destination `create_pipeline`
  makes, in the call; the schema is given to `dlt.pipeline`. None of them is written to
  the environment, and what the run did not name is left to dlt's config.
  Held by: `tests/test_pipeline.py::test_what_the_run_named_is_set_on_the_destination_itself`,
  `tests/test_pipeline.py::test_what_the_run_did_not_name_is_left_to_dlts_config`,
  `tests/test_prepare.py::test_a_schema_is_given_to_dlt_as_it_is`.
- **DST-4** — A warehouse the app or the run names is given to dlt as the `http_path`
  `/sql/1.0/warehouses/<id>`. The app's `catalog` and `warehouse` are used when a run
  names none.
  Held by: `tests/test_prepare.py::test_a_warehouse_is_kept_as_its_id_and_its_path`,
  `tests/test_pipeline.py::test_what_the_run_named_is_set_on_the_destination_itself`,
  `tests/test_app.py::test_doctor_checks_the_identity_the_scopes_and_the_warehouse`.
- **DST-5** — A `run` of the app that loads into Databricks with no warehouse named
  stops before the pipeline is called. A warehouse named by `DATABRICKS_WAREHOUSE_ID` or
  by an `http_path` in dlt's config counts; `prepare()` alone goes on, and its first
  lines say that dlt will choose.
  Held by: `tests/test_prepare.py::test_a_run_through_the_app_stops_without_a_warehouse`,
  `tests/test_prepare.py::test_a_notebook_is_told_that_dlt_will_choose`,
  `tests/test_prepare.py::test_a_warehouse_named_another_way_counts`,
  `tests/test_prepare.py::test_locally_no_warehouse_is_asked_for`,
  `tests/test_app.py::test_on_databricks_a_run_without_a_warehouse_stops_before_the_pipeline`.
- **DST-6** — A schema a run names is the schema dlt loads into, unchanged: dlt's
  normalizing of the dataset name is off for that run. `--staging-schema` is the staging
  schema's whole name, and dlt derives none of its own.
  Held by: `tests/test_app.py::test_the_schemas_a_run_names_are_the_ones_dlt_loads_into`,
  `tests/test_prepare.py::test_a_schema_is_given_to_dlt_as_it_is`,
  `tests/test_pipeline.py::test_what_the_run_named_is_set_on_the_destination_itself`,
  `tests/test_dlt.py::test_a_destination_takes_its_config_fields_in_the_call`.
- **DST-7** — A staging schema with `%s` in its name is refused. A run that loads into
  Databricks and names a schema without a staging schema stops; a run that loads
  locally may name a schema alone.
  Held by: `tests/test_prepare.py::test_what_is_refused`,
  `tests/test_prepare.py::test_on_databricks_a_schema_needs_its_staging_schema`,
  `tests/test_prepare.py::test_locally_a_schema_alone_is_enough`.

## SEC — secrets

- **SEC-1** — A secret scope is a dlt config provider, registered after dlt's own: the
  environment wins, then `secrets.toml`, then the scopes in the order they are named.
  Held by: `tests/test_secrets.py::test_an_argument_of_a_real_source_is_filled_from_the_scope`,
  `tests/test_secrets.py::test_the_environment_wins_over_a_scope`,
  `tests/test_secrets.py::test_the_first_scope_that_has_a_secret_answers`,
  `tests/test_dlt.py::test_a_provider_is_registered_after_dlts_own_and_once`.
- **SEC-2** — A value is read through the client's `dbutils.secrets.get`, on a laptop
  and on Databricks, and never through the SDK's secrets API.
  Held by: `tests/test_secrets.py::test_a_scope_is_listed_once_and_only_what_is_there_is_read`.
- **SEC-3** — A secret is found by the path dlt has for it, joined with `-`:
  `sources.github.access_token` is the secret `sources-github-access_token`.
  Held by: `tests/test_secrets.py::test_a_secret_is_named_by_dlts_path_joined_with_dashes`.
- **SEC-4** — Only a value its source types as a secret is looked up in a scope.
  Held by: `tests/test_secrets.py::test_a_value_that_is_not_a_secret_is_never_asked_of_a_scope`.
- **SEC-5** — A secret named for a section, such as `sources-<name>` or
  `dlt_secrets_toml`, is read as a piece of `secrets.toml`, as dlt's own vault providers
  read one. The piece is laid at the root of the document, not under the secret's name.
  Held by: `tests/test_secrets.py::test_a_secret_can_hold_a_whole_section`,
  `tests/test_secrets.py::test_a_section_without_its_own_heading_lands_at_the_root`,
  `tests/test_secrets.py::test_dlt_secrets_toml_is_read_as_a_whole_file`.
- **SEC-6** — A scope's provider lists its scope once in a process, and fetches only a
  secret the scope holds.
  Held by: `tests/test_secrets.py::test_a_scope_is_listed_once_and_only_what_is_there_is_read`.
- **SEC-7** — A secret under another name is pointed at as `<scope>/<key>`, split at
  the first `/`. What is pointed at is asked before any scope, and after dlt's own
  providers.
  Held by: `tests/test_secrets.py::test_a_secret_under_another_name_can_be_pointed_at`,
  `tests/test_secrets.py::test_a_pointer_is_a_scope_and_a_key_split_at_the_first_slash`.
- **SEC-8** — A run's `--secret-scope` stands in place of the app's scopes, and a run's
  `--secret` points at a secret beside the ones the app points at.
  Held by: `tests/test_app.py::test_a_run_can_name_other_scopes_and_point_at_a_secret`.
- **SEC-9** — leeghwater prints, logs and writes no secret's value, and puts none in
  the environment. The first lines, `doctor`, a provider's name and an error name scopes
  and keys, never a value.
  Held by: `tests/test_prepare.py::test_the_first_lines_say_everything_and_no_secret`,
  `tests/test_prepare.py::test_a_wheel_with_a_secrets_toml_is_refused_on_databricks`,
  `tests/test_app.py::test_doctor_checks_the_identity_the_scopes_and_the_warehouse`,
  `tests/test_app.py::test_a_secret_from_a_scope_reaches_a_pipeline`,
  `tests/test_secrets.py::test_a_pointer_at_nothing_is_an_error_that_names_it`,
  `tests/test_secrets.py::test_no_value_is_in_what_a_provider_says_about_itself`,
  `tests/test_keyvault.py::test_no_value_is_in_what_the_provider_says_about_itself`.
- **SEC-10** — A scope that does not exist, a scope that cannot be listed and a pointer
  at a key that is not there are each an error. It names the scope, and the command to
  run, the permission that is missing or the keys the scope does hold.
  Held by: `tests/test_secrets.py::test_a_scope_that_does_not_exist_is_an_error_with_its_name`,
  `tests/test_secrets.py::test_a_scope_that_refuses_says_which_scope_and_who_asked`,
  `tests/test_secrets.py::test_a_pointer_at_nothing_is_an_error_that_names_it`.
- **SEC-11** — A key that is missing, refused or empty is "not here", and dlt looks on.
  Any other error from the workspace is raised as it came.
  Held by: `tests/test_secrets.py::test_a_missing_a_refused_and_an_empty_key_are_all_not_here`,
  `tests/test_secrets.py::test_any_other_error_is_raised_as_it_came`.
- **SEC-12** — Registering a scope or a vault twice adds one provider. There is one
  provider for pointed-at secrets in a process, and pointing again replaces what it
  points at.
  Held by: `tests/test_secrets.py::test_registering_a_scope_twice_adds_it_once`,
  `tests/test_secrets.py::test_pointing_again_replaces_what_was_pointed_at`,
  `tests/test_secrets.py::test_the_pointed_provider_is_one_per_process_and_registered_once`,
  `tests/test_keyvault.py::test_registering_a_vault_twice_adds_it_once`.
- **SEC-13** — An Azure Key Vault is a provider of its own, asked after the scopes. It
  is listed once, only a secret it holds is fetched, and it is read on a laptop without
  a profile too.
  Held by: `tests/test_keyvault.py::test_an_argument_of_a_real_source_is_filled_from_the_vault`,
  `tests/test_keyvault.py::test_a_section_in_one_secret`,
  `tests/test_keyvault.py::test_a_scope_is_asked_before_a_vault`,
  `tests/test_keyvault.py::test_prepare_names_the_vaults_and_reads_them_on_a_laptop_too`.
- **SEC-14** — A secret in a vault is named as in a scope, with every underscore a
  dash: `sources-github-access-token`.
  Held by: `tests/test_keyvault.py::test_a_secret_is_named_without_underscores`.
- **SEC-15** — In a vault a missing or a refused secret is "not here". Nobody signed
  in, a vault that refuses its listing, a vault that is not there and a vault named
  without its address are each an error that names the vault.
  Held by: `tests/test_keyvault.py::test_a_missing_and_a_refused_secret_are_not_here`,
  `tests/test_keyvault.py::test_nobody_signed_in_is_said_in_plain_words`,
  `tests/test_keyvault.py::test_a_vault_that_refuses_or_is_not_there_names_itself`,
  `tests/test_keyvault.py::test_a_vault_with_nothing_for_dlt_leaves_dlts_own_error`,
  `tests/test_keyvault.py::test_a_vault_needs_an_address`.

## DLT — beside dlt

- **DLT-1** — Nothing in dlt is patched. leeghwater goes through what dlt offers: a
  registered config provider, the config dlt reads from the environment, and the
  arguments of `dlt.pipeline` and of a destination.
  Not tested: it is an absence. DLT-2 keeps the calls into dlt in one file, where a
  patch would show.
- **DLT-2** — A call into dlt beyond its documented API is a function in
  `src/leeghwater/_dlt.py`, and each has a test in `tests/test_dlt.py` that fails when
  dlt moves it. Only `_dlt.py` and the two provider modules, `secrets.py` and
  `keyvault.py`, import from inside dlt.
  Held by: `tests/test_dlt.py::test_every_reach_into_dlt_has_a_canary`,
  `tests/test_dlt.py::test_only_the_provider_modules_import_from_inside_dlt`.
- **DLT-3** — dlt is the one dependency with an upper bound, below 2. The Databricks SDK
  and typer have a lower bound only, and the Azure packages come with the `keyvault`
  extra and not without it.
  Held by: `tests/test_dlt.py::test_dlt_is_the_one_dependency_with_an_upper_bound`.

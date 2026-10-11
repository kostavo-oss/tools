# Rules

What must be true of lely. Each rule is a few sentences in the present tense, and names
the tests that hold it. Why a rule is so is in [DECISIONS.md](DECISIONS.md); how lely
works is in [docs/how-it-works.md](docs/how-it-works.md); what ran on a real workspace
and on GitHub is in [docs/tried.md](docs/tried.md).

## How this file is kept

- A rule has an identifier: an area and a number, such as `APL-3`. Code, tests and docs
  cite a rule by that identifier and by nothing else.
- A new rule takes the next number in its area. A number is never reused: a rule that is
  dropped leaves a gap, and a rule that changes its meaning gets a new number.
- Under each rule stands `Held by:` with the tests that hold it, each as
  `tests/<path>.py::<test>`. Each of those tests cites the identifier, and no other test
  does.
- A rule no test can hold says `Not tested:` and why, in place of `Held by:`.
- A rule states the whole promise, also when the code does not keep all of it yet. Such
  a rule is open: it says `Not kept yet:`, the number of the issue that tracks it, and
  what the code does instead, as `Not kept yet: #12 — what the code does`. Its
  `Held by:` names the tests of the part that holds, if there are any. When the code
  keeps the rule the line is taken out, and the rule gets the test it lacked.
- A change to behaviour changes its rule and its test in the same pull request.
  `tests/test_rules.py` at the root of the repository checks all of the above.

The tests run against stand-ins: `tests/fake_databricks.py` is the Databricks CLI,
`tests/fake_github.py` is a pull request's comments, `tests/fake_stevin.py` is the
`stevin` command: it plans from a plan file stevin recorded, and applies it. What the
plugin for bundles assumes of the real CLI, and what was seen of it, is numbered `V1` to
`V8` in the docstring of `src/lely/steps/bundle.py`; the tests and the fake cite those
numbers. What the `stevin` plugin assumes of stevin's command line is numbered `S1` to
`S9` in `tests/fake_stevin.py`.

The areas: `CFG` the config, `REF` what flows between steps, `PLG` the plugin contract,
`BDL` the `bundle` plugin, `BRUN` the `bundle.run` plugin, `STV` the `stevin` plugin,
`PROG` a program as a step,
`SOLO` a step on its own, `PLAN` the plan and its file, `WAIT` a step that cannot be
planned yet, `APL` apply, `DST` destroy, `ASK` consent, `CLI` the command line, `SEC`
secrets and what a plan says, `PAGE` a plan as a page, `GH` GitHub, `PKG` the package.

## CFG — the config

- **CFG-1** — The config is one ordered list: `steps` is the only key at the top, and a
  config without a step is refused. The order written is the order the steps are applied
  in. The bundle is one entry of the list, and a project may have several bundle steps or
  none.
  Held by: `tests/unit/test_config.py::test_reads_steps_in_the_order_written`,
  `tests/unit/test_config.py::test_the_keys_from_before_the_one_list_are_unknown`.
- **CFG-2** — A step has `uses`, and may have `name`, `with` and `targets`; any other key
  is an error where it was written. A name starts with a letter or `_`, goes on with
  letters, digits, `_` or `-`, and is unique in the config. A plain plugin name such as
  `bundle` doubles as the step's name; any other `uses` needs a `name`.
  Held by: `tests/unit/test_config.py::test_names_are_one_reference_part`,
  `tests/unit/test_config.py::test_names_are_unique`.
- **CFG-3** — `targets` is a list of names compared with `-t` as written. For any other
  target the step is skipped in a plan, an apply, a destroy and a status, and each says
  that it was.
  Held by: `tests/unit/test_config.py::test_targets_limit_a_step`,
  `tests/unit/test_planning.py::test_targets_skip_a_step_and_the_plan_says_so`.
- **CFG-4** — The config is `lely.yml`, or `[tool.lely]` in `pyproject.toml` with the same
  keys and the same meaning. The same project written either way gives the same plan and
  the same made-from hashes, so a plan made from one is accepted with the other. The
  same project is one that hands every plugin the same options: `1.10` and `yes` in a
  `lely.yml` are `1.10` and `true` in a `pyproject.toml` for an option that wants a
  number or a yes or no, and `"1.10"` and `"yes"` for one that wants text (CFG-10).
  Held by: `tests/unit/test_cli.py::test_a_project_in_pyproject`,
  `tests/unit/test_planning.py::test_the_same_project_in_pyproject_gives_the_same_plan`,
  `tests/unit/test_options.py::test_a_value_counts_the_same_in_yaml_and_in_toml`.
- **CFG-5** — Without `--config`, the config is found by walking up from the working
  directory to the first folder that has a `lely.yml`, or a `pyproject.toml` with a
  `[tool.lely]` section. A step's paths are relative to the config file, not to where the
  command was run.
  Held by: `tests/unit/test_cli.py::test_the_config_is_found_from_a_subfolder`,
  `tests/unit/test_config.py::test_the_config_is_found_from_a_subfolder`.
- **CFG-6** — A folder that has both is an error that names the two files: lely does not
  merge them and does not pick. A file named with `--config` is not checked against its
  neighbour. A `lely.yaml` met on the way up is refused with the name lely reads.
  Held by: `tests/unit/test_config.py::test_both_in_one_folder_is_an_error_that_names_them`,
  `tests/unit/test_config.py::test_a_config_named_lely_yaml_says_what_lely_reads`.
- **CFG-7** — The problems of a config's shape are reported together, and so are the
  problems of the steps' plugins, options and references, each with the file, line and
  column of what was written, in either format. In a `pyproject.toml` a position is found
  again by scanning the text: exact for a file written the usual way, a best effort
  otherwise.
  Held by: `tests/unit/test_config.py::test_every_problem_is_reported_at_once`,
  `tests/unit/test_config.py::test_bad_yaml_says_where`.
- **CFG-8** — `lely validate` checks the config, every step's options and every reference
  without a workspace, and prints the wiring: for each step what it takes and from where,
  and what it gives with when each is known.
  Held by: `tests/unit/test_cli.py::test_validate_prints_the_wiring`,
  `tests/unit/test_render_rich.py::test_the_wiring`.
- **CFG-9** — `lely schema` prints a JSON Schema (draft-07) of the config, built from the
  plugins installed and the ones the project names: each plugin's options, with the `#:`
  comment above each as its description, and what a step of it gives. It says what
  `validate` says about a config's shape and no more, and where the two could differ it
  lets a value through. It is for a `lely.yml`: a `[tool.lely]` section has no schema of
  its own.
  Held by: `tests/unit/test_schema.py::test_a_config_lely_reads_fits_the_schema`,
  `tests/unit/test_schema.py::test_a_shape_lely_refuses_doesnt_fit_the_schema`,
  `tests/unit/test_schema.py::test_a_list_or_a_mapping_given_whole_by_one_reference_fits`.
- **CFG-10** — An option that wants text gets what was written: a number or a boolean in a
  `lely.yml` is passed on as its own text (`1.10` stays `1.10`, `0123` is not read as
  octal, `yes` stays `yes`), and what a step is made from follows that text. In a
  `pyproject.toml` a number is a number: text that has to stay as written is written
  there as a string.
  Held by: `tests/unit/test_config.py::test_a_yaml_number_keeps_the_text_it_was_written_as`,
  `tests/unit/test_options.py::test_a_number_meant_as_text_is_passed_on_as_it_was_written`.
- **CFG-11** — A list or a mapping given whole by one reference is handed to the plugin
  as the option declares its elements, as if each had been written out: a `Secret` where
  the option wants secrets, a number where it wants numbers. An element that does not
  fit is an error at the reference, and a secret among elements that are no `Secret` is
  refused. A number for an element that wants text is passed on as its text, as one
  that came alone by a reference is. One case differs: a list or a mapping declared as
  text and nothing else (`tuple[str, ...]`, `Mapping[str, str]`) takes text only.
  Held by: `tests/unit/test_options.py::test_a_list_or_a_mapping_given_whole_is_converted_by_element`.

## REF — what flows between steps

- **REF-1** — A plugin declares what a step of it gives. Each output has a name and one of
  three answers to when it is known: at plan, once it exists, or after every run.
  `outputs` is a tuple, or a function of the step's options as written; a plugin that says
  nothing gives nothing.
  Held by: `tests/unit/test_planning.py::test_check_passes_the_scenario_and_returns_the_wiring`,
  `tests/unit/test_refs.py::test_a_plain_output_that_exists_only_after_apply_is_unknown`.
- **REF-2** — An output whose name depends on the project is declared as a shape, such as
  `resources.<type>.<key>.id`, where each `<…>` stands for exactly one part of the name. A
  reference is matched against the declared names: the most literal wins, then the
  longest, and what is left of the reference walks into the value. Offline a reference is
  checked against the shape; a name of a shape known at plan or once it exists that is
  neither given nor named as coming later is an error when the step that takes it is
  planned.
  Held by: `tests/unit/test_planning.py::test_a_resource_the_bundle_doesnt_have_is_refused_at_plan`,
  `tests/unit/test_refs.py::test_a_shape_stands_for_one_part_each`.
- **REF-3** — A step takes a value from another step in one way:
  `${steps.<name>.<output>}` in its own options. `${env.<NAME>}` reads the environment,
  which is not a step. `$${` is no reference: it writes a literal `${`, and is read from
  the left. Any other `${…}` is an error. One that names neither says how to write it as a
  literal and, when a step above gives an output of that name, as a reference to that
  step; no step is named that is not there.
  Held by: `tests/unit/test_refs.py::test_what_is_no_reference_says_how_to_write_it_out`,
  `tests/unit/test_running.py::test_a_literal_dollar_brace_reaches_the_program_as_it_is_meant`.
- **REF-4** — An option of type `Linked` names a whole step: the plugin is given that
  step's resolved options and what it gives. The named step stands above the one that
  names it, and `validate` checks that. What a plugin reads from a linked step is not held
  to the plan as a referenced output is: a plugin that acts on such a value puts it in the
  change it plans.
  Held by: `tests/unit/test_options.py::test_an_option_can_name_a_step`,
  `tests/unit/test_refs.py::test_a_named_step_follows_the_same_rules`.
- **REF-5** — A reference names a step listed above the one that writes it, never one
  below and never the step itself. So the order of the list is the order of dependency,
  and no circle can be written.
  Held by: `tests/unit/test_refs.py::test_a_step_may_use_the_outputs_of_a_step_above`,
  `tests/unit/test_refs.py::test_a_reference_down_the_list_says_to_move_it`.
- **REF-6** — `lely validate` refuses, offline: a reference to a step that is not there;
  to one listed further down, with a message that says to move it; to an output its plugin
  does not declare or that fits no declared shape; to a step whose `targets` leave out a
  target the referring step runs for; and a value from the environment in an option that
  is not a `Secret`: also at any depth of an option that takes anything (`object`), and
  as a list or a mapping given whole. Offline an environment value is not looked up and
  not stood in for. A plan refuses the same, and so refuses a secret a step above gives.
  Held by: `tests/unit/test_planning.py::test_check_refuses_a_reference_down_the_list`,
  `tests/unit/test_planning.py::test_validate_already_knows_where_an_environment_value_may_not_go`,
  `tests/unit/test_planning.py::test_validate_refuses_an_environment_value_as_a_bundle_variable`.
- **REF-7** — A value that is not known yet is never guessed: it resolves to the name of
  the output it waits for, and the step that takes it is waiting. A step that takes an
  output known only after every run waits on every deploy, and `validate` warns of it
  where it prints the wiring.
  Held by: `tests/unit/test_planning.py::test_check_warns_about_a_step_that_waits_on_every_deploy`,
  `tests/unit/test_refs.py::test_a_value_still_to_come_is_unknown_and_named`.
- **REF-8** — In a plan every step lists what it takes: under the option it fills, from
  which step, and with the value where it is known, as `model_version = 14  ←
  model.version`. An output is shown where it is given only when another step takes it;
  the plan file keeps a step's outputs that have a plain name and the ones another step
  takes.
  Held by: `tests/unit/test_planning.py::test_the_plan_keeps_the_outputs_another_step_takes`,
  `tests/unit/test_planning.py::test_a_value_is_shown_under_its_own_options_name`.
- **REF-9** — A destroy and a status resolve inputs from the top of the list down, by
  planning each step as a plan does, so a step that only looks something up still does its
  lookup. A destroy then removes from the bottom up, so a step below the bundle is
  destroyed while the bundle still exists. A step whose input does not exist is skipped
  with the reason, and the rest goes on.
  Held by: `tests/unit/test_planning.py::test_a_destroy_resolves_inputs_from_the_top_down`,
  `tests/unit/test_running.py::test_destroy_goes_from_the_bottom_up`.

## PLG — the plugin contract

- **PLG-1** — No module outside `src/lely/steps/` imports a plugin. The bundle goes
  through the same contract as a class in someone's repository: plugins are found through
  the registry, and what the core needs of one it reads off the contract.
  Held by: `tests/unit/test_planning.py::test_the_bundles_plan_is_one_steps_plan_like_any_other`,
  `tests/unit/test_repo.py::test_no_module_outside_steps_imports_a_plugin`.
- **PLG-2** — A plugin is found by a registered name from the entry-point group
  `lely.steps`, by `package.module:Class`, or by `./path/file.py:Class` relative to the
  config. The plugins lely ships register the same way. `lely steps` lists the registered
  ones and the ones the project names, each with its options, what it gives and when, and
  whether it can apply, list and destroy; one that cannot be loaded is said and the rest
  are listed.
  Held by: `tests/unit/test_cli.py::test_steps_lists_plugins_with_what_they_take_give_and_can_do`,
  `tests/unit/test_registry.py::test_the_plugins_lely_ships_register_like_anyones`.
- **PLG-3** — A plugin declares its options as a dataclass, and a step's `with:` is read
  into it strictly: an unknown option, a missing required one or a wrong type is an error
  where it was written, found offline by `validate`. An option is a field a config can
  set; a `Literal` takes one of its members and of its kind.
  Held by: `tests/unit/test_options.py::test_reads_every_supported_type`,
  `tests/unit/test_options.py::test_an_unknown_option_names_the_known_ones`.
- **PLG-4** — A plugin plans and applies. It may also list what exists because of a step
  (`overview`) and take it down (`plan_destroy` and `destroy`, both or neither). A plugin
  without one says so by not having it, and `overview` and `plan_destroy` may answer
  `Skip` with a reason.
  Held by: `tests/unit/test_registry.py::test_a_class_that_isnt_a_plugin`,
  `tests/unit/test_registry.py::test_destroying_is_planned_first_or_not_at_all`.
- **PLG-5** — A step is given its `Context` and nothing else: the target, its own name,
  its options with references resolved, the project's directory, the workspace's host, the
  environment for a program it runs, the Databricks CLI with the run's credentials, a log,
  the workspace client, connected on first use, what it is planned for: apply, destroy
  or status, and in `apply` its own plan as it was approved (PLG-14). For a destroy and a
  status what exists now counts, not what a deploy would make of it. A step is not given
  the other steps' outputs: what it depends on is in its options.
  Held by: `tests/unit/test_cli.py::test_a_plugin_is_given_a_client_for_the_same_profile`,
  `tests/unit/test_planning.py::test_a_destroy_takes_the_id_a_thing_has_now_not_the_one_a_deploy_would_give`.
- **PLG-6** — The target is a bare name, handed to every step as it was typed: each plugin
  reads it its own way, and lely keeps no list of targets. One run talks to one workspace,
  which comes from `--profile` or from the variables the Databricks CLI and SDK read.
  Held by: `tests/unit/test_cli.py::test_who_is_running_is_asked_of_the_sdk_with_the_profile`,
  `tests/unit/test_databricks.py::test_runs_the_cli_with_the_profile`.
- **PLG-7** — What a plugin hands back is held to the contract when it is taken. A plan is
  a `StepPlan` with unique change keys and text where text belongs. Nothing undeclared is
  given, nothing declared as known at plan is missing, and a plan gives no output of a
  run. An overview line has a kind, a key and a name. A plugin's own code that fails is
  reported with the step's name, not as a traceback.
  Held by: `tests/unit/test_planning.py::test_a_misbehaving_plugin_is_named`,
  `tests/unit/test_planning.py::test_a_plugin_whose_own_code_raises_is_named_not_a_traceback`.
- **PLG-8** — What a plugin prints goes to stderr, however it prints it: stdout is lely's.
  `sys.exit` in a plugin is that step's error and does not end lely.
  Held by: `tests/unit/test_quietly.py::test_what_a_plugin_writes_goes_to_stderr_however_it_writes`,
  `tests/unit/test_quietly.py::test_a_plugin_that_takes_its_stdout_apart_leaves_lelys_alone`.
- **PLG-9** — The rules every plugin follows: it keeps no state; `plan` and `overview`
  change nothing; `apply` does what the plan says and no more; it touches only what its
  options name; it destroys only what it can show is its own; a change that loses
  something is marked destructive, and a delete and a replace always are; its outputs are
  as declared; and no secret is in a plan. `lely.testing` holds a plugin to each of them
  as far as it sees one, which is through the Databricks CLI a step is handed, what the
  plugin answers, and what a test shows it: `check_plan`, `check_apply`, `check_destroy`
  and `check_overview`; `check_no_state`, which makes every call on a new plugin and
  hands `apply` the plan as a plan file keeps it; and `check_only_its_own`, which holds
  a second step's plan and overview, and what a test names as untouched, the same
  across this step's apply and destroy. Given a class, every check makes each call on a
  new instance, as lely does.
  Held by: `tests/unit/test_testing.py::test_a_plugin_that_follows_the_rules_passes_all_of_it`,
  `tests/unit/test_testing.py::test_plan_changes_nothing`,
  `tests/unit/test_testing.py::test_a_plugin_keeps_no_state_and_touches_only_its_own`.
- **PLG-10** — Every plugin lely ships passes the checks of `lely.testing` that apply to
  it.
  Held by: `tests/unit/test_testing.py::test_the_bundle_plugin_passes_the_whole_kit`,
  `tests/unit/test_testing.py::test_bundle_run_passes_the_parts_that_apply`,
  `tests/unit/test_testing.py::test_the_stevin_plugin_passes_the_parts_that_apply`.
- **PLG-11** — Every plugin lely ships applies what it plans. A plugin that can plan and
  cannot apply yet says so with `plan_only`, and `apply` refuses a project with a step of
  one before anything is asked or run.
  Held by: `tests/unit/test_running.py::test_a_plugin_that_cant_apply_yet_stops_it_before_anything_runs`,
  `tests/unit/test_step_stevin.py::test_it_plans_applies_and_lists_and_drops_nothing`.
- **PLG-13** — What a program writes while a step changes something is passed on to the
  step's log a line at a time, as it comes, from both of its streams; a program that only
  answers a question is run to its end and read. A failing program is quoted on both
  streams, each under its name when both were written to, and a missing program or working
  directory is said as what it is.
  Held by: `tests/unit/test_process.py::test_a_failing_program_is_quoted_on_both_streams`,
  `tests/unit/test_process.py::test_a_program_is_heard_while_it_runs_and_what_it_wrote_is_kept`.
- **PLG-14** — `apply` is handed the plan made right before it, and with it, as
  `Context.approved`, the step's own plan as it was approved: its changes and its payload,
  also when the approved plan was read from a file. A plugin that must run what was
  reviewed takes its payload from there. It is `None` in every other call, and for a step
  that was waiting when the plan was made: what was approved then is the plan `apply` is
  handed.
  Held by: `tests/unit/test_running.py::test_apply_is_handed_the_plan_that_was_approved_beside_the_fresh_one`,
  `tests/unit/test_running.py::test_a_step_that_was_waiting_is_handed_no_approved_plan`.
- **PLG-15** — A plugin with no destroy may say why in `nothing_to_destroy`: a destroy
  plan and a destroy show the step as skipped with those words, in place of "has nothing
  to destroy".
  Held by: `tests/unit/test_running.py::test_a_destroy_leaves_stevins_tables_alone_and_says_so`.
- **PLG-16** — The rules of PLG-9 hold by every road, also where `lely.testing` does not
  look: `plan` and `overview` make no write through the SDK (`ctx.workspace`) or by a
  program the plugin starts itself; a plugin keeps no state on its class, in a module,
  in a file or in a service; it changes nothing in a workspace that no step's plan or
  overview shows; and a plugin with no destroy leaves another step's things alone when
  it is applied after them. The kit's docs name these as what it does not see.
  Not tested: the kit holds only the Databricks CLI a step is handed to reading, and
  sees a workspace only through a plugin's own answers and what a test shows it. For
  the `stevin` plugin that leaves out `stevin plan`, which is another program.

## BDL — the `bundle` plugin

- **BDL-1** — `uses: bundle` has two options: `path`, the directory holding
  `databricks.yml`, relative to the config and `.` by default; and `vars`, passed to the
  bundle as `--var` on every call of the Databricks CLI the step makes. A `path` that is
  not a directory is said so at plan.
  Held by: `tests/unit/test_step_bundle.py::test_a_bundle_in_another_directory`,
  `tests/unit/test_step_bundle.py::test_a_bundle_path_that_isnt_there_says_so`.
- **BDL-2** — The plugin asks the Databricks CLI and never works out itself what the CLI
  resolves: targets, variables, names, ids. What it knows it reads from `bundle summary`
  and `bundle plan`, each with `-o json`; it never calls `bundle validate`.
  Held by: `tests/unit/test_step_bundle.py::test_what_a_deployed_bundle_gives_from_the_clis_own_recordings`,
  `tests/unit/test_step_bundle.py::test_nothing_lely_does_to_look_calls_validate`.
- **BDL-3** — It needs the direct engine. A plan without a `plan_version` is refused with
  a message that says a bundle on the Terraform engine is not supported, and a plan of
  another version than the one lely reads is refused.
  Held by: `tests/unit/test_step_bundle.py::test_another_plan_version_is_refused`,
  `tests/unit/test_step_bundle.py::test_a_plan_that_isnt_the_direct_engines_is_refused`.
- **BDL-4** — A project can have more than one bundle step. Each has its own name, path
  and outputs, one can feed another, and each takes `-t` as its own bundle target. A
  bundle whose summary names another host than the run talks to is refused; lely makes
  that comparison itself, after the CLI's first call.
  Held by: `tests/unit/test_planning.py::test_two_bundles_in_one_project`,
  `tests/unit/test_step_bundle.py::test_a_bundle_for_another_workspace_is_refused`.
- **BDL-5** — A plan holds one change per resource the CLI would create, update, replace
  or delete, keyed `<type>.<key>`, with the fields that change as its lines and the ones
  that force a replacement named. A `recreate` and an `update_id` are a replace. A delete
  and a replace are destructive, and so is any action of the CLI's that lely does not
  know. The CLI's own plan is the step's payload.
  Held by: `tests/unit/test_step_bundle.py::test_a_first_deploy_creates_everything`,
  `tests/unit/test_step_bundle.py::test_an_immutable_field_replaces_the_resource`.
- **BDL-6** — Every plan of a bundle step carries one `run`, "uploads the bundle's files":
  a deploy uploads them even when no resource changes. So a bundle step is never "nothing
  to do", and its deploy always runs.
  Held by: `tests/unit/test_step_bundle.py::test_a_bundle_step_is_never_nothing_to_do`.
- **BDL-7** — It gives `target` and `name`, `workspace.<field>`, `var.<name>` and
  `resources.<type>.<key>.<field>` at plan, and `resources.<type>.<key>.id` and `.url`
  once the resource exists. For an apply, the id and the link of a resource this deploy
  creates or replaces are named as coming later, so a step that takes one waits. A
  resource that is deployed and no longer declared gives nothing.
  Held by: `tests/unit/test_step_bundle.py::test_the_id_of_what_this_deploy_creates_or_replaces_comes_later`,
  `tests/unit/test_step_bundle.py::test_a_resource_this_deploy_removes_gives_nothing`.
- **BDL-8** — Apply deploys the plan that was made and checked right before it: that fresh
  plan is written to a file and handed to `bundle deploy --plan`, with `--auto-approve`.
  It is not the plan from the plan file.
  Held by: `tests/unit/test_running.py::test_the_bundle_deploys_a_fresh_plan_not_the_one_that_was_reviewed`,
  `tests/unit/test_step_bundle.py::test_apply_deploys_the_plan_it_is_handed`.
- **BDL-9** — A second run finishes the first. After an apply that failed below the
  bundle, running again finds no resource to change, deploys anyway, which uploads the
  files, and goes on to the steps after it.
  Held by: `tests/unit/test_running.py::test_running_it_again_finishes_the_job`,
  `tests/unit/test_step_bundle.py::test_a_second_run_deploys_again_and_only_uploads`.
- **BDL-10** — A deploy the CLI refuses because the state has moved on since the plan was
  made is passed on in the CLI's own words and ends the run as refused. Any other failed
  deploy is a failure, quoted in the CLI's words.
  Held by: `tests/unit/test_step_bundle.py::test_a_plan_the_state_has_moved_on_from_is_refused_in_the_clis_words`,
  `tests/unit/test_step_bundle.py::test_a_deploy_that_fails_is_a_failure_not_a_refusal`.
- **BDL-11** — The overview comes from `bundle summary` and from nothing else: every
  resource the bundle declares for the target, with its kind, key and name, and its id and
  link once it is deployed.
  Held by: `tests/unit/test_step_bundle.py::test_the_overview_lists_every_resource_with_its_id_and_link`.
- **BDL-12** — Before a first deploy the overview shows what would exist: every resource
  the bundle declares, each marked as not deployed.
  Held by: `tests/unit/test_step_bundle.py::test_before_a_first_deploy_it_shows_what_would_exist`.
- **BDL-13** — The overview and the destroy plan say whose view they are: the identity and
  the bundle's root path the summary was read under. Nothing deployed is said as "not
  deployed, as far as `<identity>` can see under `<path>`", never as a bare "nothing
  there".
  Held by: `tests/unit/test_cli.py::test_status_shows_what_is_deployed_and_whose_view_it_is`,
  `tests/unit/test_running.py::test_a_destroy_that_finds_nothing_says_whose_view_that_is`,
  `tests/unit/test_step_bundle.py::test_before_a_first_deploy_it_shows_what_would_exist`,
  `tests/unit/test_step_bundle.py::test_what_another_identity_deployed_looks_not_deployed_from_here`.
- **BDL-14** — A destroy plan lists every resource the summary shows as deployed, each as
  a delete, and says that the bundle's uploaded files go with them, "and whatever else
  `bundle destroy` removes". With nothing deployed it has no changes and says so in the
  words of BDL-13.
  Held by: `tests/unit/test_step_bundle.py::test_a_destroy_plan_lists_what_the_summary_shows_as_deployed`,
  `tests/unit/test_step_bundle.py::test_nothing_deployed_is_an_empty_destroy_plan_that_says_so`.
- **BDL-15** — Destroying runs `bundle destroy --auto-approve` for the target and nothing
  else: lely deletes no resource itself, and what another bundle deployed is still there
  afterwards.
  Held by: `tests/unit/test_step_bundle.py::test_destroy_runs_bundle_destroy_and_nothing_else`,
  `tests/unit/test_step_bundle.py::test_destroy_undoes_apply`.
- **BDL-16** — A bundle variable is text, passed as written, and a null is passed as
  empty. A value with a comma or a quote is CSV-quoted, because `--var` reads its value as
  a line of CSV. A secret, a list or a mapping is refused where it is written, and a value
  with a line break is not sent.
  Held by: `tests/unit/test_planning.py::test_a_bundle_variable_is_passed_as_it_was_written`,
  `tests/unit/test_step_bundle.py::test_a_variable_that_would_hold_a_secret_is_refused`.
- **BDL-17** — The bundle's view for the page is every resource it declares, by type, with
  what the plan does to each and its id now, the ones the plan leaves alone too. It holds
  keys, names and ids, each escaped, and nothing of a resource's config.
  Held by: `tests/unit/test_step_bundle.py::test_the_bundles_view_is_its_resources_by_type_with_what_happens_to_each`,
  `tests/unit/test_step_bundle.py::test_a_destroy_plans_view_is_what_would_go`.

## BRUN — the `bundle.run` plugin

- **BRUN-1** — `uses: bundle.run` has three options: `bundle`, the bundle step the
  resource belongs to, always named; `resource`, as `<type>.<key>`; and `args`, passed to
  the job or pipeline after `--`. The step it names must be a bundle step.
  Held by: `tests/unit/test_step_bundle_run.py::test_the_step_it_names_must_be_a_bundle_step`.
- **BRUN-2** — Its plan is one `run` of that resource, on every apply. A resource the
  bundle does not have for the target is an error at plan; one this deploy creates can be
  run.
  Held by: `tests/unit/test_step_bundle_run.py::test_plans_one_run`,
  `tests/unit/test_step_bundle_run.py::test_a_resource_this_deploy_creates_can_be_run_too`.
- **BRUN-3** — Apply runs `databricks bundle run <key>` the way its bundle step asks the
  CLI: the same directory, the same target, the same `--var`s. It waits for the run and
  passes on what the CLI writes meanwhile, and a failed run is a failed step.
  Held by: `tests/unit/test_step_bundle_run.py::test_apply_runs_the_resource_the_way_its_bundle_is_asked`,
  `tests/unit/test_step_bundle_run.py::test_what_the_run_says_is_passed_on`.
- **BRUN-4** — It stands below the bundle step it names, and `validate` refuses it
  anywhere else.
  Held by: `tests/unit/test_planning.py::test_check_refuses_a_run_placed_above_its_bundle`.
- **BRUN-5** — It has nothing to destroy and nothing to list, and it gives nothing. A
  destroy skips it with the reason.
  Held by: `tests/unit/test_step_bundle_run.py::test_nothing_to_destroy_and_nothing_to_list`,
  `tests/unit/test_step_bundle_run.py::test_the_core_skips_it_in_a_destroy_and_says_why`.

## STV — the `stevin` plugin

- **STV-1** — `uses: stevin` runs the `stevin` command and reads its plan file: lely
  imports nothing of stevin. Its options are `config`, stevin's project file, relative to
  the config and `stevin.yml` by default; `target`, stevin's target, which is `-t` when
  not given; `select`, passed as `--select`; and `executable`, how to run stevin. A
  `stevin` that is not installed is said with how to get it.
  Held by: `tests/unit/test_step_stevin.py::test_plans_through_stevins_cli`,
  `tests/unit/test_step_stevin.py::test_its_own_target_wins`,
  `tests/unit/test_step_stevin.py::test_a_missing_stevin_says_how_to_get_it`.
- **STV-2** — A plan holds one change per table, view or other object stevin has steps
  for, keyed by its full name, with one line per step: the step's title, the column it is
  about, and its risk class, and under it what stevin warns of. An object that does not
  exist yet is a create, one stevin drops is a delete, any other is an update. A table
  with a step of the class `rewrite` says `rewrite` in its own line.
  Held by: `tests/unit/test_step_stevin.py::test_a_first_plan_creates_each_table`,
  `tests/unit/test_step_stevin.py::test_a_rewrite_is_visible_as_a_rewrite`,
  `tests/unit/test_cli.py::test_a_stevin_plan_is_shown_with_its_risks_and_applied_from_the_file`.
- **STV-3** — stevin's risk classes map onto lely's: `meta`, `feature` and `rewrite` are
  not destructive, and `destructive` is. A step with a class lely does not know, or with
  none, makes its change destructive, and its line says that the class is not known.
  Held by: `tests/unit/test_step_stevin.py::test_a_dropped_column_is_a_destructive_update`,
  `tests/unit/test_step_stevin.py::test_a_risk_class_lely_doesnt_know_is_destructive`,
  `tests/unit/test_running.py::test_a_risk_class_lely_doesnt_know_needs_allow_destructive`.
- **STV-4** — Apply runs the plan that was approved, never a new one. stevin's plan file
  is the step's payload, whole, so it is in lely's plan file; `apply` writes the approved
  payload to a temporary file and hands that to `stevin apply`, also when the plan went
  through a file from one command to the next. The plan lely makes right before a step
  runs is not what stevin is handed.
  Held by: `tests/unit/test_step_stevin.py::test_apply_hands_stevin_the_plan_that_was_approved`,
  `tests/unit/test_running.py::test_the_stevin_step_applies_the_plan_file_that_was_approved`,
  `tests/unit/test_cli.py::test_a_stevin_plan_is_shown_with_its_risks_and_applied_from_the_file`.
- **STV-5** — Before stevin is run, the approved file is held to the plan made right
  before the step runs: it is of the format lely reads and for the step's target, it was
  made from the same specs, and its steps and the changes they carry out are the ones
  stevin would run now, in the same order and alike in everything but what follows a
  table's data: a size estimate, a restore point. A file that differs is refused and asks
  for a new plan, and the message repeats nothing the file says. So a plan of which
  stevin applied a part is not gone on with from the approved file: it takes a new plan.
  The fingerprint of the live tables is not compared: that is stevin's check (STV-6).
  Held by: `tests/unit/test_step_stevin.py::test_a_file_stevin_would_no_longer_run_the_same_is_refused`,
  `tests/unit/test_step_stevin.py::test_a_file_for_another_target_is_refused`,
  `tests/unit/test_running.py::test_a_stevin_plan_that_was_applied_in_part_is_not_resumed`.
- **STV-6** — A plan stevin refuses because it will never run ends the run as refused, in
  stevin's words and with the advice to plan again: the live tables moved since it was
  made, its file is not a plan that stevin reads, or it holds a step without SQL. The
  step knows such a refusal by the exit code of `stevin apply`, 3, and never by its
  words. Nothing is planned again in its place, and no step after it starts.
  Held by: `tests/unit/test_step_stevin.py::test_a_stale_plan_is_refused_in_stevins_words`,
  `tests/unit/test_step_stevin.py::test_a_refusal_is_known_by_its_exit_code_and_not_by_its_words`,
  `tests/unit/test_running.py::test_a_stale_stevin_plan_stops_the_run_and_nothing_after_it_starts`.
- **STV-7** — An exit of `stevin apply` that is not 0, 3 or 4 is the step's failure, quoted
  in stevin's words from both of its streams. What stevin applied before it stopped stays
  applied.
  Held by: `tests/unit/test_step_stevin.py::test_a_failing_apply_is_a_failure_in_stevins_words`.
- **STV-8** — `--allow-destructive` is passed to stevin only when the plan lely let
  through holds a destructive change, which it does only when `lely apply` was given
  `--allow-destructive` itself. Without it stevin is not asked to apply.
  Held by: `tests/unit/test_step_stevin.py::test_allow_destructive_goes_to_stevin_only_with_a_destructive_plan`,
  `tests/unit/test_running.py::test_a_destructive_stevin_step_needs_allow_destructive`.
- **STV-9** — A stevin step that was waiting when the plan was made has no approved file.
  It applies the plan it is shown with when the run reaches it.
  Held by: `tests/unit/test_step_stevin.py::test_a_step_that_was_waiting_applies_the_plan_it_was_shown_with`.
- **STV-10** — A destroy drops nothing. In a destroy plan and in a destroy the step is
  skipped with one line that says the tables stay, and stevin is not run. No option
  changes that.
  Held by: `tests/unit/test_step_stevin.py::test_it_plans_applies_and_lists_and_drops_nothing`,
  `tests/unit/test_running.py::test_a_destroy_leaves_stevins_tables_alone_and_says_so`,
  `tests/unit/test_cli.py::test_a_destroy_plan_says_in_one_line_that_stevins_tables_stay`.
- **STV-12** — Of stevin's plan file lely shows the names of tables, and each step's
  title, column, risk class and warnings, and nothing else: no owner, and no statement.
  What `stevin apply` writes is passed on to the step's log as it comes, under the step's
  name.
  Held by: `tests/unit/test_step_stevin.py::test_the_plan_names_no_owner`,
  `tests/unit/test_step_stevin.py::test_what_stevin_says_is_passed_on`.
- **STV-13** — The overview is every object stevin's specs describe for the target, with
  its kind and whether it exists, as `stevin list --json` answers and from nothing else:
  no plan is made for a status. A `list` that fails is said in stevin's words, and a
  stevin that has no `list` is said with the version that has it. The step gives no
  outputs.
  Held by: `tests/unit/test_step_stevin.py::test_the_overview_is_what_the_specs_describe`,
  `tests/unit/test_step_stevin.py::test_a_list_that_fails_or_cant_be_read_is_said`,
  `tests/unit/test_running.py::test_status_lists_what_stevins_specs_describe`.
- **STV-14** — The step needs stevin 0.4.0a2 or newer. It reads the version from the plan
  file stevin wrote, and a plan an older stevin wrote fails when the step is planned,
  with both versions and how to upgrade. A version it cannot read as one is let through.
  Held by: `tests/unit/test_step_stevin.py::test_a_plan_of_an_older_stevin_fails_with_both_versions`,
  `tests/unit/test_step_stevin.py::test_which_stevin_is_new_enough`.
- **STV-15** — A plan stevin refuses because it destroys something and stevin was not
  told to allow it, exit 4 of `stevin apply`, ends the run as refused, in stevin's words.
  It does not say to plan again: lely's plan did not show the change as destructive, and
  a new plan would read the same.
  Held by: `tests/unit/test_step_stevin.py::test_allow_destructive_goes_to_stevin_only_with_a_destructive_plan`.

## PROG — a program as a step

- **PROG-1** — `Program` is a base in `lely.step` for a program as a step. Its plan is one
  `run` that shows the command, destructive if the class says so. The command is a list,
  or a method that builds one from the options; an empty one is an error.
  Held by: `tests/unit/test_step_program.py::test_the_plan_is_one_run`,
  `tests/unit/test_step_program.py::test_destructive_is_declared_on_the_run`.
- **PROG-2** — Apply runs the program in the project's directory, never through a shell,
  with the environment lely was given, the class's `env`, `LELY_TARGET` and `LELY_STEP`. A
  program that exits non-zero fails the step. What it prints is logged under the step's
  name as it comes.
  Held by: `tests/unit/test_step_program.py::test_the_program_hears_the_step_and_the_target`,
  `tests/unit/test_step_program.py::test_a_failing_program_fails_the_step`.
- **PROG-3** — Its outputs, when the class declares any, are read from the JSON object on
  the last line the program printed. A last line that is not one, or that lacks a declared
  name, fails the step.
  Held by: `tests/unit/test_step_program.py::test_apply_runs_it_and_gives_what_it_printed`,
  `tests/unit/test_step_program.py::test_declared_outputs_need_json_on_the_last_line`.
- **PROG-4** — It has no destroy and nothing to list: a destroy skips it with the reason.
  A secret reaches the program through `env`, and is in no plan.
  Held by: `tests/unit/test_step_program.py::test_a_secret_reaches_the_program_through_its_environment`,
  `tests/unit/test_step_program.py::test_a_program_has_no_destroy_and_nothing_to_list`.
- **PROG-5** — There is no `command` plugin: a config that names it is told that no plugin
  of that name is installed.
  Held by: `tests/unit/test_registry.py::test_command_is_no_plugin_any_more`.

## SOLO — a step on its own

- **SOLO-1** — A step that inherits `lely.step.Step` and calls `Step.main()` is a command
  of its own, with no `lely.yml`. Inheriting changes nothing about the contract, and under
  lely the same file is `uses: ./path/file.py:Class`. Its commands go through lely's own
  planning, running, plan file and approval, with a config of that one step made from the
  flags; its name is the class's in lower case, and its root the working directory.
  Held by: `tests/unit/test_solo.py::test_plan_shows_the_change_and_changes_nothing`.
- **SOLO-2** — Its commands are `plan`, `apply`, `destroy`, `status` and `check`. Each
  takes `-t`, which `apply` may leave out when it is given a plan file, `--profile`, and
  the step's own flags. `plan` takes `-o`, and `--destroy` to plan a teardown, which
  `destroy --plan-file` runs; `apply` and `destroy` take `--plan-file` and `--yes`;
  `apply` takes `--allow-destructive`; all but `check` take `-f rich|json|md`. Consent
  is asked as `lely` asks it.
  Held by: `tests/unit/test_solo.py::test_apply_with_a_target_plans_asks_and_applies`,
  `tests/unit/test_solo.py::test_without_a_terminal_apply_needs_yes`,
  `tests/unit/test_solo.py::test_a_destroy_can_be_planned_saved_and_run`.
- **SOLO-3** — Each field of `Options` is a flag, `--<name>` with dashes for underscores,
  with the field's type and the `#:` comment above it as its help. A flag carries text, a
  whole or a decimal number, a yes or no as a word, a `Secret`, one of a `Literal`'s
  values, a list (the flag more than once), a mapping of text, numbers, yes or no or
  secrets (`--<name> key=value`, more than once, the value read as the mapping declares
  it) and `T | None`. An option of another type is refused when the step starts, and a
  value that does not parse is refused by the flag's name. A flag that is not given is
  left out, so the option's own default applies.
  Held by: `tests/unit/test_solo.py::test_the_options_are_the_flags_with_their_help`,
  `tests/unit/test_solo.py::test_a_missing_required_option_is_refused_by_name`,
  `tests/unit/test_solo.py::test_a_mapping_of_numbers_arrives_as_numbers`.
- **SOLO-4** — A flag whose value holds a `${…}` is refused before anything runs, with what
  to do: run the step under lely, or pass the value. `$${` is none, as in a config file
  (REF-3): it reaches the step as a literal `${`.
  Held by: `tests/unit/test_solo.py::test_a_reference_is_refused_with_what_to_do`,
  `tests/unit/test_solo.py::test_a_literal_dollar_brace_is_written_as_in_a_config`.
- **SOLO-5** — A plan a step writes is a one-step lely plan: `lely apply plan.json` takes
  it, given a config that names the step the same way, and the same checks are made before
  anything runs. A step refuses a plan file that holds any other step.
  Held by: `tests/unit/test_solo.py::test_plan_writes_a_one_step_lely_plan`,
  `tests/unit/test_solo.py::test_lely_itself_runs_the_steps_plan_file`.
- **SOLO-7** — `check` holds the step to the rules, on a target: `plan` and `overview`
  behind a Databricks CLI that refuses anything but a read, the plan through a plan file
  and back, and outputs as declared. `--live` also applies and destroys on the target, or
  applies and plans again for a step with no destroy. Before it runs anything it says
  which of the two it is about to do, on which target, on which workspace and as whom.
  Without `--live` it says what `--live` would do, and speaks of no destroy the step
  does not have. A check that fails ends with 1.
  Held by: `tests/unit/test_solo.py::test_check_holds_the_step_to_the_rules`,
  `tests/unit/test_solo.py::test_check_live_applies_and_destroys`,
  `tests/unit/test_solo.py::test_check_live_says_what_it_will_do_before_it_does`.
- **SOLO-8** — On its own, `plan` prints the outputs the step knows and names the ones
  known later, each with when, and `apply` prints what the step returned, or what it
  knows when it had nothing to do. They stand under `Gives:`, after the plan or the
  result: on stdout, and on stderr with `-f json` or `-f md`, where stdout holds that
  and nothing else. A `Secret` is shown as `***`, and so is an output that holds what a
  `Secret` option was given.
  Held by: `tests/unit/test_solo.py::test_plan_prints_what_the_step_knows_and_names_what_comes_later`,
  `tests/unit/test_solo.py::test_apply_prints_what_the_step_returned`,
  `tests/unit/test_solo.py::test_no_secret_is_printed_with_what_the_step_gives`.

## PLAN — the plan and its file

- **PLAN-1** — `lely plan -t <target>` plans every step in the order written and changes
  nothing. `-o` writes the plan to a file, and `--destroy` plans a teardown.
  Held by: `tests/unit/test_cli.py::test_plan_shows_the_plan_and_names_the_workspace`,
  `tests/unit/test_cli.py::test_plan_writes_a_file_and_show_renders_it`.
- **PLAN-2** — A plan file says what it is, and holds what was shown. At the top: its
  format, lely's version, whether it is a plan to apply or to destroy, the target, the
  workspace's host and the identity it was planned as, and the git tree with the project's
  folder and whether anything was uncommitted. Then every step in order: its name and
  plugin; ready, waiting and for what, or skipped and why; a hash of what it was made
  from; what it takes and from where, with the value where it was known; its changes, each
  with its key, its action, whether it is destructive and its lines; the outputs it keeps;
  the plugin's payload; and the plugin's view.
  Held by: `tests/unit/test_planfile.py::test_a_plan_survives_the_round_trip`,
  `tests/unit/test_planfile.py::test_the_file_says_what_it_is_and_holds_what_was_shown`.
- **PLAN-3** — A plan file in another format is refused with a message that names both
  versions and says to plan again. A plan file is read strictly: a key lely does not
  write, a flag that is not true or false, two steps of one name, an empty target, a tree
  without its project, a state that disagrees with the rest of the step, or a step that is
  skipped or waits for an output and holds changes is a file lely did not write. Handed to
  `apply` or `destroy`, a file that is there and is no plan lely reads is a refusal.
  Held by: `tests/unit/test_cli.py::test_a_plan_file_this_lely_doesnt_read_is_refused`,
  `tests/unit/test_cli.py::test_a_file_lely_cant_read_is_a_refusal_when_it_would_be_run`,
  `tests/unit/test_planfile.py::test_another_format_is_refused_and_says_to_plan_again`,
  `tests/unit/test_planfile.py::test_a_plan_file_is_read_strictly`.
- **PLAN-4** — A plan file is held to the project. It is refused when the project's steps,
  or any step's plugin, targets or options, differ from what it was planned with, and
  when a value a step took that was known at plan is another value now. What is compared
  is the config as lely reads it, not the file's text: each option as its plugin is
  handed it, with a reference as it was written, so a value from the environment counts
  by name. `1.10` edited to `1.1` is a change for an option that wants text, and none for
  one that wants a number. For a value a step took, the same value means the same kind
  of value: `1` is not `true`, `14` is not `14.0` and not `"14"`. A secret is never
  compared, and stays one: that holds for a secret written out in an option too
  (SEC-4). A value that is a secret on one side and not on the other is refused, and
  neither is said. Where a step differs and the plan was made by another
  version of lely, the refusal says so and names both versions: that lely may have
  counted the same options another way.
  Held by: `tests/unit/test_approval.py::test_the_same_value_means_the_same_as_it_would_be_written`,
  `tests/unit/test_cli.py::test_a_file_is_refused_when_a_steps_options_changed`,
  `tests/unit/test_cli.py::test_a_plan_for_one_project_isnt_run_on_another_in_the_same_repository`,
  `tests/unit/test_options.py::test_what_a_step_is_made_from_is_what_its_plugin_is_handed`,
  `tests/unit/test_approval.py::test_a_plan_another_lely_made_says_so_where_a_hash_differs`,
  `tests/unit/test_running.py::test_an_input_that_changed_since_the_plan_stops_the_run`,
  `tests/unit/test_running.py::test_a_destroy_is_held_to_the_inputs_the_plan_showed`.
- **PLAN-5** — Every plan, every question lely asks and every plan file names the
  workspace and the identity. A plan file made against one workspace is refused on
  another, compared by host. The identity may differ, and a question then says who
  planned.
  Held by: `tests/unit/test_cli.py::test_plan_shows_the_plan_and_names_the_workspace`,
  `tests/unit/test_cli.py::test_at_a_terminal_apply_shows_the_plan_and_asks`,
  `tests/unit/test_cli.py::test_a_file_made_against_one_workspace_is_refused_on_another`,
  `tests/unit/test_cli.py::test_the_question_names_who_runs_not_who_planned`,
  `tests/unit/test_cli.py::test_a_question_doesnt_obey_what_a_plan_file_says`,
  `tests/unit/test_cli.py::test_who_is_running_is_asked_of_the_sdk_with_the_profile`.
- **PLAN-6** — A plan file is for a clean checkout of the tree it was made on. It records
  the tree of `HEAD` for the whole repository, without the plan file itself and without
  the files a sparse checkout leaves out; which project of the repository it is for; and
  whether anything differed from `HEAD`. `apply` and `destroy` refuse the file on another
  tree, for another project, and on a checkout that differs from `HEAD`; a plan made on
  such a checkout says so and is not run from a file. Files git does not track are not
  seen. Outside a repository nothing is recorded, before its first commit no tree is, and
  the plan says so.
  Held by: `tests/unit/test_cli.py::test_a_file_is_refused_on_another_git_tree`,
  `tests/unit/test_cli.py::test_outside_git_the_plan_says_it_couldnt_be_recorded`,
  `tests/unit/test_cli.py::test_a_destroy_plan_committed_for_review_doesnt_refuse_itself`,
  `tests/unit/test_cli.py::test_a_reviewed_file_covers_a_bundle_outside_the_configs_folder`,
  `tests/unit/test_cli.py::test_a_plan_for_one_project_isnt_run_on_another_in_the_same_repository`,
  `tests/unit/test_cli.py::test_a_plan_file_is_for_a_clean_checkout`,
  `tests/unit/test_cli.py::test_git_refusing_fails_a_plan_and_doesnt_stop_an_unsaved_run`.
- **PLAN-7** — git failing is not "no repository": only git's own "not a git repository",
  or git not being there at all, where nothing looks like a repository, means that. Any
  other failure fails `lely plan` and a run from a file. A run that is planned and applied
  in one go is held to nothing, and goes on. lely writes nothing to the repository to find
  any of this out, and fetches nothing.
  Held by: `tests/unit/test_source.py::test_nothing_of_the_users_is_written`,
  `tests/unit/test_source.py::test_git_refusing_is_not_the_same_as_no_repository`,
  `tests/unit/test_source.py::test_a_git_folder_git_cant_use_is_not_no_repository`.
- **PLAN-9** — `lely show` shows a saved plan from the file alone: it reaches no
  workspace, reads no config and loads no plugin.
  Held by: `tests/unit/test_cli.py::test_plan_writes_a_file_and_show_renders_it`.
- **PLAN-10** — What a plugin hands back is made plain JSON when it is planned, so a plan
  is the same whether or not it went through a file. A payload that holds a secret, a key
  that is not text or a value JSON has no word for is refused when the step is planned.
  Held by: `tests/unit/test_planfile.py::test_a_payload_with_a_secret_is_refused`,
  `tests/unit/test_planfile.py::test_what_isnt_json_is_refused_with_its_reason`,
  `tests/unit/test_planfile.py::test_a_plan_is_made_plain_so_it_reads_back_equal`.
- **PLAN-12** — A mapping in a step's options counts in the order written, which is the
  order its plugin is handed: a plan file is refused when the entries of a mapping were
  moved since. The order of the options themselves does not count: a plugin is handed
  those by name.
  Held by: `tests/unit/test_options.py::test_a_mapping_counts_in_the_order_written`.
- **PLAN-13** — A plan is not held to what the bundle resolves from outside lely. A
  reviewed plan is held to the steps as written, the values each step took from the
  steps above, the workspace and the git tree (PLAN-4, PLAN-5, PLAN-6), and each step
  runs only the changes the plan showed (APL-3). A bundle variable set as
  `BUNDLE_VAR_<name>` in the environment of the apply, or one whose `lookup` answers
  something else than at plan, is none of those: lely keeps no fingerprint of the
  variables a bundle resolved, and where the Databricks CLI's plan reads the same with
  the other value, the apply goes through.
  Not tested: it is a limit, not a behaviour, and the stand-in for the Databricks CLI
  resolves no variable from the environment or by a lookup. What the CLI's plan shows
  when only such a value differs, and which of two places a variable is set in wins,
  were not tried on a workspace.

## WAIT — a step that cannot be planned yet

- **WAIT-1** — Every step in a plan is ready, waiting or skipped. A ready step shows its
  changes. A waiting step takes something that does not exist yet, and then the plan names
  what it waits for and shows no changes; or its plugin says that part of its plan cannot
  be made yet. A skipped step says why.
  Held by: `tests/unit/test_planning.py::test_a_step_that_takes_what_doesnt_exist_yet_is_waiting`.
- **WAIT-2** — One rule wherever the step stands, above the bundle or below: a step waits
  when it takes something a step above does not have yet. An output known once it exists
  makes it wait on the first deploy only; one known after every run makes it wait on every
  deploy, and the plan and its file mark that.
  Held by: `tests/unit/test_planning.py::test_a_bundle_fed_by_a_run_waits_and_so_does_what_is_below_it`,
  `tests/unit/test_running.py::test_a_step_that_takes_an_output_of_a_run_gets_it_at_apply`.
- **WAIT-3** — `lely apply plan.json` stops at a step that was waiting when the plan was
  made, as a refusal, and says to plan again: the next plan shows the step ready. For a
  step that waits on every deploy it says that a file can never take it further. A saved
  plan with a waiting step says, where it is shown, that applied from a file it stops
  before the first of them.
  Held by: `tests/unit/test_cli.py::test_plan_shows_the_plan_and_names_the_workspace`,
  `tests/unit/test_cli.py::test_a_reviewed_file_stops_at_a_waiting_step_and_takes_a_second_round`,
  `tests/unit/test_render_rich.py::test_a_step_that_waits_on_every_deploy_says_a_file_never_gets_past_it`,
  `tests/unit/test_running.py::test_a_reviewed_file_stops_at_a_waiting_step`,
  `tests/unit/test_running.py::test_the_next_plan_shows_the_step_ready_and_one_round_finishes`.
- **WAIT-4** — `lely apply -t <target> --yes` plans a waiting step when it gets there,
  shows it and runs it.
  Held by: `tests/unit/test_cli.py::test_yes_without_a_file_runs_a_waiting_step_when_it_gets_there`,
  `tests/unit/test_running.py::test_without_a_file_the_step_is_planned_when_it_gets_there`.
- **WAIT-5** — At a terminal, `lely apply -t <target>` shows the waiting step's plan when
  it gets there and asks once more. An answer that is not yes stops the run there.
  Held by: `tests/unit/test_cli.py::test_at_a_terminal_lely_asks_again_at_a_waiting_step`,
  `tests/unit/test_running.py::test_without_a_file_the_step_is_planned_when_it_gets_there`,
  `tests/unit/test_running.py::test_saying_no_at_a_waiting_step_stops_there`.
- **WAIT-6** — Unless `--from` names a step below it, apply never goes past a waiting step
  to the ones below, and a destructive change in a step that was waiting needs
  `--allow-destructive` like any other.
  Held by: `tests/unit/test_cli.py::test_at_a_terminal_lely_asks_again_at_a_waiting_step`,
  `tests/unit/test_running.py::test_a_reviewed_file_stops_at_a_waiting_step`,
  `tests/unit/test_running.py::test_a_waiting_step_doesnt_get_past_the_other_rules`.

## APL — apply

- **APL-1** — `lely apply plan.json` runs a plan that was saved; `lely apply -t <target>`
  plans, shows the plan, asks and runs. `apply` runs plans to apply: handed a plan to
  destroy it refuses, and names the command that takes one. A plan file for another target
  than `-t` names is refused.
  Held by: `tests/unit/test_cli.py::test_at_a_terminal_apply_shows_the_plan_and_asks`,
  `tests/unit/test_cli.py::test_a_file_for_another_target_than_the_command_says_is_refused`,
  `tests/unit/test_running.py::test_apply_runs_the_steps_in_the_order_written`,
  `tests/unit/test_running.py::test_apply_refuses_a_plan_to_destroy`.
- **APL-2** — Steps are applied in the order written. A step whose `targets` leave the
  target out is skipped, and the result says so.
  Held by: `tests/unit/test_running.py::test_apply_runs_the_steps_in_the_order_written`.
- **APL-3** — Each step is planned again right before it runs, and runs only if every
  change in the fresh plan is one the approved plan showed: the same key, the same action,
  the same summary and lines, the same destructive mark. Fewer changes is fine. Anything
  new, or anything that reads differently, stops the run as a refusal and asks for a new
  plan. A step that is not in the approved plan, or that it showed as skipped, does not
  run.
  Held by: `tests/unit/test_running.py::test_every_step_is_planned_again_right_before_it_runs`,
  `tests/unit/test_running.py::test_fewer_changes_than_approved_is_fine`,
  `tests/unit/test_running.py::test_a_change_that_wasnt_shown_stops_the_run`.
- **APL-4** — A destructive change is refused without `--allow-destructive`. Where the
  plan already shows one, the refusal comes before anything is asked or run.
  Held by: `tests/unit/test_cli.py::test_a_destructive_change_is_refused_without_the_flag`,
  `tests/unit/test_running.py::test_a_destructive_change_is_refused_before_anything_runs`.
- **APL-5** — A plan with nothing to do runs nothing, asks nothing, says so and ends as
  done.
  Held by: `tests/unit/test_running.py::test_a_plan_with_nothing_to_do_runs_nothing_and_ends_as_done`.
- **APL-6** — When an apply is done it shows what each step did and, from every plugin
  that can list, what now exists.
  Held by: `tests/unit/test_cli.py::test_yes_in_the_command_runs_without_asking`,
  `tests/unit/test_render_rich.py::test_an_apply_and_what_exists_after_it`,
  `tests/unit/test_running.py::test_after_an_apply_every_plugin_that_can_says_what_exists`.
- **APL-7** — Right after an apply each line of an overview says what this run did to it:
  created, changed, replaced or unchanged, and what it deleted is listed after what is
  left. That comes from the plan that was just applied. Nothing is remembered, so a later
  run shows as unchanged what an earlier one created.
  Held by: `tests/unit/test_cli.py::test_a_reviewed_file_stops_at_a_waiting_step_and_takes_a_second_round`,
  `tests/unit/test_render_rich.py::test_an_apply_and_what_exists_after_it`,
  `tests/unit/test_running.py::test_after_an_apply_every_plugin_that_can_says_what_exists`.
- **APL-8** — The first step that fails or is refused stops the run, an apply and a
  destroy alike: nothing after it starts. The result names what ran, what failed or was
  refused, and what never started. A step with nothing to do did not run.
  Held by: `tests/unit/test_cli.py::test_a_failed_step_ends_with_1_and_three_lists`,
  `tests/unit/test_cli.py::test_the_result_as_json`,
  `tests/unit/test_planfile.py::test_a_result_has_its_three_lists`,
  `tests/unit/test_render_rich.py::test_a_run_that_failed`,
  `tests/unit/test_running.py::test_the_first_failing_step_stops_the_run`,
  `tests/unit/test_running.py::test_a_failing_destroy_stops_and_leaves_the_rest`.
- **APL-9** — After a failure, running the same command again finishes the job: a step
  that did its work plans as nothing to do. After a refusal the same file is refused
  again: it takes a new plan. A `stevin` step that applied part of its plan is the one
  failure that takes a new plan (STV-5).
  Held by: `tests/unit/test_cli.py::test_a_reviewed_file_stops_at_a_waiting_step_and_takes_a_second_round`,
  `tests/unit/test_running.py::test_running_it_again_finishes_the_job`.
- **APL-10** — `--from <step>` starts at a named step; in a destroy it names where to
  start going up the list. The steps it passes over are still planned, for what they give
  the others, and held to the inputs the plan showed; they are not applied or destroyed. A
  `--from` that names no step of the run is refused before anything is planned.
  Held by: `tests/unit/test_cli.py::test_from_resumes_at_a_step`,
  `tests/unit/test_cli.py::test_a_from_that_names_no_step_is_refused_before_anything_is_planned`,
  `tests/unit/test_running.py::test_from_starts_at_a_named_step`,
  `tests/unit/test_running.py::test_from_names_where_a_destroy_starts_going_up`,
  `tests/unit/test_running.py::test_from_doesnt_pass_over_the_check_on_what_a_step_takes`.
- **APL-11** — There is no rollback. A run that stops leaves what was done, done, and its
  result says "Nothing was rolled back."
  Held by: `tests/unit/test_cli.py::test_a_failed_step_ends_with_1_and_three_lists`,
  `tests/unit/test_render_rich.py::test_a_run_that_failed`,
  `tests/unit/test_running.py::test_the_first_failing_step_stops_the_run`.

## DST — destroy

- **DST-1** — `lely destroy -t <target>` plans the destroy, shows it, asks and runs. The
  plan lists, per step, what would be removed, and every change in it is destructive
  whatever the plugin marked.
  Held by: `tests/unit/test_planning.py::test_a_destroy_plan_says_per_step_what_would_be_removed`,
  `tests/unit/test_running.py::test_destroy_goes_from_the_bottom_up`.
- **DST-2** — Steps are destroyed in the reverse of the order written, and a destroy plan
  is shown in the order it runs.
  Held by: `tests/unit/test_render_rich.py::test_a_destroy_plan_runs_from_the_bottom_up`,
  `tests/unit/test_running.py::test_destroy_goes_from_the_bottom_up`.
- **DST-3** — A step with nothing to destroy is listed in the destroy plan as skipped,
  with the reason, and the rest is destroyed. So is a step that needs something that is
  not there.
  Held by: `tests/unit/test_running.py::test_a_step_with_nothing_to_destroy_is_skipped_and_says_why`.
- **DST-4** — A destroy can be saved and reviewed first: `lely plan -t <target> --destroy
  -o destroy.json` writes it, `lely show` shows it, and `lely destroy destroy.json -t
  <target>` runs it. It is one file format for both. The plan file itself is left out of
  the tree it records, so a plan committed for review does not refuse itself.
  Held by: `tests/unit/test_cli.py::test_a_destroy_can_be_saved_reviewed_and_run_as_a_file`,
  `tests/unit/test_cli.py::test_a_destroy_plan_committed_for_review_doesnt_refuse_itself`.
- **DST-5** — A destroy is checked as an apply is: each step's destroy is planned again
  before it runs, and anything that was not in the approved plan stops the run. Every
  value a step took when the destroy was planned is compared before anything is removed. A
  step the approved plan showed as skipped showed nothing, so whatever it would remove now
  was not approved.
  Held by: `tests/unit/test_running.py::test_a_destroy_is_checked_against_what_was_approved`,
  `tests/unit/test_running.py::test_a_destroy_is_held_to_the_inputs_the_plan_showed`.
- **DST-6** — Destroying a target that has nothing deployed does nothing, asks nothing,
  says so and ends as done.
  Held by: `tests/unit/test_cli.py::test_destroying_what_isnt_deployed_says_so_and_ends_as_done`,
  `tests/unit/test_running.py::test_destroying_what_isnt_deployed_does_nothing_and_ends_as_done`.

## ASK — consent

- **ASK-1** — Nothing that changes a workspace runs unasked: `apply` and `destroy` ask, or
  were given `--yes`. With no terminal and no `--yes` they refuse, and the message names
  the flag. A plan that holds nothing is not asked about.
  Held by: `tests/unit/test_cli.py::test_with_no_terminal_and_no_yes_apply_refuses`,
  `tests/unit/test_cli.py::test_yes_in_the_command_runs_without_asking`,
  `tests/unit/test_cli.py::test_without_a_terminal_consent_to_destroy_is_given_in_the_command`,
  `tests/unit/test_cli.py::test_a_destroy_file_edited_to_hide_what_it_removes_is_refused`.
- **ASK-2** — To destroy at a terminal the answer is the target's name, typed: not `y`,
  and not an empty line.
  Held by: `tests/unit/test_cli.py::test_to_destroy_at_a_terminal_the_answer_is_the_targets_name`,
  `tests/unit/test_cli.py::test_pressing_enter_doesnt_destroy`.
- **ASK-3** — `lely destroy` always takes `-t`, with or without a file, and a file made
  for another target is refused. Without a terminal, `--yes` in the command is the
  consent.
  Held by: `tests/unit/test_cli.py::test_destroy_always_needs_a_target`,
  `tests/unit/test_cli.py::test_without_a_terminal_consent_to_destroy_is_given_in_the_command`.
- **ASK-4** — A saved plan is asked about too: applying one at a terminal shows what is in
  it and asks, and `--yes` answers. A plan to destroy is run only by `lely destroy`, which
  asks for the target's name, and `lely destroy` runs no plan to apply.
  `--allow-destructive` is no option of `destroy`: everything in one is destructive.
  Held by: `tests/unit/test_cli.py::test_a_file_is_asked_about_too`,
  `tests/unit/test_cli.py::test_apply_cant_be_handed_a_destroy`,
  `tests/unit/test_cli.py::test_a_destroy_file_is_asked_about_with_the_targets_name`,
  `tests/unit/test_cli.py::test_a_destroy_file_edited_to_hide_what_it_removes_is_refused`,
  `tests/unit/test_running.py::test_apply_refuses_a_plan_to_destroy`.

## CLI — the command line

- **CLI-1** — Exit codes: 0 done, "nothing to do" included; 1 something failed; 2 lely
  refused, before or between steps, and running the same thing again will not help: a
  stale plan, a waiting step in a saved plan, a change that was not approved, a
  destructive change that was not allowed, no consent, a plan file that is no plan it
  reads. `plan`, `show`, `status`, `validate` and `doctor` change nothing, so what goes
  wrong in them ends with 1. A command line lely cannot make sense of ends with 2 whatever
  the command, before the config is read or a workspace reached.
  Held by: `tests/unit/test_cli.py::test_a_reviewed_file_stops_at_a_waiting_step_and_takes_a_second_round`,
  `tests/unit/test_cli.py::test_a_failed_step_ends_with_1_and_three_lists`,
  `tests/unit/test_cli.py::test_a_file_lely_cant_read_is_a_refusal_when_it_would_be_run`.
- **CLI-2** — `-t <target>` is always given to `plan`, `apply`, `destroy` and `status`:
  there is no default target. With a plan file, `apply` takes the file's target. An empty
  `-t` is refused, and so is a target no step runs for.
  Held by: `tests/unit/test_cli.py::test_plan_always_needs_a_target`,
  `tests/unit/test_cli.py::test_apply_without_a_file_needs_a_target`,
  `tests/unit/test_cli.py::test_destroy_always_needs_a_target`,
  `tests/unit/test_cli.py::test_status_shows_what_is_deployed_and_whose_view_it_is`,
  `tests/unit/test_cli.py::test_an_empty_target_is_no_target`,
  `tests/unit/test_cli.py::test_a_target_no_step_runs_for_isnt_nothing_to_do`,
  `tests/unit/test_running.py::test_a_target_no_step_runs_for_is_refused`.
- **CLI-3** — `lely status -t <target>` changes nothing and shows, for every step, what
  exists because of it. A step whose plugin has nothing to list says so, one skipped for
  the target is shown as skipped, and one whose input is not there says that it cannot be
  listed.
  Held by: `tests/unit/test_cli.py::test_status_shows_what_is_deployed_and_whose_view_it_is`,
  `tests/unit/test_running.py::test_status_shows_every_step_and_changes_nothing`.
- **CLI-4** — With `-f json` or `-f md`, stdout holds that and nothing else, on `plan`,
  `show`, `apply`, `destroy` and `status`; `plan -f json -o` prints nothing, because the
  file holds the JSON. With `-f json` a run that ends before its first step still prints a
  result; a command line typer rejects prints its usage on stderr and no JSON.
  Held by: `tests/unit/test_cli.py::test_a_refusal_before_the_first_step_is_said_as_json_too`,
  `tests/unit/test_cli.py::test_with_json_stdout_holds_json_and_nothing_else`.
- **CLI-5** — `lely doctor` changes nothing and reports: the Databricks CLI's version, and
  whether it is older than the first with the direct engine; whether git is there and can
  say what a plan is made on; which workspace is reached and as whom; and whether each
  program a step runs is there. It speaks of the Databricks CLI as needed only where a
  step runs it, or where there is no project. A tool a step needs that is missing, git
  failing in a repository and a plugin that fails are failed checks, and it then ends with
  1; a plugin that fails is one line, and the rest is still checked.
  Held by: `tests/unit/test_cli.py::test_doctor_reports_the_tools_the_workspace_and_the_identity`,
  `tests/unit/test_cli.py::test_doctor_fails_when_a_tool_is_missing`,
  `tests/unit/test_cli.py::test_doctor_compares_the_clis_version_with_the_one_bundles_need`,
  `tests/unit/test_cli.py::test_doctor_says_a_plugin_that_fails_in_one_line_and_goes_on`.
- **CLI-7** — A file lely writes with `-o` is written beside its place and moved there,
  where there is room beside it: it is then whole or as it was, and a link standing where
  it goes is replaced, not followed. What is no file, a device or a pipe, is written to as
  it is. A file marked read-only is left alone. A file made again is readable by whoever
  could read the old one, and by nobody more.
  Held by: `tests/unit/test_cli.py::test_a_file_is_whole_or_as_it_was`,
  `tests/unit/test_cli.py::test_a_file_made_again_is_readable_by_whoever_could_read_it_before`,
  `tests/unit/test_cli.py::test_what_is_no_file_is_written_to_as_it_is`.
- **CLI-8** — `lely doctor` says that planning runs the project's own code and that a pull
  request's plan should be given credentials that can read and nothing more. Of the
  credentials at hand it says one thing: whether the identity is a workspace admin. For
  an admin and for anyone else it says that lely cannot tell what the credentials may
  change. It never says that credentials are read-only, and never what an admin can
  change.
  Held by: `tests/unit/test_cli.py::test_doctor_reports_the_tools_the_workspace_and_the_identity`,
  `tests/unit/test_cli.py::test_a_member_of_admins_is_a_workspace_admin`.

## SEC — secrets, and what a plan says

- **SEC-1** — A value a plugin marks as a `Secret`, and any value from the environment, is
  never printed and never written: not in a terminal, a plan file, a page, a comment or a
  summary. It is shown as `***` and written to a plan file as a marker with no value. It
  is not kept for apply: the step that gives it is planned again, and gives it again.
  Held by: `tests/unit/test_planfile.py::test_a_secret_output_is_never_written`,
  `tests/unit/test_planning.py::test_a_value_from_the_environment_cant_reach_an_argument`.
- **SEC-2** — A plugin's payload is in the plan file, and so in `-f json`, and is shown
  nowhere else: not in a terminal, not in Markdown and not on the page. Those show a
  step's changes, what it takes and what it gives, and on the page the plugin's view.
  Not tested: no test looks for a payload in what the three renderers write; none of them
  reads `StepPlan.payload`.
- **SEC-3** — What a plan says is shown, never obeyed. In a terminal, control characters,
  invisible characters that reorder text and half a character, in anything a plan file, a
  plugin or a program said, are made visible before they are printed: in a plan, a result,
  a question and a line of a program's output.
  Held by: `tests/unit/test_cli.py::test_escape_sequences_in_a_plan_file_dont_reach_the_terminal`,
  `tests/unit/test_render_rich.py::test_what_a_plan_says_is_shown_never_obeyed`.
- **SEC-4** — What a plan file keeps of a step's options does not depend on the text of
  a secret. An option that takes a `Secret`, alone or in a list or a mapping, counts in
  what a step is made from by where it comes from, each reference as it was written, and
  never by its text: one written out in the config or given as a flag counts as given,
  and no more, and text written beside a reference does not count. So no guess at a
  secret can be tested against that hash. The price: a plan file is not refused when a
  secret that was written out, or the text around a reference in such an option, has
  changed since, as it is not when a value from the environment has.
  Held by: `tests/unit/test_options.py::test_a_secret_written_out_is_not_in_what_a_step_is_made_from`,
  `tests/unit/test_planning.py::test_a_secret_written_out_leaves_nothing_of_itself_in_a_plan_file`.
- **SEC-5** — An output that holds what its step was given as a secret is a secret, also
  when the plugin gave it as plain text: whole, inside a longer text, or inside a list or
  a mapping. It is made a `Secret` when the step is planned and when it is applied, so
  it is `***` wherever it is shown, a marker in the plan file and in `-f json`, and for a
  step below a value only a `Secret` option takes. What a step was given as a secret is
  every `Secret` its options hold: written out, from the environment, from a step above,
  or of a step it names. A list or a mapping that holds one becomes one secret, with no
  fields a step below could take. lely sees a secret as the option holds it, whole: not
  a part of it, and not another spelling of it. It looks in a step's outputs only: not
  in a change's lines, a note, a payload or a view. Which outputs of a step are secrets
  can be read in a plan file, and follows from the secret.
  Held by: `tests/unit/test_planning.py::test_an_output_that_holds_a_secret_option_is_a_secret`,
  `tests/unit/test_running.py::test_an_output_a_run_gives_that_holds_a_secret_option_is_a_secret`,
  `tests/unit/test_solo.py::test_no_secret_is_printed_with_what_the_step_gives`.

## PAGE — a plan as a page

- **PAGE-1** — `lely ui <file>` makes one HTML page of a plan: every step in the order it
  runs, each with what it takes, what it would create, change, remove or run, and what it
  gives, and which steps are waiting and for what. It writes the page beside the file, or
  where `-o` says, `-` for stdout, and opens it in a browser when run at a terminal,
  unless told otherwise.
  Held by: `tests/unit/test_cli.py::test_a_plan_file_is_made_into_a_page_beside_it`,
  `tests/unit/test_render_html.py::test_a_plan_with_a_destructive_change`.
- **PAGE-2** — Each step has a section of its own, and a plugin can supply a view of its
  plan for it: `StepPlan.view`, HTML as text, made when the step is planned and kept in
  the plan file. The page always shows lely's own list of the step's changes; the view
  stands under it, never in its place.
  Held by: `tests/unit/test_planfile.py::test_a_steps_view_is_kept_with_its_plan`,
  `tests/unit/test_render_html.py::test_a_plugins_view_is_shown_under_the_changes_never_in_their_place`.
- **PAGE-3** — Destructive changes cannot be missed: the page of a plan to apply opens
  with how many there are and names them, and each one carries the word, not only a
  colour.
  Held by: `tests/unit/test_render_html.py::test_a_plan_with_a_destructive_change`.
- **PAGE-4** — The page is made from the file alone. Making it needs no workspace, no
  credentials, no project and no plugin, and it is the same on any machine.
  Held by: `tests/unit/test_cli.py::test_a_plan_file_is_made_into_a_page_beside_it`,
  `tests/unit/test_cli.py::test_making_a_page_runs_nothing_of_the_project`.
- **PAGE-5** — A destroy plan opens the same way, in the order it runs.
  Held by: `tests/unit/test_render_html.py::test_a_destroy_plan_runs_from_the_bottom_up`.
- **PAGE-6** — `apply -o` and `destroy -o` write a record of the run, and `lely ui` makes
  the page of it: what each step did and, for an apply that is done, what exists now. An
  address becomes a link only when it is an https address on the run's own workspace. A
  run that ended before its first step leaves a record too, and a record that cannot be
  written is said and changes nothing about how the run ended. lely reads a record back
  only to show it, as strictly as a plan and as one story: its outcome, each step's own
  and the lists of names agree, or it is refused.
  Held by: `tests/unit/test_cli.py::test_a_run_can_write_its_record_and_the_record_becomes_a_page`,
  `tests/unit/test_planfile.py::test_a_record_tells_one_story`,
  `tests/unit/test_render_html.py::test_a_run_and_what_exists_after_it`,
  `tests/unit/test_render_html.py::test_open_leads_into_the_runs_own_workspace_and_nowhere_else`.
- **PAGE-7** — Nothing secret is on the page, and no plugin's payload. With `--github`, a
  run's record does not hold the run's token.
  Held by: `tests/unit/test_cli.py::test_a_runs_record_never_holds_the_runs_token`.
- **PAGE-8** — The page only shows. It is one file with its style sheet inline, no script
  and nothing fetched, and its policy lets a browser load nothing else. It has no button
  that applies or destroys, and making it starts no server.
  Held by: `tests/unit/test_cli.py::test_making_a_page_runs_nothing_of_the_project`,
  `tests/unit/test_render_html.py::test_the_page_is_one_file_that_fetches_and_runs_nothing`.
- **PAGE-9** — Nothing a plan or a run says is markup on the page: every word is escaped.
  A plugin's view is not trusted either: it is taken apart and written again from a short
  list of elements, with every word escaped. No script, style, link or image comes
  through, and no attribute but a class from lely's own list and a cell's span. No element
  the frame stands in is kept (`div`, `details`, `summary`), and nothing in a view can end
  the frame it stands in. A view is at most a million characters, where a plugin hands it
  over and where a file is read.
  Held by: `tests/unit/test_render_html.py::test_nothing_a_plan_says_is_markup`,
  `tests/unit/test_render_html.py::test_a_view_is_written_again_from_what_lely_keeps`.
- **PAGE-11** — `lely ui` never writes over the file it reads, however that file is
  spelled, and writes over a file at the default name only when it is a page lely made. A
  file that is no plan and no record is said.
  Held by: `tests/unit/test_cli.py::test_a_page_is_never_written_through_a_link_or_over_someone_elses_file`,
  `tests/unit/test_cli.py::test_the_file_to_read_is_never_the_file_written_however_it_is_spelled`.

## GH — on GitHub

- **GH-1** — `-f md` prints a plan, a destroy plan, a run's result or a status as
  Markdown, from the same plan the terminal and the plan file show.
  Held by: `tests/unit/test_render_markdown.py::test_a_first_deploy`,
  `tests/unit/test_render_markdown.py::test_status`.
- **GH-2** — With `--github`, on a pull request, a plan is posted as one comment and
  updated in place by the next plan. There is one comment per kind of plan, target and
  project, found by a marker on its first line; lely keeps no memory of it.
  Held by: `tests/unit/test_cli.py::test_the_plan_is_put_on_the_pull_request_and_kept_current`,
  `tests/unit/test_render_markdown.py::test_a_plan_that_failed_takes_the_place_of_the_last_one`.
- **GH-3** — With `--github` the plan goes on the run's page; after an apply or a destroy
  so does what each step did, and for an apply that is done what exists now, with links
  into the workspace.
  Held by: `tests/unit/test_cli.py::test_the_plan_is_put_on_the_pull_request_and_kept_current`,
  `tests/unit/test_cli.py::test_a_run_and_what_it_left_go_on_its_page`,
  `tests/unit/test_render_markdown.py::test_an_apply_and_what_exists_after_it`.
- **GH-4** — lely posts only when asked with `--github`, on `plan`, `show`, `apply` and
  `destroy`: it is never on because of where a command runs. `plan` and `show` write the
  comment and the run's page; `apply` and `destroy` write the run's page only.
  Held by: `tests/unit/test_cli.py::test_github_is_never_on_because_of_where_a_command_runs`.
- **GH-5** — A pull request from a fork gets no plan: `lely plan --github` loads nothing
  of the project, asks no workspace, says so on the run's page and ends with 0. A run
  about a pull request whose origin lely cannot read is treated as a fork's. `show
  --github` does not post a fork's plan, and `apply` and `destroy` with `--github` refuse
  one.
  Held by: `tests/unit/test_cli.py::test_a_pull_request_from_a_fork_gets_no_plan_and_is_told_so`,
  `tests/unit/test_cli.py::test_a_saved_plan_is_not_posted_for_a_fork`,
  `tests/unit/test_github.py::test_a_pull_request_from_another_repository_is_a_fork`,
  `tests/unit/test_github.py::test_a_fork_is_told_on_the_runs_page_and_nowhere_else`,
  `tests/unit/test_render_markdown.py::test_a_fork_is_told_why_there_is_no_plan`.
- **GH-6** — Outside a GitHub Actions run, without a token or without permission to
  comment, lely says what it could not do and why, and the command ends as it would have
  without the flag.
  Held by: `tests/unit/test_cli.py::test_outside_a_run_github_says_so_and_the_plan_stands`,
  `tests/unit/test_cli.py::test_a_comment_that_cant_be_written_doesnt_fail_the_plan`.
- **GH-7** — The run's token is sent to GitHub's API only, over https and not along with a
  redirect. With `--github`, which is when lely knows it, no line lely says holds it, and
  nothing it posts or writes: a comment, a summary, a result, a record. A plan that holds
  the token is shown by no command and written to no file: `lely plan --github` fails and
  names the step. It is searched for as it is written and as `actions/checkout` keeps it;
  another spelling of it passes.
  Held by: `tests/unit/test_cli.py::test_a_plan_that_holds_the_runs_token_is_not_written`,
  `tests/unit/test_cli.py::test_with_github_no_line_lely_says_holds_the_token`,
  `tests/unit/test_github.py::test_the_token_goes_to_https_and_not_along_with_a_redirect`.
- **GH-8** — Nothing a plan says is Markdown where it is posted: below the marker, every
  word that is not lely's own stands in a fenced block or a code span longer than any run
  of backticks in it, and no run of more than 16 backticks is shown as it is.
  Held by: `tests/unit/test_render_markdown.py::test_nothing_a_plan_says_is_markdown`,
  `tests/unit/test_render_markdown.py::test_no_shorter_plan_is_markdown_either`.
- **GH-9** — Only a comment lely could have written is updated: one by whoever the token
  is, or one by a bot when the token is a run's own.
  Held by: `tests/unit/test_github.py::test_a_comment_someone_else_wrote_is_never_updated`,
  `tests/unit/test_github.py::test_github_failing_for_a_moment_makes_no_second_comment`.
- **GH-10** — A plan that could not be made takes the last plan's place in the comment,
  with a link to the run and none of the error, which is on the run's page. So does a plan
  that was made and cannot be shown. When lely cannot tell which project of the repository
  a failed plan is for, it writes no comment.
  Held by: `tests/unit/test_github.py::test_a_plan_that_failed_takes_the_last_ones_place`,
  `tests/unit/test_github.py::test_a_plan_github_wont_take_says_so_where_the_last_one_stood`.
- **GH-11** — A comment has a size. A plan too long for one is told shorter, first without
  each change's details and then as counts, and says so; the counts are there in each, and
  the destructive changes, the first ten by name. A plan that is too long even so is
  replaced by a note that says there is a new plan. A summary too long for the run's page
  is not written whole.
  Held by: `tests/unit/test_github.py::test_a_plan_too_long_for_a_comment_is_told_shorter`,
  `tests/unit/test_github.py::test_a_summary_too_long_for_the_page_is_not_written_whole`.

## PKG — the package

- **PKG-1** — Every whole config the README and the docs show is one lely takes: it is
  checked as `lely validate` checks it, with the plugin classes the documents show.
  Held by: `tests/unit/test_repo.py::test_a_config_a_document_shows_is_one_lely_takes`,
  `tests/unit/test_repo.py::test_the_documents_show_whole_configs_to_check`.
- **PKG-2** — No file of the package holds a raw invisible or control character: it is
  written as its escape.
  Held by: `tests/unit/test_repo.py::test_no_file_holds_a_character_a_reader_cant_see`,
  `tests/unit/test_repo.py::test_every_text_file_is_read_with_git_or_without`.
- **PKG-4** — The page's look is two parts in `src/lely/render/`: `base.css`, which
  caland's page and stevin's hold a byte-identical copy of, and the page's own layout in
  `html.py`. The base is read once, when `render/html.py` is loaded.
  Not tested: the repository's own `tests/test_workspace.py` holds the three copies equal,
  outside this package's tests.

# Rules

What must be true of caland. Each rule is one or two sentences in the present tense, and
names the tests that hold it. Why a rule is so is in [DECISIONS.md](DECISIONS.md); what
ran on a real workspace is in [docs/tried.md](docs/tried.md).

## How this file is kept

- A rule has an identifier: an area and a number, such as `GATE-3`. Code, tests and docs
  cite a rule by that identifier and by nothing else.
- A new rule takes the next number in its area. A number is never reused: a rule that is
  dropped leaves a gap, and a rule that changes its meaning gets a new number.
- Under each rule stands `Held by:` with the tests that hold it, each as
  `tests/<file>.py::<test>`. Each of those tests cites the identifier, and no other test
  does.
- A rule no test can hold says `Not tested:` and why, in place of `Held by:`.
- A rule states the whole promise, also when the code does not keep all of it yet. Such
  a rule is open: it says `Not kept yet:`, the number of the issue that tracks it, and
  what the code does instead, as `Not kept yet: #12 — what the code does`. Its
  `Held by:` names the tests of the part that holds, if there are any. When the code
  keeps the rule the line is taken out, and the rule gets the test it lacked.
- A change to behaviour changes its rule and its test in the same pull request.
  `tests/test_rules.py` at the root of the repository checks all of the above.

The areas: `CMD` the command, `WSP` which workspace, `VIEW` what the page shows, `KEY`
the keyboard, `SEC` a secret, `VAL` a value, `FILE` a file as a value, `ACL` scopes and
grants, `ENV` a scope as `.env`, `LIST` the three lists, `ASK` what is asked first and
read-only, `GATE` the server on the machine, `KEPT` what is kept on the machine, `CODE`
how it is built.

The tests in `tests/test_page_in_a_browser.py` drive the real page in Chrome and are
skipped where there is none.

## CMD — the command

- **CMD-1** — caland installs one command, `caland`, and none under another name. It
  has no terminal version: `--tui` is refused and says that the terminal app is
  `isolinear`.
  Held by: `tests/test_cli.py::test_caland_installs_one_command_and_none_under_another_name`,
  `tests/test_cli.py::test_the_terminal_version_is_not_in_caland_and_it_says_where_it_is`,
  `tests/test_cli.py::test_nothing_of_the_terminal_version_is_left_to_import`.
- **CMD-2** — `caland` starts the page. A bare word, or `--profile NAME`, names the
  workspace to go to. `--read-only` and `--no-open` reach the page. `--page` is taken
  and does nothing.
  Held by: `tests/test_cli.py::test_caland_is_the_page`,
  `tests/test_cli.py::test_a_workspace_by_name_or_as_a_profile`,
  `tests/test_cli.py::test_page_still_says_the_page_from_when_it_was_not_the_default`.
- **CMD-3** — An option caland does not know is refused, and nothing starts. So are two
  workspaces at once, and a `--profile` with no name.
  Held by: `tests/test_cli.py::test_an_option_that_is_not_one_is_refused_and_nothing_starts`,
  `tests/test_cli.py::test_one_workspace_at_a_time`,
  `tests/test_cli.py::test_a_profile_with_no_name_is_said_and_nothing_starts`.
- **CMD-4** — A workspace that is named and was not found ends the run with exit code 2
  and the names that were found. Nothing is started.
  Held by: `tests/test_web_run.py::test_a_workspace_that_is_not_there_ends_it_before_it_starts`,
  `tests/test_choose.py::test_a_name_that_is_not_there_says_what_is`.
- **CMD-5** — With no workspace named, caland goes straight to the one there is no doubt
  about: the workspace of a bundle in the current folder, or the only one found. With
  several and no bundle, or with none, the server starts with no workspace and the page
  asks.
  Held by: `tests/test_choose.py::test_without_a_name_the_bundles_default`,
  `tests/test_choose.py::test_without_a_name_the_only_one_there_is`,
  `tests/test_web_run.py::test_no_workspace_at_all_starts_too_for_one_can_be_signed_in_to_by_address`.
- **CMD-6** — Started, caland says where it is. When a browser opens, the link with its
  key is not printed. With `--no-open`, or when no browser starts, the link is printed,
  and it works once.
  Held by: `tests/test_web_run.py::test_it_says_where_it_is_and_stops_when_left_alone`,
  `tests/test_web_run.py::test_with_a_browser_the_key_is_not_printed`,
  `tests/test_web_run.py::test_when_no_browser_starts_the_link_is_said_instead`.
- **CMD-7** — ctrl+c and a signal to terminate stop it the same way: the server closes,
  the file with the key is removed, every value held is forgotten, and it says so.
  Held by: `tests/test_web_run.py::test_being_told_to_stop_is_tidied_like_ctrl_c`,
  `tests/test_web_run.py::test_the_file_with_the_key_is_gone_when_it_stops`,
  `tests/test_web_run.py::test_every_value_is_forgotten_when_it_stops`.
- **CMD-8** — Left alone for 30 minutes, caland stops by itself and forgets every value
  it held. Closing the tab does not stop it.
  Held by: `tests/test_web_run.py::test_it_says_where_it_is_and_stops_when_left_alone`,
  `tests/test_web_server.py::test_idle_counts_from_the_last_thing_asked`.
  Not kept yet: #46 — every request with the token counts as asked, the page's own look
  at the state while it waits for a workspace among them. A tab that waits on a sign-in
  that is never finished keeps caland running.
- **CMD-9** — A signal that comes while caland stops changes nothing, and neither does
  a third: every step of the tidying is taken, also when one before it failed, no
  traceback is shown, and the exit code is 0. A step that fails is one line: what it
  was and the kind of failure.
  Held by: `tests/test_web_run.py::test_a_signal_that_comes_while_it_tidies_up_changes_nothing`,
  `tests/test_web_run.py::test_each_step_of_the_tidying_runs_whatever_became_of_the_one_before`,
  `tests/test_web_run.py::test_the_command_itself_stops_tidily_whatever_signals_it_is_sent`.

## WSP — which workspace

- **WSP-1** — The choice lists every workspace that was found, each with where it was
  found: a bundle's first, then every profile in `~/.databrickscfg` that has an address.
  A profile at the bundle's address, or at another profile's, is a row of its own.
  Held by: `tests/test_choose.py::test_two_profiles_at_one_address_are_both_offered_and_asked_for_by_name`,
  `tests/test_choose.py::test_a_profile_at_the_bundles_address_is_listed_beside_it_and_the_bundle_first`,
  `tests/test_profiles.py::test_discover_skips_sections_without_host`.
- **WSP-2** — A bundle in the current folder gives one workspace: the target marked
  `default: true`, or the only target, or the top-level `workspace.host`. A host that
  still holds a `${…}` variable is passed over.
  Held by: `tests/test_bundle.py::test_no_file_returns_none`,
  `tests/test_bundle.py::test_picks_the_default_target`,
  `tests/test_bundle.py::test_no_host_returns_none`.
- **WSP-3** — With no profile that has an address, `DATABRICKS_HOST` is offered as the
  profile `DEFAULT`.
  Held by: `tests/test_profiles.py::test_discover_env_fallback_when_no_config`.
- **WSP-4** — A name means the profile of that name before a bundle's target of that
  name. Two that were found under one name are told apart by their address and by where
  each was found.
  Held by: `tests/test_choose.py::test_by_name`,
  `tests/test_choose.py::test_a_bundle_target_by_its_name`,
  `tests/test_page_in_a_browser.py::test_the_row_that_is_picked_is_gone_to_also_when_two_have_one_name_and_address`.
- **WSP-5** — A profile connects with its own way of signing in. A bundle's workspace
  and an address sign in through the browser, which is the Databricks SDK's work. No
  token is asked for.
  Held by: `tests/test_choose.py::test_a_profile_at_the_bundles_address_signs_in_as_the_profile_does`,
  `tests/test_web_picker.py::test_a_workspace_is_gone_to_by_its_name`,
  `tests/test_web_picker.py::test_a_workspace_is_signed_in_to_by_its_address`.
- **WSP-6** — An address is `https`, a host as workspaces have them, and nothing after
  it but a port: no path, no query, no user, no number in the place of a name, no
  letter that only looks like the one meant. It is used in small letters.
  Held by: `tests/test_web_picker.py::test_an_address_is_https_a_host_and_nothing_more`,
  `tests/test_web_picker.py::test_a_host_is_one_as_workspaces_have_them`,
  `tests/test_page_in_a_browser.py::test_an_address_that_is_none_is_said_in_the_dialog`.
- **WSP-7** — A sign-in to an address is kept as a profile only when asked, once the
  sign-in has worked, and under a new name: letters, digits, dots, dashes and
  underscores, never `DEFAULT`, never the name of a profile the file has, whatever its
  case and whether it has an address or not. What is written is `host` and
  `auth_type = external-browser`.
  Held by: `tests/test_web_picker.py::test_an_address_is_kept_as_a_profile_once_the_sign_in_has_worked`,
  `tests/test_web_picker.py::test_an_address_that_cannot_be_signed_in_to_is_kept_nowhere`,
  `tests/test_page_in_a_browser.py::test_a_workspace_is_signed_in_to_by_its_address_and_kept_under_a_name`.
- **WSP-8** — With no workspace, the choice is the page's first dialog and cannot be
  left. A list with nothing in it says so, and the field for an address is what there
  is. A workspace that cannot be reached brings the choice back, with the reason.
  Held by: `tests/test_web_picker.py::test_with_no_workspace_yet_the_state_says_there_is_one_to_choose`,
  `tests/test_web_picker.py::test_a_page_with_nothing_to_choose_from_says_so`,
  `tests/test_page_in_a_browser.py::test_the_choice_comes_back_even_when_something_else_was_open`.
- **WSP-9** — `w` opens the choice again, and esc leaves the workspace as it is. Going
  to another workspace leaves nothing of the one that is left: nothing on the page, no
  value held, nothing to put back.
  Held by: `tests/test_web_picker.py::test_going_to_another_workspace_keeps_nothing_of_the_one_that_is_left`,
  `tests/test_page_in_a_browser.py::test_w_goes_to_another_workspace_and_keeps_nothing_of_the_one_left`,
  `tests/test_page_in_a_browser.py::test_enter_twice_is_one_sign_in`.
- **WSP-10** — A request about a workspace says which one it means, in the header
  `X-Caland-Workspace`, and is refused for any other. The server takes the workspace it
  is in once per request. The page drops a change that was queued, and an answer that
  comes late, once it has moved to another workspace.
  Held by: `tests/test_web_picker.py::test_a_page_left_showing_another_workspace_changes_and_reads_nothing`,
  `tests/test_web_picker.py::test_the_state_says_which_workspace_it_is_counted_from_the_first`,
  `tests/test_page_in_a_browser.py::test_a_value_that_comes_late_is_not_shown_under_another_workspace`.
- **WSP-11** — Choosing a workspace changes none, so it works when caland was started
  read-only.
  Held by: `tests/test_web_picker.py::test_choosing_a_workspace_changes_none_and_so_read_only_does_not_mind`.
## VIEW — what the page shows

- **VIEW-1** — Three panes: the scopes, each with how many secrets it holds; the
  selected scope's secrets, each with the day it was last changed and how long ago; and
  the detail of what is selected: the scope and what backs it, Databricks or Azure Key
  Vault, the person's access, the value once it is shown, and who has a grant.
  Held by: `tests/test_web_server.py::test_a_scope_says_its_secrets_and_its_grants`,
  `tests/test_web_server.py::test_state_says_who_and_what_and_how_far`,
  `tests/test_models.py::test_scope_backend_flags`.
- **VIEW-2** — Every scope of the workspace is listed, and the ones out of the person's
  reach are greyed. Selecting one says so, and that someone with MANAGE on it can change
  that. `f` hides them, and shows them again; the choice is kept for the next run.
  Held by: `tests/test_page_in_a_browser.py::test_it_opens_with_its_key_and_shows_the_workspace`,
  `tests/test_page_in_a_browser.py::test_f_hides_the_scopes_out_of_reach_and_shows_them_again`,
  `tests/test_page_in_a_browser.py::test_two_quick_changes_to_a_setting_are_kept_in_the_order_made`.
- **VIEW-3** — The page is there before the workspace is. On connecting, the scopes,
  the names and dates of their secrets and their grants are read in the background,
  eight scopes at a time, and kept for the session. No value is read.
  Held by: `tests/test_loading.py::test_it_starts_out_connecting_with_nothing_to_show`,
  `tests/test_loading.py::test_it_ends_ready_with_every_scope_read`,
  `tests/test_session.py::test_warm_scope_pulls_secrets_and_acls`.
- **VIEW-4** — A scope that cannot be read is shown with no secrets and is no error. A
  workspace that cannot be connected to, or whose scopes cannot be listed, says why.
  Held by: `tests/test_loading.py::test_a_scope_out_of_reach_is_empty_not_an_error`,
  `tests/test_loading.py::test_a_connection_that_fails_says_why`,
  `tests/test_session.py::test_warm_scope_swallows_store_errors`.
- **VIEW-5** — `r` reads the selected scope again and `R` the whole workspace. The
  request is answered at once and the reading is done in the background. Every change
  and every reading moves the version of the state, which is how the page knows to read
  again.
  Held by: `tests/test_loading.py::test_one_scope_can_be_read_again`,
  `tests/test_loading.py::test_the_whole_workspace_can_be_read_again`,
  `tests/test_web_changing.py::test_every_change_moves_the_version`.
- **VIEW-6** — The filter narrows what is shown by letters in order, over scopes and
  secrets together: a scope is shown when its name or one of its secrets matches. It
  happens in the page, over names it already has, with no request.
  Held by: `tests/test_page_in_a_browser.py::test_the_filter_picks_while_typing_and_goes_back`,
  `tests/test_web_server.py::test_keys_says_every_name_and_no_value`.
- **VIEW-7** — `s` sorts the pane the keyboard is in by its next column, and `S` the
  other way round: the scopes by name or by how many secrets they hold, the secrets by
  key or by when they were last changed. A click on a heading of the secrets does the
  same. The column in use is marked, and the selection stays on its row.
  Held by: `tests/test_page_in_a_browser.py::test_s_sorts_the_pane_the_keyboard_is_in_and_keeps_what_was_selected`.
- **VIEW-8** — The page is painted within 300 ms of being asked for, and before the
  workspace has answered. In a workspace of 500 scopes and 5,000 secrets a keystroke in
  the filter takes 50 ms at most. The test allows three times each number, for a shared
  machine.
  Held by: `tests/test_page_in_a_browser.py::test_a_big_workspace_draws_at_once_and_filters_without_waiting`.
- **VIEW-9** — What a workspace says is written as text, never as markup: the script
  uses no `innerHTML`. A scope may have the name of something every object has, such as
  `constructor`.
  Held by: `tests/test_web_server.py::test_the_script_writes_text_never_markup`,
  `tests/test_page_in_a_browser.py::test_a_name_is_text_and_never_markup`,
  `tests/test_page_in_a_browser.py::test_a_scope_may_be_called_what_every_object_has`.
- **VIEW-10** — The page is four files, all caland's own and inside the package:
  `page.html`, `base.css`, `page.css` and `page.js`. No framework, no build step,
  nothing fetched from anywhere else, and no script or style written into the page.
  Held by: `tests/test_web_server.py::test_the_page_is_four_files_and_holds_no_secret_and_no_token`,
  `tests/test_web_server.py::test_the_page_has_no_script_or_style_written_into_it`,
  `tests/test_web_server.py::test_no_other_file_is_served`.
- **VIEW-11** — The look is two style sheets, loaded in this order. `base.css` is the
  look the three Kostavo pages share, and caland's copy is the same as lely's and
  stevin's, byte for byte. `page.css` is caland's own layout. Light or dark is the
  system's. READ is muted, WRITE is blue, MANAGE is amber and bold, wherever a
  permission is shown.
  Not tested: no test of this package looks at a colour. The copies of `base.css` are
  held equal by `tests/test_workspace.py` at the root of the repository.
## KEY — the keyboard

- **KEY-1** — Every action has a key, and everything can be clicked. Every key the page
  takes is in the list `?` opens and in `docs/page.md`.
  Held by: `tests/test_page_in_a_browser.py::test_every_key_the_page_takes_is_in_the_list_of_keys_and_in_the_docs`.
- **KEY-2** — The keys of the page: `/` the filter, `?` the keys. `↑` `↓` or `j` `k`
  inside a pane, `←` `→` or `h` `l` across, `g` and `G` to a pane's ends. `space` shows
  or hides the value, `c` copies it, `C` copies how to reach it from code. `n` new
  secret, `e` edit, `m` move, copy or rename, `d` delete the secret, `u` put back. `N`
  new scope, `D` delete the scope, `p` the scope's grants. `a` what the person can
  reach, `P` what somebody else can, `A` secrets gone stale. `i` fill the scope from a
  `.env` file, `x` copy the scope as `.env`. `s` and `S` sort, `f` the scopes out of
  reach, `r` and `R` read again, `w` another workspace.
  Held by: `tests/test_page_in_a_browser.py::test_every_key_the_page_takes_is_in_the_list_of_keys_and_in_the_docs`,
  `tests/test_page_in_a_browser.py::test_arrows_move_inside_a_pane_and_across`.
- **KEY-3** — The keys of a dialog: esc closes it, and enter in a field saves. `y`
  answers the question that is showing. `1` and `2` choose in the `.env` dialog. In a
  list and in the choice of a workspace `↑` `↓` or `j` `k` pick and enter goes there; in
  the stale list `t` moves the number of days and `c` copies the table. In the grants
  `↑` `↓` or `j` `k` pick a grant, `e` changes it and `d` removes it. `z` forgets every
  value, in the list of keys and nowhere else.
  Held by: `tests/test_page_in_a_browser.py::test_a_grant_is_picked_changed_and_removed_by_its_keys`,
  `tests/test_page_in_a_browser.py::test_enter_in_a_list_goes_to_what_is_picked`,
  `tests/test_page_in_a_browser.py::test_a_scopes_values_are_copied_only_after_a_y`.
- **KEY-4** — Tab goes from pane to pane: scopes, secrets, detail, and shift+tab back.
  A pane is one stop, and nothing that scrolls is a stop of its own. Tab is not caught:
  after the last stop it goes on to the browser's own bar.
  Held by: `tests/test_page_in_a_browser.py::test_tab_goes_from_pane_to_pane`,
  `tests/test_page_in_a_browser.py::test_nothing_that_scrolls_is_a_stop_of_its_own`,
  `tests/test_page_in_a_browser.py::test_tab_is_not_kept_by_the_page`.
- **KEY-5** — In the detail the arrows walk its buttons, in the order they stand.
  Held by: `tests/test_page_in_a_browser.py::test_arrows_move_inside_a_pane_and_across`,
  `tests/test_page_in_a_browser.py::test_the_buttons_of_a_secret_in_the_order_the_arrows_walk_them`.
- **KEY-6** — Space and enter belong to what has the keyboard. In the scopes enter goes
  on to the secrets, on a secret it shows or hides the value, and on a button both press
  that button. A letter acts on what is selected from anywhere that is not a field: a
  letter typed into a field is no key.
  Held by: `tests/test_page_in_a_browser.py::test_enter_goes_on_from_the_scopes_and_shows_the_value_of_a_secret`,
  `tests/test_page_in_a_browser.py::test_space_on_a_button_presses_that_button`,
  `tests/test_page_in_a_browser.py::test_a_y_typed_into_a_filter_answers_no_question`.
- **KEY-7** — The keyboard is never nowhere. The page opens with it in the scopes, and
  closing a dialog, leaving the filter, or a change that draws the page again puts it
  back where it was.
  Held by: `tests/test_page_in_a_browser.py::test_it_opens_with_the_keyboard_in_the_scopes`,
  `tests/test_page_in_a_browser.py::test_the_filter_picks_while_typing_and_goes_back`,
  `tests/test_page_in_a_browser.py::test_after_a_delete_the_selection_stays_where_it_was`.
- **KEY-8** — In the filter `↑` `↓` pick a secret while typing, enter goes to what is
  left, and esc clears the filter and goes back.
  Held by: `tests/test_page_in_a_browser.py::test_the_filter_picks_while_typing_and_goes_back`.
## SEC — a secret

- **SEC-1** — `n` opens a form for a new secret and `e` the same form for the selected
  one, with its scope and key fixed. The value is typed into a masked field, or is a
  file (FILE-1). Text is stored as it was typed.
  Held by: `tests/test_web_changing.py::test_text_is_stored_as_it_was_typed`,
  `tests/test_page_in_a_browser.py::test_a_new_secret_is_typed_in_and_selected`.
- **SEC-2** — A new secret never overwrites one that is there, under any case of its
  name. Whether one is there is asked of the workspace at that moment. The refusal is
  said in the dialog.
  Held by: `tests/test_web_changing.py::test_a_new_secret_does_not_overwrite_one_that_is_there`,
  `tests/test_web_changing.py::test_a_new_secret_in_another_case_does_not_overwrite`,
  `tests/test_page_in_a_browser.py::test_a_new_secret_does_not_overwrite_and_says_so_in_the_dialog`.
- **SEC-3** — An empty value is refused, typed or as a file: it is taken for a slip, not
  for a wish to wipe. Editing with nothing typed changes nothing.
  Held by: `tests/test_web_changing.py::test_an_empty_value_is_a_slip_not_a_wish_to_wipe`,
  `tests/test_web_changing.py::test_an_empty_file_wipes_nothing`,
  `tests/test_page_in_a_browser.py::test_an_empty_file_is_refused_in_the_form`.
- **SEC-4** — A value holds 128 kB at most, which is Databricks' limit. A name that is
  made is not padded with spaces and is 128 characters at most. A scope that is not
  there is not written to.
  Held by: `tests/test_web_changing.py::test_a_value_may_be_as_large_as_a_secret_holds_and_no_larger`,
  `tests/test_web_changing.py::test_a_secret_said_badly_is_not_saved`,
  `tests/test_files.py::test_the_limit_is_databricks`.
- **SEC-5** — `d` deletes the selected secret, wherever the keyboard is. It asks first,
  naming the key and the scope and saying that `u` puts it back. `d` never reaches a
  scope: with no secret selected it deletes nothing and names the key that would.
  Held by: `tests/test_web_changing.py::test_deleting_what_is_not_there`,
  `tests/test_page_in_a_browser.py::test_deleting_takes_a_deliberate_y_and_u_puts_it_back`,
  `tests/test_page_in_a_browser.py::test_after_a_delete_the_selection_stays_where_it_was`.
- **SEC-6** — `m` asks for a scope and a key: another scope is a move, the same scope a
  rename, and with *keep the original* it is a copy. It is done in the safe order: read
  the value, write it at the new place, and only then remove the old. A failure halfway
  leaves the secret in two places and never in none.
  Held by: `tests/test_web_changing.py::test_a_move_a_rename_and_a_copy`,
  `tests/test_values_as_bytes.py::test_moving_is_done_in_the_safe_order`,
  `tests/test_page_in_a_browser.py::test_a_copy_to_another_scope`.
- **SEC-7** — A move never lands on a secret that is there. A rename that only changes
  the case of the name is refused: to Databricks that is the same secret, and it would
  be written and then removed.
  Held by: `tests/test_web_changing.py::test_a_move_that_makes_no_sense_moves_nothing`,
  `tests/test_values_as_bytes.py::test_a_move_does_not_land_on_one_made_elsewhere_since`,
  `tests/test_page_in_a_browser.py::test_a_move_onto_another_secret_is_refused_in_the_dialog`.
- **SEC-8** — Two names that differ only in case are one name, for a scope and for a
  secret, because they are to Databricks. `domain.same_name` is the one place that says
  so.
  Held by: `tests/test_web_changing.py::test_a_scope_in_another_case_is_there_already`,
  `tests/test_web_changing.py::test_after_an_import_in_another_case_the_new_value_is_the_one_shown`,
  `tests/test_values_as_bytes.py::test_the_fake_takes_a_name_in_another_case_for_the_same_secret`.
- **SEC-9** — `u` puts back the secret that was last deleted or moved away, with the
  value it had. It is one deep. After a move the copy at the new place stays. A copy
  leaves nothing to put back. A secret whose value could not be read before it was
  deleted is gone for good, and the page says so.
  Held by: `tests/test_web_changing.py::test_deleting_keeps_what_it_held_and_undo_puts_it_back`,
  `tests/test_web_changing.py::test_undo_with_nothing_to_put_back`,
  `tests/test_values_as_bytes.py::test_a_secret_whose_value_cannot_be_read_is_deleted_for_good`.
- **SEC-10** — A secret is not put back over one made since, nor into a scope that is
  gone or is Azure Key Vault's. What is held to be put back is let go of only once it is
  back.
  Held by: `tests/test_web_changing.py::test_undo_does_not_overwrite_a_secret_made_since_and_keeps_what_it_holds`,
  `tests/test_values_as_bytes.py::test_it_is_not_put_back_over_a_secret_made_since`,
  `tests/test_values_as_bytes.py::test_what_cannot_be_put_back_now_is_kept_for_when_it_can`.
- **SEC-11** — One change at a time, against what is there now. `WorkspaceService`
  takes one change at a time; a move, a delete and a put-back read the value at that
  moment; and whether a name is free is asked of the workspace, not of what was read
  before. The page queues its changes: a key pressed while one is under way waits.
  Held by: `tests/test_values_as_bytes.py::test_a_put_back_asked_for_while_a_delete_is_under_way_loses_nothing`,
  `tests/test_values_as_bytes.py::test_two_new_secrets_of_one_name_at_once_make_one`,
  `tests/test_page_in_a_browser.py::test_u_pressed_before_the_delete_is_answered_loses_nothing`.
- **SEC-12** — The secrets of an Azure Key Vault-backed scope are Azure's. The server
  refuses to make, edit, delete, move or import one there, and says why. Showing,
  copying, and copying one out to a Databricks-backed scope work.
  Held by: `tests/test_web_changing.py::test_a_key_vault_scopes_secrets_are_azures`,
  `tests/test_web_changing.py::test_a_secret_can_be_copied_out_of_a_key_vault_scope`,
  `tests/test_page_in_a_browser.py::test_a_key_vault_scopes_secrets_can_only_be_copied_out`.
- **SEC-13** — As a place to put a secret the page offers the scopes within the
  person's reach that are not Azure Key Vault's.
  Held by: `tests/test_page_in_a_browser.py::test_a_key_vault_scopes_secrets_can_only_be_copied_out`.
## VAL — a value

- **VAL-1** — A value is never written: not to disk, not to the settings, not to a log,
  not to the terminal. It is held in memory, for the session at most.
  Held by: `tests/test_web_server.py::test_nothing_a_request_says_is_printed`,
  `tests/test_web_server.py::test_a_failure_inside_is_said_in_the_terminal_and_not_what_it_said`.
- **VAL-2** — A value is read only for something the person asked for: to show it, to
  copy it, to move or copy its secret, to delete its secret, so that `u` can put it
  back, and for an export with values. Connecting reads names, dates and grants. No
  `GET` reads a value.
  Held by: `tests/test_loading.py::test_no_value_is_read_while_loading`,
  `tests/test_web_server.py::test_no_get_ever_reads_a_value`,
  `tests/test_page_in_a_browser.py::test_a_scopes_keys_are_copied_as_a_template_without_reading_a_value`.
- **VAL-3** — A value is read from the workspace every time it is asked for. A second
  look is never answered from the first.
  Held by: `tests/test_values_as_bytes.py::test_a_value_is_read_from_the_workspace_every_time_it_is_asked_for`,
  `tests/test_values_as_bytes.py::test_a_second_look_shows_what_is_there_now`,
  `tests/test_page_in_a_browser.py::test_a_value_shown_again_is_read_again_and_is_what_is_there_now`.
- **VAL-4** — What caland holds of values, in memory: each value it read or wrote, by
  scope and key, and the secret last deleted or moved away. A scope's values are let go
  of when that scope is read again or deleted, a secret's when it is deleted. Nothing is
  answered from them.
  Held by: `tests/test_values_as_bytes.py::test_reading_a_scope_again_lets_go_of_what_was_read_of_it`,
  `tests/test_values_as_bytes.py::test_deleting_a_scope_drops_the_values_held_from_it`,
  `tests/test_cache.py::test_remove_secret_drops_row_and_the_value_held_of_it`.
- **VAL-5** — *Forget every value caland holds* drops every value, and with them what
  `u` could put back. Its key is `?` and then `z`, and it has none outside the list of
  keys. Going to another workspace (WSP-9) and stopping (CMD-7) forget the same.
  Held by: `tests/test_web_server.py::test_forgetting_drops_every_value_held`,
  `tests/test_web_changing.py::test_forgetting_ends_the_chance_to_put_it_back`,
  `tests/test_page_in_a_browser.py::test_every_value_is_forgotten_by_a_key_in_the_keys_and_by_none_outside`.
- **VAL-6** — A shown value hides itself after 30 seconds by the clock: a machine that
  slept, or a tab that was in the background, hides it as soon as the page is looked at
  again, and so does a clock that was put back. The key that showed it hides it, and so
  does moving to another secret.
  Held by: `tests/test_page_in_a_browser.py::test_a_shown_value_hides_itself_when_30_seconds_have_gone_by_the_clock`,
  `tests/test_page_in_a_browser.py::test_a_page_that_is_looked_at_again_hides_a_value_whose_time_has_gone_at_once`,
  `tests/test_page_in_a_browser.py::test_moving_on_takes_the_value_off_the_page`.
- **VAL-7** — A value is in the page only while it is shown: not in the page's source,
  not in an address, not in anything the browser keeps.
  Held by: `tests/test_page_in_a_browser.py::test_a_value_is_in_the_page_only_while_it_is_shown`,
  `tests/test_page_in_a_browser.py::test_nothing_is_kept_by_the_browser_but_the_token_for_this_tab`.
- **VAL-8** — `c` copies a value without showing it. It goes from the server's answer
  to the clipboard and is never written into the page.
  Held by: `tests/test_page_in_a_browser.py::test_copy_puts_the_value_on_the_clipboard_and_never_in_the_page`.
- **VAL-9** — `C` offers the secret as code, never as its value: the
  `dbutils.secrets.get(…)` call, the `{{secrets/scope/key}}` form, and the CLI command.
  A name goes into each as a name, whatever is in it.
  Held by: `tests/test_page_in_a_browser.py::test_a_name_goes_into_code_as_a_name_whatever_is_in_it`.
- **VAL-10** — A value is bytes from end to end: it is stored, moved, put back and read
  byte for byte. Text is shown as text. A value that is no text is shown as what it is:
  so many bytes, in base64.
  Held by: `tests/test_values_as_bytes.py::test_bytes_go_in_and_come_back_as_they_were`,
  `tests/test_values_as_bytes.py::test_moving_keeps_every_byte`,
  `tests/test_page_in_a_browser.py::test_a_file_that_is_no_text_goes_in_and_is_shown_as_what_it_is`.
## FILE — a file as a value

- **FILE-1** — The form takes a file: chosen with the system's own file dialog, dropped
  on the form, or pasted as text of more than one line, which is taken line for line.
  One line that is pasted is just pasted. Typing a value lets go of the file, and
  choosing a file lets go of what was typed. A form that is closed keeps nothing.
  Held by: `tests/test_page_in_a_browser.py::test_a_certificate_is_picked_described_and_stored_as_it_is`,
  `tests/test_page_in_a_browser.py::test_a_certificate_pasted_into_the_value_is_taken_line_for_line`,
  `tests/test_page_in_a_browser.py::test_a_form_that_is_closed_keeps_nothing_typed_or_chosen`.
- **FILE-2** — Before a file is saved the form says what it is: its name, its size and
  its kind. For a certificate it says who it is for, who issued it and when it expires.
  Held by: `tests/test_files.py::test_a_pem_certificate_says_who_it_is_for_who_issued_it_and_when_it_ends`,
  `tests/test_files.py::test_the_names_it_lists_count_before_its_subject`,
  `tests/test_page_in_a_browser.py::test_a_certificate_is_picked_described_and_stored_as_it_is`.
- **FILE-3** — A private key and a PKCS#12 bundle are named and never opened. Nothing
  asks for a password, and nothing in `application/files.py` can open a bundle.
  Held by: `tests/test_files.py::test_a_private_key_is_named_and_never_read`,
  `tests/test_files.py::test_a_pkcs12_bundle_is_named_by_its_shape_and_never_opened`,
  `tests/test_files.py::test_nothing_here_can_open_a_pkcs12_bundle`.
- **FILE-4** — Describing a file never raises, prints nothing, and does no work the
  file sets the size of. What cannot be read is said to be that.
  Held by: `tests/test_files.py::test_no_file_makes_it_raise_or_take_its_time`,
  `tests/test_files.py::test_a_certificate_that_cannot_be_read_is_said_to_be_that`,
  `tests/test_web_changing.py::test_describing_any_file_answers`.
- **FILE-5** — A file goes from the page to caland on the same machine, and from there
  to Databricks. It is written nowhere on the way, and nothing of it is kept once it has
  been described. A file larger than a secret may hold is refused by the page before it
  is sent, and by the server.
  Held by: `tests/test_web_changing.py::test_a_file_is_described_and_kept_nowhere`,
  `tests/test_web_changing.py::test_describing_takes_the_token_like_everything_else`,
  `tests/test_page_in_a_browser.py::test_a_file_too_large_to_be_a_secret_is_refused_before_it_is_sent`.
## ACL — scopes and grants

- **ACL-1** — `N` makes a scope, and who made it is seen to have it at once. A name
  that is there, in any case, is refused.
  Held by: `tests/test_web_changing.py::test_a_scope_is_made_and_seen_at_once`,
  `tests/test_web_changing.py::test_a_scope_that_is_there_is_not_made_again`,
  `tests/test_page_in_a_browser.py::test_a_scope_is_made_and_selected`.
- **ACL-2** — `D` deletes the selected scope. The dialog says how many secrets go with
  it, or that they cannot be listed from here. A deleted scope cannot be put back.
  Held by: `tests/test_web_changing.py::test_a_scope_is_deleted_with_what_was_in_it`,
  `tests/test_page_in_a_browser.py::test_a_scope_has_a_key_of_its_own_and_says_what_goes_with_it`,
  `tests/test_page_in_a_browser.py::test_a_scope_whose_secrets_cannot_be_listed_is_not_called_empty`.
- **ACL-3** — The person's access to a scope is the highest permission granted to them,
  to `users`, or to a group they are in. Where the grants cannot be listed, which takes
  MANAGE, and the secrets can, it is READ.
  Held by: `tests/test_permissions.py::test_perm_rank_orders_permissions`,
  `tests/test_permissions.py::test_authorization_summary_computes_effective_permission`,
  `tests/test_session.py::test_warm_scope_marks_readability_per_scope`.
- **ACL-4** — `p` lists who has what on the selected scope. From it a grant is given,
  changed or removed: READ, WRITE or MANAGE, for a user, a group or a service principal.
  Removing says so when the grant is the person's own. Grants on a Key Vault-backed
  scope are edited the same way.
  Held by: `tests/test_web_changing.py::test_a_grant_is_given_changed_and_taken`,
  `tests/test_web_changing.py::test_grants_on_a_key_vault_scope_are_changed_like_any`,
  `tests/test_page_in_a_browser.py::test_a_grant_with_nobody_named_is_said_in_the_dialog`.
## ENV — a scope as `.env`

- **ENV-1** — A `.env` file is `KEY=VALUE` lines. Blank lines and `#` comments are
  passed over, an `export ` in front is dropped, quotes are taken off, and a value
  quoted over several lines is read whole.
  Held by: `tests/test_dotenv.py::test_parse_ignores_noise_and_strips_quotes`,
  `tests/test_dotenv.py::test_a_value_quoted_over_several_lines_is_one_value`,
  `tests/test_web_changing.py::test_a_key_quoted_over_several_lines_is_one_secret_and_whole`.
- **ENV-2** — A file that cannot be read without guessing is refused whole, before any
  of it is written: a quote that is never closed, a value that is no text, two keys that
  are one secret to Databricks, or more than 1,000 entries.
  Held by: `tests/test_dotenv.py::test_a_quote_that_is_never_closed_is_refused_not_guessed_at`,
  `tests/test_web_changing.py::test_a_file_that_cannot_be_read_without_guessing_is_refused_whole`,
  `tests/test_web_changing.py::test_an_import_of_more_than_a_scope_holds_is_refused`.
- **ENV-3** — `i` fills the selected scope from a file chosen with the system's file
  dialog. Before anything is written the server says how many secrets go in and which
  of those that are there are overwritten, whatever the case of their names. A key with
  no value is left out, and named. No value is said back.
  Held by: `tests/test_web_changing.py::test_an_import_is_shown_before_it_is_done_and_says_no_value`,
  `tests/test_web_changing.py::test_an_import_puts_every_pair_and_leaves_out_the_empty`,
  `tests/test_page_in_a_browser.py::test_an_import_that_overwrites_nothing_is_not_dressed_as_a_danger`.
- **ENV-4** — An import that the workspace refuses halfway stops there, and says at
  which key and how many went in. What went in before it stays.
  Held by: `tests/test_web_changing.py::test_an_import_that_stops_says_how_far_it_got_and_at_which_key`,
  `tests/test_page_in_a_browser.py::test_an_import_that_stops_says_where_and_that_the_rest_stays`.
- **ENV-5** — `x`, then `1`, puts the scope's keys on the clipboard as `KEY=` lines. No
  value is read.
  Held by: `tests/test_page_in_a_browser.py::test_a_scopes_keys_are_copied_as_a_template_without_reading_a_value`.
- **ENV-6** — `x`, then `2`, says how many values will be read, and puts the scope with
  its values on the clipboard and nowhere else: never in a file. Every value is read at
  that moment. A secret that is no text is left out, and named.
  Held by: `tests/test_web_changing.py::test_an_export_is_the_scopes_text_values_and_names_what_it_left_out`,
  `tests/test_web_changing.py::test_an_export_reads_values_so_it_is_no_get_and_takes_the_token`,
  `tests/test_page_in_a_browser.py::test_a_scopes_values_are_copied_only_after_a_y`.
- **ENV-7** — What is written as `.env` is read back the same: a value that would break
  a line is quoted, and a value that ends in a newline keeps it.
  Held by: `tests/test_dotenv.py::test_multiline_values_round_trip`,
  `tests/test_dotenv.py::test_what_is_written_is_read_back_the_same`,
  `tests/test_web_changing.py::test_a_value_that_ends_in_a_newline_comes_back_with_it`.
## LIST — the three lists

- **LIST-1** — `A` lists every secret not changed within a number of days, oldest
  first. The number is 30, 90, 180 or 365, starts at 90, and is kept for the next run.
  The table is copied as Markdown, in which a name stays a name whatever is in it.
  Held by: `tests/test_page_in_a_browser.py::test_the_stale_report_lists_what_was_not_changed_oldest_first`,
  `tests/test_page_in_a_browser.py::test_a_name_in_a_copied_table_stays_a_name`,
  `tests/test_web_changing.py::test_a_preference_is_kept_and_said_back`.
- **LIST-2** — `a` lists every scope with the person's access and how many principals
  have a grant on it, strongest access first.
  Held by: `tests/test_page_in_a_browser.py::test_the_overview_says_what_you_can_reach_strongest_first`,
  `tests/test_web_changing.py::test_every_scopes_grants_at_once`.
- **LIST-3** — `P` lists every grant made to a name as it is typed: a user, a group or
  a service principal. It shows the grants made to the name itself, not what is reached
  through a group, and says so.
  Held by: `tests/test_page_in_a_browser.py::test_who_has_access_narrows_as_a_name_is_typed`.
- **LIST-4** — The lists are made in the page from names, dates and grants, and read no
  value. A list asked for while the workspace is still being read says so, and fills.
  Held by: `tests/test_page_in_a_browser.py::test_a_list_asked_for_while_the_workspace_is_read_says_so_and_fills`,
  `tests/test_page_in_a_browser.py::test_enter_in_a_list_goes_to_what_is_picked`.
## ASK — what is asked first, and read-only

- **ASK-1** — Nothing destructive is done without a deliberate `y`: deleting a secret
  or a scope, removing a grant, an import, an export with values. Each says what it is
  about to do to what. `y` is never the key that opened the dialog, and esc does
  nothing.
  Held by: `tests/test_page_in_a_browser.py::test_deleting_takes_a_deliberate_y_and_u_puts_it_back`,
  `tests/test_page_in_a_browser.py::test_escape_deletes_nothing`,
  `tests/test_page_in_a_browser.py::test_a_scopes_values_are_copied_only_after_a_y`.
- **ASK-2** — One dialog is open at a time, but for a question over the grants. A
  dialog whose answer comes back late does not open over what the person has gone on to
  do. `y` reaches only the question that is showing.
  Held by: `tests/test_page_in_a_browser.py::test_no_dialog_opens_over_another_but_a_question_over_the_grants`,
  `tests/test_page_in_a_browser.py::test_an_import_answered_late_does_not_take_the_place_of_another_question`,
  `tests/test_page_in_a_browser.py::test_a_y_typed_into_a_filter_answers_no_question`.
- **ASK-3** — Started with `--read-only`, the server refuses every change to the
  workspace, whatever the page shows: a secret made, edited, moved, deleted or put
  back, an import and its preview, a grant given or removed, a scope made or deleted.
  The page offers none of them, the grants are only shown, and the header says
  `read-only`. What reads still works: showing, copying, the lists, the exports.
  Held by: `tests/test_web_changing.py::test_read_only_is_the_servers_to_hold`,
  `tests/test_web_changing.py::test_read_only_still_reads`,
  `tests/test_page_in_a_browser.py::test_started_read_only_the_keys_in_the_grants_pick_and_change_nothing`.
- **ASK-4** — Read-only is about the workspace. On the person's own machine caland may
  still write the two preferences (KEPT-3), and a profile that is asked for when
  signing in to an address (WSP-7).
  Held by: `tests/test_web_changing.py::test_a_preference_is_kept_and_said_back`,
  `tests/test_web_picker.py::test_choosing_a_workspace_changes_none_and_so_read_only_does_not_mind`.
## GATE — the server on the machine

- **GATE-1** — The server listens on `127.0.0.1` only, on a port chosen at start. There
  is no option to listen wider.
  Held by: `tests/test_web_server.py::test_it_listens_on_this_machine_only`,
  `tests/test_web_server.py::test_it_cannot_be_reached_by_the_machines_other_address`.
- **GATE-2** — A request whose `Host` is not the address the server listens on is
  refused. That is what a site does that had its name pointed at this machine.
  Held by: `tests/test_web_gate.py::test_its_own_page_is_answered`,
  `tests/test_web_gate.py::test_localhost_is_this_server_too`,
  `tests/test_web_server.py::test_a_site_whose_name_points_here_gets_nothing`.
- **GATE-3** — A request that says where it came from (`Origin`, `Sec-Fetch-Site`) and
  did not come from caland's own page is refused, also with the token. A client that
  does not say is held to the token.
  Held by: `tests/test_web_gate.py::test_another_site_is_refused_even_with_the_token`,
  `tests/test_web_gate.py::test_the_api_is_only_for_the_page_itself`,
  `tests/test_web_changing.py::test_no_change_without_the_token_or_from_another_site`.
- **GATE-4** — Everything under `/api/` but `/api/enter` needs the session's token, in
  the header `X-Caland-Token`. The token is never a cookie and never in an address, is
  made anew for each run, and is compared in time that does not depend on where two
  differ.
  Held by: `tests/test_web_gate.py::test_without_the_token_nothing_under_api_is_answered`,
  `tests/test_web_gate.py::test_a_token_in_the_address_is_not_a_token`,
  `tests/test_web_server.py::test_the_token_is_long_and_differs_from_run_to_run`.
- **GATE-5** — Only `GET` and `POST` are answered. A `POST` under `/api/` must say it is
  JSON, which a form on another site cannot. Nothing that changes or reveals is done by
  a `GET`, so by nothing that could have come from a link.
  Held by: `tests/test_web_gate.py::test_nothing_but_get_and_post`,
  `tests/test_web_gate.py::test_what_a_form_on_another_site_can_send_is_refused`,
  `tests/test_web_changing.py::test_no_change_by_a_get`.
- **GATE-6** — The four files of the page hold no name, no value and no token, are only
  read, and are given to anyone who asks.
  Held by: `tests/test_web_gate.py::test_the_page_itself_needs_no_token_and_holds_nothing`,
  `tests/test_web_gate.py::test_the_page_is_only_read`,
  `tests/test_web_server.py::test_the_page_is_four_files_and_holds_no_secret_and_no_token`.
- **GATE-7** — A page is let in with a one-time key, which the address carries in its
  fragment. `/api/enter` gives the token for the right key, once: the key is then spent,
  a new key ends the one before it, and the page takes the key out of the address at
  once. A page with no key shows nothing and says what to do.
  Held by: `tests/test_web_gate.py::test_entering_needs_the_key_not_the_token`,
  `tests/test_web_gate.py::test_entering_from_another_site_is_refused`,
  `tests/test_page_in_a_browser.py::test_a_wrong_key_is_no_key`.
- **GATE-8** — The browser is handed a file that only its owner can read, which sends
  it on to the page: the key is never on a command line. The file is removed when the
  key has been used, and when caland stops.
  Held by: `tests/test_web_opening.py::test_the_browser_is_handed_a_file_and_never_the_key`,
  `tests/test_web_opening.py::test_the_file_is_its_owners_alone`,
  `tests/test_web_server.py::test_entering_is_told_to_who_holds_the_file_with_the_key`.
- **GATE-9** — The browser keeps one thing: the token, in the tab's `sessionStorage`,
  for a reload of the page and nothing else. No cookie, no local storage, no cache.
  Another tab, and a tab that comes back from another site, find the page locked, and a
  page that loses its key shows nothing it was told.
  Held by: `tests/test_page_in_a_browser.py::test_a_reload_stays_in`,
  `tests/test_page_in_a_browser.py::test_another_tab_is_not_in`,
  `tests/test_page_in_a_browser.py::test_a_locked_page_keeps_no_list_and_no_file`.
- **GATE-10** — Every answer carries the same headers, a refusal and what Python's
  server refuses by itself included: a content policy that lets the page load only
  caland's own, `no-store`, no sniffing, no framing, no referrer.
  Held by: `tests/test_web_server.py::test_every_answer_carries_the_same_care`,
  `tests/test_web_server.py::test_the_policy_lets_the_page_load_only_what_is_calands_own`,
  `tests/test_web_server.py::test_a_request_that_cannot_be_read_is_refused_the_same_way`.
- **GATE-11** — A request says at most 256 kB, says how much is coming, and is a JSON
  object. What is not is refused unread, and the connection ends there, so that nothing
  that came with it is taken for a request of its own.
  Held by: `tests/test_web_server.py::test_too_much_is_refused_unread`,
  `tests/test_web_server.py::test_what_is_not_a_json_object_is_refused`,
  `tests/test_web_changing.py::test_text_that_is_no_text_is_refused_not_failed_on`.
- **GATE-12** — At most 64 connections are kept at once, and one that says nothing for
  10 seconds is closed. A program on the machine that holds all 64 keeps the page from
  loading and gets nothing.
  Held by: `tests/test_web_server.py::test_connections_left_hanging_do_not_use_the_server_up`.
- **GATE-13** — Nothing a request says is written anywhere, and a connection that
  breaks prints nothing.
  Held by: `tests/test_web_server.py::test_nothing_a_request_says_is_printed`,
  `tests/test_web_server.py::test_a_connection_that_breaks_prints_nothing`.
- **GATE-14** — A failure inside caland is one line in the terminal: the method and
  path of the request, the kind of failure, and the file and line it came from. Never
  the failure's own words, which can quote a value, and no traceback. Only for a
  request the gate let through, each line once, and twenty at most. The page is told
  "caland failed" and no more.
  Held by: `tests/test_web_server.py::test_a_failure_inside_says_nothing_of_what_failed`,
  `tests/test_web_server.py::test_a_failure_inside_is_said_in_the_terminal_and_not_what_it_said`,
  `tests/test_web_server.py::test_a_path_that_is_not_as_calands_own_are_is_not_said_in_the_terminal`.
## KEPT — what is kept on the machine

- **KEPT-1** — caland has no credentials of its own. It asks for no token and stores
  none. A sign-in through the browser is kept by the Databricks SDK, in its own folder,
  `~/.config/databricks-sdk-py/oauth/`.
  Not tested: it is an absence, and the folder is the SDK's. What a profile that caland
  keeps holds is WSP-7.
- **KEPT-2** — The profile file is `~/.databrickscfg`, or the file
  `DATABRICKS_CONFIG_FILE` names. It is written whole or not at all, one writer at a
  time. A profile is added to the end and what was there is left as it was. A new file
  is its owner's alone, one that is there keeps who may read it, and a link stays a
  link: the file it points to is what is written.
  Held by: `tests/test_profiles.py::test_a_profile_is_added_to_the_end_and_what_was_there_is_as_it_was`,
  `tests/test_profiles.py::test_a_new_file_is_its_owners_alone_and_one_that_was_there_keeps_its_mode`,
  `tests/test_profiles.py::test_a_link_to_a_file_that_is_not_there_yet_gets_that_file_and_stays`.
- **KEPT-3** — caland keeps two preferences, in `settings.json` in the folder `caland`
  under `$XDG_CONFIG_HOME`, which is `~/.config` when it is not set: whether the scopes
  out of reach are shown, and the stale list's number of days. A file that is missing
  or broken means the defaults, a value of the wrong kind is passed over, and a folder
  that cannot be written does not stop caland. A preference that is asked for badly
  changes none.
  Held by: `tests/test_settings.py::test_what_is_saved_is_what_is_loaded`,
  `tests/test_settings.py::test_a_missing_or_broken_file_means_the_defaults_never_a_failure`,
  `tests/test_web_changing.py::test_a_preference_asked_for_badly_changes_none`.
## CODE — how it is built

- **CODE-1** — Only `infrastructure/` imports the Databricks SDK. The page, its server
  and the use-cases have no way to a workspace but through the ports in `domain/`.
  Held by: `tests/test_layers.py::test_only_infrastructure_imports_the_databricks_sdk`,
  `tests/test_databricks.py::test_databricks_store_satisfies_protocol`.
- **CODE-2** — Only the SDK, and of it only the secrets API and who is signed in.
  caland runs no query, starts no warehouse and reads no system table.
  Held by: `tests/test_layers.py::test_a_workspace_is_asked_only_for_secrets_and_who_is_signed_in`.
- **CODE-3** — The layers point inward. `domain/` imports no other layer and no
  library. `application/` imports `domain/`, and one library in one file:
  `cryptography`, in `files.py`. `interface/` imports `application/` and `domain/`.
  Held by: `tests/test_layers.py::test_the_layers_point_inward`.

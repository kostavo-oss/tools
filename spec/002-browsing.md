# 002 — browsing

**Status:** built. Written 2026-10-06 from the tool at 0.4.1.

## Why

The question a person brings is rarely "show me this key". It is "where is it", "what else
is in there", "how old is it", "who can read it". The answer should be on the screen before
the question is finished.

## Requirements

- **R1 — Three panes.** Scopes on the left, with how many secrets each holds; the selected
  scope's keys in the middle, with when each was last updated and how long ago; the
  selection's detail on the right — its scope, your access, who else has access, and the
  value once revealed. A breadcrumb says where you are. *(built, 0.1.0)*
- **R2 — Everything by keyboard.** Arrows or `h` `j` `k` `l`, `tab` between panes, `g` and
  `G` to the ends. The footer shows the keys that apply; `?` shows all of them; `ctrl+p`
  finds any action by name. *(built, 0.1.0; the palette 0.2.0)*
- **R3 — Loaded before it is asked for.** On connecting, scopes, keys and permissions are
  fetched in the background — eight scopes at a time — and kept for the session, so moving
  around waits for nothing. Values are not part of this. *(built; concurrent since 0.3.0)*
- **R4 — Refresh when asked.** `r` reloads the selected scope, `R` the workspace. *(built)*
- **R5 — Sort any table.** `s` goes to the next column, `S` reverses, a click on a header
  does the same; the column in use is marked, and the selection stays on its row. The same
  everywhere a table is shown. *(built; one implementation since 0.4.0)*
- **R6 — Filter the pane in focus.** `/` narrows scopes or keys as you type, by letters in
  order. A chip above the table shows a filter is on and how many rows it leaves; it
  survives a refresh; `esc` clears it. *(built, 0.3.0)*
- **R7 — Search every scope at once.** `ctrl+f` matches `scope/key` across the workspace,
  from what is already loaded; `enter` goes to the secret. *(built, 0.3.0)*
- **R8 — It works in a small terminal.** Dialogs size to the window, the help scrolls, and in
  a narrow header the secret's name outranks the identity. Where a terminal keeps `ctrl+f`
  and `ctrl+p` for itself, `F` and `P` do the same. *(built, 0.4.1)*
- **R9 — Four looks.** Graphite by default; violet, amber and phosphor from the palette.
  The choice is kept. *(built)*

## Not in this spec

- **A mouse-first screen.** Clicks work where a table has headers; nothing needs one.
- **Changing what a key does.** There is no key map to edit.

## To decide

Nothing.

## Done when

Built. Held by `tests/test_ui_browse.py`, `test_sorting.py`, `test_ui_scope_filter.py`,
`test_ui_small_terminal.py`, `test_cache.py`, `test_help.py` — which fails when a key on the
screen is missing from the help — and the screen snapshots.

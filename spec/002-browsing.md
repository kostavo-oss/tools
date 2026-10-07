# 002 — browsing

**Status:** built, on the page. Written 2026-10-06 from the terminal app at 0.4.1, which
met these first and is not in caland any more ([008](008-the-page.md)), and rewritten on
2026-10-07 to say what the page does. A requirement names the release it first arrived in,
and the one it came to the page in. What only the terminal app had is under
[Gone with the terminal app](#gone-with-the-terminal-app).

## Why

The question a person brings is rarely "show me this key". It is "where is it", "what else
is in there", "how old is it", "who can read it". The answer should be on the screen before
the question is finished.

## Requirements

- **R1 — Three panes.** Scopes on the left, with how many secrets each holds; the selected
  scope's keys in the middle, with when each was last changed and how long ago; the
  selection's detail on the right — its scope and what backs it, your access, when it was
  last changed, the value once it is shown, and who else has access. The heading of the
  middle pane names the scope, and the header the workspace.
  *(built, 0.1.0; on the page since 0.5.0)*
- **R2 — Everything by keyboard.** Arrows or `h` `j` `k` `l`, `g` and `G` to a pane's ends,
  `tab` from pane to pane ([008, R3a](008-the-page.md)); `enter` goes on from the scopes
  to the secrets. The buttons show their keys, and `?` lists them all.
  *(built, 0.1.0; on the page since 0.5.0)*
- **R3 — Loaded before it is asked for.** On connecting, scopes, keys and grants are read
  in the background — eight scopes at a time — and kept for the session, so moving around
  waits for nothing. The page is there before the workspace is, and fills as it arrives.
  Values are not part of this. *(built; eight at a time since 0.3.0; on the page since
  0.5.0)*
- **R4 — Read again when asked.** `r` reads the selected scope again, `R` the workspace.
  *(built; on the page since 0.5.0)*
- **R5 — Sort a pane.** `s` sorts the pane the keyboard is in by its next column — the
  scopes by name or by how many secrets they hold, the secrets by key or by when they
  were last changed — and `S` the other way round; a click on a heading of the secrets
  does the same. The column in use is marked, and the selection stays on its row.
  *(built; on the page since 0.5.2)*
- **R6 — Filter as you type.** `/` narrows what is shown, by letters in order. It happens
  in the page, over names it already has. The arrows pick while typing, `enter` goes to
  what is left, `esc` clears it; it stays on while a scope is read again.
  *(built, 0.3.0; on the page since 0.5.0)*
- **R7 — Find a secret in any scope.** The filter is one, over scopes and secrets
  together: a scope is shown when its name or one of its secrets matches, so a key is
  found in whichever scope holds it, from what is already loaded.
  *(built, 0.3.0; on the page since 0.5.0)*
- **R8 — It works in a small window.** A narrow window puts the panes under each other, a
  dialog is never wider than the window, and the list of keys scrolls and opens at its
  first line. *(built, 0.4.1 for a small terminal; on the page since 0.5.0)*
- **R9 — Light or dark by the system.** The page has one look, lely's
  ([008, R2](008-the-page.md)), and follows the system's light or dark.
  *(on the page since 0.5.0)*

## Gone with the terminal app

- **The breadcrumb** that said where you were (R1): the pane's heading and the header do.
- **The footer** with the keys that apply (R2): the buttons show their own.
- **The palette**, `ctrl+p`, that found an action by name (R2): there is no palette.
- **The filter's chip** with how many rows are left (R6): the field shows what is typed.
- **A search of its own**, `ctrl+f`, across every scope (R7): the one filter does it. With
  it went `F` and `P` as stand-ins where a terminal kept `ctrl+f` and `ctrl+p` (R8).
- **Sorting in every table** (R5): the lists in dialogs each have one order.
- **Four looks** — graphite, violet, amber, phosphor (R9): there are no themes.

## Not in this spec

- **A mouse-first page.** Everything can be clicked; nothing needs to be.
- **Changing what a key does.** There is no key map to edit.

## To decide

Nothing.

## Done when

Built. Held by `tests/test_web_server.py`, `test_loading.py`, `test_cache.py` and the
browser tests (`test_page_in_a_browser.py`): the panes, the keys and where the keyboard
lands, that every key is in the list of keys, the filter, sorting, and the two numbers of
[008, R7](008-the-page.md).

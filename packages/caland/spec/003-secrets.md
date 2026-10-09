# 003 — secrets

**Status:** built, on the page. Written 2026-10-06 from the terminal app at 0.4.1, which
met these first and is not in caland any more ([008](008-the-page.md)), and rewritten on
2026-10-07 to say what the page does. A requirement names the release it first arrived in,
and the one it came to the page in. What only the terminal app had is under
[Gone with the terminal app](#gone-with-the-terminal-app).

## Why

This is the work the tool exists for: put a secret in, change it, move it, take it out, and
look at its value — each in a keystroke or two, and none of them by accident.

## Requirements

- **R1 — Create and edit.** `n` opens a form for a new secret in the selected scope; `e` the
  same form for the selected one. The value is typed into a masked line. A new secret
  does not overwrite one that is there — under any case of its name: edit that one
  instead. *(built, 0.1.0; on the page since 0.5.1)*
- **R2 — A value of more than one line comes from a file.** The form takes a file: chosen
  with the system's own dialog, dropped on the form, or pasted as text of more than one
  line. Before it is saved the form says what it is, and it is stored byte for byte
  ([008, R4–R6](008-the-page.md)). That is how a PEM key or a certificate goes in.
  *(built, 0.4.0; on the page since 0.5.1)*
- **R3 — Delete, when meant.** `d` asks first, naming the key and the scope and saying that
  `u` puts it back, and takes a deliberate `y` to confirm — `d` twice does nothing. `d` is
  the secret wherever the keyboard is; a scope has a key of its own
  ([004, R1](004-scopes-and-permissions.md)). *(built; the `y` since 0.3.0; on the page
  since 0.5.1)*
- **R4 — Move, copy, rename in one dialog.** `m` asks for a scope and a key. Another scope
  is a move, the same scope a rename, and *keep the original* makes it a copy. It is done in
  the safe order — read the value as it is at that moment, write it at the new place, and
  only then remove the old — so a failure halfway leaves a secret in two places and never
  in none. It does not land on a secret that is there, and a rename that only changes the
  case is refused: to Databricks that is the same secret, and it would be written and
  then removed. *(built, 0.4.0; on the page since 0.5.1)*
- **R5 — Take back the last delete or move.** `u` puts back the secret that was last deleted
  or moved away, with its value. One deep: the one before it is gone. It holds until
  another is deleted or moved, values are forgotten (R9), caland goes to another workspace
  or stops. It is not put back over a secret made since, and what is held is let go of
  only once it is back. After a move, the copy at the new place stays. A deleted scope is
  not put back. *(built, 0.3.0; moves since 0.4.0; on the page since 0.5.1)*
- **R6 — See a value when you ask.** `space` — or `enter`, with the keyboard on a secret —
  reads the selected secret's value and shows it in the detail pane; the same key hides
  it, and it hides itself after 30 seconds by the clock: a machine that slept, or a tab
  that was in the background, hides it as soon as the page is looked at again. A value
  that is no text is shown as what it is: so many bytes, as base64.
  *(built; hiding itself since 0.3.0; on the page since 0.5.0)*
- **R7 — Copy a value.** `c` puts it on the clipboard without showing it, and without
  writing it into the page. *(built, 0.1.0; on the page since 0.5.0)*
- **R8 — Copy how to reach it instead.** `C` offers the secret as code — the
  `dbutils.secrets.get(…)` call, the `{{secrets/scope/key}}` form for a Spark conf or a job,
  the CLI command — so that what is pasted into a notebook is never the value.
  *(built, 0.3.0; on the page since 0.5.0)*
- **R9 — Forget on demand.** *Forget every value caland holds*, in the list of keys — `?`,
  then `z` — drops every value caland holds in memory, the one kept for `u` included. It
  has a key there and only there: it is not one to press by a slip.
  *(built, 0.3.0; on the page since 0.5.2; the key since the fix of 2026-10-07)*
- **R10 — A Key Vault-backed scope's secrets are Azure's.** Create, edit and delete are off
  for them, and say why; reading, copying, and copying one *out* to a Databricks-backed
  scope work. *(built, 0.3.0; on the page since 0.5.1)*

## How a value is held

A value is read from the workspace every time it is asked for — to show it (R6), to copy
it (R7), to move or delete its secret (R4, R5), for an export
([005](005-bulk-and-audit.md)). A second look asks Databricks again: it is never answered
from the first, which may be a value that was changed since. *(Decided by the owner,
2026-10-07. Until then a value was read once and kept, and a second look could show what
was no longer there.)*

What caland holds, in memory and nowhere else:

- **The secret last deleted or moved away**, with the value it had, so that `u` can put it
  back (R5). It is the one value caland uses again.
- **Each value it read or wrote**, by scope and key. Nothing reads these back any more;
  they are held as they were before the decision above (D2).

How long: a scope's values until that scope is read again (`r`, `R`) or deleted, a secret's
until it is deleted; all of them, the one for `u` included, until *Forget every value*
(R9), going to another workspace, or caland stopping — by ctrl+c, or by itself after 30
minutes of nothing asked. Hiding takes a value off the page, not out of caland's memory.
It is never written anywhere. → [006](006-safety.md)

## Gone with the terminal app

- **Typing a path** to the file a value comes from (R2): the page takes the file itself.
- **The palette**, from which values were forgotten (R9).
- **A delete that said "This can't be undone"** when `u` could undo it (R3).
- **A value that is no text, written back as base64 text** when its secret was moved or
  put back (R4, R5): the page carries bytes.

## Not in this spec

- **Versions of a secret.** Databricks keeps none; neither does caland.
- **Editing a value of more than one line in place.** It goes in from a file.
- **Generating values** — passwords, keys.

## Decided

- **The dialog says what is so**: that `u` puts a deleted secret back, for as long as
  caland runs and nothing else is deleted. *(Found while writing this spec; built with the
  page, 2026-10-06, 0.5.1. Was D1.)*
- **A value is carried as bytes end to end**, so that a file that is no text — a PKCS#12
  bundle — goes in, moves, is put back and comes out the same.
  *(Built with the page, 2026-10-06, 0.5.1 — [008, R6](008-the-page.md). Was D3.)*
- **A rename that only changes the case is refused.** To Databricks `API-KEY` is
  `api-key`; move wrote the one and removed the other, which was the same secret. *(Found
  on 2026-10-06 while the page was reviewed, and fixed that day, in 0.5.1. Was D4.)*
- **Showing or copying a value reads it from the workspace every time.**
  *(Decided by the owner, 2026-10-07.)*

## To decide

- **D2 — Should a hidden value also be forgotten?** Today it stays in memory until the
  session ends, which means a session left open for a day holds every value it was ever
  asked for. It used to make a second look instant; since 2026-10-07 a second look reads
  the workspace again, so what is held of a value that was only shown or copied is used
  by nothing. *Proposal:* hold only what `u` needs, and let go of the rest as soon as it
  has been answered.

## Done when

Built. Held by `tests/test_values_as_bytes.py`, `test_web_changing.py`, `test_files.py` and
the browser tests under "changing things".

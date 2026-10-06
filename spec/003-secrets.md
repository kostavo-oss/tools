# 003 — secrets

**Status:** built, on the page. Written 2026-10-06 from the terminal app at 0.4.1, which
met these first and is not in caland any more ([008](008-the-page.md)); where the page does
a thing differently, [what changed with the page](#what-changed-with-the-page) says so.

## Why

This is the work the tool exists for: put a secret in, change it, move it, take it out, and
look at its value — each in a keystroke or two, and none of them by accident.

## Requirements

- **R1 — Create and edit.** `n` opens a form for a new secret in the selected scope; `e` the
  same form for the selected one. The value is typed into a masked line. *(built, 0.1.0)*
- **R2 — A value of more than one line comes from a file.** The form has a file field: name
  a file, and its content is the value. That is how a PEM key or a certificate goes in.
  *(built, 0.4.0)*
- **R3 — Delete, when meant.** `d` on a secret asks first, naming the key and the scope, and
  takes a deliberate `y` to confirm — `d` twice does nothing. *(built; the `y` since 0.3.0)*
- **R4 — Move, copy, rename in one dialog.** `m` asks for a scope and a key. Another scope
  is a move, the same scope a rename, and *keep the original* makes it a copy. It is done in
  the safe order — read the value, write it at the new place, and only then remove the old —
  so a failure halfway leaves a secret in two places and never in none. *(built, 0.4.0)*
- **R5 — Take back the last delete or move.** `u` puts back the secret that was last deleted
  or moved away, with its value. One deep: the one before it is gone. It holds until the
  session ends or values are forgotten (R9). After a move, the copy at the new place stays.
  A deleted scope is not put back. *(built, 0.3.0; moves since 0.4.0)*
- **R6 — See a value when you ask.** `space` or `enter` fetches the selected secret's value
  and shows it in the detail pane; the same key hides it, and it hides itself after 30
  seconds. *(built; hiding itself since 0.3.0)*
- **R7 — Copy a value.** `c` puts it on the clipboard without showing it. *(built, 0.1.0)*
- **R8 — Copy how to reach it instead.** `C` offers the secret as code — the
  `dbutils.secrets.get(…)` call, the `{{secrets/scope/key}}` form for a Spark conf or a job,
  the CLI command — so that what is pasted into a notebook is never the value.
  *(built, 0.3.0)*
- **R9 — Forget on demand.** *Forget revealed values*, from the palette, drops every value
  caland holds in memory, the one kept for `u` included. *(built, 0.3.0)*
- **R10 — A Key Vault-backed scope's secrets are Azure's.** Create, edit and delete are off
  for them, and say why; reading, copying, and copying one *out* to a Databricks-backed
  scope work. *(built, 0.3.0)*

## How a value is held

A value fetched for R6, R7, R4, R5 or an export ([005](005-bulk-and-audit.md)) stays in
memory for the session, so asking twice does not ask Databricks twice. Hiding after 30
seconds takes it off the screen, not out of memory; R9 and quitting do that. It is never
written anywhere. → [006](006-safety.md)

## What changed with the page

- R2: a file is chosen with the system's own dialog, or dropped, or pasted; it is said what
  it is before it is saved, and is stored byte for byte ([008, R4–R6](008-the-page.md)).
- R3, R5: the dialog says the truth — `u` puts it back (D1). `u` does not put a secret
  back over one made since, and holds what it holds until it is back.
- R4: a move does not land on another secret, takes the value as it is at that moment,
  and refuses a rename that only changes the case (D4).
- A new secret does not overwrite one that is there: edit it instead.
- D3: a value that is no text survives — it is carried as bytes.

## Not in this spec

- **Versions of a secret.** Databricks keeps none; neither does caland.
- **Editing a value of more than one line in place.** It goes in from a file.
- **Generating values** — passwords, keys.

## To decide

- **D1 — The dialog and the message disagree.** Before a secret is deleted the dialog says
  "This can't be undone"; after, the message says "press u to undo". The second is the true
  one. *Proposal:* the dialog says what is so — that `u` puts it back, for as long as the
  session lasts and nothing else is deleted. *(found while writing this spec)*
- **D2 — Should a hidden value also be forgotten?** Today it stays in memory until the
  session ends. That makes a second look instant, and means a session left open for a day
  holds every value it was ever asked for. *The writer has no strong view;* forgetting a
  value some minutes after it was last used would cost one round-trip and is easy to build.
- **D3 — A value that is not text does not survive caland.** A secret holding bytes — a
  PKCS#12 bundle put in with the CLI — is shown as base64, which is fair. But moving it,
  copying it, or taking back its delete writes that base64 back *as text*: the secret at
  the new place is no longer the file it was. And no binary file can be put in at all: the
  file field reads text. *Proposal:* values are carried as bytes end to end —
  [008, R6](008-the-page.md) needs it for certificates anyway. *(found while writing 008)*
  **On the page this is so since 2026-10-06; the terminal version, which is frozen, is as
  it was.**

- **D4 — A rename that only changes the case deleted the secret.** *Found 2026-10-06 while
  the page was reviewed, and fixed the same day — here too, though the terminal version is
  frozen: it was losing secrets.* To Databricks `API-KEY` is `api-key`; move wrote the one
  and removed the other, which was the same. It is refused now.

## Done when

Built. Held by `tests/test_values_as_bytes.py`, `test_web_changing.py`, `test_files.py` and
the browser tests under "changing things".

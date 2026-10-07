# 005 — bulk work and audits

**Status:** built, on the page. Written 2026-10-06 from the terminal app at 0.4.1, which
met these first and is not in caland any more ([008](008-the-page.md)), and rewritten on
2026-10-07 to say what the page does. A requirement names the release it first arrived in,
and the one it came to the page in. What only the terminal app had is under
[Gone with the terminal app](#gone-with-the-terminal-app).

## Why

Two jobs that are miserable a secret at a time: filling a scope from what a project already
has in a `.env` file, and finding out which secrets nobody has rotated.

## Requirements

- **R1 — Fill a scope from a `.env` file.** `i` opens the system's file dialog and reads
  the chosen file's `KEY=VALUE` lines: blank lines and `#` comments are passed over, an
  `export ` in front is dropped, quotes are taken off, and a value quoted over several
  lines is read whole. Before anything is written a dialog says how many secrets will be,
  and which of those that exist will be overwritten — whatever the case of their names; a
  key with no value is left out, and named. If the workspace refuses one, the import
  stops there and says at which key and how many went in; what went in before it stays.
  A file that cannot be read without guessing is refused whole.
  *(built, 0.4.0; on the page since 0.5.2)*
- **R2 — A scope's keys as a template.** `x`, then `1`, puts `KEY=` lines on the clipboard —
  for another scope, or a project's `.env.example`. No value is read.
  *(built, 0.4.0; on the page since 0.5.2)*
- **R3 — A scope with its values, when meant.** `x`, then `2`, asks first, saying how many
  values, takes a `y`, and puts them on the clipboard and nowhere else. A value that would
  break a line is quoted so that R1 reads it back as it was; a secret that is no text is
  left out, and named. *(built, 0.4.0; on the page since 0.5.2)*
- **R4 — What has gone stale.** `A` lists every secret not updated within a number of days,
  oldest first. `t` moves the number through 30, 90, 180 and 365, and it is kept; `enter`
  goes to the secret; `c` copies the table as Markdown, for a ticket. No value is read.
  *(built, 0.3.0; kept since 0.4.0; on the page since 0.5.2)*

## Gone with the terminal app

- **The palette**, from which the import and the two exports were started (R1–R3): each
  has a key.
- **A typed path** to the file to import (R1): the page takes the file itself.
- **An import that said only how many went in** when it stopped (R1): the page names the
  key.

## Not in this spec

- **Writing an export to a file.** On purpose: a value on disk outlives the session.
  → [006](006-safety.md)
- **Importing into several scopes, or from other formats** — JSON, a vault's export.
- **Rotating.** The audit says what is old; a person changes it.

## Decided

- **An import that stops halfway stays halfway, and says at which key.** The secrets
  written before the failure are in the scope; nothing is taken back, and one that was
  overwritten has lost its old value. That is the honest behaviour for a tool with no
  state. *(The writer's view, built with the page's tools on 2026-10-06, 0.5.2. Was D1.)*

## To decide

Nothing.

## Done when

Built. Held by `tests/test_dotenv.py`, `test_web_changing.py` (from ".env" down) and the
browser tests under "the tools".

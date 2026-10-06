# 005 — bulk work and audits

**Status:** built. Written 2026-10-06 from the tool at 0.4.1.

## Why

Two jobs that are miserable a secret at a time: filling a scope from what a project already
has in a `.env` file, and finding out which secrets nobody has rotated.

## Requirements

- **R1 — Fill a scope from a `.env` file.** *Import .env file into scope*, from the palette,
  asks for a path and reads its `KEY=VALUE` lines: blank lines and `#` comments are passed
  over, an `export ` in front is dropped, quotes are taken off. Before anything is written a
  dialog says how many secrets will be, and how many that exist will be overwritten. If a
  write fails the import stops there and says how far it got. *(built, 0.4.0)*
- **R2 — A scope's keys as a template.** *Copy scope as .env (keys only)* puts `KEY=` lines
  on the clipboard — for another scope, or a project's `.env.example`. No value is read.
  *(built, 0.4.0)*
- **R3 — A scope with its values, when meant.** *Copy scope as .env (with values)* asks
  first, saying how many values, and puts them on the clipboard and nowhere else. A value
  that would break a line is quoted so that R1 reads it back as it was. *(built, 0.4.0)*
- **R4 — What has gone stale.** `A` lists every secret not updated within a number of days,
  oldest first. `t` moves the number through 30, 90, 180 and 365, and it is kept; `enter`
  goes to the secret; `c` copies the table as Markdown, for a ticket. No value is read.
  *(built, 0.3.0; kept since 0.4.0)*

## Not in this spec

- **Writing an export to a file.** On purpose: a value on disk outlives the session.
  → [006](006-safety.md)
- **Importing into several scopes, or from other formats** — JSON, a vault's export.
- **Rotating.** The audit says what is old; a person changes it.

## To decide

- **D1 — An import that stops halfway stays halfway.** The secrets written before the
  failure are in the scope; nothing is taken back, and one that was overwritten has lost its
  old value. The message says how many went in, not which. *The writer's view:* that is the
  honest behaviour for a tool with no state; naming the key it stopped at would help.
  *(found while writing this spec)*

## On the page (2026-10-06)

All four are on the page ([008](008-the-page.md), "the tools"), with two things the
terminal version does not have: an import says which key it stopped at (D1), and it treats
a key in another case as the secret it is to Databricks when it says what is overwritten.

## Done when

Built. Held by `tests/test_dotenv.py`, `test_ui_tools.py` and the audit's snapshot.

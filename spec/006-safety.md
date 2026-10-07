# 006 — what caland may do

**Status:** built, on the page. Written 2026-10-06 from the terminal app at 0.4.1, which
met these first and is not in caland any more ([008](008-the-page.md)); where the page does
a thing differently, [what changed with the page](#what-changed-with-the-page) says so.

## Why

It is a tool that shows secrets and can delete them, pointed at workspaces that matter. What
it will not do has to be as firm as what it does.

## Requirements

- **R1 — A value is never written.** Not to disk, not to a cache file, not to the settings,
  not to a log. It is held in memory, for the session at most. *(built, 0.1.0)*
- **R2 — A value is read only for something you asked for.** Nothing is fetched on
  connecting but names, dates and grants. A value is fetched for: showing it, copying it,
  moving or copying its secret, deleting its secret — so that the delete can be taken back
  — and an export with values. *(built)*
- **R3 — Nothing destructive without a deliberate `y`.** Deleting a secret or a scope,
  removing a grant, an import that overwrites, an export with values: each asks, says what
  it is about to do to what, and takes a deliberate `y` — never the key that opened the
  dialog, so a key pressed twice cannot slip through. *(built, 0.3.0)*
- **R4 — Read-only when asked.** `caland --read-only` turns off everything that changes a
  workspace: create, edit, move, delete, undo, import, and every change to a grant. Their
  keys leave the footer, the grants dialog only shows, and the header says `read-only`.
  Everything that reads still works — showing, copying, searching, the audit, exports.
  *(built, 0.3.0)*
- **R5 — No credentials of its own.** caland asks for no token and stores none. It signs in
  through the Databricks SDK, and a profile it saves holds a host and
  `auth_type = external-browser`. *(built, 0.2.0)*
- **R6 — What it keeps is three preferences.** `~/.config/caland/settings.json` holds the
  theme, whether all scopes are shown, and the audit's number of days. A file that is
  missing or broken means the defaults, never a failure to start. *(built, 0.4.0)*
- **R7 — The clipboard is yours.** A copied value stays on it until you replace it. caland
  does not clear it after a while: it cannot read the clipboard back, so it could not know
  it was clearing its own value and not something copied since. *(built; decided)*
- **R8 — One door to the network.** Only `infrastructure/` imports the Databricks SDK. The
  screens and the rules reach a workspace through the ports in `domain/`, and are tested
  against a fake behind the same ports. *(built, 0.2.0)*

## What changed with the page

- R3: one dialog is open at a time, and `y` reaches only the question that is showing.
- R4: read-only is about the workspace. On the person's own machine caland may still
  write what R6 keeps, and a profile that is asked for when signing in to an address
  ([001, R4](001-connecting.md)).
- R6: two preferences — whether all scopes are shown, and the stale report's number of
  days. There is no theme.
- R8: the door is `interface/web/`: the browser talks to a server on the person's machine,
  and that to the same ports. What that server answers, and to whom, is
  [008, R9](008-the-page.md).
- D1: the docs say what R2 says now.

## Not in this spec

- **Keeping an audit trail of its own.** Databricks logs who read and changed what.
- **Protecting against the machine it runs on.** A value in memory, or on the clipboard, is
  as safe as the session it is in.

## To decide

- **D1 — The docs say less than R2.** `docs/security.md` says a value leaves Databricks
  "only when you explicitly reveal or copy it". Deleting a secret and moving one read it as
  well — and where a workspace logs secret reads, a delete shows up as a read first.
  *Proposal:* the docs say what R2 says. Whether a delete *should* read the value — it is
  what makes `u` possible — is the owner's. *(found while writing this spec)*
- **D2 — Should some workspaces open read-only unless told otherwise?** Today read-only is
  a flag on the command, every time. *Proposal, the writer's and not asked for:* a profile
  could be marked so — in the settings file — and open read-only by default, with a flag to
  lift it.
- **D3 — Where a vulnerability is reported.** `SECURITY.md` and `docs/security.md` give a
  GitHub advisory link and a personal work address. *Proposal:* the advisory link only, as
  for lely. → [007, Decided](007-name-and-release.md#decided)

## Done when

Built. Held across the suite: `tests/test_settings.py` and `test_profiles.py` for what is
written, `test_web_gate.py` and `test_web_server.py` for what the server answers,
`test_web_changing.py` for read-only and every refusal, and `tests/fakes.py` — the fake
workspace everything is tested against.

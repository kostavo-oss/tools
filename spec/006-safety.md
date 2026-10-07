# 006 — what caland may do

**Status:** built, on the page. Written 2026-10-06 from the terminal app at 0.4.1, which
met these first and is not in caland any more ([008](008-the-page.md)), and rewritten on
2026-10-07 to say what the page does. A requirement names the release it first arrived in,
and the one it came to the page in. What only the terminal app had is under
[Gone with the terminal app](#gone-with-the-terminal-app).

## Why

It is a tool that shows secrets and can delete them, pointed at workspaces that matter. What
it will not do has to be as firm as what it does.

## Requirements

- **R1 — A value is never written.** Not to disk, not to a cache file, not to the settings,
  not to a log. It is held in memory, for the session at most
  ([003](003-secrets.md#how-a-value-is-held) says what, and for how long).
  *(built, 0.1.0; on the page since 0.5.0)*
- **R2 — A value is read only for something you asked for.** Nothing is read on
  connecting but names, dates and grants. A value is read for: showing it, copying it,
  moving or copying its secret, deleting its secret — so that the delete can be taken back
  — and an export with values. The docs say the same. *(built; on the page since 0.5.0)*
- **R3 — Nothing destructive without a deliberate `y`.** Deleting a secret or a scope,
  removing a grant, an import, an export with values: each asks, says what it is about to
  do to what, and takes a deliberate `y` — never the key that opened the dialog, so a key
  pressed twice cannot slip through. One dialog is open at a time, and `y` reaches only
  the question that is showing. *(built, 0.3.0; on the page since 0.5.1)*
- **R4 — Read-only when asked.** `caland --read-only` turns off everything that changes a
  workspace: create, edit, move, delete, undo, import, and every change to a grant. What
  would change one is not on the page, the grants dialog only shows, and the header says
  `read-only`; the server refuses every change whatever the page shows. Everything that
  reads still works — showing, copying, filtering, the stale report, exports. Read-only is
  about the workspace: on the person's own machine caland may still write what R6 keeps,
  and a profile that is asked for when signing in to an address
  ([001, R4](001-connecting.md)). *(built, 0.3.0; on the page since 0.5.0)*
- **R5 — No credentials of its own.** caland asks for no token and stores none. It signs in
  through the Databricks SDK, which keeps a sign-in through the browser itself, in its own
  folder; a profile caland saves holds a host and `auth_type = external-browser`
  ([001](001-connecting.md)). *(built, 0.2.0; on the page since 0.6.0)*
- **R6 — What it keeps is two preferences.** `~/.config/caland/settings.json` holds
  whether all scopes are shown, and the stale report's number of days. A file that is
  missing or broken means the defaults, never a failure to start.
  *(built, 0.4.0; on the page since 0.5.2)*
- **R7 — The clipboard is yours.** A copied value stays on it until you replace it. caland
  does not clear it after a while: it cannot read the clipboard back, so it could not know
  it was clearing its own value and not something copied since. *(built; decided)*
- **R8 — One door to the network.** Only `infrastructure/` imports the Databricks SDK. The
  page talks to a server on the person's machine (`interface/web/`), the server to the
  use-cases, and those reach a workspace through the ports in `domain/`; all of it is
  tested against a fake behind the same ports. What that server answers, and to whom, is
  [008, R9](008-the-page.md). *(built, 0.2.0; on the page since 0.5.0)*

## Gone with the terminal app

- **The footer**, which the keys of what changes a workspace left when read-only (R4):
  on the page the buttons themselves are not there.
- **A third preference: the theme** (R6). There are no themes.
- **Screens** that reached a workspace through the ports (R8): the page and its server do.

## Not in this spec

- **Keeping an audit trail of its own.** Databricks logs who read and changed what.
- **Protecting against the machine it runs on.** A value in memory, or on the clipboard, is
  as safe as the session it is in.

## Decided

- **The docs say what R2 says**: a value is read to show it, to copy it, to move or copy
  its secret, to delete its secret, and for an export with values — not "only when you
  explicitly reveal or copy it". *(Found while writing this spec; done with the page,
  2026-10-06. Was D1.)* Whether a delete *should* read the value — it is what makes `u`
  possible — was the owner's to say, and stands as built.

## To decide

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

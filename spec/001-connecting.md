# 001 — connecting

**Status:** built, on the page. Written 2026-10-06 from the terminal app at 0.4.1, which
met these first and is not in caland any more ([008](008-the-page.md)), and rewritten on
2026-10-07 to say what the page does. A requirement names the release it first arrived in,
and the one it came to the page in. What only the terminal app had is under
[Gone with the terminal app](#gone-with-the-terminal-app).

## Why

A person has several workspaces and several ways of reaching each. Before anything can be
shown, caland has to know which one, and the person has to trust that it is the one they
meant.

## Requirements

- **R1 — One choice for every way in.** The page's choice of a workspace lists what was
  found, and every row says where: the target of an Asset Bundle in the current folder,
  and every profile in `~/.databrickscfg` that has an address — also one at the bundle's
  address or at another profile's, which has its own way of signing in. With no such
  profile, `DATABRICKS_HOST` from the environment is offered as the profile `DEFAULT`.
  Under the list is a field for an address (R3). A bundle's target and a profile of one
  name at one address are two rows, told apart by where each was found.
  *(built, 0.1.0; on the page since 0.6.0; every profile since the fix of 2026-10-07)*
- **R2 — A bundle's workspace is the default.** With a `databricks.yml` in the current
  folder, its workspace is listed first and selected, and is where caland goes when no
  workspace is named: the target marked `default: true`, or the only target, or the
  top-level `workspace.host`. A host that still holds a `${…}` variable is not a host, and
  is passed over. *(built, 0.2.0; on the page since 0.6.0)*
- **R3 — Sign in to an address, in the browser.** An address typed into the field signs in
  through the browser (OAuth, done by the Databricks SDK), in a tab of its own. An address
  is `https`, a host, and nothing after it. No token is asked for.
  *(built, 0.2.0; on the page since 0.6.0)*
- **R4 — Keep a sign-in as a profile.** Ticking *keep it as a profile* and giving it a name
  writes the host and `auth_type = external-browser` to `~/.databrickscfg`, and nothing
  else, once the sign-in has worked. The name is a **new** one: never over a profile that
  is there, which keeps its own way of signing in. The file is written whole or not at
  all. A new file is its owner's alone; one that is there keeps who may read it, which is
  the person's to say; one that is a link stays a link, and the file it points to is what
  is written. *(built, 0.2.0; on the page since 0.6.0)*
- **R5 — The choice opens with nothing to show.** With no bundle and no profile the list is
  empty, says so, and the field for an address is what there is. *(built; on the page
  since 0.6.0)*
- **R6 — Say who is connected.** Once connected, the header shows the identity and the
  workspace. *(built, 0.1.0; on the page since 0.5.0)*
- **R7 — Switch without restarting.** `w` opens the choice again. Going to another
  workspace leaves nothing of the one that is left: not on the page, and no value held of
  it. *(built; on the page since 0.6.0)*
- **R8 — Straight to a workspace, without the choice.** `caland prod`, or `--profile prod`,
  goes to a workspace the choice would have listed. Every profile can be asked for by its
  name; where a bundle's target has that name too, the name means the profile — the
  target is where caland goes with no name at all. With no name, caland goes straight to
  the one there is no doubt about — the bundle's default, or the only one found — and
  the page asks only otherwise. A name that is not there ends it before it starts, with
  the names that are. *(built, 0.4.0; on the page since 0.6.0)*

## Gone with the terminal app

- **The picker on every launch.** The page asks only when there is doubt (R8).
- **Keeping a sign-in over a profile that is there.** A new name only (R4).

## Not in this spec

- **Finding workspaces through an account** — a cloud and an account id. It was built and
  removed: a round-trip of its own for little gain.
- **Tokens.** caland never asks for one and never stores one; a profile that holds one is
  the Databricks SDK's to read. A sign-in through the browser is kept by the SDK, in its
  own folder (`~/.config/databricks-sdk-py/oauth/`), not by caland. A profile caland keeps
  (R4) is one the SDK for Python reads; it is not what `databricks auth login` writes.

## To decide

Nothing.

## Done when

Built. Held by `tests/test_bundle.py`, `test_profiles.py`, `test_choose.py`,
`test_web_picker.py`, and the browser tests under "which workspace".

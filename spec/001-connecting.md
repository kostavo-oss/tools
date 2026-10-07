# 001 — connecting

**Status:** built, on the page. Written 2026-10-06 from the terminal app at 0.4.1, which
met these first and is not in caland any more ([008](008-the-page.md)); where the page does
a thing differently, [what changed with the page](#what-changed-with-the-page) says so.

## Why

A person has several workspaces and several ways of reaching each. Before anything can be
shown, caland has to know which one, and the person has to trust that it is the one they
meant.

## Requirements

- **R1 — One picker for every way in.** On launch, caland lists the workspaces it can reach
  from three places, and every row says where it came from: an Asset Bundle in the current
  directory, the profiles in `~/.databrickscfg`, and a URL typed in. Every profile that
  has an address is listed, also one at the bundle's address or at another profile's: it
  has its own way of signing in. With no profile that has an address, `DATABRICKS_HOST`
  from the environment is offered as the profile `DEFAULT`. *(built, 0.1.0)*
- **R2 — A bundle's workspace is the default.** With a `databricks.yml` in the current
  directory, its workspace is listed first and selected: the target marked `default: true`,
  or the only target, or the top-level `workspace.host`. A host that still holds a `${…}`
  variable is not a host, and is passed over. *(built, 0.2.0)*
- **R3 — Sign in with a URL, in the browser.** *Add by URL* signs in through the browser
  (OAuth, done by the Databricks SDK). No token is asked for. *(built, 0.2.0)*
- **R4 — Keep a sign-in as a profile.** Ticking *save as profile* writes the host and
  `auth_type = external-browser` to `~/.databrickscfg`, and nothing else. *(built, 0.2.0)*
- **R5 — The picker opens with nothing to show.** With no bundle and no profiles it is empty
  and offers the URL. *(built)*
- **R6 — Say who is connected.** Once connected, the header shows the identity and the
  workspace. *(built, 0.1.0)*
- **R7 — Switch without restarting.** `w` reopens the picker; the new workspace's data
  replaces the old. *(built)*
- **R8 — Straight to a workspace by name.** `caland prod`, or `--profile prod`, skips the
  picker and connects to a workspace the picker would have listed. Every profile can be
  asked for by its name; where a bundle's target has that name too, the name means the
  profile — the target is where caland goes with no name at all. *(built, 0.4.0)*

## What changed with the page

- R1, R5: the picker is the page's first dialog, and is not shown at all when there is no
  doubt which workspace is meant.
- R1, R8: up to 0.6.0 a profile at an address that was already listed — the bundle's, or
  an earlier profile's — was left out, and could not be asked for by name. A bundle's
  target and a profile of one name at one address are two rows, told apart by where each
  was found.
- R4: a sign-in is kept as a profile under a **new** name only — never over a profile that
  is there, which keeps its own way of signing in. The file is written whole or not at
  all. A new file is its owner's alone; one that is there keeps who may read it, which is
  the person's to say; one that is a link stays a link, and the file it points to is what
  is written.
- R7: `w`. Going to another workspace forgets every value held of the one that is left.
- R8: a name that is not there ends it before it starts, with the names that are.

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

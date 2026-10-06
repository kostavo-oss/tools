# Caland

Databricks secrets, by hand: a keyboard-driven page in your browser, served from your own
machine. Browse scopes, secrets and grants; create, edit, move and delete; show and copy
values; put a certificate in from a file.

![Caland with a secret's value shown](img/page-browse.png)

Databricks secrets have an API and a CLI, and no screen. Caland is the screen: everything
about a workspace's secrets at once, a keystroke away, with a value read only when you ask
for it and written nowhere.

## Highlights

- **Three panes** — the scopes you can reach, the secrets of one with when each was last
  changed, and the detail: your access, who else has a grant, and the value once you ask.
- **Everything has a key**, and everything can be clicked. ++tab++ goes from pane to pane.
- **Secrets, with a way back** — create, edit, move, copy, rename and delete; nothing is
  deleted without a ++y++, and ++u++ puts the last one back.
- **Files as they are** — choose a certificate with your system's own file dialog. Caland
  says who it is for and when it expires before it is saved, and stores it byte for byte.
- **Grants** — who has access to a scope, given, changed and removed; what you can reach;
  what somebody else can.
- **`.env` in and out**, and a report of the secrets nobody has changed in a while.
- **A value is shown when asked, and hides itself after 30 seconds.** Nothing is kept: no
  cache, no cookie, no file.
- **Yours only** — the page is served from `127.0.0.1` to you, and answers to nothing else.
- **Read-only when you want it** — `caland prod --read-only` changes nothing.
- **Nothing to set up** — it finds the workspace of a bundle in the current folder and the
  profiles in `~/.databrickscfg`, or signs in to an address through the browser.

## Quick start

=== "uvx"

    ```sh
    uvx caland
    ```

=== "uv tool"

    ```sh
    uv tool install caland
    caland
    ```

Caland starts, opens a tab, and — when there is more than one workspace it could mean —
asks which. ++ctrl+c++ in the terminal stops it and forgets every value it held.

## Next steps

- [Installation](installation.md) — install with uvx, uv tool, or pipx.
- [Connecting](connecting.md) — which workspace, and how it is found.
- [Using the page](page.md) — what it does, its keys, and how it is kept yours.
- [The terminal version](terminal.md) — `caland --tui`, as it was.

---

Caland is named after Pieter Caland (1826–1902), the engineer who designed and built the
Nieuwe Waterweg, the cut through the dunes that gave Rotterdam its way to the sea.

Community project, not affiliated with or endorsed by Databricks.

# 007 — the name and the releases under it

**Status:** done. The rename was merged on 2026-10-06 (pull request #15) and released the
same day as caland 0.5.0, the first release under the name; 0.5.1 and 0.5.2 followed that
day, and 0.6.0 on 2026-10-07. Of what the rename first set out to do, R2–R4 were undone in
0.6.0 ([below](#changed-on-2026-10-07-the-old-name-is-isolinears-again)). One question is
open: D4. Written 2026-10-06, and brought up to where things stand on 2026-10-07.

## Why

Up to 0.4.1 the tool was released as `isolinear`. It is caland now, and people have the old
one installed. The rename must cost them nothing, and the release that carries it is the
first under a name nobody has registered yet.

## Requirements

- **R1 — One name.** The command, the package, the repository and the docs are `caland`.
  *(built, 0.5.0)*
- **R2 — The old name still answers.** *(built, 0.5.0; undone in 0.6.0)*
    - `isolinear` and `iso` are installed beside `caland`. They say the new name on stderr
      and then are caland.
    - The settings in `~/.config/isolinear/` are read until a preference is changed; that
      saves under the new name and leaves the old file.
    - A theme saved under its old name is the theme you get.
    - A profile caland saved as `[isolinear]` in `~/.databrickscfg` is found as before.
- **R3 — The old name is spelled in one place.** `src/caland/formerly.py`, and a test keeps
  it so. When the old name is let go, that module goes and nothing else changes.
  *(built, 0.5.0; undone in 0.6.0)*
- **R4 — `isolinear` gets one last release.** `isolinear-shim/` is a package with no code:
  it depends on caland and says where it went. It is published once, by hand, after caland
  is on PyPI; no workflow builds it. *(written, never published; undone in 0.6.0)*
- **R5 — Released the way stevin and lely are.** A change to `version` in `pyproject.toml`,
  merged to `main`, is the release: the workflow builds, publishes to PyPI through a Trusted
  Publisher, and makes the tag and the GitHub release from the changelog. A push that leaves
  the version alone releases nothing. *(built)*
- **R6 — Apache-2.0**, as every Kostavo tool. *(built, 0.5.0)*

## Changed on 2026-10-07: the old name is isolinear's again

The owner decided to treat caland as the better tool and to leave isolinear as it is. So
R2, R3 and R4 are undone:

- ~~R2 — the old name still answers.~~ caland installs one command, `caland`. `isolinear`
  and `iso` are isolinear's; with both tools installed they no longer collide.
- ~~R3 — the old name is spelled in one place.~~ `formerly.py` is gone; nothing in caland
  reads isolinear's settings.
- ~~R4 — isolinear gets one last release.~~ `isolinear-shim/` is removed and was never
  published: it would have turned isolinear into a pointer at caland, and isolinear is to
  stay what it is.

What that leaves: **isolinear 0.4.1 has two bugs caland fixed** — a rename that only
changes the case deletes the secret, and a `.env` value quoted over several lines is
mis-read. They are fixed in caland only ([To decide](#to-decide)).

## What only the owner could do

- Merge #15. *Done, 2026-10-06.*
- Register a Trusted Publisher for `caland` on PyPI: owner `kostavo-oss`, repository
  `caland`, workflow `release.yml`, environment `pypi`. *Done, 2026-10-06, before 0.5.0.*
- ~~Publish the shim.~~ Not any more (see above).
- Whatever is to happen to `isolinear` on PyPI. *Open: D4.*

## Not in this spec

- **Dropping the old commands** was not part of the rename. It came with the decision of
  2026-10-07 above, after three releases that had them.
- **What the tool should do next.** → [008](008-the-page.md)

## Decided

- **The name.** *(Decided by the owner, 2026-10-06.)*
- **All three tools release the same way.** *(Decided by the owner, 2026-10-06, for lely;
  taken to hold here, and the four releases since were made that way.)*
- **The first caland is 0.5.0**: a new name with nothing lost is a minor release.
  *(Decided by the owner, 2026-10-06, by merging the release as proposed; was D1.)*
- **The author is given by name, without an address**, as for lely. *(Decided by the
  owner, 2026-10-06, by merging the release as proposed; was D2.)*
- **The rename was not released on its own.** `main` already had the first part of the
  page when the release was made, so 0.5.0 carried it as a preview. *(Decided by the
  owner, 2026-10-06, by merging the release as proposed; was D3.)*

## 0.5.0 (2026-10-06)

The owner registered the Trusted Publisher and said to go on. The release was a pull
request of its own (#18), and merging it published it. With it the owner took the writer's
proposals for D1–D3:

- **0.5.0.**
- **The author by name, without an address** — as the owner chose for lely.
- **Not the rename on its own:** `main` already had the first part of the page
  ([008](008-the-page.md)) when the release was prepared, so 0.5.0 carried `caland --page`
  as a preview beside the terminal version, which was unchanged and still the whole tool.
- The notices that `caland` was not on PyPI yet — in the README and two docs pages, put
  there when the rename reached `main` before the name was registered — went with it.

## 0.5.1 (2026-10-06)

Released the same day as 0.5.0, on the owner's word, for one fix above all: a rename that
only changes the case of a secret's name deleted the secret, in the terminal version as
released in 0.4.1 and 0.5.0 ([003, Decided](003-secrets.md#decided)). It also carries the
second part of the page — changing things, and the file picker — still behind `--page`, and
with it one new dependency, `cryptography`.

## 0.5.2 (2026-10-06)

Released on the owner's word for a second fix in what was already out: a `.env` value quoted
over several lines — a private key pasted into the file — was stored as its first line, and
its lines that end in `=` became secrets of their own
([008](008-the-page.md), "the tools", Reviewed). It also carries the page's tools, still
behind `--page`.

## 0.6.0 (2026-10-07)

Released on the owner's word, as a minor version. It is the release in which caland
becomes the page: `caland` opens it, a workspace is chosen on it, and the terminal app, the
old command names and `textual` are gone ([008](008-the-page.md)). A minor version, because
it takes things away: whoever typed `caland` for a terminal app gets a browser tab, and
`caland --tui` says where the terminal app is.

## To decide

- **D4 — isolinear's two bugs.** Left as it is, isolinear 0.4.1 goes on deleting a secret
  renamed to another case of its own name. *The writer's view:* either yank it soon, or
  say so on its PyPI page; both are the owner's to do, with isolinear's credentials.

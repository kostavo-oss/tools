# 007 — the name and the next release

**Status:** prepared on a branch (pull request #15), not merged, not released. Written
2026-10-06.

## Why

Up to 0.4.1 the tool was released as `isolinear`. It is caland now, and people have the old
one installed. The rename must cost them nothing, and the release that carries it is the
first under a name nobody has registered yet.

## Requirements

- **R1 — One name.** The command, the package, the repository and the docs are `caland`.
  *(prepared, #15)*
- **R2 — The old name still answers.** *(prepared, #15)*
    - `isolinear` and `iso` are installed beside `caland`. They say the new name on stderr
      and then are caland.
    - The settings in `~/.config/isolinear/` are read until a preference is changed; that
      saves under the new name and leaves the old file.
    - A theme saved under its old name is the theme you get.
    - A profile caland saved as `[isolinear]` in `~/.databrickscfg` is found as before.
- **R3 — The old name is spelled in one place.** `src/caland/formerly.py`, and a test keeps
  it so. When the old name is let go, that module goes and nothing else changes.
  *(prepared, #15)*
- **R4 — `isolinear` gets one last release.** `isolinear-shim/` is a package with no code:
  it depends on caland and says where it went. It is published once, by hand, after caland
  is on PyPI; no workflow builds it. *(prepared; not published)*
- **R5 — Released the way stevin and lely are.** A change to `version` in `pyproject.toml`,
  merged to `main`, is the release: the workflow builds, publishes to PyPI through a Trusted
  Publisher, and makes the tag and the GitHub release from the changelog. A push that leaves
  the version alone releases nothing. *(built)*
- **R6 — Apache-2.0**, as every Kostavo tool. *(prepared, #15)*

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

## What only the owner can do

- Merge #15.
- Register a Trusted Publisher for `caland` on PyPI — a *pending* one, since the project
  does not exist there yet (checked 2026-10-06: the name is free): owner `kostavo-oss`,
  repository `caland`, workflow `release.yml`, environment `pypi`.
- ~~Publish the shim.~~ Not any more (see above).
- Whatever is to happen to `isolinear` on PyPI.

## Not in this spec

- **Dropping the old commands.** Not before there has been a release with them.
- **What the tool should do next.** → [008](008-the-page.md)

## Decided

- **The name.** *(owner, 2026-10-06)*
- **All three tools release the same way.** *(owner, 2026-10-06, for lely; taken to hold
  here — say if not)*

## As prepared — 0.5.0 (2026-10-06)

The owner registered the Trusted Publisher and said to go on; the release is a pull request
of its own, and merging it is what publishes. In it, the writer's proposals for D1–D3, for
the owner to take by merging or to change first:

- **0.5.0.** The shim was written for it.
- **The author by name, without an address** — as the owner chose for lely.
- **Not the rename on its own any more:** `main` already had the first part of the page
  ([008](008-the-page.md)) when the release was prepared, so 0.5.0 carries `caland --page`
  as a preview beside the terminal version, which is unchanged and still the whole tool.
- The notices that `caland` is not on PyPI yet — in the README and two docs pages, put there
  when the rename reached `main` before the name was registered — go with this release.

After it is on PyPI: the shim, once, by hand, by the owner (R4).

## 0.5.1 (2026-10-06)

Released the same day as 0.5.0, on the owner's word, for one fix above all: a rename that
only changes the case of a secret's name deleted the secret, in the terminal version as
released in 0.4.1 and 0.5.0 ([003, D4](003-secrets.md#to-decide)). It also carries the
second part of the page — changing things, and the file picker — still behind `--page`, and
with it one new dependency, `cryptography`.

## 0.5.2 (2026-10-06)

Released on the owner's word for a second fix in what was already out: a `.env` value quoted
over several lines — a private key pasted into the file — was stored as its first line, and
its lines that end in `=` became secrets of their own
([008](008-the-page.md), "the tools", Reviewed). It also carries the page's tools, still
behind `--page`.

## To decide

- **D4 — isolinear's two bugs.** Left as it is, isolinear 0.4.1 goes on deleting a secret
  renamed to another case of its own name. *The writer's view:* either yank it soon, or
  say so on its PyPI page; both are the owner's to do, with isolinear's credentials.

- **D1 — Which version is the first caland?** The shim is written for `0.5.0`.
  *Proposal:* 0.5.0 — a new name with nothing lost is a minor release.
- **D2 — The address in the package.** `pyproject.toml` gives a personal work address as
  the author's, and PyPI shows it. For lely the owner chose a name without an address.
  *Proposal:* the same here.
- **D3 — When.** *Proposal:* release the rename on its own, soon, before the page: a
  name on PyPI belongs to whoever publishes first, and the people on `isolinear` hear about
  the move from the shim, not from a README they will not read.

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

## What only the owner can do

- Merge #15.
- Register a Trusted Publisher for `caland` on PyPI — a *pending* one, since the project
  does not exist there yet (checked 2026-10-06: the name is free): owner `kostavo-oss`,
  repository `caland`, workflow `release.yml`, environment `pypi`.
- Publish the shim, with `isolinear`'s own credentials.

## Not in this spec

- **Dropping the old commands.** Not before there has been a release with them.
- **What the tool should do next.** → [008](008-the-page.md), [009](009-who-reads-a-secret.md)

## Decided

- **The name.** *(owner, 2026-10-06)*
- **All three tools release the same way.** *(owner, 2026-10-06, for lely; taken to hold
  here — say if not)*

## To decide

- **D1 — Which version is the first caland?** The shim is written for `0.5.0`.
  *Proposal:* 0.5.0 — a new name with nothing lost is a minor release.
- **D2 — The address in the package.** `pyproject.toml` gives a personal work address as
  the author's, and PyPI shows it. For lely the owner chose a name without an address.
  *Proposal:* the same here.
- **D3 — When.** *Proposal:* release the rename on its own, soon, before the page: a
  name on PyPI belongs to whoever publishes first, and the people on `isolinear` hear about
  the move from the shim, not from a README they will not read.

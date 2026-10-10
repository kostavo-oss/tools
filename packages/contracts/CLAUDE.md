# CLAUDE.md

`contracts` (a working name): a consumer's gate for data contracts on Databricks. Three
verbs — `pull`, `check`, `evaluate` — over ODPS product files and ODCS contracts kept in
git, with the Data Contract CLI doing the testing.

**Nothing is built.** `spec/` is the source of truth; read `spec/README.md` first. It
says what the owner decided on 2026-10-09 and lists ten questions under "Still open"
that only the owner answers. The specs are written to the writer's proposals so they
read as a whole — a proposal is not a decision. Do not build on a *(proposed)*
requirement, or on anything marked *to verify*, as if it were settled.

## Rules

- No verb, no command line and no dependency is added before the owner has answered
  the Still open list.
- The name is not chosen. `contracts` is taken on PyPI; `pyproject.toml` carries the
  classifier that makes PyPI refuse an upload, and `release.yml` does not list this
  package. Leave both until the package has its name.
- The standards are Bitol's: ODCS and ODPS. Check a fact about either against the
  published JSON schema or changelog, and link it. Never model a whole standard: read
  the few fields `spec/001` lists, by hand.
- Everything asked of the Data Contract CLI goes through one seam (`spec/002`, R4). It
  is run as a command, not imported (R4a, proposed).
- This package resolves no `${…}` and stevin never substitutes inside a contract
  (`spec/002`, R5).
- No package in this repository imports another. That holds here too: nothing from
  stevin, lely or leeghwater.

## Not wired in yet

`tests/test_spec.py` checks the spec's own shape. It is not run by CI or by
`mise run test`: this package joins the CI matrix, the mise tasks and `release.yml`
with its first code. Run it by hand: `cd packages/contracts && uv run pytest`.

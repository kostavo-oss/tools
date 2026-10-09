<!-- Thanks for contributing to the Kostavo tools! -->

## What & why

<!-- Which tool, what does this change for someone using it, and why? Link any related issue (#123). -->

## Checklist

- [ ] `mise run check` passes (lint, format, types, unit tests — every package)
- [ ] New behaviour has a test; changed plans have refreshed snapshots
- [ ] Anything a user sees in the terminal changed: `mise run screens` (stevin), and the docs say so
- [ ] Any assumption about Databricks behaviour is backed by a live test + docs link, or
      marked `TODO(verify)`
- [ ] The package's `CHANGELOG.md` updated under `## [Unreleased]`
- [ ] The package's own `CLAUDE.md` rules held (stevin: `differ.py` / `planner.py` stayed pure,
      every identifier through `quote_ident()`, no destructive step outside the `destructive`
      risk class)

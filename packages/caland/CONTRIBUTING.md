# Contributing to Caland

Thanks for your interest! Issues and pull requests are very welcome.

## Toolchain

Caland uses [`mise`](https://mise.jdx.dev) to pin tools and the all-Astral
stack — [`uv`](https://docs.astral.sh/uv/) (env / deps / run),
[`ruff`](https://docs.astral.sh/ruff/) (lint + format), and
[`ty`](https://docs.astral.sh/ty/) (type check).

```sh
mise install   # installs the pinned Python + uv (optional but recommended)
uv sync        # creates .venv and installs deps + dev tools
```

## Day-to-day

```sh
uv run caland                  # run it: opens the page
uv run caland --no-open        # print the link instead

uv run pytest                     # test suite
uv run ruff check . && uv run ruff format .   # lint + format
uv run ty check                   # type check
```

All four of these run in CI on every push/PR — please make sure they're green
before opening a PR. New behaviour should come with a test.

## Architecture

The codebase is hexagonal / DDD; the dependency rule is enforced by convention:

```
interface → application → domain ← infrastructure
```

- **`domain/`** — pure model, rules, and ports (`Protocol`s). No UI, no SDK.
- **`application/`** — use-cases (`WorkspaceService`, `OnboardingService`) and
  the in-memory read model. Depends on `domain`, never on `infrastructure`, the
  SDK or the page — and on one library: `files.py` reads what a picked file is
  with `cryptography`, bytes in and facts out, no I/O.
- **`infrastructure/`** — adapters that implement the ports; the *only* place
  that imports the Databricks SDK.
- **`interface/web/`** — the page: a server on this machine (`gate.py` decides which
  requests are answered, `server.py` answers them) and what it serves (`static/`). Talks
  to `application` + `domain` only.
- **`app.py`** — the command, which wires the adapters together.

Keep business logic out of the UI, keep the SDK out of everything but
`infrastructure/`, and tests can substitute the in-memory fakes in `tests/`.

## Tests

- `domain` / `application` are covered by fast unit tests with fake ports.
- The server is asked over real HTTP, and the page is driven in a real browser — Chrome,
  over its debugging pipe (`tests/chrome.py`) — against the in-memory doubles in
  `tests/fakes.py`. No network, no real Databricks. The browser tests skip without Chrome;
  CI has one. Run them after any change to `interface/web/static/`.

## Commits & PRs

- Small, focused PRs are easiest to review.
- Describe the *why*, not just the *what*.
- By contributing you agree your work is licensed under the project's
  [Apache-2.0 License](LICENSE).

## Releasing

Releases are **version-driven**: the `version` in `pyproject.toml` is the single
source of truth, and merging a bump to `main` ships it. No manual tagging.

1. On a branch, bump the version:

   ```sh
   uv version --bump patch   # or: minor / major — edits pyproject.toml + uv.lock
   ```

2. In `CHANGELOG.md`, rename the `## [Unreleased]` heading to `## [X.Y.Z]` (the
   new version) and start a fresh, empty `## [Unreleased]` above it. Those notes
   become the GitHub release body.
3. Open a PR. When it merges to `main`, the [`release`](.github/workflows/release.yml)
   workflow:
   - runs the gate on that commit — lint, format, types and the tests, the page in
     Chrome among them — and publishes nothing if it fails,
   - builds the wheel + sdist and publishes them to **PyPI** (via Trusted
     Publishing — no API token), and
   - creates the **`vX.Y.Z`** git tag and a **GitHub release** with the changelog
     notes.

A merge that doesn't change the version is a no-op, a version that's already tagged or
already on PyPI is skipped, and a version with no section in `CHANGELOG.md` is refused —
so the workflow is safe to re-run. Started by hand, it picks a release up again after a
failure.

> **One-time setup.** Releasing uses [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
> instead of a token. Add a publisher at
> <https://pypi.org/manage/account/publishing/> for repository
> `kostavo-oss/tools`, workflow `release.yml`, and environment `pypi`.

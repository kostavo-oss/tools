# CLAUDE.md

Guidance for Claude / agents working in this repo. **Caland** is a
keyboard-driven Textual TUI for managing Databricks secrets.

## The spec

`spec/` says *what* each part of the tool must do; `docs/` tells a user how to use it, and
`docs/architecture.md` how it is built. Read the spec of a part before changing it, and
change the spec in the same pull request when the behaviour changes. Where the spec, the
docs and the code disagree, say so instead of silently picking one. Don't build past a
"To decide" that is still open — those are the owner's to answer.

## The page

Caland is moving from the terminal to a page in the browser (`spec/008-the-page.md`). Until
the page does everything the terminal version does, it is behind `caland --page`; the
terminal version is **frozen** — fix what is broken in it, add nothing.

- The page is `src/caland/interface/web/`: `gate.py` (which requests are answered — pure),
  `server.py`, `views.py` (what the page is told — pure), `opening.py`, and `static/`.
- The gate is the security of it. A change there, or a new thing the server answers, gets
  a test in `tests/test_web_gate.py` or `test_web_server.py`, and a second pair of eyes.
- No cookie, no script or style written into the page, nothing from another origin, no
  `innerHTML`: what a workspace says is text. Tests hold each of these.
- `tests/test_page_in_a_browser.py` drives the real page in Chrome (`tests/chrome.py`, over
  Chrome's debugging pipe — no package). It skips without Chrome; CI has one. Run it after
  any change to `static/`.
- Only the SDK: no query, no warehouse, no system table (`spec/000`).

## Toolchain — use these, nothing else

This project is **all-[Astral](https://astral.sh)**, version-managed by
**[mise](https://mise.jdx.dev)**. Reach for exactly these four tools:

| Tool | Role | How it's provided |
|------|------|-------------------|
| **mise** | Provisions the toolchain (Python 3.14, uv) | `mise.toml` → `mise install` |
| **uv** | Env, deps, and command runner (`.venv`) | installed by mise |
| **ruff** | Lint **and** format | `uv run ruff` |
| **ty** | Type checking | `uv run ty` |

**Rules:**

- **Never** use system `python`/`python3`, bare `pip`, `virtualenv`, `poetry`,
  `pipenv`, `conda`, `black`, `flake8`, `isort`, `mypy`, or hand-rolled `.venv`s.
  uv replaces pip/virtualenv; ruff replaces black/flake8/isort; ty replaces mypy.
- **Always** invoke project tools through `uv run …` (uv comes from mise, so it
  resolves the right Python and the project `.venv` automatically).
- Need a one-off dependency for a script (e.g. an image lib for mockups)?
  Use `uv run --with <pkg> python script.py` — **do not** install it into the
  project or create a separate venv.
- Add a real dependency with `uv add <pkg>` (runtime) or `uv add --dev <pkg>`
  (dev tooling). This edits `pyproject.toml` + `uv.lock` — never edit `.venv`
  by hand.

> If `uv` isn't on `PATH` in a non-interactive shell, it's because mise hasn't
> activated. Use `mise exec -- uv …` (or `eval "$(mise activate bash)"` first).

## Commands

```sh
mise install            # one-time: install Python + uv per mise.toml
uv sync                 # create/refresh .venv from pyproject + uv.lock (incl. dev group)

uv run caland        # run the app
uv run pytest           # tests (core units + UI via Textual Pilot)
uv run ruff check .     # lint
uv run ruff format .    # format
uv run ty check         # type check
```

**Before committing**, all of these must pass: `uv run ruff check . && uv run ruff format --check . && uv run ty check && uv run pytest`.

## Architecture

Hexagonal / DDD — dependencies point **inward**, all I/O sits behind domain
ports, so the domain is unit-testable with no network. Respect the layering:

```
src/caland/
  domain/          model, rules + ports (SecretStore, WorkspaceConnector, ProfileStore)
  application/     use-cases (WorkspaceService, OnboardingService) + read model
  infrastructure/  adapters — the ONLY place the Databricks SDK is imported
  interface/       Textual presentation — no business logic, no infra imports
  app.py           composition root (wires it all together)
```

- The `interface/` layer never touches the SDK or infra directly — it talks to
  `application/` services. The `domain/` layer imports nothing outward.
- UI theming lives in `interface/theme.py` (Textual `Theme`s) and
  `styles.tcss` (Textual CSS).

## Conventions

- Python ≥ 3.11 syntax (`from __future__ import annotations` is used throughout).
- ruff: line length **90**, rules `E,F,I,UP,B,SIM` (see `pyproject.toml`).
- ty must report no errors.
- Keep blocking I/O off the UI thread — services run in worker threads via
  `asyncio.to_thread` (see `interface/screens/main.py`).

## The rename

Caland was `isolinear` up to 0.4.1 — renamed on its way into the Kostavo tools
(`kostavo-oss`: stevin, lely, caland). `src/caland/formerly.py` is the one module
that spells the old name, and `tests/test_formerly.py` keeps it that way. It holds what
still answers to it: the old settings directory (read until a file exists under the new
name, never written), the old theme names (a saved `isolinear-violet` is
`caland-violet`), and the `isolinear` and `iso` commands (still installed; they say the
new name on stderr and run caland). `isolinear-shim/` is the last `isolinear` release
for PyPI — it installs caland — and no workflow publishes it.

The TUI snapshots and `docs/img/*.svg` cannot be search-and-replaced: their element ids
are hashed from the window title. Regenerate them (`--snapshot-update`, and
`docs/redesign/capture.py` with its `cp` lines).

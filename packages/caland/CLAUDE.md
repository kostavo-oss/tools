# CLAUDE.md

Guidance for Claude / agents working in this repo. **Caland** manages Databricks
secrets by hand: a keyboard-driven page in the browser, served from the person's
own machine.

## The spec

`spec/` says *what* each part of the tool must do; `docs/` tells a user how to use it, and
`docs/architecture.md` how it is built. Read the spec of a part before changing it, and
change the spec in the same pull request when the behaviour changes. Where the spec, the
docs and the code disagree, say so instead of silently picking one. Don't build past a
"To decide" that is still open — those are the owner's to answer.

## The page

Caland is a page in the browser (`spec/008-the-page.md`), served from the person's own
machine. There is no terminal version: the terminal app it was until 0.6 is `isolinear`, a
separate tool on PyPI that the owner leaves as it is. Caland installs no command under that
name and reads none of its settings — don't bring either back.

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
- A change goes through `WorkspaceService`, which takes one at a time and asks the
  workspace what is there *now* before it writes, moves or puts back. Two names that differ
  only in case are one name (`domain.same_name`): Databricks says so.
- A request about a workspace says which one it means (`gate.WORKSPACE_HEADER`, the `turn`
  the state gave) and the server takes `Page.current()` once per request: nothing asked of
  one workspace is done to, or shown under, another. On the page `ask()` drops an answer
  that comes after the page has moved on, and `inTurn` a change that was queued before.
- `~/.databrickscfg` holds tokens: it is written through `profiles._replace` only, and the
  page keeps a profile with `add`, which never writes over one that is there.
- One dialog is open at a time (`open()` in `page.js`) — but a question over the grants —
  and a dialog asked for before an `await` checks `moment` after it: what comes back late
  does not open over what the person has gone on to do. `y` must only ever reach the
  question that is showing.
- A file is somebody else's bytes: `application/files.py` never does work the file sets
  the size of, and never raises. Nothing there opens a PKCS#12 bundle.

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
- Need a one-off dependency for a script? Use `uv run --with <pkg> python script.py`
  — **do not** install it into the project or create a separate venv.
- Add a real dependency with `uv add <pkg>` (runtime) or `uv add --dev <pkg>`
  (dev tooling). This edits `pyproject.toml` + `uv.lock` — never edit `.venv`
  by hand.

> If `uv` isn't on `PATH` in a non-interactive shell, it's because mise hasn't
> activated. Use `mise exec -- uv …` (or `eval "$(mise activate bash)"` first).

## Commands

```sh
mise install            # one-time: install Python + uv per mise.toml
uv sync                 # create/refresh .venv from pyproject + uv.lock (incl. dev group)

uv run caland           # run it: opens the page (--no-open prints the link)
uv run pytest           # tests (units, the server over HTTP, the page in Chrome)
uv run ruff check .     # lint
uv run ruff format .    # format
uv run ty check         # type check
```

**Before committing**, all of these must pass: `uv run ruff check . && uv run ruff format --check . && uv run ty check && uv run pytest`.

The tasks in `mise.toml` have the same names in every Kostavo tool (`mise tasks` lists
them): `check` is the gate, `fix` repairs what ruff can, `ci` is everything CI runs,
`test:lowest` runs the tests on the lowest dependencies, `clean` removes build output. An
assistant runs them through mise's MCP server, which `.mcp.json` sets up (`run_task`);
`dev` and `docs` keep running until they are stopped, so they are not for an assistant to
start and wait on. No secret goes into `mise.toml`: what stands under `[env]` is shown to
an assistant that asks mise for it.

`mise.toml`, `.mcp.json`, the workflows and the packaging come from
[the template](https://github.com/kostavo-oss/template-python); `.copier-answers.yml` says
which version this tool has taken, and `uvx copier update` brings the next. What every
tool shares is changed there, not here.

## Architecture

Hexagonal / DDD — dependencies point **inward**, all I/O sits behind domain
ports, so the domain is unit-testable with no network. Respect the layering:

```
src/caland/
  domain/          model, rules + ports (SecretStore, WorkspaceConnector, ProfileStore,
                   BundleStore, SettingsStore)
  application/     use-cases (WorkspaceService, OnboardingService) + read model
  infrastructure/  adapters — the ONLY place the Databricks SDK is imported
  interface/web/   the page: a server on this machine, and what it serves
  app.py           the command (reads what was asked, wires it all together)
```

- The `interface/` layer never touches the SDK or infra directly — it talks to
  `application/` services. The `domain/` layer imports nothing outward.
- The page's look is `interface/web/static/page.css`: lely's page, taken over — the
  same colours and what they mean. Light or dark is the system's.

## Conventions

- Python ≥ 3.11 syntax (`from __future__ import annotations` is used throughout).
- ruff: line length **90**, rules `E,F,I,UP,B,SIM` (see `pyproject.toml`).
- ty must report no errors.
- The server answers each request on a thread of its own; a workspace is read in the
  background (`application/loading.py`). Nothing the page asks may wait on a workspace
  it did not ask about.

## The name

Caland was `isolinear` up to 0.4.1, and a terminal app until 0.6. `isolinear` is still on
PyPI as that terminal app; the owner leaves it as it is (`spec/007`). Nothing in this
repository answers to the old name any more.

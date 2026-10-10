# CLAUDE.md

`caland`: Databricks secrets by hand. A small server on the person's own machine and a
hand-written page in the browser, talking to Databricks only through the SDK.

## Where a fact lives

One place per fact. Write a fact where it lives, and link to it from anywhere else.

| The fact | Its one place |
|---|---|
| What caland is for, when not to use it, when it is no longer needed | `README.md` |
| What must be true of the code | `RULES.md`: numbered rules, each with the tests that hold it |
| Why it is so, and what was turned down | `DECISIONS.md`: a log, appended to and never edited |
| What ran on a real workspace, and what did not | `docs/tried.md` |
| How to use it | `docs/`, and only there: the README has a quickstart and links to the pages |
| What changed for a user, per release | `CHANGELOG.md` |
| What Databricks or the SDK does that the code leans on | the docstring of the code or the test that leans on it |
| An idea that is wanted and not built | a GitHub issue |
| How it came to be | git |

There is no `spec/` folder, and none comes back. `SECURITY.md` is the repository's
policy page and repeats what `docs/security.md` says; `tests/test_repository.py` holds
the two together.

## Rules of working

- **A change to behaviour changes its rule, in the same pull request.** Find the rule in
  `RULES.md`, change it or add one with the next number of its area, and name the tests
  that hold it under `Held by:`. Each of those tests cites the identifier in its
  docstring. A number is never reused. `tests/test_rules.py` at the root of the
  repository fails when a citation, a rule and a test disagree.
- **A rule is checked against the code before it is written, and states the whole
  promise.** What the code does not keep yet gets an issue, and the rule says
  `Not kept yet:` with its number.
- **A decision goes in `DECISIONS.md` only with its reason, or with what was turned
  down.** No entry is edited: a new one names the one it supersedes.
- **A run on a workspace is recorded in `docs/tried.md`**, with its date, and nowhere
  else. Nothing under "Not yet" there is written about as if it had run.
- The gate is the security of it (`GATE`). A change to `gate.py`, or a new thing the
  server answers, gets a test in `tests/test_web_gate.py` or `tests/test_web_server.py`,
  and a second pair of eyes.
- What a workspace says is text: no `innerHTML`, no script or style written into the
  page, no cookie, nothing from another origin (VIEW-9, VIEW-10, GATE-9).
- Run `tests/test_page_in_a_browser.py` after any change to `static/`. It needs Chrome
  and is skipped without one.
- `base.css` is the look caland shares with lely's page and stevin's. Change it in all
  three packages, in one pull request: a test at the root holds the copies equal.
  `page.css` is caland's own.
- A change to a workspace goes through `WorkspaceService` (SEC-11), and a request about
  a workspace says which one it means (WSP-10). On the page `ask()` drops an answer that
  comes late and `inTurn` a change that was queued before.
- One dialog is open at a time (`open()` in `page.js`), and a dialog asked for before an
  `await` checks `moment` after it (ASK-2).
- `~/.databrickscfg` holds tokens. It is written through `profiles._replace` only, and a
  profile is kept with `add`, which never writes over one that is there (KEPT-2, WSP-7).
- A file is somebody else's bytes: `application/files.py` never raises and never opens a
  PKCS#12 bundle (FILE-3, FILE-4).
- No value is printed, logged or written to a file (VAL-1).
- Nothing in the package answers to the name `isolinear`, and caland has no terminal
  version (CMD-1). Don't bring either back.
- Small pull-request-sized commits, conventional commit messages. A release is a pull
  request of its own, opened when the owner says.

## Layout

```
src/caland/app.py               the command: reads what was asked, wires it together (CMD)
src/caland/domain/              the model, the rules and the ports; imports nothing outward
src/caland/application/         use-cases: WorkspaceService, OnboardingService, Loader,
                                the read model, .env, and what a picked file is
src/caland/infrastructure/      the adapters; the only place the Databricks SDK is imported
src/caland/interface/web/       gate.py (which requests are answered), server.py,
                                views.py (what the page is told), opening.py
src/caland/interface/web/static page.html, base.css, page.css, page.js
tests/test_<part>.py            unit tests, and the server asked over real HTTP
tests/test_page_in_a_browser.py the real page, driven in Chrome through tests/chrome.py
tests/fakes.py                  the stand-in workspace everything is tested against
tests/test_layers.py            the layering, read from the source (CODE)
tests/test_repository.py        the shape of the package itself
docs/                           the pages of the site, listed in mkdocs.yml
```

The server answers each request on a thread of its own, and a workspace is read in the
background. Nothing the page asks may wait on a workspace it did not ask about.

## Commands

uv and ruff, as in every package of this repository. Never pip, black or mypy.

```sh
uv sync                          # once, anywhere in the repository
uv run caland --no-open          # run it; prints the link
uv run pytest                    # from packages/caland: its tests
uv run ty check                  # from packages/caland: its types
uv run ruff check . && uv run ruff format --check .   # from the root: every package
uv run pytest tests              # from the root: the rules file, and what holds across packages
uv run --group docs mkdocs build --strict             # from the root: the site
```

`mise run check` at the root runs the gate for every package. Python is 3.11 and later,
with `from __future__ import annotations`; lines are 90 long.

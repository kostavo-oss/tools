# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **The page has the tools.** On `caland --page`: fill a scope from a `.env` file (`i`) and
  copy one as `.env` (`x`), the report of stale secrets (`A`), what you can reach (`a`) and
  what somebody else can (`P`), sorting (`s`, `S`), and "forget every value" from the keys.
  An import says what it will overwrite before it does, and where it stopped if it does.
  The `f` toggle and the stale report's number of days are kept between runs.

### Fixed

- **A `.env` value quoted over several lines is read whole.** Read line by line, a private
  key's own lines — some end in `=` — were taken for secrets of their own, and the key was
  stored as its first line. An import reads such a value as one now, and refuses a file
  whose quote is never closed. On the page and in the terminal version.
- A value ending in a newline keeps it when a scope is copied as `.env` and read back.
- A `#` comment after a value in a `.env` file is no longer part of the value.

## [0.5.1] - 2026-10-06

### Added

- **The page changes things.** `caland --page` now does what the terminal version does to a
  workspace: new and edited secrets (`n`, `e`), delete with a deliberate `y` and the last one
  put back (`d`, `u`), move, copy and rename (`m`), grants (`p`), and scopes made and deleted
  (`N`, `d`). `--read-only` holds on the page as it does in the terminal.
- **A file picker, and files as they are.** On the page a value can be a file, chosen with
  your system's own dialog or dropped on the form. Before it is saved the form says what it
  is — for a certificate: who it is for, who issued it, when it expires. A file is stored
  byte for byte, so a PKCS#12 bundle or a DER certificate goes in and comes out the same;
  until now a value could only be text.

### Fixed

- **Renaming a secret to the same name in another case no longer deletes it.** To
  Databricks `API-KEY` and `api-key` are one secret, so a rename that only changed the case
  wrote the secret and then removed it — altogether. It is refused now, in the terminal
  version and on the page.
- Reading a scope again (`r`) lets go of the values read from it before, so that a value
  changed elsewhere is not shown, or moved, as it used to be.

### Changed

- `cryptography` is a dependency now: it is what reads a certificate you pick.

## [0.5.0] - 2026-10-06

### Added

- **`caland --page` — a preview of Caland as a page in your browser.** It is served
  from your own machine and nowhere else, and looks like the rest of the family. This
  first part reads: browse scopes, secrets and grants, filter, show and copy a value,
  copy how to reach a secret from code. It changes nothing yet — for everything else,
  `caland` without `--page` is the terminal version, as before.

  `tab` goes from pane to pane, arrows move inside one, and every action has a key.
  The server answers only to its own page at its own address, and to nothing without
  the session's key; a value is in the page only while it is shown.
  [The page](https://kostavo-oss.github.io/caland/page/) has the whole of it.

### Changed

- **Isolinear is now Caland.** The command is `caland`, the package on PyPI is
  `caland`, and the repository and the docs are at `kostavo-oss/caland`. It is
  named after Pieter Caland — the engineer of Rotterdam's waterway to the sea —
  and it is one of a family of tools now (stevin, lely, caland), each with an
  engineer's name.

  Nothing you had is lost, and nothing changes in a workspace:

  - `isolinear` and `iso` are still installed. They say the new name on stderr
    and then open the app, so a habit or a script keeps working.
  - Settings in `~/.config/isolinear/settings.json` are read until you change a
    preference; that saves `~/.config/caland/settings.json`, and the old file
    is left where it is.
  - The four built-in themes are `caland`, `caland-violet`, `caland-amber`
    and `caland-phosphor`. A theme saved under its old name is still the theme
    you get.
  - A profile saved without a name is now written as `[caland]` in
    `~/.databrickscfg`; an existing `[isolinear]` section is found as before.

- **The license is Apache-2.0**, the same as every other Kostavo tool. Releases
  up to 0.4.1, as `isolinear`, were and remain MIT.

## [0.4.1] - 2026-07-03

### Fixed

- Small terminals (e.g. VS Code's integrated-terminal panel) no longer break
  the UI: dialog tables (permissions, stale audit, search, …) size relative to
  the viewport instead of a fixed cap, so their rows can't be clipped away;
  the help scrolls instead of collapsing to one line; and the breadcrumb's
  `secret:` segment outranks the identity chip on narrow widths, so the user
  email can no longer take the secret name's place in the top bar.
- Help rows no longer wrap onto two lines: the help card is wider and the
  longest descriptions were tightened.

### Added

- Plain-letter fallbacks for chords VS Code's integrated terminal keeps for
  itself: `F` = search everywhere (ctrl+f), `P` = command palette (ctrl+p).
  Documented alongside the `terminal.integrated.commandsToSkipShell` knob.

## [0.4.0] - 2026-07-02

### Added

- **Multiline secret values**: the secret form gained a file field — point it
  at `~/certs/key.pem` and the file's content becomes the value. The route for
  PEM keys, certificates, and JSON blobs a single-line input can't take.
- **Move / copy / rename** (`m`): one dialog covering all three — target scope
  (Key Vault-backed scopes aren't offered) + key + a "keep the original"
  checkbox. Moves are undo-able with `u`, like deletes.
- **Bulk .env import/export**: import every KEY=VALUE pair from a `.env` file
  into a scope (with an overwrite count in the confirm); export a scope as a
  keys-only `.env` template, or with values behind a confirm — clipboard only,
  never disk. Multiline values round-trip via JSON quoting.
- **Who has access** (palette): fuzzy-search any principal across every
  scope's ACLs, highest privilege first; enter jumps to the scope.
- **Direct connect**: `isolinear prod` / `isolinear --profile prod` skips the
  picker and connects to a discovered workspace by name.
- **Persisted preferences**: theme, the `f` scope toggle, and the audit
  threshold survive restarts (`~/.config/isolinear/settings.json`,
  XDG-aware, corrupt-tolerant).

### Changed

- One shared sort implementation (`SortState`) now drives all seven sortable
  tables — identical behavior, no more copy-paste drift.

### Internal

- A drift-guard test asserts every browse-screen binding appears in the help.
- CI gained a docs job (`mkdocs build --strict` + the screenshot pipeline)
  and visual snapshot tests (pytest-textual-snapshot) with committed
  baselines for the browse, login, and audit screens.

## [0.3.0] - 2026-07-02

### Added

- **Global search** (`ctrl+f`): fuzzy-match `scope/key` across the whole
  workspace, served instantly from the warmed cache; enter jumps the browser
  straight to the secret.
- **Stale-secret audit** (`A`): every secret not updated within the threshold,
  oldest first. `t` cycles the window through 30/90/180/365 days, enter jumps
  to the secret, `c` copies the table as markdown for a rotation ticket. The
  browser's Age column tints amber when a secret is overdue.
- **Copy as code reference** (`C`): copy `dbutils.secrets.get(...)`, the
  `{{secrets/scope/key}}` Spark-conf form, or the CLI command — without
  touching the value.
- **Undo delete** (`u`): the value is captured just before a secret delete, so
  the delete is restorable from the toast.
- **Read-only mode** (`isolinear --read-only`): browse, reveal, search, and
  copy with every mutation disabled; the header shows a read-only marker and
  the permissions editor becomes view-only.
- **Secret hygiene**: a revealed value hides itself after 30 seconds, and a
  "Forget revealed values" palette command purges every cached value from
  memory.
- Enter on a secret reveals/hides it (scopes keep enter = drill in).

### Changed

- Filters are visible and durable: a `⌕ query n/m` chip sits above a filtered
  table, the filter survives refreshes (a new scope clears the secrets
  filter), reopening `/` prefills the query, esc clears it, and ↑/↓ move the
  selection while typing.
- Sorting is consistent everywhere: `s` advances to the next column
  (ascending), `S` reverses — on the browser panes, auth overview,
  permissions editor, and login list alike.
- The detail pane scrolls by keyboard, so long revealed values are reachable;
  its ACL table is passive (header clicks still sort).
- Delete follows the selection like the footer says: secret from the
  secrets/detail panes, scope from the scopes pane — and the scope
  confirmation names its secret count.
- Azure Key Vault-backed scopes disable secret create/edit/delete up front
  (with an explaining hint) instead of failing at the API.
- Startup warming runs concurrently (bounded at 8), so large workspaces load
  in seconds.

### Fixed

- `q` no longer quits the app from inside dialogs; it quits from the browse
  and login screens only.
- Editing a secret with an empty value no longer silently wipes it.
- Removing an ACL now asks for confirmation, and warns when the grant you're
  revoking is your own.
- The delete confirmation no longer accepts `d` — a vim-twitch double-`d`
  can't slip past the guard; confirming is a deliberate `y`.
- Table rebuilds no longer emit a stale row-0 highlight that could steal the
  selection (and collapse a revealed value) during a refresh or sort.

## [0.2.8] - 2026-07-01

### Added

- Scopes list now shows only the scopes you can actually access, cutting the
  noise in workspaces full of other teams' scopes. Access is judged by whether
  your secrets list loads (which needs READ) — not by the ACLs, which you often
  can't read without MANAGE — so scopes you hold READ/WRITE on aren't wrongly
  hidden. Press `f` to toggle between "only mine" and every scope in the
  workspace. "Your access" now reads READ (not "none") for a scope you can list
  but whose ACLs are off-limits.

### Fixed

- Modal dialogs (new/edit secret, grant/change permission, and every other
  dialog) no longer show rendering artifacts — a garbled title and blank
  fields — on real terminals. The dialog card had no opaque fill, so the
  translucent backdrop let the dimmed main screen bleed through it; the card
  is now solid. Guarded by a test that asserts every modal card is opaque.

## [0.2.7] - 2026-07-01

### Changed

- Form polish: a fixed field — the key when editing a secret, the principal when
  editing an ACL — now reads as clearly read-only (muted, flat) instead of
  looking editable. The grant/change-permission dialog also shows the scope it
  applies to (violet, matching the scope-permissions modal's frame).
- Help: the sort line now fits on one row ("Sort the focused table / click a
  column") instead of wrapping mid-parenthesis.

## [0.2.6] - 2026-06-30

### Changed

- Consistency: the authorization overview (`a`) and the scope-permissions modal
  (`p`) tables are now sortable too — `s` or a header click, with a ↑/↓
  indicator — like every other table in the app. Scope names in the
  authorization overview are also coloured violet to match the rest of the UI.

## [0.2.5] - 2026-06-30

### Changed

- Detail-pane colour-coding: the secret key is now cyan (echoing the secrets
  section), the scope is violet (echoing the scopes section), and a revealed
  value has its own green "live" colour.
- The detail pane's permissions are now a proper sortable table (Principal /
  Access), like the scopes and secrets tables — reach it with Tab and sort with
  `s` or a header click (privilege-coloured, sorted by access by default). The
  detail pane is now focusable, and the footer reflects your current selection
  rather than which pane has focus.

### Fixed

- "Your access" now resolves **group-based** permissions. It takes the highest
  permission granted to you, to the `users` group (everyone), or to any group
  you belong to (fetched from your SCIM group memberships) — so access via a
  group no longer shows as "none". It also no longer wrongly treated every user
  as a member of the `admins` group.

## [0.2.4] - 2026-06-30

### Changed

- Onboarding polish: dropped the redundant "Databricks secret management"
  tagline (just the Isolinear mark over the workspace list now); the workspace
  picker is sortable (press `s` or click a column header); and the Add by URL /
  Quit buttons show their access keys (`a` / `q`).

### Fixed

- The scopes pane now scales out to fit long scope names. A fixed `max-width`
  cap was clamping it even when the terminal had plenty of room, truncating long
  names and clipping the secret-count column; the cap is now proportional (50%
  of the row) so it grows with the terminal but never dominates a narrow one.
- The onboarding workspace picker no longer clips the host or source columns.
  Hosts were hard-truncated to 30 characters (even on a wide terminal); now the
  full host shows and the login card sizes to fit its content, so long
  Databricks hosts and the "· default" tag stay fully visible.

## [0.2.3] - 2026-06-30

### Changed

- Panel widths: the scopes and secrets panes each size to their own content
  (as wide as they need, no wider), and the detail pane fills the remaining
  space — so the inspector gets the room instead of the secrets list hogging it.

## [0.2.2] - 2026-06-30

### Fixed

- The scopes pane now sizes to the longest scope name (within bounds), so long
  scope names are no longer clipped while the detail pane keeps a usable width.
- Docs screenshots refreshed; the screenshot export now has a dark background
  (no white margin) so it reads well in dark-mode docs.

## [0.2.1] - 2026-06-30

### Fixed

- The three browser panes now share the row's width responsively: the detail
  pane grows with the terminal (and scopes flexes within bounds) instead of the
  secrets pane absorbing all the slack while detail stayed pinned narrow.

## [0.2.0] - 2026-06-30

A full UI redesign and an onboarding rework.

### Added

- **Graphite** — a calm, near-neutral default theme. Each browser section
  (scopes / secrets / detail) carries its own accent colour on its border,
  title, and selection; the violet / amber / phosphor skins remain optional.
- **Asset-bundle onboarding** — a `databricks.yml` in the working directory is
  parsed and its target workspace is offered as the pre-selected default.
- **Sortable tables** — click a column header or press `s` to sort the scopes
  and secrets tables, with a ↑ / ↓ indicator on the active column.
- **Permission colour-coding** — READ / WRITE / MANAGE are coloured by privilege
  across the permissions modal, the authorization overview, and the detail pane.
- An example `examples/databricks.yml` so the bundle source is easy to try, and a
  `CLAUDE.md` documenting the toolchain.

### Changed

- Onboarding is a single workspace picker that labels where each workspace comes
  from (`databricks.yml` / `~/.databrickscfg` / a typed URL).
- The detail pane is a fuller inspector: identity → your access + the scope's
  ACLs → the value.
- Modals share one layout — title, content, actions at the bottom; key-driven
  dialogs show a key hint, button dialogs put the shortcut in the button.
- The authorization overview drops the redundant Write / Manage columns and
  sorts scopes by your effective privilege.
- Calmer chrome throughout: no LCARS glyphs, colour blocks, or the "decrypt"
  reveal animation; quiet status copy.

### Removed

- Account-level workspace discovery (pick a cloud, paste an Account ID). Connect
  via a saved profile, an asset bundle, or a workspace URL instead.

### Fixed

- The scope-list selection highlight never rendered (the stylesheet used the
  wrong `--highlight` class instead of Textual's `-highlight`).
- The revealed-value card's right border was clipped by the detail-pane scroll
  gutter.
- Secret values, scope/secret/principal names, and error messages containing
  square brackets no longer crash rendering (they were parsed as Rich markup).
- Refreshing or sorting the scopes table no longer resets the selected secret or
  hides a revealed value; sorting the secrets table keeps the cursor in place.
- A `databricks.yml` whose default target has a templated host still falls back
  to the top-level `workspace.host`.
- The footer no longer goes stale after drilling into a scope with Enter.

## [0.1.0]

Initial release.

### Added

- Three-pane terminal browser for Databricks scopes, secrets, and ACLs.
- Onboarding: OAuth browser login by workspace URL, account-level workspace
  discovery (AWS / Azure / GCP), and saved `~/.databrickscfg` profiles.
- Create / edit / delete secrets, create / delete scopes, and manage scope
  permissions (ACLs).
- Reveal & copy secret values (fetched lazily; never bulk-loaded).
- Authorization overview of your effective permission per scope.
- Fuzzy filter (`/`), command palette (`ctrl+p`), vim + arrow navigation.
- Pre-loads and caches scopes/secrets/ACLs on startup.
- Three switchable themes (violet, amber Okudagram, phosphor green).

[Unreleased]: https://github.com/kostavo-oss/caland/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/kostavo-oss/caland/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/kostavo-oss/caland/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/kostavo-oss/caland/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/kostavo-oss/caland/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/kostavo-oss/caland/compare/v0.2.8...v0.3.0
[0.2.8]: https://github.com/kostavo-oss/caland/compare/v0.2.7...v0.2.8
[0.2.7]: https://github.com/kostavo-oss/caland/compare/v0.2.6...v0.2.7
[0.2.6]: https://github.com/kostavo-oss/caland/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/kostavo-oss/caland/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/kostavo-oss/caland/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/kostavo-oss/caland/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/kostavo-oss/caland/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/kostavo-oss/caland/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/kostavo-oss/caland/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/misja-pronk/isolinear/releases/tag/v0.1.0

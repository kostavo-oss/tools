# 008 — the page

**Status:** built (see the *As built* sections). It is what caland is: the terminal version
was removed on 2026-10-07. Its shape is decided ([Decided](#decided)). Written
2026-10-06 from the owner's direction of that day; what is the owner's and what is the
writer's is marked.

## Why

A terminal draws text in a grid. That is enough to browse, and not enough for what a person
working with secrets needs to *see*: who reaches a secret and through which group, when it
was last read, what a certificate is before it goes in. It has no file dialog, so a
certificate goes in by typing a path. And it looks like nothing else in the family.

The owner's direction *(2026-10-06)*: caland becomes "a local tool with a html", so that it
can be better to use; it is "only for people working with secrets in Databricks"; it has a
file picker "so that people can navigate to certificates"; it follows the design language
lely has; and it stays fast — "we need to keep it performant and working".

## The shape

**`caland` starts a small server on this machine and opens a page in the browser.** The
page is caland: the scopes, the secrets, the grants, every action. Stopping caland stops the
server and forgets everything it held.

Nothing leaves the machine but the calls to Databricks that the terminal version makes
today. There is no hosted caland, no account, no telemetry.

Two other shapes were looked at *(the writer's comparison)*:

| | A page from a local server | A window of its own | The terminal app, served |
| --- | --- | --- | --- |
| What it is | Browser tab on `127.0.0.1` | HTML in a native window (pywebview) | `textual serve` |
| lely's look | yes | yes | no — it is the terminal, in a tab |
| File dialog | the browser's own | the system's own | none |
| Install | nothing new | a web view per system; awkward on Linux | nothing new |
| Over SSH, in a dev container | yes, with a forwarded port | no | yes |
| What it costs | a local port to defend (R9) | a heavier package, a second thing to trust | delivers none of the above |

**The first.** *(owner, 2026-10-06)* Nothing in it should stand in the way of the second
wrapping the same page later, if the browser turns out to be the wrong home for it.

## Requirements

- **R1 — Everything the terminal version does, and that first.** Specs 001–006 hold for the
  page: the same actions, the same confirmations, the same refusals. The first page does
  that, with R4–R6 for files — nothing else new before it. *(the order is the owner's)* The page is a second way in to the
  same core — only `interface/` is new; `domain/`, `application/` and `infrastructure/` are
  what they are today. *(proposal)*
- **R2 — It looks like lely's page.** The same colours and what they mean (green for made,
  amber for changed or waiting, red for destructive, blue for run), the same type, the same
  small capital headings, hairlines and pills, light or dark by the system. READ, WRITE and
  MANAGE are pills. Someone who has read a lely plan knows where to look. *(owner asked;
  the detail is the writer's)*
- **R3 — Still by keyboard.** Every action keeps its key — `/` to filter, `j` `k` to move,
  `n` `e` `d` `m`, `space` to show, `c` to copy — and `?` lists them. What the page adds is
  that everything can also be clicked. *(proposal)*
- **R3a — Tab goes from pane to pane, not from button to button.** A browser's own rule —
  tab stops at every button — makes a page of buttons a long walk, and never reaches a list
  at all. So: *(owner found the first mock-up wanting here, 2026-10-06; the rules are the
  writer's, and are what the mock-up now does)*
    - **Each pane is one stop.** `tab` goes scopes → secrets → detail, `shift` `tab` back,
      as it did in the terminal. The filter and the buttons above are stops before them.
    - **Arrows move inside a pane, and across.** `↑` `↓` or `j` `k` within; `←` `→` or `h`
      `l` to the next pane; `g` `G` to a pane's ends. In the detail they walk its buttons.
      Nobody needs `tab` at all.
    - **`space` and `enter` belong to what has the keyboard**: on a secret they show its
      value, on a button they press that button. Letters act on the selected secret from
      anywhere that is not a text field.
    - **The keyboard is never nowhere.** The page opens with it in the scopes. Closing a
      dialog, leaving the filter, or a change that redraws the page puts it back where it
      was.
    - **One mark for where it is.** Blue: a bar on the row, a ring on a button, and the
      pane's heading at full strength. A ring shows only when a button was reached by key.
    - **`tab` is not caught.** After the last stop it goes on to the browser's own bar, as on
      any page; a page that keeps `tab` to itself is one people cannot leave by keyboard.
    - **In the filter** `↑` `↓` pick while typing, `enter` goes to what is left, `esc`
      clears it and goes back.
- **R4 — Pick a file with the system's own dialog.** Where a value is asked for there is
  *choose a file*, which opens the file dialog the person's system has, and a file can be
  dropped onto the form. The file's content goes from the browser to caland on the same
  machine, and from there to Databricks; it is written nowhere. *(owner asked; proposal)*
- **R5 — Say what a file is before it goes in.** After choosing, and before saving, the form
  says what was picked: its name and size, and for the kinds it can tell — a PEM
  certificate, a private key, a PKCS#12 bundle — which kind. For a certificate: who it is
  for, who issued it, and when it expires. *(proposal)*
- **R6 — A binary file goes in as it is.** A `.p12`, a `.pfx`, a `.der` is stored byte for
  byte, and comes out the same. Today a value is text only. *(proposal; see
  [003, D3](003-secrets.md#to-decide))*
- **R7 — Fast, and held to it.** *(owner asked; the numbers are the writer's)*
    - The page is there before the workspace is: it draws at once and fills as scopes
      arrive, eight at a time as today.
    - Filtering and searching happen in the page, over names it already has. No round-trip.
    - No framework, no build step, nothing fetched from the internet: one stylesheet, one
      script, both inside the package. It works with no network but the workspace.
    - Anything slow is asked for, never waited on, and kept for the session.
    - It asks a workspace only what the terminal version asks: no query, no warehouse.
    - Numbers a test holds: first paint within 300 ms of the server being up; a workspace
      of 500 scopes and 5,000 secrets filters within 50 ms a keystroke.
- **R8 — A value is in the page only while it is shown.** Not in the page's source, not in a
  URL, not in anything the browser keeps: it arrives when asked for and is taken out again
  when hidden or after 30 seconds. *Copy* never writes it into the page. *(built; how copy
  is done changed while building — see As built)*
- **R9 — The local port is defended.** A server that can read secrets, on a machine with a
  browser full of other sites, is the new risk this shape brings. *(proposal — and the part
  to have reviewed by someone who did not write it, before any release)*
    - It listens on `127.0.0.1` only, on a port chosen at start. There is no option to
      listen wider.
    - The address caland opens carries a one-time key. Without the session it starts, every
      request is refused — so another program, or another user of the machine, that finds
      the port gets nothing.
    - A request whose `Host` is not the address caland is on is refused, and one that
      changes anything must come from caland's own page. Another site in the same browser
      cannot reach it, by any of the known ways round.
    - Reading changes nothing; a value is only ever the answer to a request that could not
      have come from a link.
    - The page loads nothing that is not caland's: no script, style, font or picture from
      anywhere else, and no script written into the page.
    - Nothing is stored by the browser: no cache, no history of values, no local storage.
    - Read-only is enforced by the server, not by leaving buttons off the page.
    - Closing the page does not stop caland; stopping caland, or leaving it untouched for a
      while, does — and forgets every value.
- **R10 — It says what it cannot defend.** A browser extension allowed to read every page
  can read a value while it is shown, as anyone who can see the screen can. The docs say
  so, beside the clipboard warning that is there today. *(proposal)*

## As built — the first part: reading (2026-10-06)

`caland --page [WORKSPACE] [--no-open]`. Built: R2, R3, R3a, R7, R8, R9, R10, and of R1
the reading half — browse, filter, show, copy, copy as code, mine/all, read again. Not yet:
everything that changes a workspace, R4–R6, the workspace picker, `.env`, the stale report.
Until then the page is behind `--page` and `caland` alone is the terminal version: the
switch D2 describes is made when R1 is whole, not before — a release in between must not
hand people half a tool.

Decided while building, the builder's unless marked:

- **No cookie.** A cookie for `127.0.0.1` is sent to every port of the machine — so to any
  other program serving pages there. The page holds a token in memory and sends it in a
  header of its own; another site cannot send that header without asking, and nothing here
  says yes. For a reload to work the token is also in the tab's `sessionStorage` — never a
  value, and the one thing the browser keeps (R9 said nothing would be). It is taken from
  there on a reload and on nothing else: a site the tab went on to can send the tab back, or
  open a window that is handed a copy, and both find the page locked. A browser may write
  what a tab keeps into its own profile on disk, the owner's alone; the token is worth
  nothing once caland has stopped.
- **A one-time key, in a file.** The browser is started with a file only its owner can read
  (0600, in a 0700 folder), which sends it on to the page with a key in the address's
  fragment. A link on a command line can be read by every user of the machine. The key is
  good once, is taken out of the address at once, and the file is removed when it has been
  used. With `--no-open` the link is printed instead — a terminal is its owner's.
- **Copy happens in the page, not by caland** — R8 said the opposite. Copying on the
  machine needs a different program on each system and copies to the wrong machine over a
  forwarded port. The value goes from the server's answer to the clipboard without being
  written into the page.
- **Left alone for 30 minutes, it stops.** Enter in the terminal gives a new link, for a
  tab that was closed.
- **The shell of the page is public; everything it shows is not.** `/`, the stylesheet and
  the script hold no name and no value, and are given to anyone who asks. Everything under
  `/api/` needs the token.
- **Python's own HTTP server** (D3), and no new dependency.

Held by: `tests/test_web_gate.py` (the rules of R9, as a pure function),
`test_web_server.py` (the server asked over real HTTP), `test_web_opening.py`,
`test_web_run.py`, `test_loading.py`, and `test_page_in_a_browser.py` — the real page in
Chrome: real keys, where the keyboard lands, that a value leaves the page when hidden, that
a name with markup in it is text, and R7's two numbers.

**Reviewed once, by someone who did not build it (2026-10-06).** Nothing was found by which
a name, a value or the token reached another site or a client without the token. Found and
fixed, each with a test: another site could put the person back inside the page with the
kept token (now: only a reload); a scope named `constructor` or `__proto__` broke the page;
a page that lost its key kept what it showed; the answers `http.server` gives by itself
carried none of the headers; a broken connection printed a traceback; connections left
hanging could use the process up (now 64 at most, 10 seconds of silence each); a name with
a quote in it went into the copied code as it was. Still so: who holds all 64 connections —
a program on the machine — keeps the page from loading; that is a nuisance, not a leak.
Not tried: Firefox, Safari, a real DNS name pointed at the machine, and a Mac whose `.html`
files open in something other than the browser — there `--no-open` gives the link.

**Run on a real workspace once (2026-10-06):** it connected with a profile, signed in and
was ready in 2.3 s, first paint at 60 ms. That workspace has no secret scopes, so what was
shown was the empty page; listing and showing real secrets is proven against the fake only.

## As built — the second part: changing (2026-10-06)

Built: the rest of R1 that changes a workspace — secrets made, edited, deleted and put back,
moved, copied and renamed; grants; scopes — and R4, R5, R6. Not yet: the workspace picker
and signing in by URL, `.env` in and out, the stale report, the lookup by principal. So the
page is still behind `--page`.

Decided while building, the builder's unless marked:

- **A value is bytes, end to end.** The store port has a second pair of methods that carry
  a value as it is stored; the page uses only those. The terminal version's text methods
  are as they were — a secret that is no text still does not survive a move *there*
  ([003, D3](003-secrets.md#to-decide)); on the page it does.
- **The file dialog is the browser's own** (`<input type="file">`), and a file can be
  dropped on the form. The page reads it and sends it to caland on the same machine; caland
  says what it is (`application/files.py`) and, on save, sends it on. The owner took the
  `cryptography` library for that (D4, 2026-10-06).
- **A private key and a protected PKCS#12 bundle are named, never opened.** Nothing asks
  for a password.
- **Stricter than the terminal version, on purpose:** a new secret does not overwrite one
  that is there (edit it instead), and a move does not land on another secret. Neither can
  be taken back, and both happen by a slip.
- **The server holds every refusal** — read-only, a Key Vault scope's secrets, a value that
  is empty or too large (128 kB, Databricks' own limit). The page leaves the buttons out as
  well, but nothing depends on that.
- **What can be put back is one secret, held in memory** with the value it had, until
  another is deleted, values are forgotten, or caland stops. The state says *which* secret
  can be put back, never what it held.
- **Where a secret can be put:** the scopes the page shows — those you can reach, or all
  after `f` — but for Azure's.
- **`d` is the secret, `D` is the scope** — not `d` for whichever the keyboard is on, as in
  the terminal. A key that deletes a scope when a secret was meant is one slip too many.
- **A name in another case is the same name**, because to Databricks it is (tried on a
  workspace: `Case-Key` then `case-key` is one secret, and a scope in capitals "already
  exists"). A rename that only changes the case would write the secret and then remove it.
  `domain.same_name` is the one place that says so.
- **One change at a time, against what is there now.** The service takes a lock for every
  change; a move, a delete and a put-back read the value at that moment, not from what was
  read earlier; and "is there one already" is asked of the workspace, not of what the page
  last saw. The page queues its changes too: a key pressed while one is under way waits.
- **What is held to be put back is let go of only once it is back.**
- **A PKCS#12 bundle is named by its shape and never opened.** It says itself how many
  rounds its check takes, and a 785-byte file can ask for minutes of them.
- **What goes wrong in a dialog is said in the dialog**, not behind it.

Held by: `tests/test_values_as_bytes.py`, `test_files.py`, `test_web_changing.py` — every
changing route refused when read-only, without the token, from another site and by a `GET`
— and the browser tests, which type, press `y`, and hand real files to the file input.

**Reviewed, by someone who did not build it (2026-10-06).** Nothing by which a change
could be made that may not be — read-only, the token, another site, a Key Vault scope's
secrets all held — and no value leaked. But eleven ways to lose or damage one, found and
fixed, each with a test:

- `d`, `y`, then `u` before the answer could lose the secret just deleted (no lock, and
  the page a change behind). Now: one change at a time, in the service and on the page.
- A move, a delete and a put-back used the value read earlier in the session, so a secret
  changed elsewhere since was moved as it used to be — and the new value was gone.
- An empty file wiped a secret. A PEM pasted into the value field was saved as one line.
- A 785-byte PKCS#12 file froze the whole server for minutes; ctrl+c did nothing.
- A file described late landed in the next form, over what had been typed there.
- `u` overwrote a secret of the same name made since; "new never overwrites" held only
  against what the page had last read.
- `d` reached "delete scope" where a secret was meant; an unreadable scope was called
  empty; after a delete the selection jumped to the top.
- A certificate with an extension that makes no sense failed the request; a truncated
  bundle was called "protected by a password".
- **Found on the way, and in the released terminal version too:** a rename that only
  changes the case deleted the secret. Fixed there as well.

Not tried: Firefox, Safari, a real drag and drop.

**Run on a real workspace (2026-10-06), with the owner's word:** the real page, driven in
Chrome, against the test workspace, in a throwaway scope it made and removed. Each step
was checked through the SDK, not through caland: a scope made; text stored as typed; a file
of every byte there is — NULs, a BOM, CRLF, random bytes — stored **byte for byte** and
shown as what it is; a certificate described and stored as the file was; a rename; the
original put back; a delete and the secret put back byte for byte; a grant given and taken;
a rename that only changes the case refused, with the secret still there; the scope deleted
with what was in it. 20 checks, all held — run again after the review's fixes — and the
workspace had the scopes afterwards that it had before. That settles what was assumed about `bytes_value`
(it takes base64, and what comes back is the same bytes). Not run for real: a Key
Vault-backed scope (the workspace has none), and a workspace where the person may not
write.

## As built — the third part, first half: the tools (2026-10-06)

Built: what was left of R1 but the workspace picker — `.env` in and out
([005, R1–R3](005-bulk-and-audit.md)), the stale report ([005, R4](005-bulk-and-audit.md)),
the overview and the lookup by principal ([004, R5–R6](004-scopes-and-permissions.md)),
sorting ([002, R5](002-browsing.md)), forgetting values ([003, R9](003-secrets.md)), and
the two preferences that are kept ([006, R6](006-safety.md)). Not yet: choosing a
workspace from a list, signing in by URL, switching. So the page is still behind `--page`.

Decided while building, the builder's:

- **An import is shown before it is done, by the server**: how many, and which of those
  that are there are overwritten — asked of the workspace then, and whatever the case of a
  name. The file is sent twice, once to be shown and once to be done; nothing of it is kept
  in between, and no value is said back either time.
- **An import that stops says at which key** ([005, D1](005-bulk-and-audit.md#to-decide)),
  and that what went in before it stays. A pair with no value is left out and named: an
  empty value is a slip.
- **An export with values is the one request that reads every value of a scope.** It is a
  `POST` with the token like a single value, behind a `y`, and its answer goes to the
  clipboard without being written into the page. A secret that is no text is left out and
  named: a line of text cannot carry it.
- **The reports are made in the page** from names, dates and grants it already has. The
  server is asked nothing for them but the grants of every scope, once per reading.
- **A scope has no heading row to click**, so what the scopes are sorted by is said in the
  pane's heading.
- **The themes are not on the page.** It follows the system's light or dark, as lely's
  page does ([R2](#requirements)); `theme` in the settings file is the terminal version's.

**Reviewed, by someone who did not build it (2026-10-06).** The gate held for the five new
routes, read-only and Key Vault held, an export put its text on the clipboard and nowhere
else, and of 20,000 values written as `.env` and read back only one kind changed. Found and
fixed, each with a test:

- **A value quoted over several lines was stored broken**, and the lines of it that end in
  `=` became secrets of their own, named after pieces of a key. The parser reads such a
  value whole now, or refuses the file — in the terminal version too, which shares it.
- A value ending in a newline lost it between export and import.
- After an import that spelled a key in another case, the page went on showing the old
  value. Values are kept under the name the workspace has.
- An import with a value that is no text died halfway. A file is looked at whole before any
  of it is written: such a value, a quote never closed, two keys that are one secret.
- **A dialog that opened late took the place of a question, or opened over it**, and `y`
  answered the wrong one. Now one dialog is open at a time — but a question over the
  grants — and one that comes back after the person has gone on does not open.
- The stale report, asked for while the workspace was still being read, said "0 secrets"
  and stayed that way. It says it is still reading, and fills.
- An export answered from what was read earlier. A locked page kept the chosen file. A
  name with `|` in it broke the copied table. A preference asked for badly was half taken.

Not tried: Firefox, Safari, a real workspace for this part.

## As built — the third part, second half: which workspace, and the switch (2026-10-06)

Built: the last of R1 — choosing a workspace ([001](001-connecting.md)) — and with it D2's
switch: **`caland` opens the page, `caland --tui` the terminal version.** `--page` still
says the page.

- **With no doubt which workspace is meant, there is no question**: the one named, the
  bundle's default, or the only one found. A name that is not there ends it before it
  starts, as before. Otherwise the server starts with no workspace and the page asks.
- **The choice is the page's first dialog**, and with no workspace to go back to it cannot
  be left: a browser that closes it on `esc` all the same is asked again.
- **An address is https, a host, and nothing after it.** Signing in is the SDK's, through
  the browser, in a tab of its own.
- **A profile is kept under a new name only**: letters, digits, dots and dashes; never
  `DEFAULT`; never a name that is in use, whatever its case. A profile keeps its own way of
  signing in — a token, often — and pointing it at another address would send that there.
  It is written once the sign-in has worked, and holds the address and how to sign in.
- **Going to another workspace leaves nothing of the one that is left** — on the server the
  values and what could be put back, on the page everything. The state's version never
  comes round again across workspaces, so what the page holds of one is never taken for
  another's.
- **Choosing changes no workspace**, so read-only does not mind it.
- **A request about a workspace says which one**, and the page asks nothing of one
  workspace that it then does to, or shows under, another (see Reviewed, below).
- **The terminal version was left in at first, frozen behind `--tui`**, and removed a day
  later on the owner's word (see Decided): the Textual app, its tests, its pictures and
  their pipeline, the themes, the old command names. `caland --tui` now says where the
  terminal app is: it is `isolinear`.

**Reviewed, by someone who did not build it (2026-10-06).** Choosing, and keeping a
profile, held against another site and without the token; names that are no names were
refused; other profiles' values were rewritten exactly. But three things were wrong that
matter, and eight smaller — found and fixed, each with a test:

- **A change meant for one workspace could land in another**: a delete queued behind a
  slow one and done after going elsewhere, or asked from a second tab still showing the
  old one. A request about a workspace now says which it means (`X-Caland-Workspace`, the
  number the state gave), and is refused for any other; the server acts on the workspace it
  found when the request came in; the page drops what was queued, and answers that come
  late, when it has moved on.
- **Keeping a profile could re-point one that was on no list** — at the bundle's address,
  or with none — with its token. A name is asked of every heading in the file, and the
  store itself (`add`) never writes over a profile that is there.
- **Two saves at once could leave the file with one profile in it.** It is written one
  writer at a time, whole or not at all, and a new file is its owner's alone. A profile is
  added to the end of what is there, which is not rewritten.
- A value that came late was shown under the other workspace. A save that failed left
  "Connecting…" for ever. The choice did not come back when the keys' list was open.
  Two that were found under one name could not be told apart. An address could be a number,
  or have letters in it that only look like the ones meant. `--readonly`, mistyped, opened
  a workspace to change: an option caland does not know is refused now.

Not tried: a real sign-in by address, other browsers, Windows.

**Run on a real workspace (2026-10-06):** plain `caland` opened the page on the test
workspace; `w` listed the one profile the machine has, found in `~/.databrickscfg`; chosen
again, it connected again. Not run for real: the choice between several, and signing in by
an address — that opens a browser to sign in with, which nothing here can drive.

## Not in this spec

- **A hosted caland**, or one that serves more than the person who started it.
- **A picker drawn by caland** that walks the disk in the page. The system's dialog does
  it, is familiar, and does not make caland a file server.
- **Finding certificates that are about to expire** across a workspace. It would mean
  reading every value, which caland does not do ([006, R2](006-safety.md)).
- **A shared stylesheet package** for the family. Two tools carry the same few lines; that
  is cheaper than a third project.

## Decided

- **caland is for people working with secrets in Databricks, and only that.** No side that
  runs unattended, no lely step for grants. *(owner, 2026-10-06)*
- **It becomes a local tool with an HTML face, in lely's design language, with a file
  picker for certificates.** *(owner, 2026-10-06)*
- **A browser tab, from a server on the person's own machine** — not a window of its own.
  *(owner, 2026-10-06; was D1)*
- **The terminal version is frozen, then dropped.** It stays as it is and gets nothing new;
  `caland` opens the page and `caland --tui` the terminal; it goes in the release where the
  page does everything it does. *(owner, 2026-10-06; was D2)*
- **caland has no terminal version.** *(owner, 2026-10-07; was D5)* The terminal app is
  `isolinear`, which is left as it is.
- **The page first, with what the terminal version does today.** Who reads a secret
  ([009](009-who-reads-a-secret.md)) is not part of it. *(owner, 2026-10-06)*
- **Only the SDK.** No audit table, no warehouse — caland reaches a workspace the way the
  original did. *(owner, 2026-10-06)* → [000](000-what-caland-is.md#the-rules-it-keeps)

## To decide

- **D3 — What the server is made of.** *The writer's choice unless the owner minds:* Python's
  own HTTP server — one person, one machine, no new dependency — and a small script of
  caland's own in the page.
- **D4 — Reading a certificate (R5) needs a library** (`cryptography`). The kind of a file
  can be told without one; who it is for and when it expires cannot. *Proposal:* take the
  dependency — an expiry date before saving is the most useful line on that form.

## Done when

- A mock-up of the three main views — browse, a secret with its file form, a scope's grants
  — in lely's look, with made-up data, has been seen by the owner **before** any of it is
  wired to a workspace.
  *Made 2026-10-06: [`mock/page.html`](mock/page.html) — one file, open it in a browser.
  It answers to the keys, and its file form reads a real file's name, size and kind without
  sending it anywhere. Not yet seen by the owner.*
- The page passes the tests the terminal version's screens pass, against the same fake
  workspace, and a browser test in CI drives the real page.
- R7's numbers are tests.
- R9 has been attacked by a reviewer who did not build it, and what they found is fixed.

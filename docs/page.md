# The page (preview)

Caland is becoming a page in your browser, served from your own machine. It browses, shows
and copies, and it changes things: secrets, files, grants and scopes. What is not on it yet
— choosing a workspace from a list, `.env` in and out, the report of stale secrets — is in
the terminal version, which is what `caland` without `--page` opens.

```sh
caland --page            # the bundle's workspace here, or your only profile
caland --page prod       # a profile from ~/.databrickscfg, or a bundle target, by name
caland --page --no-open  # print the link instead of opening a browser
```

It starts a small server on this machine, opens a tab, and says so:

```
caland is at http://127.0.0.1:53124/ — opened in your browser.
enter: a new link · ctrl+c: stop
```

++ctrl+c++ stops it and forgets every value it held. So does leaving it alone for 30 minutes.
If you close the tab, press ++enter++ in the terminal for a new one. Reloading the tab is
fine; coming back to it from another site is not — the page asks for a new link then.

If no tab opens, or the link opens in something that is not your browser, start it with
`--no-open` and open the link it prints. The link works once.

## What it does

Three panes: the scopes you can reach, the secrets of the selected scope with when each was
last changed, and the detail — your access, who else has a grant, and the value once you ask
for it. The page is there at once and fills as the workspace is read; filtering happens in
the page, over names it already has.

**Secrets.** ++n++ makes one, ++e++ edits the selected one: type a value, or choose a file.
++m++ moves, renames or — with *keep the original* — copies it, to any scope you can reach.
++d++ deletes it after a deliberate ++y++, and ++u++ puts the last one back, for as long as
Caland runs.

**Files.** *Choose a file* opens your system's own file dialog, and a file can be dropped on
the form. Before anything is saved the form says what you picked: its size and kind, and for
a certificate who it is for, who issued it and when it expires. A file is stored byte for
byte — a `.p12` or a `.der` goes in and comes out the same — and a value that is no text is
shown as what it is: so many bytes, as base64.

![The form for a new secret, with a certificate picked](img/page-form.png)

A certificate pasted into the value field is taken line for line, like a file — a field
holds one line, and would join the rest to it.

**Grants and scopes.** ++p++ lists who has access to the scope, and gives, changes and
removes a grant; removing asks first, and says so when the grant is your own. ++shift+n++
makes a scope; ++shift+d++ deletes one, after saying how many secrets go with it. A scope
has a key of its own so that a ++d++ meant for a secret never reaches one.

**Nothing lands on what is there.** A new secret does not overwrite an existing one, a move
does not land on another secret, and ++u++ does not put a secret back over one made since.
Databricks does not tell names apart by their case — `API-KEY` is `api-key` — and neither
does Caland: a rename that only changes the case is refused, because it would write the
secret and then remove it.

**Read-only.** `caland --page prod --read-only` offers no change at all — and the server
refuses one whatever the page shows.

A Key Vault-backed scope's secrets are Azure's: they can be shown, copied, and copied out to
another scope, and nothing else.

## Keys

Everything has a key, and everything can be clicked.

| Keys | Action |
|------|--------|
| ++tab++ / ++shift+tab++ | The next pane, and back: scopes, secrets, detail |
| ++left++ ++right++ / ++h++ ++l++ | Also from pane to pane; in the detail, along its buttons |
| ++up++ ++down++ / ++j++ ++k++ | Up and down inside a pane |
| ++g++ / ++shift+g++ | To a pane's first and last |
| ++slash++ | Filter scopes and secrets: ++down++ picks while you type, ++enter++ goes to what is left, ++esc++ clears |
| ++space++ | Show or hide the value; it hides itself after 30 s |
| ++c++ / ++shift+c++ | Copy the value / copy how to reach it from code |
| ++n++ / ++shift+n++ | New secret / new scope |
| ++e++ · ++m++ · ++d++ | Edit · move, copy or rename · delete the secret |
| ++shift+d++ | Delete the scope |
| ++u++ | Put back the secret last deleted or moved away |
| ++p++ | Who has access to the scope |
| ++f++ | Only the scopes you can reach, or all of them |
| ++r++ / ++shift+r++ | Read the scope again / the whole workspace |
| ++question++ | The keys |

++tab++ moves between panes, not between buttons, and blue marks where the keyboard is: a bar
on a row, a ring on a button. After the last pane ++tab++ goes on to the browser's own bar, as
on any page.

## How it is kept yours

A server that can read secrets, next to a browser full of other sites, has to be sure who is
asking.

- **This machine only.** It listens on `127.0.0.1`, on a port chosen at start. There is no
  option to listen wider.
- **Its own page only.** A request that did not come from Caland's own page, at Caland's own
  address, is refused — another site in your browser cannot reach it.
- **Nothing without the session's key.** The page is let in once, with a one-time key, and
  holds a token for that tab, good until Caland stops. The token is sent in a header, never as a
  cookie, so no other program serving pages on your machine is ever sent it. The one-time key
  reaches your browser in a file only you can read, not on a command line.
- **A value is in the page only while it is shown.** It is asked for when you press
  ++space++, and taken out again when hidden. Copying never writes it into the page.
- **A file you pick goes to Caland on your machine and from there to Databricks.** It is
  written nowhere on the way, and nothing of it is kept once it is saved.
- **Nothing changes without being asked, and nothing is deleted without a ++y++.** Started
  with `--read-only`, nothing changes at all.
- **Nothing is kept.** No cache, no cookie, no history of values. The page loads nothing
  that is not Caland's own.

!!! warning "What it cannot defend"
    A browser extension that is allowed to read every page can read a value while it is
    shown, as anyone who can see your screen can. If that worries you for a workspace, use a
    browser profile without extensions — or the terminal version.

## Not yet

Choosing a workspace from a list and signing in by URL, `.env` in and out, the stale-secret
report, searching by principal. They come to the page next; until they have, the terminal
version has them.

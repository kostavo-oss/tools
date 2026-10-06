# The page (preview)

Caland is becoming a page in your browser, served from your own machine. This is the first
part of it: it **reads** — browse, filter, show and copy — and changes nothing yet. Everything
else is still in the terminal version, which is what `caland` without `--page` opens.

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
If you close the tab, press ++enter++ in the terminal for a new one.

## What it does

Three panes: the scopes you can reach, the secrets of the selected scope with when each was
last changed, and the detail — your access, who else has a grant, and the value once you ask
for it. The page is there at once and fills as the workspace is read; filtering happens in
the page, over names it already has.

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
  holds a token for as long as the tab is open. The token is sent in a header, never as a
  cookie, so no other program serving pages on your machine is ever sent it. The one-time key
  reaches your browser in a file only you can read, not on a command line.
- **A value is in the page only while it is shown.** It is asked for when you press
  ++space++, and taken out again when hidden. Copying never writes it into the page.
- **Nothing is kept.** No cache, no cookie, no history of values. The page loads nothing
  that is not Caland's own.

!!! warning "What it cannot defend"
    A browser extension that is allowed to read every page can read a value while it is
    shown, as anyone who can see your screen can. If that worries you for a workspace, use a
    browser profile without extensions — or the terminal version.

## Not yet

Creating, editing, deleting and moving secrets, grants, the file picker for certificates, the
workspace picker, `.env` in and out, and the stale-secret report. They come to the page next;
until they have, the terminal version is the whole tool.

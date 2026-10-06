# The terminal version

Until 0.6 Caland was a terminal app, and it still is one when you ask:

```sh
caland --tui
caland --tui prod --read-only
```

![The terminal version browsing secrets](img/browse.svg)

It does what it did, and it gets nothing new: Caland is [a page](page.md) now, and that is
where the work goes. What the page has and the terminal version has not: a file picker and
files that are no text, certificates read before they are saved, an import that says where
it stopped, and stricter rules about overwriting. What the terminal version has and the page
has not: four colour themes, and working where there is no browser.

Its own pages are as they were:

- [Browsing and managing](browsing.md) — the three panes, and everything it does.
- [Keyboard](keyboard.md) — its keys. They differ from the page's in places: on the page
  ++tab++ goes from pane to pane the same way, but ++shift+d++ deletes a scope, and the
  palette's commands have keys of their own.
- [Themes](themes.md)

Its picker is the one [Connecting](connecting.md) describes, in a terminal:

![The terminal version's workspace picker](img/login.svg)

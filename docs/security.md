# Security

Caland shows secrets and can delete them, in workspaces that matter. What it will not do is
as firm as what it does.

## What it keeps to

- **A value is never written.** Not to disk, not to a file of any kind, not to a log. It is
  read from Databricks each time you ask — a second look shows what is there now, not
  what was there the first time. [What Caland holds in memory](#what-caland-holds-of-a-value)
  is said below.
- **A value is read only for something you asked for.** Connecting reads names, dates and
  grants. A value is read to show it, to copy it, to move or copy its secret, to delete its
  secret — so that ++u++ can put it back — and for a `.env` export with values. Where your
  workspace logs reads of secrets, those are the reads it will show.
- **A shown value hides itself after 30 seconds**, and is in the page only while it is shown.
- **Nothing is deleted without a ++y++**, and nothing lands on what is there: a new secret
  does not overwrite one, a move does not land on one, ++u++ does not put one back over one
  made since.
- **`--read-only` changes nothing in the workspace.** The server refuses every change to
  it, whatever the page shows. Read-only is about the workspace, not about your own
  machine: there Caland may still write your two preferences
  (`~/.config/caland/settings.json`), and a profile in `~/.databrickscfg` if you sign in
  to an address and ask to keep it.
- **No credentials of its own.** Caland asks for no token and stores none. Signing in
  through the browser is the Databricks SDK's work, and the SDK keeps that sign-in — a
  token it can renew, so that you are not asked every time — in a folder of its own:
  `~/.config/databricks-sdk-py/oauth/`. Stopping Caland does not remove it; deleting what
  is in that folder signs you out.
- **A profile Caland keeps holds an address and that you sign in through the browser**
  (`auth_type = external-browser`), and no token. It is a profile for tools built on the
  Databricks SDK for Python, as Caland is; it is not what `databricks auth login` writes.
  Caland never writes over a profile that is there.
- **`~/.databrickscfg` is written whole or not at all.** A new file is yours alone; one
  that is there keeps who may read it — that is yours to say, not Caland's. Where it is a
  link, the file it points to is written and the link stays.
- **One door to Databricks.** Only one layer of the code imports the Databricks SDK; the
  page and the server have no other way out.

## What Caland holds of a value

In its own memory, while it runs, and nowhere else:

- **The secret you last deleted or moved away**, with its value, so that ++u++ can put it
  back. One deep: the next delete or move takes its place.
- **The values it has read or written for you**: shown, copied, saved, moved, exported.
  They are not used again — showing or copying asks the workspace every time.

A scope's values are let go of when that scope is read again (++r++, or ++shift+r++ for
the whole workspace) or deleted. Everything, with what ++u++ could put back, is forgotten
by *Forget every value* (++question++ then ++z++), by going to another workspace, and when
Caland stops: ++ctrl+c++, or by itself after 30 minutes with nothing asked of it.

The page in your browser holds less: a value is in it only while it is shown.

The page is served from your own machine, to you only:
[how it is kept yours](page.md#how-it-is-kept-yours) has those rules, and what it cannot
defend against.

!!! warning "Clipboard"
    Copying a value places it on your system clipboard. If you share your machine, clear the clipboard after you're done. (Caland deliberately does not auto-clear the clipboard: it cannot read the clipboard back, so a timed clear could clobber something else you copied in the meantime.)

## Reporting a vulnerability

Please report security issues **privately** — not in a public issue.

- Open a [GitHub Security Advisory](https://github.com/kostavo-oss/caland/security/advisories/new), or
- Email [misja@prorexconsultancy.nl](mailto:misja@prorexconsultancy.nl).

!!! danger "Do not file a public issue"
    Public issues are visible to everyone and can expose users before a fix is available. Always use one of the private channels above.

# Security

Caland shows secrets and can delete them, in workspaces that matter. What it will not do is
as firm as what it does.

## What it keeps to

- **A value is never written.** Not to disk, not to a cache, not to a log. It is read from
  Databricks when you ask, held in memory, and forgotten when Caland stops — or sooner, with
  *Forget every value* under ++question++.
- **A value is read only for something you asked for.** Connecting reads names, dates and
  grants. A value is read to show it, to copy it, to move or copy its secret, to delete its
  secret — so that ++u++ can put it back — and for a `.env` export with values. Where your
  workspace logs reads of secrets, those are the reads it will show.
- **A shown value hides itself after 30 seconds**, and is in the page only while it is shown.
- **Nothing is deleted without a ++y++**, and nothing lands on what is there: a new secret
  does not overwrite one, a move does not land on one, ++u++ does not put one back over one
  made since.
- **`--read-only` changes nothing.** The server refuses every change, whatever the page
  shows.
- **No credentials of its own.** Caland signs in the way the Databricks CLI does and stores
  no token. A profile it keeps holds an address and that you sign in through the browser —
  and it never writes over a profile that is there.
- **`~/.databrickscfg` is written whole or not at all**, and never left readable by anybody
  but you.
- **One door to Databricks.** Only one layer of the code imports the Databricks SDK; the
  page and the server have no other way out.

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

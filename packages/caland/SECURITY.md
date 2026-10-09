# Security Policy

## How Caland handles secrets

- **A value is never written.** Not to disk, not to a log. It is read from
  Databricks each time you ask, through the Databricks SDK, and held in memory
  only — until you forget it (`?`, then `z`), go to another workspace, or stop
  Caland, which also stops by itself after 30 minutes with nothing asked of it.
- **A value is read only for something you asked for.** Connecting reads
  names, dates and grants. A value is read to show it, to copy it, to move or
  copy its secret, to delete its secret — so that `u` can put it back — and
  for a `.env` export with values.
- **The page is yours only.** Caland is a page in your browser, served from
  your own machine: on `127.0.0.1` only, to its own page at its own address
  only, and to nothing without the session's key — which is never a cookie
  and never on a command line. A value is in the page only while it is shown,
  and hides itself after 30 seconds.
- **Nothing is deleted without a `y`**, and `--read-only` changes nothing in
  the workspace: the server refuses every change, whatever the page shows.
- **Caland stores no token.** Signing in through the browser is the Databricks
  SDK's work, and the SDK keeps that sign-in — a token it can renew — in a
  folder of its own, `~/.config/databricks-sdk-py/oauth/`. Deleting what is in
  that folder signs you out.
- **A profile Caland keeps holds no secret**: only a `host` and
  `auth_type = external-browser`, in `~/.databrickscfg`. It is a profile for
  tools built on the Databricks SDK for Python; it is not what
  `databricks auth login` writes. Caland never writes over a profile that is
  there.
- **The SDK boundary is isolated.** Only the `infrastructure/` layer touches the
  Databricks SDK; the page and its server reach a workspace through it and
  nothing else.

Copying a value places it on your system clipboard — clear it afterwards if you
share your machine. A browser extension that may read every page can read a
value while it is shown.

More, and what Caland cannot defend against, in
[the docs](https://kostavo-oss.github.io/tools/caland/security/).

## Supported versions

The latest released version on PyPI is supported. Please upgrade before
reporting an issue.

## Reporting a vulnerability

Please report security issues **privately**:

- Open a [GitHub Security Advisory](https://github.com/kostavo-oss/tools/security/advisories/new), or
- email **info@kostavo.com**.

Do not open a public issue for security reports. You'll get an acknowledgement
as soon as possible, and we'll coordinate a fix and disclosure with you.

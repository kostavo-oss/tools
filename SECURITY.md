# Security Policy

## How Caland handles secrets

- **Secret values are never persisted.** They're read on demand via the
  Databricks SDK (`get_secret`) and held only in memory for the current session.
- **Reveal is lazy.** Values are fetched only when you explicitly reveal or copy
  one — they are not bulk-pulled during the startup cache warm.
- **Caland stores no token.** Signing in through the browser is the Databricks
  SDK's work, and the SDK keeps that sign-in — a token it can renew — in a
  folder of its own, `~/.config/databricks-sdk-py/oauth/`. Deleting what is in
  that folder signs you out.
- **A profile Caland keeps holds no secret**: only a `host` and
  `auth_type = external-browser`, in `~/.databrickscfg`. It is a profile for
  tools built on the Databricks SDK for Python; it is not what
  `databricks auth login` writes.
- **The SDK boundary is isolated.** Only the `infrastructure/` layer touches the
  Databricks SDK or the network.

Copying a value places it on your system clipboard — clear it afterwards if you
share your machine.

## Supported versions

The latest released version on PyPI is supported. Please upgrade before
reporting an issue.

## Reporting a vulnerability

Please report security issues **privately**:

- Open a [GitHub Security Advisory](https://github.com/kostavo-oss/caland/security/advisories/new), or
- email **misja@prorexconsultancy.nl**.

Do not open a public issue for security reports. You'll get an acknowledgement
as soon as possible, and we'll coordinate a fix and disclosure with you.

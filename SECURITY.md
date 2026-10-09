# Security Policy

Four tools, one policy for reporting and one place to read how each handles your
workspace: every package has a `SECURITY.md` of its own —
[stevin](packages/stevin/SECURITY.md), [lely](packages/lely/SECURITY.md),
[caland](packages/caland/SECURITY.md) — and leeghwater's README says what it reads and
writes.

What they have in common: **no credentials are stored** — authentication is the
Databricks SDK's unified auth (`~/.databrickscfg` profiles, the OAuth token cache, or
`DATABRICKS_*` environment variables), and no tool writes a token anywhere.

## Supported versions

The latest released version of each package on PyPI is supported. Please upgrade
before reporting an issue.

## Reporting a vulnerability

Please report security issues **privately**:

- Open a [GitHub Security Advisory](https://github.com/kostavo-oss/tools/security/advisories/new), or
- email **info@kostavo.com**.

Do not open a public issue for security reports. You'll get an acknowledgement as
soon as possible, and we'll coordinate a fix and disclosure with you.

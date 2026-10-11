# Caland ▦

**Databricks secrets, by hand: a keyboard-driven page in your browser, served
from your own machine.** Browse scopes, secrets and grants; create, edit, move
and delete; show and copy values; put a certificate in from a file.

[![ci](https://github.com/kostavo-oss/tools/actions/workflows/ci.yml/badge.svg)](https://github.com/kostavo-oss/tools/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/caland.svg)](https://pypi.org/project/caland/)
[![Python](https://img.shields.io/pypi/pyversions/caland.svg)](https://pypi.org/project/caland/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/kostavo-oss/tools/blob/main/packages/caland/LICENSE)

![Caland with a secret's value shown](https://raw.githubusercontent.com/kostavo-oss/tools/main/packages/caland/docs/img/page-browse.png)

## Why

Databricks secrets have an API and a CLI, and no screen. Rotating a key is a command
copied from a wiki, and who may read which scope is a question nobody can answer quickly.
Caland is the screen: a workspace's scopes, secrets and grants on one page, on your own
machine, with a value read only when you ask for it and written nowhere.

## Quickstart

It needs Python 3.11 or later, a browser, and macOS or Linux.

```sh
uvx caland              # run it once; or: uv tool install caland
```

It starts a small server on your machine and opens a tab. Nothing is set up first:
Caland finds the workspace of a bundle in the current folder and the profiles in
`~/.databrickscfg`. When there is no doubt which workspace you mean it goes straight
there. Otherwise the page asks, and takes an address to sign in to through the browser.

```sh
caland prod               # straight to a workspace by name
caland prod --read-only   # and change nothing there
caland --no-open          # print the link instead of opening a browser
```

<kbd>?</kbd> on the page lists the keys. <kbd>Ctrl</kbd>+<kbd>C</kbd> in the terminal
stops Caland and forgets every value it held.

## The docs

How to use it is in the [docs](https://kostavo-oss.github.io/tools/caland/), and only
there:

- [Installation](https://kostavo-oss.github.io/tools/caland/installation/): uvx, uv tool
  or pipx, and upgrading.
- [Connecting](https://kostavo-oss.github.io/tools/caland/connecting/): which workspace,
  where workspaces are found, and keeping a sign-in as a profile.
- [Using the page](https://kostavo-oss.github.io/tools/caland/page/): secrets, files,
  grants, `.env` in and out, the lists, [every key](https://kostavo-oss.github.io/tools/caland/page/#keys),
  and [how the page is kept yours](https://kostavo-oss.github.io/tools/caland/page/#how-it-is-kept-yours).
- [Security](https://kostavo-oss.github.io/tools/caland/security/): what Caland keeps
  to, what it holds of a value, and where to report a vulnerability.

## Tried, and not yet

On 2026-10-06 the page was driven in Chrome against a real workspace, in a throwaway
scope: text and files stored byte for byte, a rename, a delete and the secret put back,
a grant given and taken. A Key Vault-backed scope, a sign-in by an address, other
browsers than Chrome and Windows have not been tried.

[Tried, and not yet](https://kostavo-oss.github.io/tools/caland/tried/) is the record.

## When not to use it

- **In a pipeline.** Caland is for a person at a keyboard. It has no command that runs
  unattended, and is not to get one.
- **To keep secrets in code.** It declares nothing and plans nothing: what it does, it
  does now, to the workspace it is connected to.
- **For secrets outside Databricks secret scopes.** A Key Vault-backed scope is shown and
  its values can be read; its secrets are managed in Azure.
- **To see when a secret was last read.** That takes the audit table and a warehouse, and
  Caland uses only the Databricks SDK: no query, no warehouse, no system table.

## When you no longer need it

When a Databricks workspace has a page of its own for secret scopes — the scopes, the
secrets in each, who may read them, and a way to change one — use that. Today the docs
name one screen, a form that creates a scope; listing, reading and changing go through
the CLI, the API or the SDK.

## Where it fits

Caland is one of the [Kostavo tools](https://github.com/kostavo-oss/tools): small tools for the ugly gaps on Databricks,
one gap each. Its gap is the secret you reach through an API. Each works alone.
Kostavo is the company behind them: it builds
[a governance platform for Databricks workspaces](https://kostavo.com), and the tools are
complete without it.

Community project, not affiliated with or endorsed by Databricks.

## Named after

Pieter Caland (1826–1902), the engineer who designed and built the Nieuwe Waterweg — the
cut through the dunes that gave Rotterdam its way to the sea.

Until 0.6 Caland was a terminal app, and before that it was called `isolinear`. That
terminal app is still on PyPI under that name, as it was, and is a separate tool now:
[if you want a terminal app](https://kostavo-oss.github.io/tools/caland/installation/#if-you-want-a-terminal-app).

## License

[Apache-2.0](https://github.com/kostavo-oss/tools/blob/main/packages/caland/LICENSE).

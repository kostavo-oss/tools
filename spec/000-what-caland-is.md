# 000 — what caland is

**Status:** written 2026-10-06 from the tool as built. The owner gave the direction the same
day ([Decided](#decided)); what follows from it is in [008](008-the-page.md).

## The line

**A keyboard-driven terminal UI for managing Databricks secrets.** Browse scopes, secrets and
permissions; create, edit and delete; reveal and copy values — from a fast, calm three-pane
screen.

That is the line today. With [008](008-the-page.md) the screen becomes a page, and the line
changes with it.

## Why

Databricks secrets have an API and a CLI, and no screen. Finding which scope holds a key,
who may read it, how old it is, and what its value is takes a command each, and the value
ends up in a shell's history. caland is the screen: everything about a workspace's secrets at
once, a keystroke away, with the value shown only when asked for and never written anywhere.

## Who it is for

A person at a terminal with access to a workspace: an engineer checking a key before a
deploy, a platform owner tidying up scopes and grants, someone rotating what has gone stale.

## When not to use it

- **In a pipeline.** caland is interactive; it has no command that runs unattended, and is
  not to get one.
- **To keep secrets in code.** It declares nothing and plans nothing: what it does, it does
  now, to the workspace it is connected to.
- **For secrets outside Databricks secret scopes.** Key Vault-backed scopes are shown and
  their values can be read; their secrets are managed in Azure.

## Where it fits

One of three Kostavo tools, each with a Dutch engineer's name:

> [stevin](https://github.com/kostavo-oss/stevin) for the data model,
> [lely](https://github.com/kostavo-oss/lely) to deploy a bundle and the steps around it as
> one plan — and **caland** for the secrets, by hand.

stevin and lely plan and apply, for a pipeline to run and a reviewer to read. caland is the
one a person opens. It shares their toolchain, licence and release method, not their shape.

## The rules it keeps

- **A secret's value is never written.** Not to disk, not to a cache file, not to a log. It
  is read when asked for and held in memory. → [006](006-safety.md)
- **Nothing is done to a workspace without being asked**, and nothing destructive without a
  deliberate `y`. → [006](006-safety.md)
- **Everything has a key.** No action needs a mouse; the footer and `?` say which key.
  → [002](002-browsing.md)
- **No credentials of its own.** It signs in the way the Databricks CLI does and stores no
  token. → [001](001-connecting.md)
- **Only the SDK.** It reaches a workspace through the Databricks SDK's own calls — secrets,
  grants, who you are. It runs no query, starts no warehouse and reads no system table.
  *(owner, 2026-10-06)*
- **The Databricks SDK is behind one door.** Only `infrastructure/` imports it; the screens
  and the rules have no way to the network, and are tested without one.

## The name

Pieter Caland (1826–1902), the engineer who designed and built the Nieuwe Waterweg. Up to
0.4.1 the tool was `isolinear`; for a day it was to be `maeslant`, after the storm surge
barrier, until the owner wanted a person's name there, as stevin and lely have.
→ [007](007-name-and-release.md)

## Not in this spec

How it is built — the layers, the ports — is in `docs/architecture.md`.

## Decided

- **The name is caland.** *(owner, 2026-10-06: "the first ones are people, maeslant is not")*
- **Specs come before any further work on the tool.** *(owner, 2026-10-06)*
- **It stays a tool for people working with secrets in Databricks, and only that.** Of the
  three directions the writer laid out — deepen it, a side that runs unattended, grants as
  a lely step — the first. *(owner, 2026-10-06)*
- **What is to be refined is how it is to use.** It becomes a local tool with an HTML face
  in lely's design language, with a file picker for certificates, and it stays fast.
  *(owner, 2026-10-06)* → [008](008-the-page.md)
- **The page comes first; who has access comes after; when a secret was last read is out**
  — it would take the audit table and a warehouse, and caland uses only the SDK.
  *(owner, 2026-10-06)* → [009](009-who-reads-a-secret.md)

## To decide

- **D1 — `docs/USER_STORIES.md`** describes the tool as of its first versions and is behind:
  it lists bulk import and export as out of scope, and both are built; it has no search, no
  audit, no undo. *Proposal:* this folder replaces it, and the file goes.

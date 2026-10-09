# 009 — who reads a secret

**Status:** parked by the owner on 2026-10-06 — the page comes first
([008](008-the-page.md)). Half of it is ruled out as well: see [Decided](#decided). Nothing
is built beyond what [004](004-scopes-and-permissions.md) describes. Kept so that what was
worked out is not worked out twice.

## Why

Two questions come before a secret is rotated or removed: who *can* read it, and whether
anyone *does*. The first caland answers in part. The second it cannot answer at all — the
secrets API says when a secret was last changed and nothing about it being read.

## For later: who can read it

Needs nothing but the SDK. Not before the page is done.

- **R1 — Who can read this secret, for real.** Beside a secret: everyone with a grant on its
  scope — grants are per scope, never per secret — with a group opened into its members,
  and the workspace's admins, who reach every scope whatever the grants say.
  *(proposal; the first third is built, [004, R4](004-scopes-and-permissions.md))*
- **R2 — What this person reaches, for real.** *Who has access* follows the groups a person
  is in, and says for each scope through which grant.
  *(proposal; closes [004, D1](004-scopes-and-permissions.md#to-decide))*

## Ruled out: when it was last read

The only place Databricks records a read is its audit log: an entry for every call to the
secrets service, under the service name `secrets` — `getSecret`, `putSecret`, `deleteSecret`
with the scope and the key, and who made the call, and when.
([Audit log reference, "Secrets events"](https://docs.databricks.com/aws/en/admin/account-settings/audit-logs))
It is read as a table, `system.access.audit`, which takes Unity Catalog, a grant that is an
account admin's to give, and a SQL warehouse to ask it on.
([System tables](https://docs.databricks.com/aws/en/admin/system-tables/))

The owner ruled that out: no audit table, no warehouse. So these are **not to be built**
unless that changes — and nothing the SDK offers can stand in for them:

- ~~**R3 — When it was last read, and by whom**~~, and who last changed it.
- ~~**R4 — Never read**~~: "not read in N days" beside "not changed in N days" in the
  stale-secret report.
- ~~**R5 — Asked for, never waited on**~~: one question for the whole workspace, asked once.
- ~~**R6 — Honest when it cannot**~~: one line saying what is missing.

What caland does show, and keeps showing, is when a secret was last *changed*
([002, R1](002-browsing.md), [005, R4](005-bulk-and-audit.md)).

## Not in this spec

- **Keeping a history of its own.** caland has no state.
- **Alerts** — a message when a secret is read by someone new.

## Decided

- **Not now.** The page first, with what the terminal version did.
  *(Decided by the owner, 2026-10-06.)*
- **No audit table and no warehouse: only the SDK, as the original did.**
  *(Decided by the owner, 2026-10-06.)* That rules out R3–R6, and with them any answer in
  caland to when a secret was last read. If that is wanted after all, this rule is the one
  to reopen.

## To decide

- **D1 — Not yet verified: who can list a group's members** (R1, R2). If it takes an admin,
  the page says so for those who are not. To be tried when R1–R2 are taken up.

## Done when

Parked. When R1–R2 are taken up: they work against the fake workspace with groups in it,
and D1 has been tried on a real workspace.

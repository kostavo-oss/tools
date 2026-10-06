# 009 — who reads a secret

**Status:** proposal. Nothing is built beyond what [004](004-scopes-and-permissions.md)
describes. Written 2026-10-06 after the owner asked for "who has access and when was it last
accessed".

## Why

Two questions come before a secret is rotated or removed: who *can* read it, and whether
anyone *does*. The first caland answers in part. The second it cannot answer at all — the
secrets API says when a secret was last changed and nothing about it being read.

## What Databricks records

The audit log has an entry for every call to the secrets service, under the service name
`secrets`: `getSecret`, `putSecret` and `deleteSecret` with the scope and the key;
`putAcl` and `deleteAcl` with the scope and the principal; and who made the call, and when.
([Audit log reference, "Secrets events"](https://docs.databricks.com/aws/en/admin/account-settings/audit-logs))

It is read as a table, `system.access.audit`, kept for 365 days. That takes three things
most people who can read a secret do not have: a workspace on Unity Catalog, a grant on the
table — an account admin's to give — and a SQL warehouse to run the question on.
([System tables](https://docs.databricks.com/aws/en/admin/system-tables/))

## Requirements

- **R1 — Who can read this secret, for real.** Beside a secret: everyone with a grant on its
  scope — grants are per scope, never per secret — with a group opened into its members,
  and the workspace's admins, who reach every scope whatever the grants say.
  *(proposal; the first third is built, [004, R4](004-scopes-and-permissions.md))*
- **R2 — What this person reaches, for real.** *Who has access* follows the groups a person
  is in, and says for each scope through which grant.
  *(proposal; closes [004, D1](004-scopes-and-permissions.md#to-decide))*
- **R3 — When it was last read, and by whom.** For each secret: the last time it was read
  and who read it, and how often in the last 30 and 90 days. For each: who last changed it
  — the API gives only when. *(proposal)*
- **R4 — Never read.** The stale-secret report ([005, R4](005-bulk-and-audit.md)) gets a
  second question beside "not changed in N days": *not read in N days*. A secret nobody
  reads is one to remove, not one to rotate. *(proposal)*
- **R5 — Asked for, never waited on.** None of R3–R4 is fetched on connecting. The first
  time it is wanted, caland says which warehouse it will ask and that this costs a little
  compute, and asks once. The answer is one question for the whole workspace — not one per
  secret — kept for the session, and shown with the time it is from. The rest of the page
  never waits for it. *(proposal)*
- **R6 — Honest when it cannot.** Without Unity Catalog, without the grant, or without a
  warehouse, the column says in one line what is missing and who can give it — once, not as
  an error on every row. *(proposal)*
- **R7 — It says what the number is not.** The log is not live: a read from a minute ago may
  not be there. A read by caland itself — showing a value, moving a secret — is a read like
  any other. Both are said where the number is shown. *(proposal)*

## Not in this spec

- **Keeping a history of its own.** caland has no state; the log is Databricks'.
- **Alerts** — a message when a secret is read by someone new.
- **Reads of Key Vault-backed secrets as Azure sees them.** What Databricks logs is shown;
  Azure's log is Azure's.

## To decide

- **D1 — Is it worth it for who can use it?** R3 and R4 need a grant that is an account
  admin's to give. For a platform owner that is likely there; for an engineer checking one
  key, likely not, and they would see R6's line. *The writer's view:* yes — it is the
  question nothing else answers, and R1–R2 need none of it.
- **D2 — Not yet verified: which reads are logged.** The reference says `getSecret` is
  written when "a user gets a secret from a scope". Whether that covers a notebook's
  `dbutils.secrets.get`, and a `{{secrets/scope/key}}` in a cluster's or a job's
  configuration, it does not say. If it does not, "never read" would be wrong for exactly
  the secrets that matter most. *To be tried on a real workspace before R4 is built* — it
  needs the owner's word, a warehouse, and the grant on the test workspace.
- **D3 — Not yet verified: who can list a group's members** (R1, R2). If it takes an admin,
  the page says so for those who are not.

## Done when

- D2 and D3 have been tried on a real workspace and what was found is written here.
- R1–R2 work against the fake workspace with groups in it.
- R3–R6 work against a recorded answer of the audit table, and R6's three cases each have a
  test.

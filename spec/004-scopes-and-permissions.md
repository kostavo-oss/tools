# 004 — scopes and permissions

**Status:** built. Written 2026-10-06 from the tool at 0.4.1.

## Why

Who can read a secret is decided a scope at a time, and Databricks shows it a scope at a
time. The questions people have go the other way: what can *I* touch, and what can *they*.

## Requirements

- **R1 — Create and delete a scope.** `N` creates one. `d` with the scopes pane in focus
  deletes the selected one, after a dialog that says how many secrets go with it and takes a
  deliberate `y`. A deleted scope cannot be taken back. *(built, 0.1.0)*
- **R2 — Show the scopes you can reach.** By default the scopes pane lists the scopes you
  have any access to. `f` shows every scope in the workspace, and back; the choice is kept.
  When the default leaves nothing, the pane says so and names the key. *(built, 0.2.8; kept
  since 0.4.0)*
- **R3 — Your access is what you can really do.** Your permission on a scope is the highest
  granted to you, to `users`, or to a group you are in. Where the grants cannot be listed —
  that takes MANAGE — but the scope's secrets can, it is READ, not "none". *(built)*
- **R4 — Edit a scope's grants.** `p` lists who has what on the selected scope, and from it
  a grant is added, changed or removed: READ, WRITE or MANAGE, for a user, a group or a
  service principal. Removing asks first, and says so when the grant is your own.
  *(built, 0.1.0)*
- **R5 — Everything you can touch, at once.** `a` lists every scope with your permission and
  how many principals have a grant, strongest first. *(built, 0.1.0)*
- **R6 — Everything they can touch.** *Who has access*, from the palette: type a user, a
  group or a service principal and see every scope they have a grant on, strongest first;
  `enter` goes to the scope. The view for an access review, or for someone who has left.
  *(built, 0.4.0)*
- **R7 — The strongest grant stands out.** READ is muted, WRITE is cyan, MANAGE is amber and
  bold, wherever a permission is shown. *(built)*
- **R8 — Say what backs a scope.** The detail pane says whether a scope is Databricks-backed
  or Azure Key Vault-backed. Grants on either are edited the same way. *(built)*

## Not in this spec

- **Creating a Key Vault-backed scope.** It needs Azure's side; caland shows them.
- **What a group contains.** R6 answers for the name typed, not for the groups it is in.
- **Grants as code** — declared, planned, applied. That is direction, not this spec:
  [000, D1](000-what-caland-is.md#to-decide).

## To decide

- **D1 — R6 does not follow groups.** Asking who-has-access for a person shows the grants
  made to that person by name, and not what they reach through `users` or a group — which
  is how most access is given, and what R3 does count for *you*. For an offboarding check
  that is the half that matters less. *Proposal:* say so in the view today; following
  groups needs a call per principal and is feature work to decide on.
  *(found while writing this spec)*

## Done when

Built. Held by `tests/test_permissions.py`, `test_ui_permissions.py`, `test_ui_tools.py`
and the snapshots of the two dialogs.

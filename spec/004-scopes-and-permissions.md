# 004 — scopes and permissions

**Status:** built, on the page. Written 2026-10-06 from the terminal app at 0.4.1, which
met these first and is not in caland any more ([008](008-the-page.md)), and rewritten on
2026-10-07 to say what the page does. A requirement names the release it first arrived in,
and the one it came to the page in. What only the terminal app had is under
[Gone with the terminal app](#gone-with-the-terminal-app).

## Why

Who can read a secret is decided a scope at a time, and Databricks shows it a scope at a
time. The questions people have go the other way: what can *I* touch, and what can *they*.

## Requirements

- **R1 — Create and delete a scope.** `N` creates one. `D` deletes the selected one —
  a key of its own, so that a `d` meant for a secret never reaches a scope — after a
  dialog that says how many secrets go with it, or that they cannot be listed from here,
  and takes a deliberate `y`. A deleted scope cannot be taken back.
  *(built, 0.1.0; on the page since 0.5.1)*
- **R2 — Show the scopes you can reach.** By default the scopes pane lists the scopes you
  have any access to. `f` shows every scope in the workspace, and back; the choice is kept.
  When the default leaves nothing, the pane says so and names the key. *(built, 0.2.8; kept
  since 0.4.0; on the page since 0.5.0, kept there since 0.5.2)*
- **R3 — Your access is what you can really do.** Your permission on a scope is the highest
  granted to you, to `users`, or to a group you are in. Where the grants cannot be listed —
  that takes MANAGE — but the scope's secrets can, it is READ, not "none".
  *(built; on the page since 0.5.0)*
- **R4 — Edit a scope's grants.** `p` lists who has what on the selected scope, and from it
  a grant is added, changed or removed: READ, WRITE or MANAGE, for a user, a group or a
  service principal. In the list the arrows pick a grant, `e` changes it and `d` removes
  it. Removing asks first, takes a `y`, and says so when the grant is your own.
  *(built, 0.1.0; on the page since 0.5.1; the keys since the fix of 2026-10-07)*
- **R5 — Everything you can touch, at once.** `a` lists every scope with your permission and
  how many principals have a grant, strongest first; `enter` goes to the scope.
  *(built, 0.1.0; on the page since 0.5.2)*
- **R6 — Everything they can touch.** `P`: type a user, a group or a service principal and
  see every scope they have a grant on, strongest first; `enter` goes to the scope. The
  view for an access review, or for someone who has left. It shows the grants made to the
  name itself, and says so (D1). *(built, 0.4.0; on the page since 0.5.2)*
- **R7 — The strongest grant stands out.** READ is muted, WRITE is blue, MANAGE is amber and
  bold, wherever a permission is shown. *(built; on the page since 0.5.0)*
- **R8 — Say what backs a scope.** The detail pane says whether a scope is Databricks-backed
  or Azure Key Vault-backed. Grants on either are edited the same way.
  *(built; on the page since 0.5.0)*

## Gone with the terminal app

- **`d` for whichever the keyboard was on** — the scope, with the scopes pane in focus
  (R1): a key that deletes a scope when a secret was meant is one slip too many.
- **The palette**, from which *Who has access* was opened (R6): it has a key, `P`.
- **WRITE in cyan** (R7): the page has lely's colours, and WRITE is blue.

## Not in this spec

- **Creating a Key Vault-backed scope.** It needs Azure's side; caland shows them.
- **What a group contains.** R6 answers for the name typed, not for the groups it is in.
- **Grants as code** — declared, planned, applied. Not caland's to do: it is for people
  ([000, Decided](000-what-caland-is.md#decided)).

## To decide

- **D1 — R6 does not follow groups.** Asking who-has-access for a person shows the grants
  made to that person by name, and not what they reach through `users` or a group — which
  is how most access is given, and what R3 does count for *you*. For an offboarding check
  that is the half that matters less. *Proposal:* say so in the view today; following
  groups is [009, R2](009-who-reads-a-secret.md). *(found while writing this spec)*

## Done when

Built. Held by `tests/test_permissions.py`, `test_web_changing.py` and the browser tests
for grants, scopes and the two lists.

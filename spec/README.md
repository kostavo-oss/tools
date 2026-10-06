# The spec

What caland is, what each part of it must do, and what is still open. `docs/` tells a user
how to use it; this says what it promises, so that a change can be held to something.

Written on 2026-10-06 from the tool as it is at 0.4.1 — its code, its tests, its docs and its
changelog — when the tool took the name caland. Nothing in 001–006 is a plan: it describes
what is built. What is not decided is in each spec's **To decide**, and gathered below.

| Spec | What | Stands |
| --- | --- | --- |
| [000 — what caland is](000-what-caland-is.md) | Who it is for, where it fits, the rules it keeps | written; the direction is open |
| [001 — connecting](001-connecting.md) | The workspace picker, signing in, switching | built |
| [002 — browsing](002-browsing.md) | Three panes, sorting, filtering, searching, the cache | built |
| [003 — secrets](003-secrets.md) | Create, edit, move, delete, undo; reveal and copy | built |
| [004 — scopes and permissions](004-scopes-and-permissions.md) | Scopes, ACLs, who can touch what | built |
| [005 — bulk work and audits](005-bulk-and-audit.md) | `.env` in and out, the stale-secret report | built |
| [006 — what caland may do](006-safety.md) | What it never stores, what it asks before, read-only | built |
| [007 — the name and the next release](007-name-and-release.md) | isolinear → caland, and the first release under it | prepared; questions open |

## How to read a requirement

Each has a number (`R3`) and says where it stands: *(built, 0.3.0)* names the release it
arrived in; *(proposal)* is the writer's and not decided. A spec ends with what it leaves out
on purpose, what was decided and by whom, and what is still to decide.

## Still open

The owner's to answer. Until they are, no feature work starts — that is what "specs first"
means here.

**The direction**

1. **What should caland become?** It is a tool for a person at a terminal; stevin and lely
   are tools for a pipeline. Does it stay that, and get better at it, or does it grow a side
   that runs without a person? → [000, D1](000-what-caland-is.md#to-decide)
2. **What is wrong with it today?** The name was, and that is settled. The specs describe
   the tool as it is; which of it should be different is not written anywhere yet.
   → [000, D2](000-what-caland-is.md#to-decide)

**The release**

3. **The first release as caland**: which version, whether the address stays in the
   package, and whether the rename goes out on its own before anything else.
   → [007](007-name-and-release.md#to-decide)

**Found while writing** — where the tool and what is said about it disagree. None is fixed:
each is listed with a proposal, for a yes or a no.

4. The dialog before deleting a secret says it cannot be undone; it can.
   → [003, D1](003-secrets.md#to-decide)
5. The docs say a value is read only when revealed or copied; deleting and moving read it
   too. → [006, D1](006-safety.md#to-decide)
6. *Who has access* does not follow groups, and does not say so.
   → [004, D1](004-scopes-and-permissions.md#to-decide)
7. An import that fails halfway says how many went in, not which.
   → [005, D1](005-bulk-and-audit.md#to-decide)
8. `f` — only my scopes, or all — is in the app's help and in none of the docs.
9. `docs/USER_STORIES.md` is behind the tool: it lists bulk import and export as out of
   scope, and they are built. → [000, D3](000-what-caland-is.md#to-decide)

**Proposals nobody asked for** — the writer's, to take or leave.

10. Forget a value some minutes after it was last shown. → [003, D2](003-secrets.md#to-decide)
11. Let a workspace be marked to open read-only. → [006, D2](006-safety.md#to-decide)

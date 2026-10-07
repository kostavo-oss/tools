# The spec

What caland is, what each part of it must do, and what is still open. `docs/` tells a user
how to use it; this says what it promises, so that a change can be held to something.

Written on 2026-10-06, when the tool took the name caland. 001–006 were written from the
terminal app as it was at 0.4.1 — its code, its tests, its docs and its changelog — and say
what the page does today; what only the terminal app had is listed in each as gone. 007 and
008 were plans that day, and are built, merged and released since: caland 0.5.0, 0.5.1 and
0.5.2 on 2026-10-06, and 0.6.0 on 2026-10-07, the release in which caland became the page.
009 is parked, with nothing built beyond what 004 describes. What is not decided is in each
spec's **To decide**, and gathered below.

| Spec | What | Stands |
| --- | --- | --- |
| [000 — what caland is](000-what-caland-is.md) | Who it is for, where it fits, the rules it keeps | written; the direction is decided |
| [001 — connecting](001-connecting.md) | Which workspace, signing in, switching | built |
| [002 — browsing](002-browsing.md) | Three panes, sorting, filtering, searching, the cache | built |
| [003 — secrets](003-secrets.md) | Create, edit, move, delete, undo; reveal and copy | built |
| [004 — scopes and permissions](004-scopes-and-permissions.md) | Scopes, ACLs, who can touch what | built |
| [005 — bulk work and audits](005-bulk-and-audit.md) | `.env` in and out, the stale-secret report | built |
| [006 — what caland may do](006-safety.md) | What it never stores, what it asks before, read-only | built |
| [007 — the name and the releases under it](007-name-and-release.md) | isolinear → caland, and the releases since | done: released as 0.5.0 to 0.6.0; one question open |
| [008 — the page](008-the-page.md) | caland as a local page in lely's look, with a file picker | built and released (0.6.0); it is what caland is |
| [009 — who reads a secret](009-who-reads-a-secret.md) | Who can read it, through which group; when it was last read | parked; last-read ruled out |

## How to read a requirement

Each has a number (`R3`) and says where it stands: *(built, 0.3.0)* names the release it
arrived in; *(proposal)* is the writer's and not decided. A spec ends with what it leaves out
on purpose, what was decided and by whom, and what is still to decide.

## Still open

The owner's to answer.

**Answered** → [000, Decided](000-what-caland-is.md#decided),
[008, Decided](008-the-page.md#decided)

- caland is a tool for people working with secrets, and it is a page in the browser,
  served from the person's own machine. It uses only the SDK.
- caland has no terminal version. The terminal app is `isolinear`, left as it is until the
  owner removes it.
- The release that made caland the page is a minor version: 0.6.0, on 2026-10-07.
  → [007](007-name-and-release.md)

**Open**

1. **isolinear's two bugs** — a rename that only changes the case deletes the secret; a
   `.env` value over several lines is mis-read. Fixed in caland only.
   → [007, D4](007-name-and-release.md#to-decide)
2. *Who has access* does not follow groups. → [004, D1](004-scopes-and-permissions.md#to-decide),
   [009](009-who-reads-a-secret.md)
3. Where a vulnerability is reported: a personal work address is in `SECURITY.md` and the
   docs. → [006, D3](006-safety.md#to-decide)

**Proposals nobody asked for** — the writer's, to take or leave.

4. Forget a value once it has been shown or copied: nothing reads it back any more.
   → [003, D2](003-secrets.md#to-decide)
5. Let a workspace be marked to open read-only. → [006, D2](006-safety.md#to-decide)

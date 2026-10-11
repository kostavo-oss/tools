# Tried, and not yet

What has run against a real workspace, and what has not. This page is the one record of
it. Everything else Caland does is held by its tests: against a stand-in for the
workspace, with the server asked over real HTTP and the page driven in Chrome.

The runs below were made on 2026-10-06, on one test workspace, with the page as it was
that day, between 0.5.0 and 0.6.0. No run of a later release on a workspace is on
record.

## 2026-10-06: reading

Caland connected with a profile and was ready in 2.3 seconds; the page was painted
after 60 ms. That workspace had no secret scopes then, so what was shown was the empty
page.

## 2026-10-06: changing

The real page, driven in Chrome, in a throwaway scope it made and removed. Each step was
checked through the SDK, not through Caland. The workspace had the scopes afterwards
that it had before.

| What | Held? |
|---|---|
| A scope is made, and deleted with what was in it | yes |
| Text is stored as it was typed | yes |
| A file of every byte there is (NULs, a byte order mark, CRLF, random bytes) is stored byte for byte and shown as what it is | yes |
| A certificate is described, and stored as the file was | yes |
| A rename, and the original put back | yes |
| A delete, and the secret put back byte for byte | yes |
| A grant given and taken | yes |
| A rename that only changes the case is refused, and the secret is still there | yes |
| `Case-Key` and then `case-key` is one secret, and a scope asked for in capitals "already exists" | yes |

20 checks, all held, and run again after the fixes of that day's review.

## 2026-10-06: which workspace

Plain `caland` opened the page on the test workspace. ++w++ listed the one profile the
machine has, found in `~/.databrickscfg`; chosen again, it connected again.

## Not yet

- **A Key Vault-backed scope.** The workspace has none.
- **A workspace where the person may not write.**
- **The choice between several workspaces, and signing in by an address.** That opens a
  browser to sign in with, which nothing here can drive.
- **`.env` in and out, the stale list and the two lists of access**, on a real workspace.
- **Firefox and Safari.** The page is driven in Chrome only.
- **A real drag and drop** of a file onto the form.
- **Windows.**
- **Stopping by itself while a real sign-in in the browser waits.** The tests hold it
  with a sign-in that never finishes, made by a stand-in. The SDK's own wait was not run.
- **A real DNS name pointed at the machine**, and a Mac whose `.html` files open in
  something other than the browser. There `caland --no-open` gives the link.

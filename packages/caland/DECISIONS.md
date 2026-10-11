# Decisions

Why caland is the way it is: a log, oldest first. An entry is here because it says why,
or what was considered and turned down. What must be true of the code is in
[RULES.md](RULES.md).

**An entry is never edited.** A decision that changes gets a new entry at the end, which
names the one it supersedes by its number.

## 1. 2026-10-06 — The name is caland

It replaced `isolinear`, the name up to 0.4.1. Why: a person's name, as the other
Kostavo tools have. `maeslant` was the name for a day and was turned down: it is a
storm surge barrier, not a person.

## 2. 2026-10-06 — For a person working with secrets, and only that

Turned down: a side of caland that runs unattended, and grants as a step of lely.
caland declares nothing and plans nothing.

## 3. 2026-10-06 — Only the SDK, so no answer to when a secret was last read

caland runs no query, starts no warehouse and reads no system table. That rules out
saying when a secret was last read: the one record of a read is the audit log, read as
the table `system.access.audit`, which takes Unity Catalog, a grant from an account
admin and a SQL warehouse
([audit log reference](https://docs.databricks.com/aws/en/admin/account-settings/audit-logs)).
The secrets API says when a secret was last changed and nothing about reads.

## 4. 2026-10-06 — A page in a browser tab, from a server on the person's own machine

It replaced the terminal app. Why: a terminal has no file dialog, so a certificate went
in by typing a path, and it cannot show what a certificate is before it goes in.
Turned down: a window of its own (a web view per system, awkward on Linux, nothing over
SSH or in a dev container), the terminal app served in a tab (no file dialog), and a
file picker drawn by caland (it would make caland a file server). The cost is a local
port to defend: the `GATE` rules.

## 5. 2026-10-06 — Tab goes from pane to pane

Why: a browser stops tab at every button, which makes a page of buttons a long walk and
never reaches a list. Tab is not caught either: a page that keeps it cannot be left by
keyboard.

## 6. 2026-10-06 — Python's own HTTP server, and a script of caland's own

One HTML file, one style sheet, one script; no framework and no build step. Why: it serves one person on one machine, and it is one
dependency fewer to trust.

## 7. 2026-10-06 — A page is let in by a header and a key in a file, never by a cookie

Why no cookie: a cookie for `127.0.0.1` is sent to every port of the machine, so to any
other program serving pages there; a header of caland's own cannot be sent from another
site. Why the one-time key reaches the browser in a file: a link on a command line can
be read by every user of the machine. The token is kept in the tab's `sessionStorage`
for a reload only, because a site the tab went on to can send the tab back.

## 8. 2026-10-06 — Copying happens in the page, and the clipboard is not cleared

Turned down: caland copying on the machine it runs on, which needs a different program
on each system and copies to the wrong machine over a forwarded port. Turned down:
clearing the clipboard after a while. caland cannot read the clipboard back, so it could
not know it was clearing its own value.

## 9. 2026-10-06 — A certificate is read with `cryptography`

Why: the kind of a file can be told without a library; who a certificate is for and
when it expires cannot.

## 10. 2026-10-06 — A value is bytes from end to end

It replaced carrying a value as text. Why: a file that is no text, such as a PKCS#12
bundle, did not survive a move.

## 11. 2026-10-06 — A private key and a PKCS#12 bundle are named, never opened

Why: a bundle says itself how many rounds its check takes. A file of 785 bytes asked for
minutes of them and froze the server.

## 12. 2026-10-06 — Nothing lands on what is there, and a scope has a key of its own

A new secret does not overwrite and a move does not land on another secret: neither can
be taken back, and both happen by a slip. `D` deletes a scope; it replaced `d` for
whichever the keyboard was on, which deleted a scope when a secret was meant.

## 13. 2026-10-06 — A name in another case is the same name

Why: to Databricks it is. A rename that only changed the case wrote the secret and then
removed "the old one", which was the same secret.

## 14. 2026-10-06 — One change at a time, against what is there now

Why: a review found that `d`, `y`, then `u` before the answer could lose the secret, and
that a move used the value read earlier, so a secret changed elsewhere since lost its
new value.

## 15. 2026-10-06 — A delete reads the value first

Why: it is what makes `u` possible.

## 16. 2026-10-06 — An import that stops stays halfway; an export never goes to a file

Turned down: taking back what an import wrote before it was refused. caland keeps no
state, and a secret that was overwritten has lost its old value either way. Turned
down: writing an export to a file, because a value on disk outlives the session.

## 17. 2026-10-06 — A sign-in is kept as a profile under a new name only

Why: a profile keeps its own way of signing in, often a token. Pointed at another
address, the token would be sent there.

## 18. 2026-10-06 — A request about a workspace says which one

Why: a review found that a change queued in one workspace, or asked from a second tab,
could be done in the workspace caland had gone to since.

## 19. 2026-10-07 — No terminal version; isolinear is left as it is

It superseded freezing the terminal app behind `caland --tui`, and the commands
`isolinear` and `iso` that 0.5.0 to 0.5.2 installed beside `caland`. Turned down: a last
release of `isolinear` that only points at caland. Why: isolinear is to stay what it is,
and with both installed the commands no longer collide. What it leaves: isolinear 0.4.1
has two bugs that are fixed in caland only, and caland's installation page names them.

## 20. 2026-10-07 — A value is read from the workspace every time it is asked for

It replaced reading a value once and keeping it. Why: a second look could show a value
that was no longer there. Each value read is still held in memory and used by nothing;
letting go of them is [issue 48](https://github.com/kostavo-oss/tools/issues/48).

## 21. 2026-10-07 — A failure inside is one line in the terminal

Until then a failure left no trace. The line never holds the failure's own words, which
can quote a value, and there are twenty at most, so that nobody who can reach the port
can fill a terminal.

## 22. 2026-10-09 — Every scope is shown, the ones out of reach greyed

It replaced showing only the scopes within reach. Why: the scope a person has to ask
access to is the one they could not see.

## 23. 2026-10-10 — The look is a file, copied into three packages

`base.css` is the same in caland, lely and stevin, and a test at the root of the
repository holds the copies equal. Turned down: a shared package for it. No package of
the repository imports another, and a package for a few lines of style costs more than
the copies. It supersedes the one style sheet of entry 6.

## 24. 2026-10-11 — One place per fact, and no spec folder

It replaced `spec/`: ten files, a README and a mock-up of the page, which held rules,
decisions, runs and history together. Why: an audit found 69% of its checked statements
true as written. The parked spec on who can read a secret is
[issue 47](https://github.com/kostavo-oss/tools/issues/47); the mock-up is not kept.

## 25. 2026-10-11 — A signal leaves a note, and never raises

ctrl+c and a signal to terminate set a flag, and the server looks at the flag between
two requests, at most 0.2 seconds later. Why: a handler that raises can raise anywhere,
also inside the tidying, which then stops halfway and leaves the file with the key
behind. Turned down: ignoring the signals when the tidying starts, as the issue
proposed. Between the first signal being raised and the signals being ignored there is
a moment in which a second one still raises. Turned down too: an `Event` set by the
handler. A handler runs on the main thread, which can be holding the lock the event
needs. The cost: a browser that keeps the terminal while it starts is waited for
before caland stops.

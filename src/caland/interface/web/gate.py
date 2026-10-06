"""The gate — which requests the local server answers.

A server that can read secrets, on a machine whose browser is full of other
sites, has to be sure of who is asking. This module is that decision and
nothing else: no sockets, no workspace, no clock — a request's method, path and
headers go in, and either nothing comes out or the reason it is refused.

What it holds to (spec/008-the-page.md, R9):

* **Only its own address.** A request whose `Host` is not the address the server
  listens on is refused — that is what a site does that had its name pointed at
  this machine (DNS rebinding).
* **Only its own page.** A request that names where it came from (`Origin`,
  `Sec-Fetch-Site`) and did not come from caland's own page is refused.
* **Only with the session's token**, in a header. A header of our own cannot be
  sent from another site without asking first, and nothing here ever says yes;
  it is not a cookie, so no other server on this machine is sent it either.
* **Nothing that changes or reveals by a link.** Everything under `/api/` that
  is a `POST` must say it is JSON, which a form on another site cannot.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import dataclass

#: The header the page sends the session's token in.
TOKEN_HEADER = "X-Caland-Token"

#: The header the page says in which workspace it believes it is: the number the
#: state gave it. A request about a workspace is answered only for the one caland
#: is in — a page left showing another must not change this one.
WORKSPACE_HEADER = "X-Caland-Workspace"

#: The one request under `/api/` that needs no token: it is how the token is got.
ENTER = "/api/enter"

#: The page itself. It holds nothing: anyone may be given it.
STATIC = ("/", "/page.css", "/page.js")


@dataclass(frozen=True)
class Refusal:
    status: int
    reason: str


def same(given: str, expected: str) -> bool:
    """Whether two secrets are the same, in time that does not depend on where
    they differ."""
    return hmac.compare_digest(given.encode(), expected.encode())


def hosts(port: int) -> frozenset[str]:
    """The names this server answers to."""
    return frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})


def check(
    method: str,
    path: str,
    header: Callable[[str], str | None],
    *,
    port: int,
    token: str,
) -> Refusal | None:
    """None when the request may be answered; why not otherwise.

    `header` gives a header's value by its name, or None. Names are asked for as
    written here; hand it something that does not mind their case, as the `get`
    of `http.server`'s headers does not.
    """
    if (header("Host") or "") not in hosts(port):
        return Refusal(403, "not this server's address")

    origin = header("Origin")
    if origin is not None and origin not in {f"http://{host}" for host in hosts(port)}:
        return Refusal(403, "not from caland's page")

    if method not in ("GET", "POST"):
        return Refusal(405, "not something caland does")

    if path in STATIC:
        if method != "GET":
            return Refusal(405, "the page is only read")
        return None

    if not path.startswith("/api/"):
        return Refusal(404, "nothing here")

    # a browser says where a request was made from; anything but our own page
    # asking is refused. A client that does not say (it is no browser) is held
    # to the token like everyone else.
    site = header("Sec-Fetch-Site")
    if site is not None and site != "same-origin":
        return Refusal(403, "not from caland's page")

    if method == "POST":
        kind = (header("Content-Type") or "").split(";")[0].strip().lower()
        if kind != "application/json":
            return Refusal(415, "say it in JSON")

    if path == ENTER:
        if method != "POST":
            return Refusal(405, "ask with the key")
        return None

    given = header(TOKEN_HEADER) or ""
    if not given or not same(given, token):
        return Refusal(401, "no key for this session")
    return None

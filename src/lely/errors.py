"""One base class, so a host can catch lely and nothing else.

The classes themselves stay in the module that raises them, next to the code
that knows why: `ConfigError` in the loader, `RefError` in `refs`. Here are only
the root they share, and the one distinction every caller needs.
"""

from __future__ import annotations


class LelyError(Exception):
    """Something lely refuses to do, with the reason in the message.

    Messages are complete sentences and name the file, step or reference they
    are about, so a host can show one without adding context of its own.
    """


class Refused(LelyError):
    """lely won't go on, and running the same thing again won't help.

    A plan that went stale, a waiting step in a reviewed file, a change that
    wasn't approved, a destructive change that wasn't allowed, no consent. The
    command line ends with 2 for these and with 1 for a failure, so a pipeline
    can tell "plan again" from "something broke".
    """

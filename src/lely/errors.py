"""One base class, so a host can catch lely and nothing else.

The classes themselves stay in the module that raises them, next to the code
that knows why: `ConfigError` in the loader, `RefError` in `refs`. This is only
the root they share.
"""

from __future__ import annotations


class LelyError(Exception):
    """Something lely refuses to do, with the reason in the message.

    Messages are complete sentences and name the file, step or reference they
    are about, so a host can show one without adding context of its own.
    """

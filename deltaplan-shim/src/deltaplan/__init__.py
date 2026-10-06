"""deltaplan is now stevin.

What is left of the old name on PyPI. Installing it installs stevin; importing
it gives stevin's public names, and a `DeprecationWarning` that says to import
stevin instead. Only the names stevin exports are here — `deltaplan.<module>`
was never part of what could be relied on, and isn't forwarded.
"""

import warnings
from typing import Any

import stevin
from stevin import *  # noqa: F403 - the public API, exactly as stevin exports it
from stevin import StevinError as DeltaplanError

warnings.warn(
    "deltaplan is now stevin: install `stevin`, `import stevin`, and catch "
    "`StevinError` where this said `DeltaplanError`. This package only forwards to "
    "it, and is the last release under the old name.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [*stevin.__all__, "DeltaplanError"]


def __getattr__(name: str) -> Any:
    # what stevin answers lazily, `__version__` first of all
    return getattr(stevin, name)

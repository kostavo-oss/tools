"""isolinear is now caland.

What is left of the old name on PyPI. Installing it installs caland, and the
`isolinear` and `iso` commands run it. isolinear never had a Python API, so
there is nothing to forward here — only a warning for anyone who imports it.
"""

import warnings

warnings.warn(
    "isolinear is now caland: install `caland` and run `caland`. This "
    "package only forwards to it, and is the last release under the old name.",
    DeprecationWarning,
    stacklevel=2,
)

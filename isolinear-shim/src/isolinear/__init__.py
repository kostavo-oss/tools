"""isolinear is now maeslant.

What is left of the old name on PyPI. Installing it installs maeslant, and the
`isolinear` and `iso` commands run it. isolinear never had a Python API, so
there is nothing to forward here — only a warning for anyone who imports it.
"""

import warnings

warnings.warn(
    "isolinear is now maeslant: install `maeslant` and run `maeslant`. This "
    "package only forwards to it, and is the last release under the old name.",
    DeprecationWarning,
    stacklevel=2,
)

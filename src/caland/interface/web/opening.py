"""Opening the page in the person's browser, without telling the machine the key.

The address of the page carries a one-time key. Handing that address to the
browser the plain way puts it on a command line (`open …`, `xdg-open …`), and a
command line can be read by every user of the machine. So the browser is handed
a file instead — one only its owner can read — and the file sends it on.

The key is good once and dies with the run; the file is removed as soon as the
key has been used, and at the end whatever happened.
"""

from __future__ import annotations

import contextlib
import html
import shutil
import tempfile
import webbrowser
from collections.abc import Callable
from pathlib import Path

_PAGE = """\
<!doctype html>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0;url={address}">
<title>caland</title>
<p>Opening caland&hellip; <a href="{address}">go on</a></p>
"""


class Opener:
    def __init__(self, browser: Callable[[str], bool] = webbrowser.open) -> None:
        self._browser = browser
        self._folder: Path | None = None

    def open(self, address: str) -> bool:
        """Send the browser to `address`. False when no browser could be started."""
        self.clean()
        folder = Path(tempfile.mkdtemp(prefix="caland-"))  # the owner's alone (0700)
        self._folder = folder
        page = folder / "open.html"
        page.touch(mode=0o600)
        page.write_text(_PAGE.format(address=html.escape(address, quote=True)))
        try:
            return bool(self._browser(page.as_uri()))
        except Exception:  # noqa: BLE001 — a browser that cannot start is not an error here
            return False

    def clean(self) -> None:
        """Remove the file. Safe to call more than once."""
        if self._folder is not None:
            with contextlib.suppress(OSError):
                shutil.rmtree(self._folder)
            self._folder = None

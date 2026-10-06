"""Opening the page: the key goes to the browser in a file, not on a command line."""

from __future__ import annotations

import stat
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from caland.interface.web.opening import Opener

LINK = "http://127.0.0.1:5123/#the-one-time-key"


def opened_with(browser_says=True):
    seen: list[str] = []

    def browser(address: str) -> bool:
        seen.append(address)
        return browser_says

    return Opener(browser), seen


def path_of(address: str) -> Path:
    return Path(unquote(urlsplit(address).path))


def test_the_browser_is_handed_a_file_and_never_the_key():
    opener, seen = opened_with()
    assert opener.open(LINK) is True
    assert seen[0].startswith("file://") and "the-one-time-key" not in seen[0]
    assert LINK in path_of(seen[0]).read_text()
    opener.clean()


def test_the_file_is_its_owners_alone():
    opener, seen = opened_with()
    opener.open(LINK)
    page = path_of(seen[0])
    if sys.platform != "win32":
        assert stat.S_IMODE(page.stat().st_mode) == 0o600
        assert stat.S_IMODE(page.parent.stat().st_mode) == 0o700
    opener.clean()


def test_the_file_goes_when_cleaned_and_cleaning_twice_is_fine():
    opener, seen = opened_with()
    opener.open(LINK)
    page = path_of(seen[0])
    opener.clean()
    opener.clean()
    assert not page.exists() and not page.parent.exists()


def test_opening_again_leaves_one_file():
    opener, seen = opened_with()
    opener.open(LINK)
    opener.open(LINK.replace("the-one-time", "another"))
    assert not path_of(seen[0]).exists() and path_of(seen[1]).exists()
    opener.clean()


def test_a_browser_that_does_not_start_is_said_not_raised():
    opener, _ = opened_with(browser_says=False)
    assert opener.open(LINK) is False
    opener.clean()

    def broken(address: str) -> bool:
        raise OSError("no display")

    opener = Opener(broken)
    assert opener.open(LINK) is False
    opener.clean()


def test_an_address_cannot_break_out_of_the_file():
    opener, seen = opened_with()
    opener.open('http://127.0.0.1:1/#"><script>alert(1)</script>')
    assert "<script>" not in path_of(seen[0]).read_text()
    opener.clean()

"""The page, in a real browser, against the fake workspace.

Chrome is driven over its debugging pipe (`chrome.py`): real keys, the real page.
Skipped where there is no Chrome; CI's runners have one.
"""

from __future__ import annotations

import threading

import pytest

from caland.application import Loader, WorkspaceService
from caland.domain import Acl, Scope, Secret, Workspace
from caland.interface.web import Page, Server
from chrome import CHROME, Browser
from fakes import FakeSecretStore

pytestmark = pytest.mark.skipif(CHROME is None, reason="needs Chrome")

VALUE = "sk_made_up_4f9a1c7e2b8d"
#: A name as no workspace allows it — the page must not care. The z sorts it last.
MARKUP = "z<img src=x onerror=document.title='owned'>"


def workspace() -> FakeSecretStore:
    return FakeSecretStore(
        scopes=[
            Scope("prod"),
            Scope("staging"),
            Scope("kv", "AZURE_KEYVAULT"),
            Scope("shut"),
        ],
        secrets={
            "prod": [
                Secret("prod", "api-key", 1_758_000_000_000),
                Secret("prod", "db-password", 1_740_000_000_000),
                Secret("prod", "tls-cert", 1_730_000_000_000),
                Secret("prod", MARKUP, 1_730_000_000_000),
            ],
            "staging": [Secret("staging", "api-key", 1_759_000_000_000)],
            "kv": [Secret("kv", "tenant-id", 1_717_000_000_000)],
        },
        acls={
            "prod": [
                Acl("me@corp.com", "MANAGE"),
                Acl(MARKUP, "WRITE"),
                Acl("users", "READ"),
            ],
            "staging": [Acl("me@corp.com", "MANAGE")],
            "kv": [Acl("users", "READ")],
        },
        values={("prod", "api-key"): VALUE},
        no_read={"shut"},
    )


def big(scopes: int, secrets: int) -> FakeSecretStore:
    names = [f"scope-{i:03d}" for i in range(scopes)]
    return FakeSecretStore(
        scopes=[Scope(name) for name in names],
        secrets={
            name: [
                Secret(name, f"key-{j:02d}", 1_750_000_000_000) for j in range(secrets)
            ]
            for name in names
        },
        acls={name: [Acl("me@corp.com", "MANAGE")] for name in names},
    )


@pytest.fixture(scope="module")
def browser():
    chrome = Browser()
    yield chrome
    chrome.close()


@pytest.fixture
def serve():
    running = []

    def start(store: FakeSecretStore) -> Server:
        loader = Loader(lambda: WorkspaceService(store, "test"))
        page = Page(
            loader,
            workspace=Workspace(profile="test", host="https://x.example"),
            version="9.9",
        )
        server = Server(page)
        loader.start()
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.01}
        )
        thread.start()
        running.append((server, thread))
        return server

    yield start
    for server, thread in running:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def page(browser, serve):
    """The page, entered with its key and showing the workspace."""
    store = workspace()
    server = serve(store)
    tab = browser.tab(f"{server.address}#{server.page.new_key()}")
    tab.wait(SHOWN)
    tab.store, tab.server = store, server
    return tab


#: The first scope, `kv`, is selected and its one secret is listed.
SHOWN = (
    "document.body.dataset.phase === 'ready'"
    " && document.querySelectorAll('#scopes li').length === 3"
    " && document.querySelectorAll('#secrets tr').length === 1"
)
#: `prod` is selected: its four secrets are listed and its detail has arrived.
PROD = (
    "document.querySelectorAll('#secrets tr').length === 4"
    " && document.querySelector('#detail button')"
)
#: How many times the page has asked the server anything.
ASKED = (
    "performance.getEntriesByType('resource')"
    ".filter(r => r.name.includes('/api/')).length"
)
SELECTED_SCOPE = "document.querySelector('#scopes [aria-selected=true] span').textContent"
SELECTED_KEY = "document.querySelector('#secrets [aria-selected=true] td').textContent"
WHOLE_PAGE = "document.documentElement.outerHTML"


# ── getting in ───────────────────────────────────────────────────────
def test_it_opens_with_its_key_and_shows_the_workspace(page):
    assert page.js(
        "[...document.querySelectorAll('#scopes li span.mono')].map(n => n.textContent)"
    ) == [
        "kv",
        "prod",
        "staging",
    ]  # `shut` is out of reach, and not shown until asked for
    assert page.js("document.getElementById('who').textContent") == "me@corp.com"
    assert page.js("document.getElementById('host').textContent") == "x.example"


def test_the_key_is_gone_from_the_address_at_once(page):
    assert page.js("location.hash") == ""
    assert page.js("location.href").endswith("/")
    assert page.server.page.enter("anything") is None  # and it is spent


def test_without_a_key_the_page_shows_nothing_and_says_what_to_do(browser, serve):
    server = serve(workspace())
    tab = browser.tab(server.address)
    tab.wait("!document.getElementById('locked').hidden")
    assert tab.js("document.getElementById('app').hidden") is True
    assert "prod" not in tab.js("document.body.innerText")
    assert "press" in tab.js("document.getElementById('locked').innerText")


def test_a_wrong_key_is_no_key(browser, serve):
    server = serve(workspace())
    server.page.new_key()
    tab = browser.tab(f"{server.address}#not-the-key")
    tab.wait("!document.getElementById('locked').hidden")
    assert tab.js("sessionStorage.length") == 0


def test_a_reload_stays_in(page):
    page.reload()
    page.wait(SHOWN)


def test_another_tab_is_not_in(browser, page):
    other = browser.tab(page.server.address)
    other.wait("!document.getElementById('locked').hidden")


def test_coming_back_to_the_page_is_not_a_reload(page):
    """A site the tab went on to can send it back here, and a window it opens is
    handed a copy of what the tab kept. Neither finds the page open."""
    assert page.js("sessionStorage.getItem('caland')") == page.server.page.token
    page.go("about:blank")
    page.go(page.server.address)
    page.wait("!document.getElementById('locked').hidden")
    assert page.js("document.getElementById('app').hidden") is True
    assert page.js("sessionStorage.length") == 0
    assert "kv" not in page.js(WHOLE_PAGE.replace("outerHTML", "innerText"))


def test_a_page_that_loses_its_key_shows_nothing_it_was_told(page):
    page.press("j")
    page.wait(PROD)
    page.press("l", " ")
    page.wait("document.querySelector('pre.value.shown')")
    page.server.page.token = "another-run"  # as when caland was started again
    page.press("r")
    page.wait("!document.getElementById('locked').hidden")
    whole = page.js(WHOLE_PAGE)
    assert VALUE not in whole and "api-key" not in whole and "me@corp.com" not in whole
    assert page.js("sessionStorage.length") == 0


def test_nothing_is_kept_by_the_browser_but_the_token_for_this_tab(page):
    page.press("j")
    page.wait(PROD)
    page.press("l", " ")
    page.wait("document.querySelector('pre.value.shown')")
    assert page.js("Object.keys(sessionStorage)") == ["caland"]
    assert page.js("localStorage.length") == 0 and page.js("document.cookie") == ""
    assert VALUE not in page.js("JSON.stringify(Object.entries(sessionStorage))")


# ── the keyboard ─────────────────────────────────────────────────────
def test_it_opens_with_the_keyboard_in_the_scopes(page):
    assert page.focus() == "scopes"


def test_tab_goes_from_pane_to_pane(page):
    page.press("Tab")
    assert page.focus() == "keys"
    page.press("Tab")
    assert page.focus() == "Show"
    page.press("Tab", shift=True)
    assert page.focus() == "keys"
    page.press("Tab", shift=True)
    assert page.focus() == "scopes"


def test_nothing_that_scrolls_is_a_stop_of_its_own(page):
    """A browser makes a box that scrolls a stop for tab unless it is told not to;
    which browsers do differs. The stops are these, whatever the browser."""
    page.press("j")
    page.wait(PROD)
    stops = page.js(
        """[...document.querySelectorAll('main *')].filter((node) => {
          const scrolls = ['auto', 'scroll'].includes(getComputedStyle(node).overflowY);
          return node.tabIndex >= 0 || (scrolls && !node.hasAttribute('tabindex'));
        }).map((node) => node.id || node.textContent.trim().split(/\\s+/)[0])"""
    )
    assert stops == ["scopes", "keys", "Show"]


def test_tab_is_not_kept_by_the_page(page):
    """After the last stop it leaves for the browser's own bar, as on any page."""
    page.press("Tab", "Tab", "Tab")
    assert page.js(
        "document.activeElement === document.body || !document.hasFocus()"
    ) or (page.focus() not in ("scopes", "keys", "Show"))


def test_arrows_move_inside_a_pane_and_across(page):
    page.press("j")
    assert page.js(SELECTED_SCOPE) == "prod" and page.focus() == "scopes"
    page.wait(PROD)
    page.press("ArrowRight")
    assert page.focus() == "keys"
    page.press("ArrowDown")
    assert page.js(SELECTED_KEY) == "db-password"
    page.press("G")
    assert page.js(SELECTED_KEY) == MARKUP
    page.press("g", "l")
    assert page.focus() == "Show"
    page.press("l")
    assert page.focus() == "Copy"
    page.press("h", "h")
    assert page.focus() == "keys"
    page.press("h")
    assert page.focus() == "scopes"


def test_the_filter_picks_while_typing_and_goes_back(page):
    page.press("j")
    page.wait(PROD)
    page.press("/")
    assert page.focus() == "filter"
    asked = page.js(ASKED)
    page.type("tls")
    page.wait(f"{SELECTED_KEY} === 'tls-cert'")
    assert page.js("document.querySelectorAll('#secrets tr').length") == 1
    assert page.focus() == "filter"
    assert page.js(ASKED) == asked  # no round-trip
    page.press("Enter")
    assert page.focus() == "keys"
    page.press("/", "Escape")
    assert page.js("document.getElementById('filter').value") == ""
    assert page.focus() == "keys"
    assert page.js("document.querySelectorAll('#secrets tr').length") == 4


def test_f_shows_the_scopes_out_of_reach_too(page):
    page.press("f")
    page.wait("document.querySelectorAll('#scopes li').length === 4")
    assert page.js("document.querySelector('#scopes li.out span').textContent") == "shut"
    page.press("f")
    page.wait("document.querySelectorAll('#scopes li').length === 3")


# ── a value ──────────────────────────────────────────────────────────
def test_a_value_is_in_the_page_only_while_it_is_shown(page):
    page.press("j")
    page.wait(PROD)
    page.press("l")
    assert page.store.count("get_secret_value") == 0  # nothing was read to get here
    assert VALUE not in page.js(WHOLE_PAGE)
    page.press(" ")
    page.wait("document.querySelector('pre.value.shown')")
    assert page.js("document.querySelector('pre.value').textContent") == VALUE
    assert page.focus() == "keys"
    assert "hides in" in page.js("document.getElementById('hint').textContent")
    page.press(" ")
    page.wait("!document.querySelector('pre.value.shown')")
    assert VALUE not in page.js(WHOLE_PAGE)


def test_moving_on_takes_the_value_off_the_page(page):
    page.press("j")
    page.wait(PROD)
    page.press("l", " ")
    page.wait("document.querySelector('pre.value.shown')")
    page.press("j")
    assert VALUE not in page.js(WHOLE_PAGE)


def test_space_on_a_button_presses_that_button(page):
    page.press("j")
    page.wait(PROD)
    page.press("l", "l", "l", "l")  # secrets, then Show, Copy, Copy as code
    assert page.focus() == "Copy"
    page.press("l")
    page.press(" ")
    page.wait("document.getElementById('code').open")
    assert VALUE not in page.js(WHOLE_PAGE)  # it did not show the value
    assert 'dbutils.secrets.get(scope="prod", key="api-key")' in page.js(
        "document.getElementById('code-rows').innerText"
    )
    page.press("Escape")
    page.wait("!document.getElementById('code').open")
    assert page.focus() == "Copy"  # the keyboard is back where it was


# ── what a workspace says is text ────────────────────────────────────
def test_a_name_is_text_and_never_markup(page):
    page.press("j")
    page.wait(PROD)
    page.wait("document.querySelector('#detail table')")
    assert page.js("document.querySelectorAll('main img, main script').length") == 0
    assert page.js("document.title") == "caland"
    assert MARKUP in page.js(
        "[...document.querySelectorAll('#secrets td')].map(n => n.textContent)"
    )
    assert MARKUP in page.js("document.getElementById('detail').innerText")


def test_a_name_goes_into_code_as_a_name_whatever_is_in_it(page):
    page.press("j")
    page.wait(PROD)
    page.press("l", "G", "C")
    page.wait("document.getElementById('code').open")
    forms = page.js(
        "[...document.querySelectorAll('#code-rows .mono')].map(n => n.textContent)"
    )
    assert forms[0] == f'dbutils.secrets.get(scope="prod", key="{MARKUP}")'
    quoted = MARKUP.replace("'", "'\\''")
    assert forms[2] == f"databricks secrets get-secret prod '{quoted}'"


def test_a_scope_may_be_called_what_every_object_has(browser, serve):
    names = ["__proto__", "constructor", "toString", "hasOwnProperty"]
    server = serve(
        FakeSecretStore(
            scopes=[Scope(name) for name in names],
            secrets={
                name: [Secret(name, f"key-of-{name}", 1_750_000_000_000)]
                for name in names
            },
            acls={name: [Acl("me@corp.com", "MANAGE")] for name in names},
        )
    )
    tab = browser.tab(f"{server.address}#{server.page.new_key()}")
    tab.wait("document.body.dataset.phase === 'ready'")
    listed = (
        "[...document.querySelectorAll('#scopes li span.mono')].map(n => n.textContent)"
    )
    assert sorted(tab.js(listed)) == sorted(names)
    assert tab.js("document.getElementById('toast').hidden") is True
    assert tab.focus() == "scopes"
    for _ in names:
        name = tab.js(SELECTED_SCOPE)
        tab.wait(f"{SELECTED_KEY} === 'key-of-' + {SELECTED_SCOPE}")
        tab.wait("document.querySelector('#detail table')")
        assert f"key-of-{name}" in tab.js("document.getElementById('detail').innerText")
        tab.press("j")
    assert tab.js("document.getElementById('toast').hidden") is True


# ── fast, and held to it (spec/008, R7) ──────────────────────────────
def test_a_big_workspace_draws_at_once_and_filters_without_waiting(browser, serve):
    server = serve(big(500, 10))
    tab = browser.tab(f"{server.address}#{server.page.new_key()}")
    paint = (
        "performance.getEntriesByType('paint')"
        ".find(p => p.name === 'first-contentful-paint')"
    )
    tab.wait(paint)
    assert tab.js(f"{paint}.startTime") < 300
    tab.wait("document.body.dataset.phase === 'ready'", seconds=30)
    assert tab.js("document.querySelectorAll('#scopes li').length") == 500
    took = tab.js(
        """(() => {
          const field = document.getElementById('filter'), times = [];
          for (const text of ['s', 'sc', 'sc4', 'sc49', 'k', 'key-0', 'scope-250', '']) {
            const before = performance.now();
            field.value = text; field.dispatchEvent(new Event('input'));
            times.push(performance.now() - before);
          }
          return times.sort((a, b) => a - b)[Math.floor(times.length / 2)];
        })()"""
    )
    assert took < 50, f"a keystroke in the filter took {took:.0f} ms"

"""The page, in a real browser, against the fake workspace.

Chrome is driven over its debugging pipe (`chrome.py`): real keys, the real page.
Skipped where there is no Chrome; CI's runners have one.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import pytest

from caland.application import Loader, WorkspaceService
from caland.domain import Acl, Scope, Secret, StoreError, Workspace
from caland.interface.web import Page, Server
from caland.interface.web.server import Handler
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

    def start(store: FakeSecretStore, read_only: bool = False) -> Server:
        loader = Loader(lambda: WorkspaceService(store, "test"))
        page = Page(
            loader,
            workspace=Workspace(profile="test", host="https://x.example"),
            version="9.9",
            read_only=read_only,
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
#: Watch the page's requests to WHAT, for the tests that need an answer to come late.
#: With HOLD a request is not sent until the test calls `window.letGo()`, which is there
#: once the request is waiting. `window.answered` is true once the page has read the
#: answer: whatever the page does with it is done by the next look at the page.
LATE = """(() => { const real = window.fetch; window.answered = false;
  window.fetch = (url, options) => {
    if (!String(url).includes('WHAT')) return real(url, options);
    const first = HOLD ? new Promise((go) => { window.letGo = go; }) : Promise.resolve();
    return first.then(() => real(url, options)).then((answer) => {
      const read = answer.json.bind(answer);
      answer.json = () => read().finally(() => { window.answered = true; });
      return answer;
    });
  }; })()"""


def late(what: str, hold: bool = True) -> str:
    return LATE.replace("WHAT", what).replace("HOLD", "true" if hold else "false")


def until(so: Callable[[], object], seconds: float = 10) -> None:
    """Wait for something outside the page to be so — the server's own state, a
    call the workspace got — looked at again and again, and not for ever."""
    deadline = time.monotonic() + seconds
    while not so():
        if time.monotonic() > deadline:
            raise TimeoutError("it never came to be so")
        time.sleep(0.01)


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
    assert page.store.reads() == 0  # nothing was read to get here
    assert VALUE not in page.js(WHOLE_PAGE)
    page.press(" ")
    page.wait("document.querySelector('pre.value.shown')")
    assert page.js("document.querySelector('pre.value').textContent") == VALUE
    assert page.focus() == "keys"
    assert "hides in" in page.js("document.getElementById('hint').textContent")
    page.press(" ")
    page.wait("!document.querySelector('pre.value.shown')")
    assert VALUE not in page.js(WHOLE_PAGE)


def test_a_value_shown_again_is_read_again_and_is_what_is_there_now(page):
    page.press("j")
    page.wait(PROD)
    page.press("l", " ")
    page.wait("document.querySelector('pre.value.shown')")
    page.store._values[("prod", "api-key")] = "rotated elsewhere"
    page.press(" ")
    page.wait("!document.querySelector('pre.value.shown')")
    page.press(" ")
    page.wait("document.querySelector('pre.value.shown')")
    assert page.js("document.querySelector('pre.value').textContent") == (
        "rotated elsewhere"
    )
    assert page.store.reads() == 2
    page.press("c")
    page.wait(f"{TOAST} === 'Copied api-key.'")
    assert page.clipboard() == "rotated elsewhere" and page.store.reads() == 3


#: The page's clock, which the tests can put forward: `AHEAD` seconds from now on.
CLOCK = """(() => {
  if (window.ahead === undefined) {
    const real = Date.now.bind(Date);
    Date.now = () => real() + window.ahead;
  }
  window.ahead = AHEAD * 1000;
})()"""
#: The seconds the hint says a shown value has left.
SECONDS_LEFT = (
    "Number(/hides in (\\d+) s/.exec(document.getElementById('hint').textContent)[1])"
)


def test_a_shown_value_hides_itself_when_30_seconds_have_gone_by_the_clock(page):
    """By the clock, not by counting: a machine that slept through the seconds
    must not go on showing the value for as many more when it wakes."""
    page.press("j")
    page.wait(PROD)
    page.press("l", " ")
    page.wait("document.querySelector('pre.value.shown')")
    assert page.js(SECONDS_LEFT) in (30, 29)
    page.js(CLOCK.replace("AHEAD", "12"))
    page.wait(f"{SECONDS_LEFT} <= 18", seconds=4)  # said at the next look at the clock
    assert page.js(SECONDS_LEFT) >= 13 and VALUE in page.js(WHOLE_PAGE)
    page.js(CLOCK.replace("AHEAD", "31"))
    page.wait("!document.querySelector('pre.value.shown')", seconds=4)
    assert VALUE not in page.js(WHOLE_PAGE)
    assert "hides in" not in page.js("document.getElementById('hint').textContent")


def test_a_page_that_is_looked_at_again_hides_a_value_whose_time_has_gone_at_once(page):
    """A tab in the background is given few turns, and a machine asleep none:
    coming back, the value is gone before anything else happens."""
    page.press("j")
    page.wait(PROD)
    page.press("l", " ")
    page.wait("document.querySelector('pre.value.shown')")
    gone_at_once = page.js(
        f"""(() => {{
          {CLOCK.replace("AHEAD", "31")};
          document.dispatchEvent(new Event('visibilitychange'));
          return !document.querySelector('pre.value.shown');
        }})()"""
    )
    assert gone_at_once is True and VALUE not in page.js(WHOLE_PAGE)


def test_a_clock_put_back_does_not_keep_a_value_on_the_page(page):
    page.press("j")
    page.wait(PROD)
    page.press("l", " ")
    page.wait("document.querySelector('pre.value.shown')")
    page.js(CLOCK.replace("AHEAD", "-3600"))
    page.wait("!document.querySelector('pre.value.shown')", seconds=4)
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
    assert page.js("document.activeElement.textContent").startswith("Copy as code")
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
#: R7's two numbers, in milliseconds: how soon the page is painted, and how long a
#: keystroke in the filter may take in a workspace of 500 scopes and 5,000 secrets.
FIRST_PAINT, KEYSTROKE = 300, 50
#: A limit in milliseconds is the point of that test, so it has one — with room. On the
#: machine this was written on the page is painted in about 80 ms and a keystroke takes
#: about 8; a shared CI runner is several times slower, and a limit that fails there now
#: and then holds nothing. What must not depend on any machine's speed — that the page
#: is painted before the workspace has answered — is held without a number.
ROOM = 3


def test_a_big_workspace_draws_at_once_and_filters_without_waiting(browser, serve):
    go_on = threading.Event()

    class Held(FakeSecretStore):
        """A workspace that does not say what scopes it has until it is let."""

        def list_scopes(self):
            go_on.wait(30)
            return super().list_scopes()

    made = big(500, 10)
    store = Held(scopes=made._scopes, secrets=made._secrets, acls=made._acls)
    try:
        server = serve(store)
        tab = browser.tab(f"{server.address}#{server.page.new_key()}")
        paint = (
            "performance.getEntriesByType('paint')"
            ".find(p => p.name === 'first-contentful-paint')"
        )
        tab.wait(paint)
        # painted, and the workspace has yet to say anything: it was not waited for
        assert store.count("list_secrets") == 0 and not go_on.is_set()
        assert tab.js("document.body.dataset.phase") != "ready"
        took = tab.js(f"{paint}.startTime")
        assert took < FIRST_PAINT * ROOM, f"the page was painted after {took:.0f} ms"
    finally:
        go_on.set()
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
    assert took < KEYSTROKE * ROOM, f"a keystroke in the filter took {took:.0f} ms"


# ── changing things (spec/008, R1 and R4–R6) ─────────────────────────
OPEN = "document.getElementById('{}').open"
TOAST = "document.getElementById('toast').textContent"
KEYS_SHOWN = "[...document.querySelectorAll('#secrets td.mono')].map(n => n.textContent)"
#: The detail's buttons by what they say, without the key each shows.
BUTTONS = (
    "[...document.querySelectorAll('#detail button')].map(n =>"
    " [...n.childNodes].filter(c => c.nodeType === 3)"
    ".map(c => c.textContent).join('').trim())"
)
#: Paste TEXT into the value field, as the browser does; whether the page took it over.
PASTE = """(() => {
  const data = new DataTransfer();
  data.setData('text/plain', TEXT);
  const paste = new ClipboardEvent(
    'paste', { clipboardData: data, bubbles: true, cancelable: true });
  document.getElementById('form-value').dispatchEvent(paste);
  return paste.defaultPrevented;
})()"""
#: A scope's grants as the dialog lists them: who=what.
GRANTS = (
    "[...document.querySelectorAll('#grants-rows tr')]"
    ".map(r => r.cells[0].textContent + '=' + r.cells[1].textContent)"
)


def wrote(store: FakeSecretStore) -> list[tuple]:
    names = ("put_secret_bytes", "delete_secret", "put_acl", "delete_acl", "create_scope")
    return [call for call in store.calls if call[0] in (*names, "delete_scope")]


@pytest.fixture
def prod(page):
    """The page with `prod` selected and the keyboard in its secrets."""
    page.press("j")
    page.wait(PROD)
    page.press("l")
    return page


def test_a_new_secret_is_typed_in_and_selected(prod):
    prod.press("n")
    prod.wait(OPEN.format("form"))
    assert prod.focus() == "form-key"
    assert prod.js("document.getElementById('form-scope').value") == "prod"
    prod.type("fresh-key")
    prod.press("Tab")
    prod.type("s3cr3t wörd")
    assert prod.js("document.getElementById('form-value').type") == "password"
    prod.press("Enter")
    prod.wait(f"!{OPEN.format('form')} && {SELECTED_KEY} === 'fresh-key'")
    assert prod.store._values[("prod", "fresh-key")] == "s3cr3t wörd".encode()
    assert prod.js(TOAST) == "Saved fresh-key."
    assert "s3cr3t" not in prod.js(WHOLE_PAGE)
    assert prod.js("document.getElementById('form-value').value") == ""
    assert prod.focus() == "keys"


def test_a_new_secret_does_not_overwrite_and_says_so_in_the_dialog(prod):
    prod.press("n")
    prod.type("api-key")
    prod.press("Tab")
    prod.type("oops")
    prod.press("Enter")
    prod.wait("!document.getElementById('form-error').hidden")
    assert "already" in prod.js("document.getElementById('form-error').textContent")
    assert prod.js(OPEN.format("form")) is True and wrote(prod.store) == []


def test_a_certificate_is_picked_described_and_stored_as_it_is(prod, tmp_path):
    from test_files import certificate, pem

    cert, _ = certificate()
    file = tmp_path / "TLS Prod.pem"
    file.write_bytes(pem(cert))
    prod.press("n")
    prod.wait(OPEN.format("form"))
    prod.choose_files("#file", str(file))
    prod.wait("!document.getElementById('picked').hidden")
    card = prod.js("document.getElementById('picked').innerText")
    for line in (
        "TLS Prod.pem",
        "PEM certificate",
        "api.example.com",
        "Example CA",
        "2027-01-14",
    ):
        assert line in card
    assert "in " in card and " days" in card
    assert "Its content becomes the value" in prod.js(
        "document.getElementById('picked-note').textContent"
    )
    assert prod.js("document.getElementById('form-key').value") == "tls-prod"
    assert wrote(prod.store) == []  # described, and nothing saved yet
    prod.press("Enter")
    prod.wait(f"{SELECTED_KEY} === 'tls-prod'")
    assert prod.store._values[("prod", "tls-prod")] == pem(cert)


def test_a_file_that_is_no_text_goes_in_and_is_shown_as_what_it_is(prod, tmp_path):
    data = bytes(range(256)) * 4
    file = tmp_path / "bundle.p12"
    file.write_bytes(data)
    prod.press("n")
    prod.choose_files("#file", str(file))
    prod.wait("!document.getElementById('picked').hidden")
    assert "binary" in prod.js("document.getElementById('picked').innerText")
    assert "byte for byte" in prod.js(
        "document.getElementById('picked-note').textContent"
    )
    prod.press("Enter")
    prod.wait(f"{SELECTED_KEY} === 'bundle'")
    assert prod.store._values[("prod", "bundle")] == data
    prod.press(" ")
    prod.wait("document.querySelector('pre.value.shown')")
    assert "not text: a file of 1.0 kB" in prod.js(
        "document.getElementById('hint').textContent"
    )
    import base64

    assert prod.js("document.querySelector('pre.value').textContent") == (
        base64.b64encode(data).decode()
    )


def test_a_file_too_large_to_be_a_secret_is_refused_before_it_is_sent(prod, tmp_path):
    file = tmp_path / "huge.bin"
    file.write_bytes(b"x" * (128 * 1024 + 1))
    prod.press("n")
    asked = prod.js(ASKED)
    prod.choose_files("#file", str(file))
    prod.wait("!document.getElementById('form-error').hidden")
    assert "128 kB at most" in prod.js(
        "document.getElementById('form-error').textContent"
    )
    assert prod.js("document.getElementById('picked').hidden") is True
    assert prod.js(ASKED) == asked


def test_typing_a_value_lets_go_of_the_file_and_the_other_way_round(prod, tmp_path):
    file = tmp_path / "note.txt"
    file.write_text("from the file\n")
    prod.press("n")
    prod.type("k")
    prod.press("Tab")
    prod.type("typed")
    prod.choose_files("#file", str(file))
    prod.wait("!document.getElementById('picked').hidden")
    assert prod.js("document.getElementById('form-value').value") == ""
    prod.js("document.getElementById('form-value').focus()")
    prod.type("typed again")
    prod.wait("document.getElementById('picked').hidden")
    prod.press("Enter")
    prod.wait(f"{SELECTED_KEY} === 'k'")
    assert prod.store._values[("prod", "k")] == b"typed again"


def test_a_form_that_is_closed_keeps_nothing_typed_or_chosen(prod, tmp_path):
    file = tmp_path / "note.txt"
    file.write_text("from the file\n")
    prod.press("n")
    prod.type("k")
    prod.press("Tab")
    prod.type("typed-and-abandoned")
    prod.press("Escape")
    # the browser says a dialog is closed a moment after it is: wait for what that does
    prod.wait(
        f"!{OPEN.format('form')} && document.getElementById('form-value').value === ''"
    )
    prod.press("n")
    prod.choose_files("#file", str(file))
    prod.wait("!document.getElementById('picked').hidden")
    prod.press("Escape")
    prod.wait(f"!{OPEN.format('form')} && document.getElementById('picked').hidden")
    assert prod.js("document.getElementById('file').files.length") == 0
    assert wrote(prod.store) == []


def test_editing_with_nothing_typed_changes_nothing(prod):
    prod.press("e")
    prod.wait(OPEN.format("form"))
    assert prod.js("document.getElementById('form-title').textContent") == "Edit secret"
    assert prod.js("document.getElementById('form-key').disabled") is True
    assert prod.focus() == "form-value"
    prod.press("Enter")
    prod.wait("!document.getElementById('form-error').hidden")
    assert "changes nothing" in prod.js(
        "document.getElementById('form-error').textContent"
    )
    assert wrote(prod.store) == []
    prod.type("rotated")
    prod.press("Enter")
    prod.wait(f"!{OPEN.format('form')}")
    assert prod.store._values[("prod", "api-key")] == b"rotated"
    assert prod.js(SELECTED_KEY) == "api-key"


def test_deleting_takes_a_deliberate_y_and_u_puts_it_back(prod):
    prod.press("d")
    prod.wait(OPEN.format("confirm"))
    assert prod.js("document.getElementById('confirm-what').innerText") == (
        "Delete api-key from prod."
    )
    assert prod.focus() == "confirm-no"
    prod.press("d", "d")  # the key that opened it does not confirm it
    assert prod.js(OPEN.format("confirm")) is True and wrote(prod.store) == []
    prod.press("y")
    prod.wait(f"!{OPEN.format('confirm')} && !{KEYS_SHOWN}.includes('api-key')")
    assert "press u to put it back" in prod.js(TOAST)
    assert prod.focus() == "keys"
    prod.press("u")
    prod.wait(f"{KEYS_SHOWN}.includes('api-key')")
    assert prod.js(TOAST) == "Put back prod/api-key."
    assert prod.js(SELECTED_KEY) == "api-key"
    assert prod.store._values[("prod", "api-key")] == VALUE.encode()


def test_escape_deletes_nothing(prod):
    prod.press("d")
    prod.wait(OPEN.format("confirm"))
    prod.press("Escape")
    prod.wait(f"!{OPEN.format('confirm')}")
    prod.press("u")
    prod.wait(f"{TOAST} === 'There is nothing to put back.'")
    assert wrote(prod.store) == []


def test_a_scope_has_a_key_of_its_own_and_says_what_goes_with_it(prod):
    prod.press("h", "D")
    prod.wait(OPEN.format("confirm"))
    assert prod.js("document.getElementById('confirm-what').innerText") == (
        "Delete scope prod and its 4 secrets."
    )
    assert "cannot be put back" in prod.js(
        "document.getElementById('confirm-note').textContent"
    )
    prod.press("y")
    prod.wait("document.querySelectorAll('#scopes li').length === 2")
    assert ("delete_scope", "prod") in prod.store.calls
    assert prod.js(TOAST) == "Deleted scope prod."


def test_d_is_the_secret_wherever_the_keyboard_is(prod):
    """A `d` meant for a secret must never reach a scope: the page opens with the
    keyboard in the scopes, and the detail offers `d` for the secret."""
    prod.press("h")
    assert prod.focus() == "scopes"
    prod.press("d")
    prod.wait(OPEN.format("confirm"))
    assert (
        prod.js("document.getElementById('confirm-title').textContent") == "Delete secret"
    )
    assert prod.js("document.getElementById('confirm-what').innerText") == (
        "Delete api-key from prod."
    )


def test_d_with_no_secret_deletes_nothing_and_says_which_key_would(prod):
    prod.press("N")
    prod.type("empty-scope")
    prod.press("Enter")
    prod.wait(f"{SELECTED_SCOPE} === 'empty-scope'")
    prod.press("d")
    prod.wait(f"{TOAST} === 'No secret is selected. D deletes the scope.'")
    assert prod.js("document.querySelector('dialog[open]')") is None


def test_a_scope_whose_secrets_cannot_be_listed_is_not_called_empty(page):
    page.press("f")
    page.wait("document.querySelectorAll('#scopes li').length === 4")
    page.press("j", "j")
    page.wait(f"{SELECTED_SCOPE} === 'shut'")
    page.press("D")
    page.wait(OPEN.format("confirm"))
    assert page.js("document.getElementById('confirm-what').innerText") == (
        "Delete scope shut and whatever is in it: its secrets cannot be listed from here."
    )


def test_after_a_delete_the_selection_stays_where_it_was(prod):
    prod.press("j")
    assert prod.js(SELECTED_KEY) == "db-password"
    prod.press("d")
    prod.wait(OPEN.format("confirm"))
    prod.press("y")
    prod.wait(f"!{KEYS_SHOWN}.includes('db-password')")
    assert prod.js(SELECTED_KEY) == "tls-cert"


def test_u_pressed_before_the_delete_is_answered_loses_nothing(prod):
    prod.press("d")
    prod.wait(OPEN.format("confirm"))
    prod.press("y", "u")  # at once: the put-back waits its turn
    prod.wait(f"{TOAST} === 'Put back prod/api-key.'")
    assert "api-key" in prod.js(KEYS_SHOWN)
    assert prod.store._values[("prod", "api-key")] == VALUE.encode()
    assert prod.store.count("delete_secret") == 1


def test_an_empty_file_is_refused_in_the_form(prod, tmp_path):
    file = tmp_path / "nothing.pem"
    file.write_bytes(b"")
    prod.press("e")
    prod.wait(OPEN.format("form"))
    prod.choose_files("#file", str(file))
    prod.wait("!document.getElementById('form-error').hidden")
    assert "is empty" in prod.js("document.getElementById('form-error').textContent")
    prod.press("Enter")
    assert wrote(prod.store) == []


def test_a_file_described_too_late_does_not_land_in_another_form(prod, tmp_path):
    """Choose a file, close the form, open it for another secret and type: the
    answer about the file must not replace what was typed."""
    file = tmp_path / "late.txt"
    file.write_text("from a file chosen for another secret\n")
    prod.js(late("/api/describe"))
    prod.press("n")
    prod.wait(OPEN.format("form"))
    prod.choose_files("#file", str(file))
    prod.wait("window.letGo")  # asked what the file is, and the answer is held up
    prod.press("Escape")
    prod.wait(f"!{OPEN.format('form')}")
    prod.press("j", "e")
    prod.wait(OPEN.format("form"))
    prod.type("typed for db-password")
    prod.js("window.letGo()")
    prod.wait("window.answered")  # the late answer has come
    assert (
        prod.js("document.getElementById('form-value').value") == "typed for db-password"
    )
    assert prod.js("document.getElementById('picked').hidden") is True
    prod.press("Enter")
    prod.wait(f"!{OPEN.format('form')}")
    assert prod.store._values[("prod", "db-password")] == b"typed for db-password"


def test_a_certificate_pasted_into_the_value_is_taken_line_for_line(prod):
    import json

    from test_files import certificate, pem

    cert, _ = certificate()
    text = pem(cert).decode()
    prod.press("n")
    prod.wait(OPEN.format("form"))
    prod.type("pasted-cert")
    prod.press("Tab")
    prevented = prod.js(PASTE.replace("TEXT", json.dumps(text)))
    assert prevented is True
    prod.wait("!document.getElementById('picked').hidden")
    card = prod.js("document.getElementById('picked').innerText")
    assert (
        "pasted text" in card and "PEM certificate" in card and "api.example.com" in card
    )
    assert prod.js("document.getElementById('form-key').value") == "pasted-cert"
    prod.press("Enter")
    prod.wait(f"{SELECTED_KEY} === 'pasted-cert'")
    assert prod.store._values[("prod", "pasted-cert")] == pem(cert)


def test_one_line_pasted_into_the_value_is_just_pasted(prod):
    prod.press("n")
    prod.wait(OPEN.format("form"))
    prod.press("Tab")
    assert prod.js(PASTE.replace("TEXT", "'one line'")) is False


def test_a_rename_and_the_original_put_back(prod):
    prod.press("m")
    prod.wait(OPEN.format("move"))
    assert prod.js("document.getElementById('move-from').textContent") == "prod/api-key"
    assert prod.focus() == "move-key"
    prod.type("api-key-old")  # the key was selected: typing replaces it
    prod.press("Enter")
    prod.wait(f"!{OPEN.format('move')} && {SELECTED_KEY} === 'api-key-old'")
    assert "api-key" not in prod.js(KEYS_SHOWN)
    assert prod.store._values[("prod", "api-key-old")] == VALUE.encode()
    prod.press("u")
    prod.wait(f"{KEYS_SHOWN}.includes('api-key')")
    assert "api-key-old" in prod.js(KEYS_SHOWN)  # the copy stays


def test_a_copy_to_another_scope(prod):
    prod.press("m")
    prod.wait(OPEN.format("move"))
    prod.type("from-prod")
    prod.js("document.getElementById('move-scope').value = 'staging'")
    prod.js("document.getElementById('move-keep').click()")
    prod.press("Enter")
    prod.wait(f"{SELECTED_SCOPE} === 'staging' && {SELECTED_KEY} === 'from-prod'")
    assert prod.store._values[("staging", "from-prod")] == VALUE.encode()
    assert any(s.key == "api-key" for s in prod.store._secrets["prod"])
    assert prod.js(TOAST) == "Copied api-key to staging/from-prod."


def test_a_move_onto_another_secret_is_refused_in_the_dialog(prod):
    prod.press("m")
    prod.wait(OPEN.format("move"))
    prod.type("db-password")
    prod.press("Enter")
    prod.wait("!document.getElementById('move-error').hidden")
    assert "already" in prod.js("document.getElementById('move-error').textContent")
    assert wrote(prod.store) == []


def test_grants_are_given_changed_and_removed(prod):
    prod.press("p")
    prod.wait(OPEN.format("grants"))
    rows = GRANTS
    assert prod.js(rows) == ["me@corp.com (you)=MANAGE", "users=READ", f"{MARKUP}=WRITE"]
    prod.js("document.getElementById('grant-who').focus()")
    prod.type("data-engineers")
    prod.js("document.getElementById('grant-may').value = 'WRITE'")
    prod.js("document.getElementById('grant-give').click()")
    prod.wait(f"{rows}.includes('data-engineers=WRITE')")
    assert ("put_acl", "prod", "data-engineers", "WRITE") in prod.store.calls
    assert prod.js("document.getElementById('grant-who').value") == ""
    # removing asks first, and a y is what removes
    prod.js(
        "[...document.querySelectorAll('#grants-rows tr')]"
        ".find(r => r.cells[0].textContent === 'data-engineers')"
        ".querySelector('button.danger').click()"
    )
    prod.wait(OPEN.format("confirm"))
    assert "data-engineers" in prod.js(
        "document.getElementById('confirm-what').innerText"
    )
    prod.press("y")
    prod.wait(f"!{rows}.includes('data-engineers=WRITE')")
    assert ("delete_acl", "prod", "data-engineers") in prod.store.calls
    assert prod.js(OPEN.format("grants")) is True  # still in the grants


def test_removing_your_own_grant_is_said_to_be_that(prod):
    prod.press("p")
    prod.wait(OPEN.format("grants"))
    prod.js("document.querySelector('#grants-rows tr button.danger').click()")
    prod.wait(OPEN.format("confirm"))
    assert "your own grant" in prod.js(
        "document.getElementById('confirm-note').textContent"
    )
    prod.press("Escape")
    assert wrote(prod.store) == []


#: The grant the keyboard is on, in the dialog: whose it is.
PICKED_GRANT = (
    "document.querySelector('#grants-rows [aria-selected=true] td').textContent"
)


def test_a_grant_is_picked_changed_and_removed_by_its_keys(prod):
    prod.press("p")
    prod.wait(OPEN.format("grants"))
    assert prod.focus() == "grants-box"
    assert prod.js(PICKED_GRANT) == "me@corp.com (you)"
    prod.press("j")
    assert prod.js(PICKED_GRANT) == "users"
    prod.press("ArrowDown", "ArrowDown", "k")  # round past the last, and back to it
    assert prod.js(PICKED_GRANT) == MARKUP
    prod.press("k")
    assert prod.js(PICKED_GRANT) == "users" and prod.focus() == "grants-box"
    # e: the grant that is picked is put in the form, to be changed
    prod.press("e")
    assert prod.focus() == "grant-may"
    assert prod.js("document.getElementById('grant-who').value") == "users"
    assert prod.js("document.getElementById('grant-may').value") == "READ"
    assert wrote(prod.store) == []
    prod.js("document.getElementById('grant-may').value = 'WRITE'")
    prod.js("document.getElementById('grant-give').click()")
    prod.wait(f"{GRANTS}.includes('users=WRITE')")
    assert ("put_acl", "prod", "users", "WRITE") in prod.store.calls
    # d: removing asks first, names who, and a y is what removes
    prod.js("document.getElementById('grants-box').focus()")
    assert prod.js(PICKED_GRANT) == "users"
    prod.press("d")
    prod.wait(OPEN.format("confirm"))
    assert prod.js("document.getElementById('confirm-what').innerText") == (
        "Remove the grant of users on prod."
    )
    prod.press("d", "d")  # the key that opened it does not confirm it
    assert prod.store.count("delete_acl") == 0
    prod.press("y")
    prod.wait(f"!{GRANTS}.some(row => row.startsWith('users='))")
    assert ("delete_acl", "prod", "users") in prod.store.calls
    assert prod.js(OPEN.format("grants")) is True and prod.focus() == "grants-box"


def test_a_letter_typed_into_a_grants_name_is_no_key(prod):
    prod.press("p")
    prod.wait(OPEN.format("grants"))
    prod.js("document.getElementById('grant-who').focus()")
    prod.type("jed")
    prod.press("d", "e", "j")
    assert prod.js("document.getElementById('grant-who').value").startswith("jed")
    assert prod.js(OPEN.format("confirm")) is False
    assert prod.js(PICKED_GRANT) == "me@corp.com (you)" and wrote(prod.store) == []


def test_started_read_only_the_keys_in_the_grants_pick_and_change_nothing(browser, serve):
    store = workspace()
    server = serve(store, read_only=True)
    tab = browser.tab(f"{server.address}#{server.page.new_key()}")
    tab.wait(SHOWN)
    tab.press("j")
    tab.wait(PROD)
    tab.press("p")
    tab.wait(OPEN.format("grants"))
    tab.press("j", "e", "d")
    assert tab.js(PICKED_GRANT) == "users"
    assert tab.js("[...document.querySelectorAll('dialog[open]')].map(d => d.id)") == [
        "grants"
    ]
    assert tab.js("document.getElementById('grant-who').value") == ""
    assert wrote(store) == []


def test_a_grant_with_nobody_named_is_said_in_the_dialog(prod):
    prod.press("p")
    prod.wait(OPEN.format("grants"))
    prod.js("document.getElementById('grant-give').click()")
    prod.wait("!document.getElementById('grants-error').hidden")
    assert "Say who" in prod.js("document.getElementById('grants-error').textContent")


def test_a_scope_is_made_and_selected(prod):
    prod.press("N")
    prod.wait(OPEN.format("scope-form"))
    assert prod.focus() == "scope-name"
    prod.type("fresh-scope")
    prod.press("Enter")
    prod.wait(f"{SELECTED_SCOPE} === 'fresh-scope'")
    assert ("create_scope", "fresh-scope") in prod.store.calls
    assert prod.js(TOAST) == "Made scope fresh-scope."
    assert prod.focus() == "scopes"
    assert prod.js("document.getElementById('secrets-none').textContent") == (
        "No secrets in this scope."
    )


def test_a_key_vault_scopes_secrets_can_only_be_copied_out(page):
    page.wait("document.querySelector('#detail button')")
    assert page.js(SELECTED_SCOPE) == "kv"
    assert page.js(BUTTONS) == [
        "Show",
        "Copy",
        "Copy as code",
        "Copy to…",
        "Change",
        "Copy as .env",
        "Delete scope",
    ]
    page.press("l", "e", "d")
    assert page.js("document.querySelector('dialog[open]')") is None
    assert "Azure Key Vault" in page.js(TOAST)
    page.press("m")
    page.wait(OPEN.format("move"))
    assert page.js("document.getElementById('move-keep').checked") is True
    assert page.js("document.getElementById('move-keep').disabled") is True
    assert page.js(
        "[...document.getElementById('move-scope').options].map(o => o.value)"
    ) == [
        "prod",
        "staging",
    ]


def test_started_read_only_the_page_offers_no_change(browser, serve):
    store = workspace()
    server = serve(store, read_only=True)
    tab = browser.tab(f"{server.address}#{server.page.new_key()}")
    tab.wait(SHOWN)
    tab.press("j")
    tab.wait(PROD)
    assert tab.js("!document.getElementById('read-only').hidden") is True
    assert (
        tab.js("getComputedStyle(document.getElementById('new-open')).display") == "none"
    )
    assert tab.js(BUTTONS) == [
        "Show",
        "Copy",
        "Copy as code",
        "Look closer",
        "Copy as .env",
    ]
    tab.press("l", "n", "N", "e", "m", "d", "D", "u", "i")
    assert tab.js("document.querySelector('dialog[open]')") is None
    tab.press("p")
    tab.wait(OPEN.format("grants"))
    assert tab.js("document.querySelectorAll('#grants-rows button').length") == 0
    assert tab.js("getComputedStyle(document.querySelector('.grant')).display") == "none"
    assert wrote(store) == []


def test_the_buttons_of_a_secret_in_the_order_the_arrows_walk_them(prod):
    assert prod.js(BUTTONS) == [
        "Show",
        "Copy",
        "Copy as code",
        "Edit",
        "Move or copy",
        "Delete",
        "Change",
        "Import .env…",
        "Copy as .env",
        "Delete scope",
    ]


# ── the tools (spec/005, and 002 R5) ─────────────────────────────────
LIST = (
    "[...document.querySelectorAll('#list-rows tr')]"
    ".map(r => [...r.cells].map(c => c.textContent))"
)
LIST_TITLE = "document.getElementById('list-title').textContent"


def test_copy_puts_the_value_on_the_clipboard_and_never_in_the_page(prod):
    prod.press("c")
    prod.wait(f"{TOAST} === 'Copied api-key.'")
    assert prod.clipboard() == VALUE
    assert VALUE not in prod.js(WHOLE_PAGE)


def test_s_sorts_the_pane_the_keyboard_is_in_and_keeps_what_was_selected(prod):
    prod.press("j")  # db-password
    prod.press("s")
    shown = prod.js(KEYS_SHOWN)
    assert shown[:2] == ["tls-cert", MARKUP] or shown[:2] == [
        MARKUP,
        "tls-cert",
    ]  # the oldest
    assert shown[-1] == "api-key" and prod.js(SELECTED_KEY) == "db-password"
    assert prod.js("document.getElementById('by-changed').className") == "sorted"
    prod.press("S")
    assert prod.js(KEYS_SHOWN)[0] == "api-key"
    assert prod.js("document.getElementById('by-changed').className") == "sorted down"
    assert prod.js(SELECTED_KEY) == "db-password"
    prod.press("s")
    assert (
        prod.js(KEYS_SHOWN)[0] == "api-key"
        and prod.js("document.getElementById('by-key').className") == "sorted"
    )
    prod.press("h", "s")
    scopes = (
        "[...document.querySelectorAll('#scopes li span.mono')].map(n => n.textContent)"
    )
    assert prod.js(scopes) in (["kv", "staging", "prod"], ["staging", "kv", "prod"])
    assert "by how many" in prod.js("document.getElementById('scopes-title').textContent")
    assert prod.js(SELECTED_SCOPE) == "prod"


def test_the_stale_report_lists_what_was_not_changed_oldest_first(prod):
    prod.press("A")
    prod.wait(OPEN.format("list"))
    assert prod.js(LIST_TITLE) == "Not changed in 90 days: 6 secrets"
    rows = prod.js(LIST)
    assert rows[0][:2] == ["kv", "tenant-id"] and rows[-1][:2] == ["staging", "api-key"]
    assert prod.store.reads() == 0  # names and dates: no value is read for it
    prod.press("t", "t")
    prod.wait(f"{LIST_TITLE}.startsWith('Not changed in 365 days')")
    until(lambda: prod.server.page.settings.audit_threshold == 365)  # and kept
    prod.press("c")
    prod.wait("document.getElementById('list-note').textContent.startsWith('Copied')")
    copied = prod.clipboard().splitlines()
    assert (
        copied[0] == "| Scope | Key | Last changed | Age |"
        and copied[1] == "|---|---|---|---|"
    )
    assert copied[2].startswith("| `kv` | `tenant-id` | 2024-05-29 |")


def test_enter_in_a_list_goes_to_what_is_picked(prod):
    prod.press("A")
    prod.wait(OPEN.format("list"))
    prod.press("j", "Enter")  # the second oldest
    prod.wait(f"!{OPEN.format('list')} && document.activeElement.id === 'keys'")
    picked = (prod.js(SELECTED_SCOPE), prod.js(SELECTED_KEY))
    assert picked in (("prod", "tls-cert"), ("prod", MARKUP))


def test_the_overview_says_what_you_can_reach_strongest_first(prod):
    prod.press("a")
    prod.wait(OPEN.format("list"))
    assert prod.js(LIST_TITLE) == "What you can reach: 3 of 4 scopes"
    assert prod.js(LIST) == [
        ["prod", "MANAGE", "3"],
        ["staging", "MANAGE", "1"],
        ["kv", "READ", "1"],
        ["shut", "none", "0"],
    ]
    prod.press("j", "Enter")
    prod.wait(f"{SELECTED_SCOPE} === 'staging' && document.activeElement.id === 'scopes'")


def test_who_has_access_narrows_as_a_name_is_typed(prod):
    prod.press("P")
    prod.wait(OPEN.format("list"))
    assert prod.focus() == "list-filter"
    assert len(prod.js(LIST)) == 5
    prod.type("users")
    prod.wait(f"{LIST}.length === 2")
    assert prod.js(LIST) == [["users", "kv", "READ"], ["users", "prod", "READ"]]
    prod.press("ArrowDown", "Enter")
    prod.wait(f"!{OPEN.format('list')} && {SELECTED_SCOPE} === 'prod'")


def test_a_scope_is_filled_from_a_file_after_it_is_said_what_that_does(prod, tmp_path):
    file = tmp_path / "app.env"
    file.write_text("# made up\nexport NEW_ONE=first\nAPI-KEY='rotated'\nEMPTY=\n")
    prod.choose_files("#env-file", str(file))
    prod.wait(OPEN.format("confirm"))
    said = prod.js("document.getElementById('confirm-what').innerText")
    assert "Put 2 secrets into prod." in said
    assert "1 secret there will be overwritten: api-key." in said
    assert "Left out, having no value: EMPTY." in prod.js(
        "document.getElementById('confirm-note').textContent"
    )
    assert "rotated" not in prod.js(WHOLE_PAGE) and wrote(prod.store) == []
    prod.press("y")
    prod.wait(f"{TOAST} === 'Imported 2 secrets into prod.'")
    assert prod.store._values[("prod", "NEW_ONE")] == b"first"
    assert prod.store._values[("prod", "api-key")] == b"rotated"
    assert "NEW_ONE" in prod.js(KEYS_SHOWN)


def test_an_import_that_overwrites_nothing_is_not_dressed_as_a_danger(prod, tmp_path):
    file = tmp_path / "app.env"
    file.write_text("ONLY_NEW=1\n")
    prod.choose_files("#env-file", str(file))
    prod.wait(OPEN.format("confirm"))
    assert prod.js("document.getElementById('confirm-what').className") == "quiet"
    assert prod.js("document.getElementById('confirm-yes').className") == "main"
    prod.press("Escape")
    prod.wait(f"!{OPEN.format('confirm')}")
    assert wrote(prod.store) == []
    prod.press("d")  # and the next thing that is one, is
    prod.wait(OPEN.format("confirm"))
    assert prod.js("document.getElementById('confirm-what').className") == "alert"


def test_an_import_that_stops_says_where_and_that_the_rest_stays(prod, tmp_path):
    file = tmp_path / "app.env"
    file.write_text("FIRST=1\nSECOND=2\nTHIRD=3\n")
    real = prod.store.put_secret_bytes

    def refusing(scope, key, value):
        if key == "SECOND":
            raise StoreError("the workspace said no")
        real(scope, key, value)

    prod.store.put_secret_bytes = refusing
    prod.choose_files("#env-file", str(file))
    prod.wait(OPEN.format("confirm"))
    prod.press("y")
    prod.wait(f"{TOAST}.startsWith('Stopped at SECOND, after 1 of 3')")
    assert "the workspace said no" in prod.js(TOAST) and "stays" in prod.js(TOAST)
    assert "FIRST" in prod.js(KEYS_SHOWN) and "THIRD" not in prod.js(KEYS_SHOWN)


def test_a_scopes_keys_are_copied_as_a_template_without_reading_a_value(prod):
    prod.press("x")
    prod.wait(OPEN.format("env"))
    prod.press("1")
    prod.wait(f"{TOAST}.startsWith('Copied 4 keys of prod')")
    assert prod.clipboard() == f"api-key=\ndb-password=\ntls-cert=\n{MARKUP}=\n"
    assert prod.store.reads() == 0


def test_a_scopes_values_are_copied_only_after_a_y(prod):
    prod.press("x")
    prod.wait(OPEN.format("env"))
    prod.press("2")
    prod.wait(OPEN.format("confirm"))
    assert "all 4 values of prod" in prod.js(
        "document.getElementById('confirm-what').innerText"
    )
    assert prod.store.reads() == 0
    prod.press("y")
    prod.wait(f"{TOAST}.startsWith('Copied the values of prod as .env.')")
    assert prod.clipboard().splitlines()[0] == f"api-key={VALUE}"
    assert VALUE not in prod.js(WHOLE_PAGE)


def test_two_quick_changes_to_a_setting_are_kept_in_the_order_made(prod, monkeypatch):
    """The first is held up on its way. Were the second sent beside it, it would
    overtake, and what is kept would be the older choice."""
    prefer, asked, done = Handler._prefer, [], []
    overtaken, both = threading.Event(), threading.Event()

    def held_up(self, body):
        asked.append(body.get("stale_after"))
        if len(asked) == 1:
            overtaken.wait(1)
        else:
            overtaken.set()
        try:
            return prefer(self, body)
        finally:
            done.append(body.get("stale_after"))
            if len(done) == 2:
                both.set()

    monkeypatch.setattr(Handler, "_prefer", held_up)
    prod.press("A")
    prod.wait(OPEN.format("list"))
    prod.press("t", "t")
    prod.wait(f"{LIST_TITLE}.startsWith('Not changed in 365 days')")
    assert both.wait(10)
    assert done == [180, 365]
    assert prod.server.page.settings.audit_threshold == 365


def test_f_is_kept_for_the_next_time(page):
    page.press("f")
    page.wait("document.querySelectorAll('#scopes li').length === 4")
    until(lambda: page.server.page.settings.show_all_scopes is True)


def test_every_value_can_be_forgotten_from_the_keys(prod):
    prod.press(" ")
    prod.wait("document.querySelector('pre.value.shown')")
    assert prod.server.page.loader.service.cache.raw != {}
    prod.press("?")
    prod.wait(OPEN.format("help"))
    prod.js("document.getElementById('forget').click()")
    prod.wait(f"{TOAST}.startsWith('Forgot every value')")
    assert prod.server.page.loader.service.cache.raw == {}
    assert VALUE not in prod.js(WHOLE_PAGE)


def test_every_value_is_forgotten_by_a_key_in_the_keys_and_by_none_outside(prod):
    prod.press(" ")
    prod.wait("document.querySelector('pre.value.shown')")
    held = prod.server.page.loader.service.cache.raw
    prod.press("z")  # on the page itself it is no key: forgetting is not done by a slip
    prod.press("?")
    prod.wait(OPEN.format("help"))
    assert held != {} and prod.js("document.getElementById('toast').hidden") is True
    assert prod.js("document.getElementById('forget').innerText").endswith("z")
    prod.press("z")
    prod.wait(f"{TOAST}.startsWith('Forgot every value')")
    assert prod.server.page.loader.service.cache.raw == {}
    assert prod.js(OPEN.format("help")) is False and VALUE not in prod.js(WHOLE_PAGE)


def test_the_keys_open_at_their_first_line(page):
    """The list is longer than a small window, and the browser gives the keyboard
    to its first button, which is at its end."""
    page.press("?")
    page.wait(OPEN.format("help"))
    assert page.js("document.getElementById('help').scrollTop") == 0
    assert page.js(
        "document.getElementById('help-title').getBoundingClientRect().top >= 0"
    )


def test_enter_goes_on_from_the_scopes_and_shows_the_value_of_a_secret(page):
    page.press("j")
    page.wait(PROD)
    assert page.focus() == "scopes"
    page.press("Enter")
    assert page.focus() == "keys" and page.store.reads() == 0
    page.press("Enter")
    page.wait("document.querySelector('pre.value.shown')")
    assert page.js("document.querySelector('pre.value').textContent") == VALUE
    page.press("Enter")
    page.wait("!document.querySelector('pre.value.shown')")


#: A key as the page's list of keys and the docs name it, and as the page takes it.
NAMED = {
    "space": " ",
    "enter": "Enter",
    "slash": "/",
    "question": "?",
    "←": "ArrowLeft",
    "→": "ArrowRight",
    "↑": "ArrowUp",
    "↓": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
    "up": "ArrowUp",
    "down": "ArrowDown",
}


def test_every_key_the_page_takes_is_in_the_list_of_keys_and_in_the_docs(page):
    """ "Everything has a key" — and a key nobody is told of is no key."""
    import re
    from pathlib import Path

    taken = set(page.js("Object.keys(KEYS)"))
    assert {"Enter", "f", "w", "D"} <= taken  # it is the page's own list that is read
    listed = page.js(
        "[...document.querySelectorAll('#help kbd, #help-open kbd')]"
        ".map(k => k.textContent)"
    )
    assert taken - {NAMED.get(key, key) for key in listed} == set()
    docs = (Path(__file__).parent.parent / "docs" / "page.md").read_text("utf-8")
    written = set()
    for key in re.findall(r"\+\+([a-z+]+?)\+\+", docs):
        shifted, name = key.startswith("shift+"), key.removeprefix("shift+")
        written.add(name.upper() if shifted and len(name) == 1 else NAMED.get(name, name))
    assert taken - written == set()
    # enter has a line of its own, in both: it is not only what the filter does with it
    in_front = (
        "[...document.querySelectorAll('#help td:first-child')].map(c => c.innerText)"
    )
    assert "enter" in page.js(in_front) and "\n| ++enter++ |" in docs
    # and the keys that are keys only where they are shown: in the grants, in the keys
    for inside in ("++e++ changes", "++d++ removes", "++question++ then ++z++"):
        assert inside in docs, inside
    in_the_keys = page.js("document.getElementById('help').textContent")
    assert "e changes it, d removes it" in " ".join(in_the_keys.split())


# ── what a second pair of eyes found in the tools ────────────────────
def test_an_import_answered_late_does_not_take_the_place_of_another_question(
    prod, tmp_path
):
    """Choose a file, then `d` before the server has said what the import would
    do: the question on the page stays "Delete", and `y` deletes — it must not
    have become "Import" underneath."""
    file = tmp_path / "app.env"
    file.write_text("NEW_ONE=1\nAPI-KEY=overwritten\n")
    prod.js(late("/api/env/preview"))
    prod.choose_files("#env-file", str(file))
    prod.wait("window.letGo")  # asked what the import would do, and the answer is held up
    prod.press("d")
    prod.wait(OPEN.format("confirm"))
    prod.js("window.letGo()")
    prod.wait("window.answered")  # the late answer has come
    assert (
        prod.js("document.getElementById('confirm-title').textContent") == "Delete secret"
    )
    prod.press("Escape")
    prod.wait(f"!{OPEN.format('confirm')}")
    prod.wait(f"{TOAST}.includes('was not imported')")
    assert wrote(prod.store) == []
    assert prod.js("document.getElementById('env-file').files.length") == 0


def test_a_list_answered_late_does_not_open_over_a_question(prod):
    """`P` then `d` at once: the list must not open over "Delete?" — typing a name
    with a y in it into its filter would answer the question underneath."""
    prod.js(late("/api/grants"))
    prod.press("P")
    prod.wait("window.letGo")  # asked for the grants, and the answer is held up
    prod.press("d")
    prod.wait(OPEN.format("confirm"))
    prod.js("window.letGo()")
    prod.wait("window.answered")  # the late answer has come
    assert prod.js(OPEN.format("list")) is False
    assert prod.js("document.querySelectorAll('dialog[open]').length") == 1
    prod.press("Escape")
    prod.wait(f"!{OPEN.format('confirm')}")
    assert wrote(prod.store) == []


def test_no_dialog_opens_over_another_but_a_question_over_the_grants(prod):
    prod.press("A")
    prod.wait(OPEN.format("list"))
    prod.js(
        "for (const id of ['new-open', 'scope-new', 'help-open'])"
        " document.getElementById(id).click()"
    )
    assert prod.js("[...document.querySelectorAll('dialog[open]')].map(d => d.id)") == [
        "list"
    ]
    prod.press("Escape")
    prod.wait(f"!{OPEN.format('list')}")
    prod.press("p")
    prod.wait(OPEN.format("grants"))
    prod.js("document.querySelector('#grants-rows tr button.danger').click()")
    prod.wait(OPEN.format("confirm"))
    assert prod.js(
        "[...document.querySelectorAll('dialog[open]')].map(d => d.id).sort()"
    ) == [
        "confirm",
        "grants",
    ]


def test_a_y_typed_into_a_filter_answers_no_question(prod):
    prod.press("P")
    prod.wait(OPEN.format("list"))
    prod.type("yy")
    prod.press("y")
    assert prod.js("document.getElementById('list-filter').value").startswith("yy")
    assert wrote(prod.store) == []


def test_a_list_asked_for_while_the_workspace_is_read_says_so_and_fills(browser, serve):
    go_on = threading.Event()

    class Held(FakeSecretStore):
        """A workspace that answers nothing about its secrets until it is let."""

        def list_secrets(self, scope):
            go_on.wait(30)
            return super().list_secrets(scope)

    made = workspace()
    store = Held(scopes=made._scopes, secrets=made._secrets, acls=made._acls)
    try:
        server = serve(store)
        tab = browser.tab(f"{server.address}#{server.page.new_key()}")
        tab.wait("document.querySelectorAll('#scopes li').length > 0")
        assert tab.js("document.body.dataset.phase") == "loading"
        tab.press("A")
        tab.wait(OPEN.format("list"))
        assert "still being read" in tab.js(
            "document.getElementById('list-note').textContent"
        )
        assert tab.js(LIST_TITLE) == "Not changed in 90 days: 0 secrets"
        go_on.set()
        tab.wait(f"{LIST_TITLE} === 'Not changed in 90 days: 6 secrets'", seconds=30)
        note = "document.getElementById('list-note').textContent"
        tab.wait(f"!{note}.includes('still being read')", seconds=30)
    finally:
        go_on.set()


def test_a_locked_page_keeps_no_list_and_no_file(prod, tmp_path):
    file = tmp_path / "app.env"
    file.write_text("NEW_ONE=held-value\n")
    prod.choose_files("#env-file", str(file))
    prod.wait(OPEN.format("confirm"))
    prod.press("Escape")
    prod.wait(f"!{OPEN.format('confirm')}")
    prod.press("A")
    prod.wait(OPEN.format("list"))
    prod.server.page.token = "another-run"
    prod.press("t")  # asks the server, and finds the key gone
    prod.wait("!document.getElementById('locked').hidden")
    whole = prod.js(WHOLE_PAGE)
    for told in ("tenant-id", "api-key", "Not changed in", "NEW_ONE"):
        assert told not in whole
    assert prod.js("document.getElementById('env-file').files.length") == 0
    assert prod.js("document.querySelector('dialog[open]')") is None


def test_a_name_in_a_copied_table_stays_a_name(browser, serve):
    odd = "a|b __init__ `x`"
    server = serve(
        FakeSecretStore(
            scopes=[Scope("s")],
            secrets={"s": [Secret("s", odd, 1_600_000_000_000)]},
            acls={"s": [Acl("me@corp.com", "MANAGE")]},
        )
    )
    tab = browser.tab(f"{server.address}#{server.page.new_key()}")
    tab.wait("document.body.dataset.phase === 'ready'")
    tab.press("A")
    tab.wait(OPEN.format("list"))
    tab.press("c")
    tab.wait("document.getElementById('list-note').textContent.startsWith('Copied')")
    row = tab.clipboard().splitlines()[2]
    assert row.startswith("| `s` | `a\\|b __init__ 'x'` | 2020-09-13 |")
    assert row.count(" | ") == 3  # four columns, as the heading has


# ── which workspace (spec/001) ───────────────────────────────────────
PLACES = (
    "[...document.querySelectorAll('#picker-rows tr')].map(r => r.cells[0].textContent)"
)
SCOPES = "[...document.querySelectorAll('#scopes li span.mono')].map(n => n.textContent)"


@pytest.fixture
def choosing(browser):
    """The page with two workspaces to choose from and none chosen. Each has a
    scope the other has not, so that it shows which one is on the page."""
    from caland.application import OnboardingService
    from fakes import StubBundle, StubProfiles
    from test_web_picker import DEV, PROD, Connector

    connector = Connector()
    for name in ("dev", "prod", "https://new.example.com"):
        only = "only-" + name.removeprefix("https://").split(".")[0]
        # `common` is in every one of them, under the same names: what is meant for
        # the one must be seen not to reach the other
        mine = [Acl("me@corp.com", "MANAGE")]
        connector.stores[name] = FakeSecretStore(
            scopes=[Scope("common"), Scope(only), Scope("shared")],
            secrets={
                "common": [
                    Secret("common", "A", 1_750_000_000_000),
                    Secret("common", "B"),
                ],
                only: [Secret(only, f"key-of-{only}", 1_750_000_000_000)],
            },
            acls={"common": mine, only: mine, "shared": mine},
            values={
                (only, f"key-of-{only}"): f"value of {only}",
                ("common", "A"): f"A of {only}",
            },
        )
    profiles = StubProfiles([DEV, PROD])
    page = Page(onboarding=OnboardingService(connector, profiles, StubBundle()))
    server = Server(page)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    tab = browser.tab(f"{server.address}#{page.new_key()}")
    tab.server, tab.connector, tab.profiles = server, connector, profiles
    try:
        yield tab
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_with_several_workspaces_the_page_asks_which(choosing):
    choosing.wait(OPEN.format("picker"))
    assert choosing.js(PLACES) == ["dev", "prod"]
    assert choosing.js("document.getElementById('picker-close').hidden") is True
    choosing.press("Escape")  # there is nothing to go back to: it stays, or comes back
    choosing.wait("true")
    choosing.wait(OPEN.format("picker"))
    choosing.wait(f"{PLACES}.length === 2")
    choosing.press("j", "Enter")
    choosing.wait(f"!{OPEN.format('picker')} && document.body.dataset.phase === 'ready'")
    assert choosing.js(SCOPES) == ["common", "only-prod", "shared"]
    assert (
        choosing.js("document.getElementById('host').textContent") == "prod.example.com"
    )
    assert choosing.focus() == "scopes"


def test_w_goes_to_another_workspace_and_keeps_nothing_of_the_one_left(choosing):
    choosing.wait(OPEN.format("picker"))
    choosing.press("Enter")  # dev
    choosing.wait(
        f"document.body.dataset.phase === 'ready' && {SCOPES}.includes('only-dev')"
    )
    choosing.press("j")
    choosing.wait(f"{SELECTED_KEY} === 'key-of-only-dev'")
    choosing.press("l", " ")
    choosing.wait("document.querySelector('pre.value.shown')")
    assert "value of only-dev" in choosing.js(WHOLE_PAGE)
    choosing.press("w")
    choosing.wait(OPEN.format("picker"))
    assert (
        choosing.js(
            "document.querySelector('#picker-rows [aria-selected=true] td').textContent"
        )
        == "dev"
    )
    assert choosing.js("document.getElementById('picker-close').hidden") is False
    choosing.press("j", "Enter")
    choosing.wait(
        f"document.body.dataset.phase === 'ready' && {SCOPES}.includes('only-prod')"
    )
    whole = choosing.js(WHOLE_PAGE)
    assert "only-dev" not in whole and "value of only-dev" not in whole
    choosing.press("A")  # and the lists are the new one's
    choosing.wait(OPEN.format("list"))
    assert [row[0] for row in choosing.js(LIST)] == ["common", "only-prod"]


def test_esc_leaves_the_workspace_as_it_is_when_there_is_one(choosing):
    choosing.wait(OPEN.format("picker"))
    choosing.press("Enter")
    choosing.wait(
        f"document.body.dataset.phase === 'ready' && {SCOPES}.includes('only-dev')"
    )
    choosing.press("w")
    choosing.wait(OPEN.format("picker"))
    choosing.press("j", "Escape")
    choosing.wait(f"!{OPEN.format('picker')}")
    assert choosing.js(SCOPES) == ["common", "only-dev", "shared"]
    assert choosing.js("document.getElementById('host').textContent") == "dev.example.com"


def test_a_workspace_is_signed_in_to_by_its_address_and_kept_under_a_name(choosing):
    choosing.wait(OPEN.format("picker"))
    choosing.js("document.getElementById('picker-url').focus()")
    choosing.type("new.example.com")
    choosing.js("document.getElementById('picker-save').click()")
    assert choosing.focus() == "picker-name"
    choosing.press("Enter")  # no name yet
    choosing.wait("!document.getElementById('picker-error').hidden")
    assert "Give the profile a name" in choosing.js(
        "document.getElementById('picker-error').textContent"
    )
    choosing.type("prod")  # in use
    choosing.press("Enter")
    choosing.wait(
        "document.getElementById('picker-error').textContent.includes('already')"
    )
    assert choosing.profiles.saved == []
    choosing.type("-new")  # prod-new
    choosing.press("Enter")
    choosing.wait(
        f"document.body.dataset.phase === 'ready' && {SCOPES}.includes('only-new')"
    )
    assert choosing.profiles.saved == [("prod-new", "https://new.example.com", None)]


def test_an_address_that_is_none_is_said_in_the_dialog(choosing):
    choosing.wait(OPEN.format("picker"))
    choosing.js("document.getElementById('picker-url').focus()")
    choosing.type("http://insecure.example.com/path")
    choosing.press("Enter")
    choosing.wait("!document.getElementById('picker-error').hidden")
    assert "address" in choosing.js("document.getElementById('picker-error').textContent")
    assert choosing.js(OPEN.format("picker")) is True


def test_a_workspace_that_cannot_be_reached_brings_the_choice_back_with_the_reason(
    choosing,
):
    choosing.connector.refuse.add("prod")
    choosing.wait(OPEN.format("picker"))
    choosing.press("j", "Enter")
    choosing.wait(
        "document.getElementById('picker').open"
        " && document.getElementById('picker-error').textContent.includes('cancelled')"
    )
    choosing.press("k", "Enter")  # dev works
    choosing.wait(
        f"document.body.dataset.phase === 'ready' && {SCOPES}.includes('only-dev')"
    )


# ── what a second pair of eyes found in the choice of a workspace ─────
#: The page has taken up the workspace of this name, and read it.
READY_IN = (
    "document.body.dataset.phase === 'ready'"
    " && [...document.querySelectorAll('#scopes li span.mono')]"
    ".some(n => n.textContent === 'only-{}')"
)


def in_common(tab, name):
    """Go to workspace `name` from the open choice, and into `common`, which is first."""
    tab.wait(OPEN.format("picker"))
    tab.press(*(["j", "Enter"] if name == "prod" else ["Enter"]))
    tab.wait(
        f"document.body.dataset.phase === 'ready' && {SCOPES}.includes('only-{name}')"
    )
    tab.wait(f"{SELECTED_SCOPE} === 'common' && document.querySelector('#detail button')")
    tab.press("l")


def keys_of(store, scope="common"):
    return sorted(secret.key for secret in store._secrets[scope])


def test_a_change_asked_for_in_one_workspace_is_never_done_in_another(choosing):
    """`d y`, `d y` again while the first is still under way, then off to prod: the
    second delete was asked of dev. prod has the same names — and keeps them."""
    in_common(choosing, "dev")
    dev, prod = choosing.connector.stores["dev"], choosing.connector.stores["prod"]
    real = dev.delete_secret
    under_way, go_on = threading.Event(), threading.Event()

    def held(scope, key):
        under_way.set()
        go_on.wait(30)
        real(scope, key)

    dev.delete_secret = held
    try:
        choosing.press("d")
        choosing.wait(OPEN.format("confirm"))
        choosing.press("y")
        assert under_way.wait(10)  # the first is with the workspace, and stays there
        choosing.press("d")
        choosing.wait(OPEN.format("confirm"))
        choosing.press("y")
        # the page's own queue of changes, as it is now: the second delete is its end
        choosing.js("window.queued = queue, true")
        choosing.press("w")
        choosing.wait(OPEN.format("picker"))
        choosing.press("j", "Enter")
        choosing.wait(
            f"document.body.dataset.phase === 'ready' && {SCOPES}.includes('only-prod')"
        )
        go_on.set()
        # whatever was still to come has come: the queue has been gone through
        assert choosing.js("window.queued.then(() => true)") is True
    finally:
        go_on.set()
    assert keys_of(prod) == ["A", "B"] and prod.count("delete_secret") == 0
    assert keys_of(dev) == ["B"]  # the one that was under way, and no more


def test_a_tab_left_showing_another_workspace_changes_nothing_and_catches_up(choosing):
    from test_web_picker import PROD

    in_common(choosing, "dev")
    choosing.server.page.connect(PROD)  # another tab went to prod
    prod = choosing.connector.stores["prod"]
    choosing.press("d")
    choosing.wait(OPEN.format("confirm"))
    choosing.press("y")
    choosing.wait(f"{TOAST}.includes('another workspace')")
    choosing.wait(f"{SCOPES}.includes('only-prod')")
    assert keys_of(prod) == ["A", "B"] and prod.count("delete_secret") == 0
    assert "only-dev" not in choosing.js(WHOLE_PAGE)
    assert (
        choosing.js("document.getElementById('host').textContent") == "prod.example.com"
    )


def test_a_value_that_comes_late_is_not_shown_under_another_workspace(choosing):
    in_common(choosing, "dev")
    dev = choosing.connector.stores["dev"]
    real = dev.get_secret_bytes
    asked, go_on = threading.Event(), threading.Event()

    def held(scope, key):
        asked.set()
        go_on.wait(30)
        return real(scope, key)

    dev.get_secret_bytes = held
    choosing.js(late("/api/value", hold=False))
    try:
        choosing.press(" ")
        assert asked.wait(10)  # the value is being read, and stays so
        choosing.press("w")
        choosing.wait(OPEN.format("picker"))
        choosing.press("j", "Enter")
        choosing.wait(
            f"document.body.dataset.phase === 'ready' && {SCOPES}.includes('only-prod')"
        )
        go_on.set()
        choosing.wait("window.answered")  # the value has come, late
    finally:
        go_on.set()
    assert "A of only-dev" not in choosing.js(WHOLE_PAGE)
    assert choosing.js("document.querySelector('pre.value.shown')") is None


def test_the_choice_comes_back_even_when_something_else_was_open(choosing):
    go_on = threading.Event()
    real = choosing.connector.connect_profile

    def slowly(profile):
        go_on.wait(10)
        return real(profile)

    choosing.connector.connect_profile = slowly
    choosing.connector.refuse.add("prod")
    try:
        choosing.wait(OPEN.format("picker"))
        choosing.press("j", "Enter")
        choosing.wait("document.body.dataset.phase === 'connecting'")
        for key in ("N", "A", "n", "i"):  # nothing to act on yet: they open nothing
            choosing.press(key)
        assert choosing.js("document.querySelector('dialog[open]')") is None
        choosing.press("?")
        choosing.wait(OPEN.format("help"))
        go_on.set()
        choosing.wait("document.body.dataset.phase === 'failed'")
        assert choosing.js(OPEN.format("picker")) is False  # the keys' list is in the way
        choosing.press("Escape")
        choosing.wait(
            "document.getElementById('picker').open"
            " && document.getElementById('picker-error')"
            ".textContent.includes('cancelled')"
        )
    finally:
        go_on.set()


def test_enter_twice_is_one_sign_in(choosing):
    choosing.wait(OPEN.format("picker"))
    choosing.js("document.getElementById('picker-url').focus()")
    choosing.type("new.example.com")
    choosing.press("Enter", "Enter", "Enter")
    choosing.wait(
        f"document.body.dataset.phase === 'ready' && {SCOPES}.includes('only-new')"
    )
    asked = (
        "performance.getEntriesByType('resource')"
        ".filter(r => r.name.endsWith('/api/connect')).length"
    )
    assert choosing.js(asked) == 1
    assert choosing.server.page.turn == 1


def test_after_going_elsewhere_nothing_of_the_old_is_behind_a_closed_dialog(choosing):
    in_common(choosing, "dev")
    opened = (("p", "grants"), ("m", "move"), ("C", "code"), ("A", "list"), ("e", "form"))
    for key, dialog in opened:
        choosing.press(key)
        choosing.wait(OPEN.format(dialog))
        choosing.press("Escape")
        choosing.wait(f"!{OPEN.format(dialog)}")
    choosing.press("w")
    choosing.wait(OPEN.format("picker"))
    choosing.press("j", "Enter")
    choosing.wait(
        f"document.body.dataset.phase === 'ready' && {SCOPES}.includes('only-prod')"
    )
    whole = choosing.js(WHOLE_PAGE)
    assert "only-dev" not in whole and "common/A" not in whole
    for id_ in ("grants-rows", "move-from", "code-rows", "list-rows"):
        assert choosing.js(f"document.getElementById('{id_}').childNodes.length") == 0
    assert choosing.js("document.getElementById('form-key').value") == ""


def test_a_profile_not_kept_is_said_once_and_the_sign_in_stands(choosing):
    def refusing(name, host):
        raise OSError("~/.databrickscfg cannot be written")

    choosing.profiles.add = refusing
    choosing.wait(OPEN.format("picker"))
    choosing.js("document.getElementById('picker-url').focus()")
    choosing.type("new.example.com")
    choosing.js("document.getElementById('picker-save').click()")
    choosing.type("kept")
    choosing.press("Enter")
    choosing.wait(
        f"document.body.dataset.phase === 'ready' && {SCOPES}.includes('only-new')"
    )
    choosing.wait(f"{TOAST}.includes('profile was not kept')")
    assert "cannot be written" in choosing.js(TOAST)


def test_the_row_that_is_picked_is_gone_to_also_when_two_have_one_name_and_address(
    browser,
):
    """A bundle's target and a profile for the same workspace: the second row is
    the profile, and signs in as the profile does."""
    from caland.application import OnboardingService
    from caland.domain import SOURCE_BUNDLE
    from fakes import StubBundle, StubProfiles
    from test_web_picker import PROD, Connector

    bundle = Workspace(
        host="https://prod.example.com", source=SOURCE_BUNDLE, target="prod", default=True
    )
    connector = Connector()
    page = Page(
        onboarding=OnboardingService(connector, StubProfiles([PROD]), StubBundle(bundle))
    )
    server = Server(page)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        tab = browser.tab(f"{server.address}#{page.new_key()}")
        tab.wait(OPEN.format("picker"))
        found_in = (
            "[...document.querySelectorAll('#picker-rows tr')]"
            ".map(r => r.cells[2].textContent)"
        )
        assert tab.js(PLACES) == ["prod", "prod"]
        assert tab.js(found_in)[1] == "~/.databrickscfg"
        tab.press("j", "Enter")
        tab.wait(f"!{OPEN.format('picker')} && document.body.dataset.phase === 'ready'")
        assert list(connector.stores) == ["prod"]  # the profile: no sign-in by address
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

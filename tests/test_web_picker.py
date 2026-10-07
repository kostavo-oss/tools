"""Which workspace: chosen on the page, from what was found or by its address."""

from __future__ import annotations

import threading

import pytest

from caland.application import OnboardingService
from caland.domain import AuthError, Connected, Workspace
from caland.interface.web import Page, Server
from fakes import FakeSecretStore, StubBundle, StubProfiles, seeded_store
from test_web_server import Served

DEV = Workspace(profile="dev", host="https://dev.example.com")
PROD = Workspace(profile="prod", host="https://prod.example.com")


class Connector:
    """Connects a profile to its own made-up workspace, and an address to another."""

    def __init__(self) -> None:
        self.stores: dict[str, FakeSecretStore] = {}
        self.refuse: set[str] = set()

    def _store(self, name: str) -> FakeSecretStore:
        if name in self.refuse:
            raise AuthError(f"sign-in to {name} was cancelled")
        return self.stores.setdefault(name, seeded_store())

    def connect_profile(self, profile):
        return Connected(store=self._store(profile), label=profile)

    def connect_url(self, host):
        return Connected(store=self._store(host), label=host, host=host)


class Choosing(Served):
    """A running server with no workspace yet, and what it chooses from."""

    connector: Connector
    profiles: StubProfiles


@pytest.fixture
def served():
    connector, profiles = Connector(), StubProfiles([DEV, PROD])
    page = Page(onboarding=OnboardingService(connector, profiles, StubBundle()))
    server = Server(page)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    made = Choosing(server, None)
    made.connector, made.profiles = connector, profiles
    made.enter()
    try:
        yield made
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def state(served):
    return served.json("GET", "/api/state")[1]


def ready(served):
    for _ in range(300):
        told = state(served)
        if told["phase"] in ("ready", "failed"):
            return told
        threading.Event().wait(0.01)
    raise AssertionError("it never got there")


def connect(served, **body):
    return served.json("POST", "/api/connect", body)


def test_with_no_workspace_yet_the_state_says_there_is_one_to_choose(served):
    told = state(served)
    assert told["phase"] == "choosing" and told["scopes"] == []
    assert told["workspace"] == {"name": "", "host": ""} and told["identity"] is None
    for path in ("/api/keys", "/api/grants", "/api/scope?name=prod"):
        assert served.json("GET", path)[0] == 409
    assert (
        served.json("POST", "/api/value", {"scope": "prod", "key": "api-key"})[0] == 409
    )


def test_what_there_is_to_choose_from_is_said_with_where_it_was_found(served):
    status, told = served.json("GET", "/api/workspaces")
    assert status == 200 and told == {
        "workspaces": [
            {
                "name": "dev",
                "host": "dev.example.com",
                "from": "~/.databrickscfg",
                "default": False,
            },
            {
                "name": "prod",
                "host": "prod.example.com",
                "from": "~/.databrickscfg",
                "default": False,
            },
        ],
        "current": "",
    }
    assert served.ask("GET", "/api/workspaces", token="wrong")[0] == 401


def test_a_workspace_is_gone_to_by_its_name(served):
    assert connect(served, name="prod")[0] == 202
    told = ready(served)
    assert told["phase"] == "ready" and told["workspace"]["name"] == "prod"
    assert [scope["name"] for scope in told["scopes"]] == ["kv", "prod"]
    assert served.json("GET", "/api/workspaces")[1]["current"] == "prod"


def test_a_name_that_is_not_there_is_not_gone_to(served):
    status, told = connect(served, name="nope")
    assert status == 404 and "There is: dev, prod." in told["error"]
    assert state(served)["phase"] == "choosing"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": "dev", "url": "https://x.example.com"},
        {"name": ""},
        {"name": 7},
        {"url": 7},
    ],
)
def test_which_workspace_said_badly(served, body):
    assert served.json("POST", "/api/connect", body)[0] == 400
    assert state(served)["phase"] == "choosing"


def test_a_workspace_is_signed_in_to_by_its_address(served):
    assert connect(served, url="adb-123.azuredatabricks.net/")[0] == 202
    told = ready(served)
    assert told["phase"] == "ready"
    assert told["workspace"] == {
        "name": "adb-123.azuredatabricks.net",
        "host": "adb-123.azuredatabricks.net",
    }
    assert list(served.connector.stores) == ["https://adb-123.azuredatabricks.net"]
    assert served.profiles.saved == []


@pytest.mark.parametrize(
    "url",
    [
        "http://dev.example.com",
        "https://dev.example.com/some/path",
        "https://dev.example.com?o=1",
        "https://dev.example.com#x",
        "https://user:pw@dev.example.com",
        "https://localhost",
        "ftp://dev.example.com",
        "https://",
        "not an address",
        "https://" + "a" * 250 + ".example.com",
        "javascript:alert(1)",
        "https://dev.example.com:notaport",
    ],
)
def test_an_address_is_https_a_host_and_nothing_more(served, url):
    status, told = connect(served, url=url)
    assert status == 400 and "address" in told["error"]
    assert served.connector.stores == {} and state(served)["phase"] == "choosing"


def test_an_address_is_kept_as_a_profile_once_the_sign_in_has_worked(served):
    assert connect(served, url="https://new.example.com", save_as="new-one")[0] == 202
    assert ready(served)["phase"] == "ready"
    assert served.profiles.saved == [("new-one", "https://new.example.com", None)]


def test_an_address_that_cannot_be_signed_in_to_is_kept_nowhere(served):
    served.connector.refuse.add("https://new.example.com")
    assert connect(served, url="https://new.example.com", save_as="new-one")[0] == 202
    told = ready(served)
    assert told["phase"] == "failed" and "cancelled" in told["error"]
    assert served.profiles.saved == []


@pytest.mark.parametrize(
    ("name", "status"),
    [
        ("x]\ntoken = stolen", 400),
        ("with space", 400),
        ("-starts-with-a-dash", 400),
        ("a" * 65, 400),
        ("näme", 400),
        (7, 400),
        ("DEFAULT", 409),
        ("default", 409),
        ("prod", 409),  # in use: its way of signing in must not be pointed elsewhere
        ("PROD", 409),
    ],
)
def test_a_profiles_name_is_a_name_and_one_that_is_free(served, name, status):
    got, told = connect(served, url="https://new.example.com", save_as=name)
    assert got == status and "profile" in told["error"]
    assert served.connector.stores == {} and served.profiles.saved == []
    assert state(served)["phase"] == "choosing"


def test_going_to_another_workspace_keeps_nothing_of_the_one_that_is_left(served):
    connect(served, name="dev")
    first = ready(served)
    served.json("POST", "/api/value", {"scope": "prod", "key": "api-key"})
    served.json("POST", "/api/secret/delete", {"scope": "prod", "key": "db-password"})
    left = served.page.loader.service
    assert left.cache.raw != {} and left.taken is not None
    connect(served, name="prod")
    second = ready(served)
    assert left.cache.raw == {} and left.taken is None
    assert second["taken"] is None and second["workspace"]["name"] == "prod"
    # what the page holds of the one is never taken for the other's
    assert second["version"] > first["version"] + 900_000
    assert [call[0] for call in served.connector.stores["prod"].calls].count(
        "delete_secret"
    ) == 0


def test_the_version_never_comes_round_again_across_workspaces(served):
    seen = []
    for name in ("dev", "prod", "dev"):
        connect(served, name=name)
        seen.append(ready(served)["version"])
    assert seen == sorted(set(seen))


def test_choosing_a_workspace_changes_none_and_so_read_only_does_not_mind():
    connector = Connector()
    page = Page(
        onboarding=OnboardingService(connector, StubProfiles([DEV]), StubBundle()),
        read_only=True,
    )
    server = Server(page)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        served = Served(server, None)
        served.enter()
        assert connect(served, name="dev")[0] == 202
        assert ready(served)["read_only"] is True
        assert (
            served.ask("POST", "/api/connect", {"name": "dev"}, token="wrong")[0] == 401
        )
        cross = {"Origin": "https://evil.example"}
        assert (
            served.ask("POST", "/api/connect", {"name": "dev"}, headers=cross)[0] == 403
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_a_page_with_nothing_to_choose_from_says_so():
    page = Page()
    server = Server(page)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        served = Served(server, None)
        served.enter()
        assert served.json("GET", "/api/workspaces")[1]["workspaces"] == []
        assert connect(served, name="dev")[0] == 409
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ── what a second pair of eyes found ─────────────────────────────────
ABOUT_A_WORKSPACE = [
    ("GET", "/api/keys", None),
    ("GET", "/api/grants", None),
    ("GET", "/api/scope?name=prod", None),
    ("POST", "/api/value", {"scope": "prod", "key": "api-key"}),
    ("POST", "/api/forget", {}),
    ("POST", "/api/refresh", {}),
    ("POST", "/api/secret/put", {"scope": "prod", "key": "new", "text": "x"}),
    ("POST", "/api/secret/delete", {"scope": "prod", "key": "api-key"}),
    (
        "POST",
        "/api/secret/move",
        {"scope": "prod", "key": "api-key", "to_scope": "prod", "to_key": "b"},
    ),
    ("POST", "/api/undo", {}),
    (
        "POST",
        "/api/grant/put",
        {"scope": "prod", "principal": "a@b.c", "permission": "READ"},
    ),
    ("POST", "/api/grant/delete", {"scope": "prod", "principal": "users"}),
    ("POST", "/api/scope/create", {"name": "new-scope"}),
    ("POST", "/api/scope/delete", {"name": "prod"}),
    ("POST", "/api/env/preview", {"scope": "prod", "base64": "QT0x"}),
    ("POST", "/api/env/import", {"scope": "prod", "base64": "QT0x"}),
    ("POST", "/api/env/export", {"scope": "prod"}),
]
WRITES = (
    "put_secret_bytes",
    "delete_secret",
    "put_acl",
    "delete_acl",
    "create_scope",
    "delete_scope",
)


def wrote(store) -> list[str]:
    return [call[0] for call in store.calls if call[0] in WRITES]


@pytest.mark.parametrize(("method", "path", "body"), ABOUT_A_WORKSPACE)
def test_a_page_left_showing_another_workspace_changes_and_reads_nothing(
    served, method, path, body
):
    """A second tab still on dev, or a key pressed before the switch: what it
    asks was meant for dev, and must not be done to prod."""
    connect(served, name="dev")
    ready(served)
    on_dev = {"X-Caland-Workspace": str(served.page.turn)}
    connect(served, name="prod")
    ready(served)
    reads = served.connector.stores["prod"].reads()
    for headers in (on_dev, {"X-Caland-Workspace": None}, {"X-Caland-Workspace": "x"}):
        status, _, text = served.ask(method, path, body, headers=headers)
        assert status == 412 and b"another workspace" in text
    assert wrote(served.connector.stores["prod"]) == []
    assert served.connector.stores["prod"].reads() == reads


def test_the_state_says_which_workspace_it_is_counted_from_the_first(served):
    assert state(served)["turn"] == 0
    connect(served, name="dev")
    assert ready(served)["turn"] == 1
    connect(served, name="prod")
    assert ready(served)["turn"] == 2


def test_a_change_under_way_when_caland_goes_elsewhere_stays_in_its_own_workspace(served):
    connect(served, name="dev")
    ready(served)
    dev = served.connector.stores["dev"]
    real = dev.delete_secret
    under_way, go_on = threading.Event(), threading.Event()

    def held(scope, key):
        under_way.set()
        go_on.wait(30)
        real(scope, key)

    dev.delete_secret = held
    done = []
    asking = threading.Thread(
        target=lambda: done.append(
            served.json("POST", "/api/secret/delete", {"scope": "prod", "key": "api-key"})
        )
    )
    asking.start()
    try:
        assert under_way.wait(10)  # the delete is with dev, and stays there
        connect(served, name="prod")
        ready(served)
    finally:
        go_on.set()
    asking.join(timeout=10)
    assert done[0][0] == 200
    assert "delete_secret" in [call[0] for call in dev.calls]
    assert wrote(served.connector.stores["prod"]) == []
    assert any(
        s.key == "api-key" for s in served.connector.stores["prod"]._secrets["prod"]
    )


def test_a_profile_that_is_on_no_list_is_in_use_all_the_same(served):
    """One with no address: not offered, and still there — with its token."""
    served.profiles.others = ["prod-sp"]
    for name in ("prod-sp", "PROD-SP"):
        status, told = connect(served, url="https://evil.example.com", save_as=name)
        assert status == 409 and "already" in told["error"]
    assert served.connector.stores == {} and served.profiles.saved == []


def test_a_name_taken_while_signing_in_is_said_and_the_sign_in_stands(served):
    real, asked = served.profiles.names, []

    def names():
        asked.append(1)  # free when the request asks, taken when it is written
        return ["DEFAULT"] if len(asked) == 1 else real()

    served.profiles.names = names
    assert connect(served, url="https://new.example.com", save_as="prod")[0] == 202
    told = ready(served)
    assert told["phase"] == "ready" and "profile was not kept" in told["notice"]
    assert served.profiles.saved == []


def test_a_sign_in_given_up_for_another_keeps_nothing(served):
    held = threading.Event()
    real = served.connector.connect_url

    def slowly(host):
        held.wait(30)
        return real(host)

    served.connector.connect_url = slowly
    connect(served, url="https://new.example.com", save_as="given-up")
    given_up = served.page.loader
    connect(served, name="dev")
    assert ready(served)["workspace"]["name"] == "dev"
    held.set()
    # the sign-in that was given up runs to its end: by then it has kept what it would
    for _ in range(1000):
        if given_up.progress().phase in ("ready", "failed"):
            break
        threading.Event().wait(0.01)
    assert given_up.progress().phase == "ready"
    assert served.profiles.saved == []
    assert state(served)["workspace"]["name"] == "dev" and state(served)["notice"] == ""


def test_whatever_goes_wrong_on_the_way_in_is_said(served):
    def broken(profile):
        raise PermissionError("~/.databrickscfg cannot be read")

    served.connector.connect_profile = broken
    connect(served, name="dev")
    told = ready(served)
    assert told["phase"] == "failed" and "cannot be read" in told["error"]


def test_two_that_were_found_under_one_name_are_told_apart_by_their_address():
    from caland.domain import SOURCE_BUNDLE

    bundle = Workspace(
        host="https://bundle.example.com", source=SOURCE_BUNDLE, target="prod"
    )
    connector = Connector()
    page = Page(
        onboarding=OnboardingService(connector, StubProfiles([PROD]), StubBundle(bundle))
    )
    server = Server(page)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        served = Served(server, None)
        served.enter()
        rows = served.json("GET", "/api/workspaces")[1]["workspaces"]
        assert [(row["name"], row["host"]) for row in rows] == [
            ("prod", "bundle.example.com"),
            ("prod", "prod.example.com"),
        ]
        status, told = connect(served, name="prod")
        assert status == 409 and "say which address" in told["error"]
        assert connect(served, name="prod", host="prod.example.com")[0] == 202
        assert ready(served)["workspace"]["host"] == "prod.example.com"
        assert list(connector.stores) == ["prod"]  # the profile, not the bundle's address
        assert connect(served, name="prod", host="nope.example.com")[0] == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    "url",
    [
        "https://exаmple.com",  # a Cyrillic а
        "https://1.2.3.4",
        "https://[::ffff:1.2.3.4]",
        "https://a.%(token)s.b",
        "https://dev.example.com\x00.evil.example",
        "https://dev_example.com",
        "https://-dev.example.com",
        "https://dev.example.com.",
        "https://dev..example.com",
        "https://example.123",
    ],
)
def test_a_host_is_one_as_workspaces_have_them(served, url):
    status, told = connect(served, url=url, save_as="new-one")
    assert status == 400 and "address" in told["error"]
    assert served.connector.stores == {} and served.profiles.saved == []


def test_an_address_is_kept_as_it_was_read_in_small_letters(served):
    connect(served, url="HTTPS://Adb-123.AzureDatabricks.NET:443/", save_as="azure")
    assert ready(served)["phase"] == "ready"
    assert served.profiles.saved == [
        ("azure", "https://adb-123.azuredatabricks.net:443", None)
    ]


def test_a_bundles_target_and_a_profile_at_one_address_are_both_there_to_go_to():
    """One name, one address: told apart by where each was found. The profile
    signs in as profiles do — with its token, say — and the target through the
    browser."""
    from caland.domain import SOURCE_BUNDLE

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
        served = Served(server, None)
        served.enter()
        rows = served.json("GET", "/api/workspaces")[1]["workspaces"]
        assert [(row["name"], row["host"], row["default"]) for row in rows] == [
            ("prod", "prod.example.com", True),
            ("prod", "prod.example.com", False),
        ]
        status, told = connect(served, name="prod", host="prod.example.com")
        assert status == 409 and "where it was found" in told["error"]
        profile = {key: rows[1][key] for key in ("name", "host", "from")}
        assert connect(served, **profile)[0] == 202
        assert ready(served)["phase"] == "ready"
        assert list(connector.stores) == ["prod"]  # the profile: no sign-in by address
        target = {key: rows[0][key] for key in ("name", "host", "from")}
        assert connect(served, **target)[0] == 202
        assert ready(served)["phase"] == "ready"
        assert list(connector.stores) == ["prod", "https://prod.example.com"]
        assert connect(served, name="prod", **{"from": "nowhere"})[0] == 404
        # said badly, it picks none of the two
        assert connect(served, name="prod", **{"from": 7})[0] == 409
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

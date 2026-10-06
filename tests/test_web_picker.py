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

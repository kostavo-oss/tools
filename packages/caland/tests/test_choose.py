"""Choosing a workspace without a picker: by name, or the one there is no doubt about."""

from __future__ import annotations

import pytest

from caland.domain import SOURCE_BUNDLE, AuthError, Workspace
from fakes import stub_onboarding

DEV = Workspace(profile="dev", host="https://dev.example")
PROD = Workspace(profile="prod", host="https://prod.example")
BUNDLE = Workspace(
    host="https://b.example", source=SOURCE_BUNDLE, target="shop", default=True
)


def test_by_name():
    assert stub_onboarding([DEV, PROD]).choose("prod") is PROD


def test_a_bundle_target_by_its_name():
    assert stub_onboarding([DEV], BUNDLE).choose("shop") is BUNDLE


def test_a_name_that_is_not_there_says_what_is():
    with pytest.raises(
        AuthError, match="No workspace “nope” found. There is: dev, prod."
    ):
        stub_onboarding([DEV, PROD]).choose("nope")


def test_without_a_name_the_bundles_default():
    assert stub_onboarding([DEV, PROD], BUNDLE).choose() is BUNDLE


def test_without_a_name_the_only_one_there_is():
    assert stub_onboarding([DEV]).choose() is DEV


def test_without_a_name_and_several_it_asks_which():
    with pytest.raises(AuthError, match="Which workspace\\? There is: dev, prod."):
        stub_onboarding([DEV, PROD]).choose()


def test_with_nothing_at_all_it_says_so():
    with pytest.raises(AuthError, match="No workspace found"):
        stub_onboarding().choose()


# ── every profile is offered, whatever its address ───────────────────
ME = Workspace(profile="me", host="https://one.example")
SP = Workspace(profile="sp", host="https://one.example/")
AT_THE_BUNDLES = Workspace(profile="shop-sp", host="https://b.example")


def test_two_profiles_at_one_address_are_both_offered_and_asked_for_by_name():
    board = stub_onboarding([ME, SP, DEV])
    assert board.available_workspaces() == [ME, SP, DEV]
    assert board.choose("sp") is SP and board.choose("me") is ME


def test_a_profile_at_the_bundles_address_is_listed_beside_it_and_the_bundle_first():
    board = stub_onboarding([AT_THE_BUNDLES, DEV], BUNDLE)
    assert board.available_workspaces() == [BUNDLE, AT_THE_BUNDLES, DEV]
    assert board.choose("shop-sp") is AT_THE_BUNDLES
    assert board.choose() is BUNDLE  # with no name, the bundle's still


def test_asked_for_by_name_a_profile_comes_before_a_bundles_target_of_that_name():
    """The target needs no name — it is where caland goes without one — and the
    profile has no other way to be asked for."""
    profile = Workspace(profile="shop", host="https://b.example")
    board = stub_onboarding([profile], BUNDLE)
    assert board.choose("shop") is profile and board.choose() is BUNDLE


def test_a_profile_at_the_bundles_address_signs_in_as_the_profile_does():
    """Its token, or its service principal: not the browser, as the bundle's
    target does at the same address."""
    from caland.application import OnboardingService
    from fakes import ConnectingStubConnector, StubBundle, StubProfiles

    class Connector(ConnectingStubConnector):
        asked: list[tuple[str, str]] = []

        def connect_profile(self, profile):
            self.asked.append(("profile", profile))
            return super().connect_profile(profile)

        def connect_url(self, host):
            self.asked.append(("url", host))
            return super().connect_url(host)

    connector = Connector()
    board = OnboardingService(
        connector, StubProfiles([AT_THE_BUNDLES]), StubBundle(BUNDLE)
    )
    board.connect(board.choose("shop-sp"))
    board.connect(board.choose())
    assert connector.asked == [("profile", "shop-sp"), ("url", "https://b.example")]

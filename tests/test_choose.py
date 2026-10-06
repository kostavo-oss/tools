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

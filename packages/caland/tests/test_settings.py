"""Preferences: kept in a small file of caland's own, and forgiving about it."""

from __future__ import annotations

import json

from caland.domain import Settings
from caland.infrastructure import JsonSettingsStore
from caland.infrastructure.settings import settings_path


def test_what_is_saved_is_what_is_loaded(tmp_path):
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(Settings(show_all_scopes=True, audit_threshold=180))
    assert store.load() == Settings(show_all_scopes=True, audit_threshold=180)
    assert json.loads((tmp_path / "settings.json").read_text()) == {
        "show_all_scopes": True,
        "audit_threshold": 180,
    }


def test_a_missing_or_broken_file_means_the_defaults_never_a_failure(tmp_path):
    path = tmp_path / "settings.json"
    assert JsonSettingsStore(path).load() == Settings()
    for broken in ("{not json", "[1, 2]", '"text"', ""):
        path.write_text(broken)
        assert JsonSettingsStore(path).load() == Settings()


def test_what_is_the_wrong_kind_or_not_known_is_passed_over(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        '{"show_all_scopes": "yes", "audit_threshold": true, "theme": "phosphor", "x": 1}'
    )
    assert JsonSettingsStore(path).load() == Settings()
    path.write_text('{"show_all_scopes": true, "audit_threshold": 30.0}')
    assert JsonSettingsStore(path).load() == Settings(show_all_scopes=True)


def test_a_folder_that_cannot_be_written_does_not_stop_caland(tmp_path):
    blocked = tmp_path / "a-file"
    blocked.write_text("in the way")
    JsonSettingsStore(blocked / "settings.json").save(Settings(show_all_scopes=True))


def test_the_file_is_calands_own(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert settings_path() == tmp_path / "caland" / "settings.json"
    JsonSettingsStore().save(Settings(audit_threshold=365))
    assert JsonSettingsStore().load().audit_threshold == 365

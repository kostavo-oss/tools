from __future__ import annotations

import pytest

from caland.infrastructure import DatabricksCfgProfileStore


def _store(tmp_path, monkeypatch, body: str = ""):
    cfg = tmp_path / "databrickscfg"
    if body:
        cfg.write_text(body)
    monkeypatch.setenv("DATABRICKS_CONFIG_FILE", str(cfg))
    return DatabricksCfgProfileStore(), cfg


def test_discover_parses_profiles_including_default(tmp_path, monkeypatch):
    store, _ = _store(
        tmp_path,
        monkeypatch,
        """
[DEFAULT]
host = https://default.cloud.databricks.com
token = dapi-x

[staging]
host = https://staging.cloud.databricks.com
auth_type = external-browser
""",
    )
    profiles = {w.profile: w for w in store.discover()}
    assert set(profiles) == {"DEFAULT", "staging"}
    assert profiles["staging"].host == "https://staging.cloud.databricks.com"


def test_discover_skips_sections_without_host(tmp_path, monkeypatch):
    store, _ = _store(
        tmp_path,
        monkeypatch,
        """
[has-host]
host = https://a.databricks.com

[no-host]
token = dapi-y
""",
    )
    assert [w.profile for w in store.discover()] == ["has-host"]


def test_discover_env_fallback_when_no_config(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABRICKS_CONFIG_FILE", str(tmp_path / "missing"))
    monkeypatch.setenv("DATABRICKS_HOST", "https://env.databricks.com")
    profiles = DatabricksCfgProfileStore().discover()
    assert len(profiles) == 1
    assert profiles[0].host == "https://env.databricks.com"


# ── the file holds tokens: what a second pair of eyes found ───────────
CFG = (
    "; my own comment\n"
    "[DEFAULT]\nhost = https://default.example.com\n\n"
    "[prod-sp]\nhost   =   https://prod.example.com\ntoken = dapi%MADE=UP;TOKEN\n"
    "client_secret = line one\n  line two\n\n"
    "[no-host-yet]\ntoken = another-made-up\n"
)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    path = tmp_path / ".databrickscfg"
    path.write_text(CFG)
    path.chmod(0o600)
    monkeypatch.setenv("DATABRICKS_CONFIG_FILE", str(path))
    return path


def test_a_profile_is_added_to_the_end_and_what_was_there_is_as_it_was(cfg):
    DatabricksCfgProfileStore().add("new-one", "https://new.example.com/")
    assert cfg.read_text() == (
        CFG
        + "\n[new-one]\nhost = https://new.example.com\nauth_type = external-browser\n"
    )
    found = {w.profile: w.host for w in DatabricksCfgProfileStore().discover()}
    assert found["new-one"] == "https://new.example.com"
    assert found["prod-sp"] == "https://prod.example.com"


@pytest.mark.parametrize(
    "name", ["prod-sp", "PROD-SP", "no-host-yet", "No-Host-Yet", "DEFAULT", "default"]
)
def test_a_profile_that_is_there_is_never_written_over(cfg, name):
    """It keeps its own way of signing in — a token — and under another address
    that would be sent there. Also one that has no address, and so is on no list."""
    from caland.domain import Exists

    with pytest.raises(Exists, match="already"):
        DatabricksCfgProfileStore().add(name, "https://evil.example.com")
    assert cfg.read_text() == CFG


@pytest.mark.parametrize("name", ["", "  ", "x]\ntoken = stolen", "[x", "a\rb"])
def test_what_is_no_name_is_not_written_as_one(cfg, name):
    from caland.domain import Exists

    with pytest.raises(Exists):
        DatabricksCfgProfileStore().add(name, "https://new.example.com")
    assert cfg.read_text() == CFG


def test_every_profile_is_named_with_an_address_or_not(cfg):
    assert DatabricksCfgProfileStore().names() == ["DEFAULT", "prod-sp", "no-host-yet"]


def test_a_new_file_is_its_owners_alone_and_one_that_was_there_keeps_its_mode(
    tmp_path, monkeypatch
):
    import stat
    import sys

    if sys.platform == "win32":
        pytest.skip("modes are another matter there")
    path = tmp_path / "sub" / ".databrickscfg"
    monkeypatch.setenv("DATABRICKS_CONFIG_FILE", str(path))
    DatabricksCfgProfileStore().add("first", "https://a.example.com")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    path.chmod(0o640)
    DatabricksCfgProfileStore().add("second", "https://b.example.com")
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert [p.name for p in path.parent.iterdir()] == [".databrickscfg"]  # no copy left


def test_many_added_at_once_are_all_there_and_none_is_lost(cfg):
    import threading

    store = DatabricksCfgProfileStore()
    threads = [
        threading.Thread(target=store.add, args=(f"p{n}", f"https://p{n}.example.com"))
        for n in range(40)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    text = cfg.read_text()
    assert text.startswith(CFG)
    assert sorted(store.names()) == sorted(
        ["DEFAULT", "prod-sp", "no-host-yet", *[f"p{n}" for n in range(40)]]
    )


def test_a_write_that_fails_leaves_the_file_as_it_was(cfg, monkeypatch):
    import os

    def broken(*args, **kwargs):
        raise OSError("the disk is full")

    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(OSError):
        DatabricksCfgProfileStore().add("new-one", "https://new.example.com")
    assert cfg.read_text() == CFG
    assert [p.name for p in cfg.parent.iterdir()] == [".databrickscfg"]


def test_a_profile_that_is_there_twice_is_one_profile_not_a_failure(
    tmp_path, monkeypatch
):
    path = tmp_path / ".databrickscfg"
    path.write_text(
        "[dup]\nhost = https://a.example.com\n\n[dup]\nhost = https://b.example.com\n"
    )
    monkeypatch.setenv("DATABRICKS_CONFIG_FILE", str(path))
    assert [w.profile for w in DatabricksCfgProfileStore().discover()] == ["dup"]


# ── a config that is a link: kept in a folder of dotfiles, say ────────
ADDED = "\n[new-one]\nhost = https://new.example.com\nauth_type = external-browser\n"


def _linked(tmp_path, monkeypatch, to: str | None = None):
    """A config that is a link to a file elsewhere. The file, and the link."""
    import sys

    if sys.platform == "win32":
        pytest.skip("links are another matter there")
    real = tmp_path / "dotfiles" / "databrickscfg"
    real.parent.mkdir()
    link = tmp_path / "home" / ".databrickscfg"
    link.parent.mkdir()
    link.symlink_to(to or real)
    monkeypatch.setenv("DATABRICKS_CONFIG_FILE", str(link))
    return real, link


def test_a_config_that_is_a_link_is_written_through_the_link(tmp_path, monkeypatch):
    import stat

    real, link = _linked(tmp_path, monkeypatch)
    real.write_text(CFG)
    real.chmod(0o640)
    DatabricksCfgProfileStore().add("new-one", "https://new.example.com")
    assert link.is_symlink() and link.resolve() == real.resolve()
    assert real.read_text() == CFG + ADDED and link.read_text() == CFG + ADDED
    assert stat.S_IMODE(real.stat().st_mode) == 0o640  # the person's, as it was
    # no copy is left, beside the file or beside the link
    assert [p.name for p in real.parent.iterdir()] == ["databrickscfg"]
    assert [p.name for p in link.parent.iterdir()] == [".databrickscfg"]


def test_a_link_said_from_where_it_is_and_a_link_to_a_link_stay_links(
    tmp_path, monkeypatch
):
    real, link = _linked(tmp_path, monkeypatch, to="../dotfiles/first")
    (real.parent / "first").symlink_to("databrickscfg")
    real.write_text(CFG)
    DatabricksCfgProfileStore().add("new-one", "https://new.example.com")
    assert link.is_symlink() and (real.parent / "first").is_symlink()
    assert real.read_text() == CFG + ADDED and not real.is_symlink()


def test_a_link_to_a_file_that_is_not_there_yet_gets_that_file_and_stays(
    tmp_path, monkeypatch
):
    import stat

    real, link = _linked(tmp_path, monkeypatch)
    DatabricksCfgProfileStore().add("new-one", "https://new.example.com")
    assert link.is_symlink() and real.read_text() == ADDED.lstrip("\n")
    assert stat.S_IMODE(real.stat().st_mode) == 0o600  # a new file: its owner's alone

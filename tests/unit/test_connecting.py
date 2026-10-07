"""Which workspace a command talks to.

Dev and prod are usually different workspaces, so a target can name a
`~/.databrickscfg` profile, and `--profile` overrides it. Without either, the
Databricks SDK's own defaults apply.
"""

from pathlib import Path
from typing import Any

import pytest

from stevin.connect import Connection, NotConnected
from stevin.loader import Target, load_project


class RecordingClient:
    """Stands in for WorkspaceClient, remembering how it was made."""

    made: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        RecordingClient.made.append(kwargs)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> type[RecordingClient]:
    import databricks.sdk

    RecordingClient.made = []
    monkeypatch.setattr(databricks.sdk, "WorkspaceClient", RecordingClient)
    return RecordingClient


def test_a_target_can_name_its_profile(tmp_path: Path) -> None:
    (tmp_path / "stevin.yml").write_text(
        "targets:\n  dev: {profile: dev-workspace, warehouse_id: abc}\n  prod: {}\n"
    )
    project = load_project(tmp_path / "stevin.yml")
    assert project.target("dev").profile == "dev-workspace"
    assert project.target("prod").profile is None


def test_the_targets_profile_is_used(client: type[RecordingClient]) -> None:
    Connection.from_target(Target("dev", warehouse_id="abc", profile="dev-workspace"))
    assert client.made == [{"profile": "dev-workspace"}]


def test_profile_on_the_command_line_wins(client: type[RecordingClient]) -> None:
    Connection.from_target(
        Target("dev", warehouse_id="abc", profile="dev-workspace"), profile="other"
    )
    assert client.made == [{"profile": "other"}]


def test_without_a_profile_the_sdk_decides(client: type[RecordingClient]) -> None:
    Connection.from_target(Target("dev"), warehouse_id="abc")
    assert client.made == [{}], "no profile argument at all, so env vars still work"


def test_a_workspace_that_cant_be_reached_is_a_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import databricks.sdk

    def unconfigured(**_kwargs: Any) -> None:
        raise ValueError("default auth: cannot configure default credentials")

    monkeypatch.setattr(databricks.sdk, "WorkspaceClient", unconfigured)
    with pytest.raises(NotConnected) as raised:
        Connection.from_target(Target("dev", profile="missing"), warehouse_id="abc")
    said = str(raised.value)
    assert "can't connect to a Databricks workspace using profile 'missing'" in said
    assert "cannot configure default credentials" in said


# ---------------------------------------------------------------------------
# the command line says what it is waiting for
# ---------------------------------------------------------------------------


def test_the_command_says_which_workspace_it_is_connecting_to_before_it_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Databricks SDK looks a host up when a client is made, and keeps
    trying one that doesn't answer — for minutes, with nothing on the screen.
    So the line that says what is being waited for comes before the call.
    """
    import databricks.sdk
    from typer.testing import CliRunner

    from stevin import cli

    said_so_far: list[str] = []

    class NeverAnswers:
        def __init__(self, **_kwargs: Any) -> None:
            said_so_far.append(recording.export_text())
            raise ValueError("Timed out after 0:05:00")

    recording = cli.Console(record=True, width=200)
    monkeypatch.setattr(cli, "err", recording)
    monkeypatch.setattr(databricks.sdk, "WorkspaceClient", NeverAnswers)
    (tmp_path / "stevin.yml").write_text(
        "targets:\n  dev: {profile: dev-workspace, warehouse_id: abc}\n"
    )
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli.app, ["import", "main.sales"])
    assert result.exit_code == 1
    [before_the_call] = said_so_far
    assert "Connecting to the Databricks workspace" in before_the_call
    assert "profile 'dev-workspace'" in before_the_call
    assert "Timed out after 0:05:00" in recording.export_text()


def test_what_it_connects_with_is_named_the_way_the_connection_decides() -> None:
    from stevin.connect import workspace_named

    bundle = Target("dev", host="https://adb-1.azuredatabricks.net")
    assert workspace_named(Target("dev", profile="a"), None) == "profile 'a'"
    assert workspace_named(Target("dev", profile="a"), "b") == "profile 'b'"
    assert workspace_named(bundle, None) == "host https://adb-1.azuredatabricks.net"
    assert workspace_named(bundle, "b") == "profile 'b'", "a profile beats the host"
    assert workspace_named(None, None) == "the environment or the DEFAULT profile"

"""A project's command line, with dlt loading into a local database: the APP rules."""

import json
import logging
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from azure.core.exceptions import HttpResponseError

import leeghwater
from leeghwater import App, LeeghwaterError, pipeline

TESTS = Path(__file__).parent


def _app(**settings) -> App:
    return App(pipelines="my_ingest.pipelines", **settings)


def _odd(**settings) -> App:
    return App(pipelines="my_ingest_odd.pipelines", **settings)


def _schemas(database: str) -> set[str]:
    with duckdb.connect(database, read_only=True) as connection:
        rows = connection.sql("select schema_name from information_schema.schemata")
        return {row[0] for row in rows.fetchall()}


def _rows(database: str, table: str) -> list[tuple]:
    with duckdb.connect(database, read_only=True) as connection:
        return connection.sql(
            f"select * exclude (_dlt_load_id, _dlt_id) from {table}"
        ).fetchall()


def test_list_names_the_pipelines_and_their_parameters(capsys):
    """APP-2, APP-8."""
    _app()(["list"])

    said = capsys.readouterr().out
    assert "github  Load GitHub issues." in said
    assert "--since <date>  default datetime.date(2024, 1, 1)" in said
    assert "orders_pipeline" in said
    assert "--region <str>  required" in said


def test_list_answers_as_json(capsys):
    """APP-8."""
    _app()(["list", "--json"])

    listed = json.loads(capsys.readouterr().out)["pipelines"]
    assert [item["name"] for item in listed] == ["github", "orders_pipeline"]
    since, full = listed[0]["parameters"]
    assert since == {
        "name": "since",
        "option": "--since",
        "type": "date",
        "required": False,
        "default": "2024-01-01",
    }
    assert full["type"] == "bool"
    assert listed[1]["parameters"][0]["required"] is True


def test_run_runs_a_pipeline_and_its_parameters_arrive_typed(capsys, monkeypatch):
    """APP-3, APP-4."""
    monkeypatch.setenv("SOURCES__GITHUB__ACCESS_TOKEN", "abc")

    _app()(["run", "github", "--since", "2024-06-01", "--limit", "1", "--full", "yes"])

    said = capsys.readouterr().out
    assert "leeghwater" in said and "run github" in said
    assert "load report" in said
    assert _rows("github.duckdb", "github_dataset.issues") == [(1, "2024-06-01", 3)]


def test_a_parameter_keeps_its_default_and_its_type(monkeypatch):
    """APP-3, APP-4."""
    seen = {}

    @pipeline
    def typed(
        day: date = date(2024, 1, 1), n: int = 3, ratio: float = 0.5, on: bool = True
    ):
        seen.update(day=day, n=n, ratio=ratio, on=on)
        p = leeghwater.create_pipeline("typed", schema="shop")
        leeghwater.run(p, [{"id": 1}], table_name="rows")

    monkeypatch.setitem(sys.modules, "typed_pipelines", _module(typed))
    App(pipelines="typed_pipelines")(["run", "typed"])
    assert seen == {"day": date(2024, 1, 1), "n": 3, "ratio": 0.5, "on": True}

    App(pipelines="typed_pipelines")(
        [
            "run",
            "typed",
            "--day",
            "2025-02-03",
            "--n",
            "7",
            "--ratio",
            "1.5",
            "--on",
            "no",
        ]
    )
    assert seen == {"day": date(2025, 2, 3), "n": 7, "ratio": 1.5, "on": False}


def _module(*functions):
    import types

    module = types.ModuleType("made_up")
    for function in functions:
        setattr(module, function.__name__, function)
    return module


def test_a_parameter_may_have_a_name_the_app_uses_itself(monkeypatch):
    """APP-5."""
    seen = {}

    @pipeline
    def named(
        name: str,
        self: int = 1,
        cls: str = "c",
        args: str = "a",
        kwargs: str = "k",
        function: str = "f",
        pipeline: str = "p",
        values: str = "v",
    ):
        seen.update(locals())
        p = leeghwater.create_pipeline("named", schema="shop")
        leeghwater.run(p, [{"id": 1}], table_name="rows")

    monkeypatch.setitem(sys.modules, "named_pipelines", _module(named))
    words = ["run", "named", "--name", "n", "--self", "2", "--kwargs", "kw"]
    App(pipelines="named_pipelines")([*words, "--schema", "elsewhere"])

    assert seen.pop("seen") is seen
    assert seen == {
        "name": "n",
        "self": 2,
        "cls": "c",
        "args": "a",
        "kwargs": "kw",
        "function": "f",
        "pipeline": "p",
        "values": "v",
    }
    assert "elsewhere" in _schemas("named.duckdb")


def test_a_parameter_keeps_its_capitals_and_its_place(monkeypatch, capsys):
    """APP-5."""
    seen = {}

    @pipeline
    def placed(day: str, /, Schema: str = "S", since: str = "s", Since: str = "S"):
        seen.update(day=day, Schema=Schema, since=since, Since=Since)
        p = leeghwater.create_pipeline("placed", schema="shop")
        leeghwater.run(p, [{"id": 1}], table_name="rows")

    monkeypatch.setitem(sys.modules, "placed_pipelines", _module(placed))
    words = ["--day", "d", "--Schema", "mine", "--Since", "then", "--schema", "runs"]
    App(pipelines="placed_pipelines")(["run", "placed", *words])

    assert seen == {"day": "d", "Schema": "mine", "since": "s", "Since": "then"}
    assert "runs" in _schemas("placed.duckdb")

    App(pipelines="placed_pipelines")(["list"])
    assert "--Schema <str>  default 'S'" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["run", "github", "--since", "yesterday"], "not an ISO date"),
        (["run", "github", "--full", "perhaps"], "not one of true"),
        (["run", "orders_pipeline"], "--region"),
        (["run", "no_such_pipeline"], "No such command"),
    ],
)
def test_a_wrong_option_is_refused_by_name(arguments, message, capsys):
    """APP-3, APP-4."""
    with pytest.raises(SystemExit) as exit_:
        _app()(arguments)

    assert exit_.value.code == 2
    assert message in " ".join(capsys.readouterr().err.split())


def test_the_same_words_run_the_same_pipeline_as_a_console_script(tmp_path):
    """APP-1.

    What a wheel task does: call the project's entry point with the words as argv.
    """
    code = "import sys; from my_ingest.cli import app; sys.argv[0] = 'ingest'; app()"
    done = subprocess.run(
        [sys.executable, "-c", code, "run", "orders_pipeline", "--region", "eu"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(TESTS)},
    )

    assert done.returncode == 0, done.stderr
    assert "run orders_pipeline" in done.stdout
    assert _rows(str(tmp_path / "orders.duckdb"), "shop.orders") == [
        (1, "eu"),
        (2, "eu"),
    ]


def test_the_schemas_a_run_names_are_the_ones_dlt_loads_into(monkeypatch):
    """DST-6. For real: two underscores kept, and no third schema."""
    monkeypatch.setenv("SOURCES__GITHUB__ACCESS_TOKEN", "abc")

    _app()(
        [
            "run",
            "github",
            "--schema",
            "github__anna",
            "--staging-schema",
            "github_staging__anna",
        ]
    )

    schemas = _schemas("github.duckdb")
    assert {"github__anna", "github_staging__anna"} <= schemas
    assert not {"github_anna", "github__anna_staging", "github_dataset"} & schemas


def test_a_pipeline_that_raises_ends_the_run_with_its_own_error():
    """APP-11."""
    with pytest.raises(RuntimeError, match="the source is down"):
        _odd()(["run", "raises"])


def test_a_failed_load_job_ends_with_1_even_when_dlt_was_told_not_to_raise(capsys):
    """RUN-7. dlt calls this package `loaded`, with a table missing."""
    with pytest.raises(SystemExit) as exit_:
        _odd()(["run", "fails_quietly"])

    said = capsys.readouterr()
    assert exit_.value.code == 1
    assert "FAILED  rows: " in said.out
    assert "Conversion Error" in said.out
    assert "Traceback" not in said.out
    assert "1 load job(s) failed, for: rows." in said.err


def test_a_pipeline_that_calls_dlt_itself_is_not_a_green_run(capsys):
    """RUN-8. The run's names reach only a pipeline leeghwater made."""
    with pytest.raises(SystemExit) as exit_:
        _odd()(["run", "calls_dlt_itself", "--schema", "asked"])

    assert exit_.value.code == 1
    error = capsys.readouterr().err
    assert "made no load with leeghwater.run()" in error
    assert "dlt.pipeline() loads wherever dlt's own config says" in error


def test_a_pipeline_that_returns_nothing_is_still_reported(capsys):
    _odd()(["run", "returns_nothing"])

    assert "done    rows" in capsys.readouterr().out


def test_a_pipeline_that_ran_nothing_is_not_a_green_run(capsys):
    """RUN-8."""
    with pytest.raises(SystemExit):
        _odd()(["run", "runs_nothing"])

    assert "made no load with leeghwater.run()" in capsys.readouterr().err


def test_a_limit_reaches_the_pipeline(capsys):
    """RUN-5. Two rows, yielded one at a time: two pages. One page is one row."""
    _app()(["run", "orders_pipeline", "--region", "eu", "--limit", "1"])

    assert "1 page(s) from each resource" in capsys.readouterr().out
    assert _rows("orders.duckdb", "shop.orders") == [(1, "eu")]


def test_set_gives_dlt_any_config_value(capsys):
    """PRE-4."""
    _odd()(["run", "reads_config", "--set", "sources.orders.page_size=50"])

    assert "page_size is 50" in capsys.readouterr().out


def test_the_log_level_is_still_the_level_after_dlt_has_run(monkeypatch):
    """PRE-4."""
    from dlt.common import logger

    monkeypatch.setenv("SOURCES__GITHUB__ACCESS_TOKEN", "abc")

    _app()(["run", "github", "--log-level", "ERROR"])

    assert logger.LOGGER.level == logging.ERROR


def test_on_databricks_a_run_without_a_warehouse_stops_before_the_pipeline(on_databricks):
    """APP-11, DST-5."""
    with pytest.raises(LeeghwaterError, match="No SQL warehouse is named"):
        _odd()(["run", "raises"])


def test_on_a_laptop_an_error_of_leeghwaters_is_one_line(capsys):
    """APP-11, APP-12."""
    with pytest.raises(SystemExit) as exit_:
        _odd()(["run", "raises", "--schema", ""])

    assert exit_.value.code == 1
    assert capsys.readouterr().err.startswith("error: --schema is empty")


@pytest.mark.parametrize(
    "words",
    [
        ["--help"],
        ["run", "--help"],
        ["run", "github", "--help"],
        ["list", "--help"],
        ["doctor", "--help"],
        ["backfill", "--help"],
    ],
)
def test_help_is_plain_text_for_every_command(words, capsys):
    """APP-12. rich is installed here, as it is wherever typer is."""
    import rich  # noqa: F401

    from my_ingest.cli import app

    app(words)

    said = capsys.readouterr().out
    assert said.startswith("Usage: ")
    assert "--help" in said
    # Box drawing and block elements, and the escape that starts a colour.
    assert [c for c in said if "\u2500" <= c <= "\u259f" or c == "\x1b"] == []


def test_an_empty_option_from_a_bundle_is_refused_not_skipped(on_databricks):
    """APP-7. A variable that resolved to nothing must not pass for an option left out."""
    with pytest.raises(LeeghwaterError, match="--staging-schema is empty"):
        _odd(warehouse="abc123")(
            ["run", "raises", "--schema", "github", "--staging-schema", ""]
        )


def test_a_secret_from_a_scope_reaches_a_pipeline(on_databricks, workspace, capsys):
    """PRE-5, SEC-9."""
    app = _app(secret_scopes=["ingest"], destination="duckdb", workspace_client=workspace)

    app(["run", "github"])

    said = capsys.readouterr().out
    assert "secret scopes    ingest" in said
    assert "tok-from-ingest" not in said
    assert _rows("github.duckdb", "github_dataset.issues") == [
        (1, "2024-01-01", len("tok-from-ingest"))
    ]


def test_a_run_can_name_other_scopes_and_point_at_a_secret(
    on_databricks, workspace, capsys
):
    """SEC-8."""
    app = _app(
        secret_scopes=["no-such-scope"], destination="duckdb", workspace_client=workspace
    )

    app(
        [
            "run",
            "github",
            "--secret-scope",
            "ingest",
            "--secret",
            "sources.github.access_token=platform-shared/github-token",
        ]
    )

    said = capsys.readouterr().out
    assert "sources.github.access_token is platform-shared/github-token" in said
    assert _rows("github.duckdb", "github_dataset.issues") == [
        (1, "2024-01-01", len("tok-from-platform"))
    ]
    assert "no-such-scope" not in workspace.lists


def test_a_command_the_project_added_runs_and_finds_a_secret(
    on_databricks, workspace, capsys
):
    """APP-10."""
    import dlt

    app = _app(secret_scopes=["ingest"], destination="duckdb", workspace_client=workspace)

    @app.command()
    def backfill(day: str, dry: bool = False):
        """Load one day again."""
        token = dlt.secrets["sources.github.access_token"]
        print(f"backfill {day} dry={dry} token of {len(token)}")

    app(["backfill", "2024-06-01", "--dry"])

    said = capsys.readouterr().out
    assert "backfill 2024-06-01 dry=True token of 15" in said
    assert "secret scopes    ingest" in said


def test_a_parameter_named_like_an_option_of_every_run_is_refused_at_the_start(
    monkeypatch, capsys
):
    """APP-6."""

    @pipeline
    def clash(schema: str = "x"):
        pass

    @pipeline
    def asks(help: str = "x"):
        pass

    for function, message in (
        (clash, "Pipeline 'clash' has a parameter 'schema', and --schema is an option"),
        (asks, "Pipeline 'asks' has a parameter 'help', and --help is an option"),
    ):
        monkeypatch.setitem(sys.modules, "clash_pipelines", _module(function))
        with pytest.raises(SystemExit):
            App(pipelines="clash_pipelines")(["list"])
        assert message in capsys.readouterr().err


def test_what_else_is_refused_at_the_start(monkeypatch, capsys):
    """APP-2, APP-6."""

    @pipeline
    def takes_a_list(items: list[str]):
        pass

    @pipeline
    def takes_anything(**anything):
        pass

    @pipeline(name="takes_a_list")
    def same_name():
        pass

    for module, message in (
        (_module(takes_a_list), "is one of: str, int, float, bool, date, datetime"),
        (_module(takes_anything), "every parameter needs a name"),
        (_module(takes_a_list, same_name), "Two pipelines are named 'takes_a_list'"),
    ):
        monkeypatch.setitem(sys.modules, "refused_pipelines", module)
        with pytest.raises(SystemExit):
            App(pipelines="refused_pipelines")(["list"])
        assert message in capsys.readouterr().err

    with pytest.raises(SystemExit):
        App(pipelines="nowhere.to.be.found")(["list"])
    assert "there is no such module" in capsys.readouterr().err


class _Vault:
    """A stand-in for a Key Vault's client that can only be listed."""

    def __init__(self, names=(), error=None):
        self.names, self.error = names, error

    def list_properties_of_secrets(self):
        if self.error:
            raise self.error
        return [SimpleNamespace(name=name) for name in self.names]


VAULT = "https://kv-ingest.vault.azure.net"


def test_doctor_on_a_laptop_checks_the_vaults_and_asks_no_workspace(
    workspace, monkeypatch, capsys
):
    """APP-9. A local run reads no scope and loads through no warehouse, so neither is
    checked and nobody has to be signed in. A Key Vault it does read, so that is."""
    app = _app(secret_scopes=["ingest"], warehouse="abc123", workspace_client=workspace)
    app(["doctor"])

    said = capsys.readouterr().out
    assert "a laptop" in said
    assert "nothing to check: this run reads no workspace and no key vault" in said
    assert workspace.lists == []
    assert not Path("github.duckdb").exists()

    vaults = {VAULT: _Vault(["sources-orders", "sources-github-access-token"])}
    monkeypatch.setattr("leeghwater.keyvault._default_client", vaults.__getitem__)
    app(["doctor", "--key-vault", VAULT])

    said = capsys.readouterr().out
    assert (
        f"ok      key vault {VAULT}: sources-github-access-token, sources-orders" in said
    )
    assert "nothing to check" not in said
    assert workspace.lists == []

    refused = HttpResponseError("Forbidden")
    refused.status_code = 403
    vaults[VAULT] = _Vault(error=refused)
    with pytest.raises(SystemExit) as exit_:
        app(["doctor", "--key-vault", VAULT, "--json"])

    answer = json.loads(capsys.readouterr().out)
    assert exit_.value.code == 1
    assert [(check["what"], check["ok"]) for check in answer["checks"]] == [
        (f"key vault {VAULT}", False)
    ]
    assert "can't be listed by this identity" in answer["checks"][0]["found"]


def test_run_and_doctor_name_no_profile_the_run_does_not_use(
    workspace, monkeypatch, capsys
):
    """PRE-7, PRE-8. With a profile in the shell and no `--profile`, the run loads
    locally and neither `run` nor `doctor` says a workspace is in play: no profile, and
    not the catalog and the warehouse the app names."""
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "mine")
    monkeypatch.setenv("SOURCES__GITHUB__ACCESS_TOKEN", "abc")
    app = _app(
        secret_scopes=["ingest"],
        catalog="main",
        warehouse="abc123",
        workspace_client=workspace,
    )
    unused = "the profile in DATABRICKS_CONFIG_PROFILE (mine) is not used"

    app(["run", "github", "--limit", "1"])

    said = capsys.readouterr().out
    assert "\n  workspace " not in said and "profile mine" not in said
    assert "\n  catalog " not in said and "\n  warehouse " not in said
    assert "destination      duckdb" in said and unused in said
    assert Path("github.duckdb").exists()

    app(["doctor"])

    said = capsys.readouterr().out
    assert "\n  workspace " not in said and "profile mine" not in said
    assert "\n  catalog " not in said and "\n  warehouse " not in said
    assert unused in said
    assert "nothing to check: this run reads no workspace and no key vault" in said

    app(["doctor", "--json"])

    answer = json.loads(capsys.readouterr().out)
    assert (answer["setup"]["profile"], answer["checks"]) == (None, [])
    assert [answer["setup"][key] for key in ("catalog", "warehouse", "http_path")] == [
        None,
        None,
        None,
    ]
    assert workspace.lists == []
    assert os.environ["DATABRICKS_CONFIG_PROFILE"] == "mine"


def test_doctor_checks_the_identity_the_scopes_and_the_warehouse(
    on_databricks, workspace, capsys
):
    """APP-9, DST-4, SEC-9."""
    app = _app(
        secret_scopes=["ingest"],
        secrets={"sources.github.access_token": "platform-shared/github-token"},
        warehouse="abc123",
        workspace_client=workspace,
    )

    app(["doctor"])

    said = capsys.readouterr().out
    assert "ok      identity: dev@example.com" in said
    assert "ok      secret scope ingest: empty, sources-github-access_token" in said
    assert (
        "ok      secret sources.github.access_token: platform-shared/github-token" in said
    )
    assert "ok      warehouse abc123: ingest (RUNNING)" in said
    assert "tok-from" not in said
    assert workspace.reads == []

    # Wherever it would load: a run that loads somewhere else reads the scopes too.
    elsewhere = _app(
        secret_scopes=["ingest"], destination="duckdb", workspace_client=workspace
    )
    elsewhere(["doctor"])

    said = capsys.readouterr().out
    assert "destination      duckdb" in said
    assert "ok      identity: dev@example.com" in said
    assert "ok      secret scope ingest: empty, sources-github-access_token" in said
    assert workspace.reads == []


def test_doctor_fails_by_name_and_answers_as_json(on_databricks, workspace, capsys):
    """APP-9."""
    app = _app(
        secret_scopes=["no-such-scope"],
        secrets={"a.b": "ingest/not-there"},
        warehouse="gone",
        workspace_client=workspace,
    )

    with pytest.raises(SystemExit) as exit_:
        app(["doctor", "--json"])

    answer = json.loads(capsys.readouterr().out)
    assert exit_.value.code == 1
    assert answer["ok"] is False
    assert answer["setup"]["destination"] == "databricks"
    failed = {
        check["what"]: check["found"] for check in answer["checks"] if not check["ok"]
    }
    assert set(failed) == {"secret scope no-such-scope", "secret a.b", "warehouse gone"}
    assert "no secret 'not-there' in scope 'ingest'" in failed["secret a.b"]

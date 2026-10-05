"""The Databricks CLI's answers, read.

The plan documents are the CLI's own recordings (`tests/fixtures/cli/`), from
its acceptance tests: https://github.com/databricks/cli/tree/e41a5c87436a5b8fa81ce192e2aac77675d4b4c2/acceptance/bundle/resource_deps
"""

import pytest

from fakes import fixture
from lely import bundle
from lely.errors import LelyError
from lely.model import Change


def test_a_first_deploy_creates_everything() -> None:
    changes = bundle.changes(fixture("cli/plan-create.json"))
    assert [(c.key, c.action, c.destructive) for c in changes] == [
        ("resources.jobs.bar", "create", False),
        ("resources.pipelines.foo", "create", False),
    ]
    assert bundle.created(changes) == {"jobs.bar", "pipelines.foo"}


def test_an_immutable_field_replaces_the_resource() -> None:
    bar, foo = bundle.changes(fixture("cli/plan-update-recreate.json"))
    assert bar == Change(
        "resources.jobs.bar", "update", "jobs.bar", detail=("description",)
    )
    assert foo == Change(
        "resources.pipelines.foo",
        "replace",
        "pipelines.foo",
        destructive=True,
        detail=("replaced: storage (immutable)",),
    )
    assert bundle.created((bar, foo)) == {"pipelines.foo"}


def test_a_removed_resource_is_deleted() -> None:
    bar, foo = bundle.changes(fixture("cli/plan-delete-update.json"))
    assert (bar.action, bar.destructive) == ("delete", True)
    assert (foo.action, foo.detail) == ("update", ("tasks",))


def test_skipped_resources_are_no_change() -> None:
    document = fixture("cli/plan-create.json")
    for entry in document["plan"].values():
        entry["action"] = "skip"
    assert bundle.changes(document) == ()


def test_an_action_lely_doesnt_know_is_treated_as_destructive() -> None:
    document = fixture("cli/plan-create.json")
    document["plan"]["resources.jobs.bar"]["action"] = "teleport"
    change = bundle.changes(document)[0]
    assert change.destructive
    assert change.detail == ("the CLI plans `teleport`, which lely doesn't know",)


def test_another_plan_version_is_refused() -> None:
    document = fixture("cli/plan-create.json")
    document["plan_version"] = 3
    with pytest.raises(LelyError, match="plan of version 3; lely reads version 2"):
        bundle.changes(document)


def test_reads_name_target_host_and_resources_from_validate() -> None:
    config = fixture("cli/validate-default-python.json")
    assert bundle.name(config) == "project_name"
    assert bundle.target(config) == "dev"
    assert bundle.host(config) == "https://dbc-example.cloud.databricks.com"
    assert bundle.resource_keys(config) == {
        "jobs.sample_job",
        "pipelines.project_name_etl",
    }

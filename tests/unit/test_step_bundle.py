"""The `bundle` plugin: an Asset Bundle planned, deployed, listed and destroyed.

Reading the CLI's answers is tested against its own recordings
(`tests/fixtures/cli/`, from its acceptance tests:
https://github.com/databricks/cli/tree/e41a5c87436a5b8fa81ce192e2aac77675d4b4c2/acceptance/bundle).

Everything that deploys or destroys runs against the simulated bundle of
`tests/fake_databricks.py`, which is what lely *believes* the CLI does — the
assumptions V1–V7 of `spec/004-asset-bundle.md`. Each test that leans on one
names it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import project
from fakes import HOST, FakeDatabricks, deploy, fixture, write_bundle
from lely.errors import LelyError, Refused
from lely.model import Change, Item, Linked, Overview, Secret, StepPlan
from lely.step import Context
from lely.steps import bundle
from lely.steps.bundle import UPLOAD, Bundle
from lely.testing import (
    check_apply,
    check_destroy,
    check_overview,
    check_plan,
    context,
)

VARS = {"model_version": 14}


# -- reading the CLI's answers ---------------------------------------------------


def test_a_first_deploy_creates_everything() -> None:
    changes = bundle.changes(fixture("cli/plan-create.json"))
    assert [(c.key, c.action, c.destructive) for c in changes] == [
        ("jobs.bar", "create", False),
        ("pipelines.foo", "create", False),
    ]


def test_an_immutable_field_replaces_the_resource() -> None:
    bar, foo = bundle.changes(fixture("cli/plan-update-recreate.json"))
    assert bar == Change("jobs.bar", "update", "jobs.bar", detail=("description",))
    assert foo == Change(
        "pipelines.foo",
        "replace",
        "pipelines.foo",
        destructive=True,
        detail=("replaced: storage (immutable)",),
    )


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


def test_a_plan_that_isnt_the_direct_engines_is_refused() -> None:
    with pytest.raises(LelyError, match="the Terraform engine isn't supported"):
        bundle.changes({"resources": {}})


def test_reads_host_and_resources_from_validate() -> None:
    config = fixture("cli/validate-default-python.json")
    assert bundle.host(config) == HOST
    assert set(bundle.resources(config)) == {
        "jobs.sample_job",
        "pipelines.project_name_etl",
    }


def test_what_a_deployed_bundle_gives_from_the_clis_own_recordings() -> None:
    config = fixture("cli/validate-default-python.json")
    summary = fixture("cli/summary-default-python.json")
    given, later = bundle.gives(config, summary, frozenset())
    outputs: Any = given
    assert later == ()
    assert outputs["target"] == "dev"
    assert outputs["name"] == "project_name"
    assert outputs["var.catalog"] == "hive_metastore"
    assert outputs["workspace.host"] == HOST
    assert outputs["workspace.current_user"]["short_name"] == "jane"
    assert outputs["resources.jobs.sample_job.name"] == "[dev jane] sample_job"
    assert outputs["resources.jobs.sample_job.id"] == "662311427418745"
    assert outputs["resources.jobs.sample_job.url"].endswith("/jobs/662311427418745")


def test_the_id_of_what_this_deploy_creates_or_replaces_comes_later() -> None:
    config = fixture("cli/validate-default-python.json")
    summary = fixture("cli/summary-default-python.json")
    outputs, later = bundle.gives(config, config, frozenset())  # nothing deployed
    assert "resources.jobs.sample_job.id" not in outputs
    assert later == (
        "resources.jobs.sample_job.id",
        "resources.jobs.sample_job.url",
        "resources.pipelines.project_name_etl.id",
        "resources.pipelines.project_name_etl.url",
    )
    # deployed, but replaced by this deploy: the id it has isn't the id it will have
    outputs, later = bundle.gives(config, summary, frozenset({"jobs.sample_job"}))
    assert "resources.jobs.sample_job.id" in later
    assert "resources.pipelines.project_name_etl.id" in outputs


# -- as a step -------------------------------------------------------------------


def ctx(
    tmp_path: Path, fake: FakeDatabricks | None = None, **options: Any
) -> Context[Bundle.Options]:
    write_bundle(tmp_path, project.BUNDLE)
    given: dict[str, Any] = {"vars": VARS, **options}
    return context(
        Bundle.Options(**given),
        name="app",
        root=tmp_path,
        databricks=fake or project.databricks(tmp_path),
    )


def test_plans_one_change_per_resource_and_the_upload(tmp_path: Path) -> None:
    fake = project.databricks(tmp_path)
    plan = check_plan(Bundle(), ctx(tmp_path, fake))
    assert plan.changes == (
        Change("jobs.bar", "create", "jobs.bar"),
        Change("pipelines.foo", "create", "pipelines.foo"),
        UPLOAD,
    )
    # the same vars go to every call
    assert fake.calls == [
        ["bundle", verb, "--target", "dev", "--var=model_version=14", "--output", "json"]
        for verb in ("validate", "plan", "summary")
    ]
    assert isinstance(plan.payload, dict)
    assert plan.payload["plan_version"] == 2  # the CLI's own plan, whole


def test_the_plan_gives_what_is_known_and_names_what_comes_later(
    tmp_path: Path,
) -> None:
    plan = check_plan(Bundle(), ctx(tmp_path))
    assert plan.outputs["var.model_version"] == "14"
    assert plan.outputs["resources.jobs.bar.description"] == "model 14"
    assert plan.outputs["resources.jobs.backfill.id"] == "771"  # deployed already
    assert plan.later == (
        "resources.jobs.bar.id",
        "resources.jobs.bar.url",
        "resources.pipelines.foo.id",
        "resources.pipelines.foo.url",
    )


def test_a_bundle_step_is_never_nothing_to_do(tmp_path: Path) -> None:
    """R5a: a deploy uploads the bundle's files even when no resource changes
    (assumes V5: `bundle plan` speaks only of resources)."""
    step = ctx(tmp_path)
    Bundle().apply(step, Bundle().plan(step))
    again = Bundle().plan(step)
    assert again.changes == (UPLOAD,)
    assert not again.empty


def test_a_bundle_in_another_directory(tmp_path: Path) -> None:
    fake = project.databricks(tmp_path)
    write_bundle(tmp_path / "apps" / "api", {**project.BUNDLE, "name": "api"})
    step = context(
        Bundle.Options(path="apps/api", vars=VARS), root=tmp_path, databricks=fake
    )
    assert Bundle().plan(step).outputs["name"] == "api"


def test_a_variable_that_would_hold_a_secret_is_refused(tmp_path: Path) -> None:
    with pytest.raises(LelyError, match="`token` would hold a secret"):
        Bundle().plan(ctx(tmp_path, vars={"token": Secret("t0k")}))
    with pytest.raises(LelyError, match="single values only"):
        Bundle().plan(ctx(tmp_path, vars={"tags": ["a", "b"]}))


def test_a_bundle_for_another_workspace_is_refused(tmp_path: Path) -> None:
    """One run talks to one workspace. lely checks the bundle's host itself
    rather than wait for the CLI to (V4)."""
    write_bundle(tmp_path, {**project.BUNDLE, "host": "https://other.example.com"})
    step = context(
        Bundle.Options(vars=VARS), root=tmp_path, databricks=project.databricks(tmp_path)
    )
    with pytest.raises(LelyError) as caught:
        Bundle().plan(step)
    assert "deploys to https://other.example.com" in str(caught.value)
    assert f"this run talks to {HOST}" in str(caught.value)


def test_a_failing_cli_is_shown_in_its_own_words(tmp_path: Path) -> None:
    step = ctx(tmp_path, vars={})  # model_version has no default
    with pytest.raises(
        LelyError, match="(?s)`databricks bundle validate` failed.*model_version"
    ):
        Bundle().plan(step)


# -- apply ------------------------------------------------------------------------


def test_apply_deploys_the_plan_it_is_handed(tmp_path: Path) -> None:
    fake = project.databricks(tmp_path)
    step = ctx(tmp_path, fake)
    plan = Bundle().plan(step)
    fake.clear_calls()
    outputs: Any = Bundle().apply(step, plan)
    deploy_call, summary_call = fake.calls
    assert deploy_call[:3] == ["bundle", "deploy", "--plan"]
    assert deploy_call[4:] == [
        "--auto-approve",
        "--target",
        "dev",
        "--var=model_version=14",
    ]
    assert summary_call[:2] == ["bundle", "summary"]
    assert set(fake.deployed()) == {"jobs.backfill", "jobs.bar", "pipelines.foo"}
    # what only exists after the deploy is given now
    assert outputs["resources.jobs.bar.id"] == fake.deployed()["jobs.bar"]["id"]
    assert outputs["resources.jobs.bar.url"].startswith(f"{HOST}/jobs/")


def test_apply_converges(tmp_path: Path) -> None:
    check_apply(Bundle(), ctx(tmp_path))


def test_a_second_run_deploys_again_and_only_uploads(tmp_path: Path) -> None:
    """R6a: a run that finishes an earlier one finds no resource left to change
    and deploys anyway (assumes V6: `deploy --plan` with nothing to change still
    uploads the files and succeeds)."""
    fake = project.databricks(tmp_path)
    step = ctx(tmp_path, fake)
    Bundle().apply(step, Bundle().plan(step))
    before = fake.deployed()
    Bundle().apply(step, Bundle().plan(step))
    assert fake.deployed() == before
    assert fake.uploads() == 3  # the one before the scenario, and these two


def test_a_plan_the_state_has_moved_on_from_is_refused_in_the_clis_words(
    tmp_path: Path,
) -> None:
    """R6b: the CLI checks its own part — `lineage` and `serial`."""
    step = ctx(tmp_path)
    stale = Bundle().plan(step)
    Bundle().apply(step, Bundle().plan(step))  # someone else deploys in between
    with pytest.raises(Refused) as caught:
        Bundle().apply(step, stale)
    assert "plan is stale: the state has been modified since the plan was created" in str(
        caught.value
    )


def test_a_deploy_that_fails_is_a_failure_not_a_refusal(tmp_path: Path) -> None:
    fake = project.databricks(tmp_path)
    step = ctx(tmp_path, fake)
    plan = Bundle().plan(step)
    (fake.world / "fail-deploy").write_text("PERMISSION_DENIED: can't create jobs")
    with pytest.raises(LelyError) as caught:
        Bundle().apply(step, plan)
    assert not isinstance(caught.value, Refused)
    assert "`databricks bundle deploy` failed" in str(caught.value)
    assert "PERMISSION_DENIED" in str(caught.value)


# -- overview ----------------------------------------------------------------------


def test_the_overview_lists_every_resource_with_its_id_and_link(tmp_path: Path) -> None:
    """Assumes V3: the summary has an id and a url for every resource type."""
    fake = project.databricks(tmp_path)
    step = ctx(tmp_path, fake)
    Bundle().apply(step, Bundle().plan(step))
    fake.clear_calls()
    overview = check_overview(Bundle(), step)
    assert isinstance(overview, Overview)
    assert fake.verbs == ["summary"]  # from `bundle summary`, and nothing else
    ids = {key: record["id"] for key, record in fake.deployed().items()}
    assert overview.items == (
        Item("job", "jobs.backfill", "backfill", True, "771", f"{HOST}/jobs/771"),
        Item(
            "job",
            "jobs.bar",
            "job bar",
            True,
            ids["jobs.bar"],
            f"{HOST}/jobs/{ids['jobs.bar']}",
        ),
        Item(
            "pipeline",
            "pipelines.foo",
            "pipeline foo",
            True,
            ids["pipelines.foo"],
            f"{HOST}/pipelines/{ids['pipelines.foo']}",
        ),
    )
    assert overview.notes == (
        "as seen by jane@example.com under "
        "/Workspace/Users/jane@example.com/.bundle/shop/dev",
    )


def test_before_a_first_deploy_it_shows_what_would_exist(tmp_path: Path) -> None:
    """R9a, and R9b's words for "nothing there"."""
    fake = FakeDatabricks(project.world(tmp_path, deployed=False))
    overview = Bundle().overview(ctx(tmp_path, fake))
    assert [(i.key, i.deployed, i.id) for i in overview.items] == [
        ("jobs.backfill", False, None),
        ("jobs.bar", False, None),
        ("pipelines.foo", False, None),
    ]
    assert overview.notes == (
        "not deployed, as far as jane@example.com can see under "
        "/Workspace/Users/jane@example.com/.bundle/shop/dev",
    )


def test_what_another_identity_deployed_looks_not_deployed_from_here(
    tmp_path: Path,
) -> None:
    """R9b (assumes V7: a deployment is recorded under the bundle's root path,
    which can hold the deploying user's name)."""
    write_bundle(tmp_path, {**project.BUNDLE, "profiles": {"ci": "ci@example.com"}})
    world = project.world(tmp_path)
    step = context(
        Bundle.Options(vars=VARS),
        root=tmp_path,
        databricks=FakeDatabricks(world, profile="ci"),
    )
    overview = Bundle().overview(step)
    assert not any(item.deployed for item in overview.items)
    assert overview.notes == (
        "not deployed, as far as ci@example.com can see under "
        "/Workspace/Users/ci@example.com/.bundle/shop/dev",
    )
    assert Bundle().plan_destroy(step).changes == ()


# -- destroy -----------------------------------------------------------------------


def test_a_destroy_plan_lists_what_the_summary_shows_as_deployed(
    tmp_path: Path,
) -> None:
    """R11 (assumes V1: `bundle destroy` removes what the summary lists)."""
    plan = Bundle().plan_destroy(ctx(tmp_path))
    assert plan.changes == (
        Change(
            "jobs.backfill",
            "delete",
            "jobs.backfill",
            destructive=True,
            detail=("backfill · id 771",),
        ),
    )
    assert plan.notes == (
        "the bundle's uploaded files go with them",
        "and whatever else `bundle destroy` removes",
        "as seen by jane@example.com under "
        "/Workspace/Users/jane@example.com/.bundle/shop/dev",
    )


def test_nothing_deployed_is_an_empty_destroy_plan_that_says_so(tmp_path: Path) -> None:
    fake = FakeDatabricks(project.world(tmp_path, deployed=False))
    plan = Bundle().plan_destroy(ctx(tmp_path, fake))
    assert plan == StepPlan(
        notes=(
            "not deployed, as far as jane@example.com can see under "
            "/Workspace/Users/jane@example.com/.bundle/shop/dev",
        )
    )


def test_destroy_runs_bundle_destroy_and_nothing_else(tmp_path: Path) -> None:
    """R12 (assumes V2: `--auto-approve` answers when nobody can)."""
    fake = project.databricks(tmp_path)
    step = ctx(tmp_path, fake)
    plan = Bundle().plan_destroy(step)
    fake.clear_calls()
    Bundle().destroy(step, plan)
    assert fake.calls == [
        [
            "bundle",
            "destroy",
            "--auto-approve",
            "--target",
            "dev",
            "--var=model_version=14",
        ]
    ]
    assert fake.deployed() == {}


def test_destroy_undoes_apply(tmp_path: Path) -> None:
    fake = FakeDatabricks(project.world(tmp_path, deployed=False))
    removal = check_destroy(Bundle(), ctx(tmp_path, fake))
    assert [c.key for c in removal.changes] == [
        "jobs.backfill",
        "jobs.bar",
        "pipelines.foo",
    ]


def test_only_its_own(tmp_path: Path) -> None:
    """A look-alike the bundle didn't deploy — the same job, under another
    bundle's path — is not listed, and is still there after apply and destroy."""
    fake = project.databricks(tmp_path)
    theirs = {"jobs.bar": {"id": "9", "config": {"name": "job bar"}}}
    deploy(fake.world, theirs, name="other")
    step = ctx(tmp_path, fake)
    Bundle().apply(step, Bundle().plan(step))
    assert "9" not in [item.id for item in Bundle().overview(step).items]
    Bundle().destroy(step, Bundle().plan_destroy(step))
    assert fake.deployed(name="other") == theirs
    assert fake.deployed() == {}


def test_a_failing_destroy_is_shown(tmp_path: Path) -> None:
    fake = project.databricks(tmp_path)
    step = ctx(tmp_path, fake)
    (fake.world / "fail-destroy").write_text("lock held by ci@example.com")
    with pytest.raises(LelyError, match="(?s)`databricks bundle destroy` failed.*lock"):
        Bundle().destroy(step, StepPlan())


# -- for the steps that name a bundle step -----------------------------------------


def test_the_resources_of_a_linked_bundle_step() -> None:
    linked = Linked(
        "app",
        "bundle",
        Bundle.Options(),
        outputs={
            "resources.jobs.backfill.id": "771",
            "resources.jobs.backfill.name": "b",
        },
        later=("resources.jobs.bar.id", "resources.jobs.bar.url"),
    )
    assert bundle.resource_keys(linked) == {"jobs.backfill", "jobs.bar"}


def test_the_plan_file_keeps_the_payload_without_a_secret(tmp_path: Path) -> None:
    plan = Bundle().plan(ctx(tmp_path))
    assert json.dumps(plan.payload)  # plain JSON, as the CLI wrote it


# -- found in review ---------------------------------------------------------------


def test_a_variable_with_a_comma_is_quoted_the_way_the_cli_reads_it(
    tmp_path: Path,
) -> None:
    """V8, unverified: `--var` is a list flag that reads its value as CSV. A
    value with a comma would be cut in two — and `14,catalog=prod` from a step
    above would set a second variable nobody wrote."""
    fake = project.databricks(tmp_path)
    plan = Bundle().plan(ctx(tmp_path, fake, vars={"model_version": "14,catalog=prod"}))
    assert '--var="model_version=14,catalog=prod"' in fake.calls[0]
    assert plan.outputs["var.model_version"] == "14,catalog=prod"
    assert plan.outputs["var.catalog"] == "dev"  # not overridden through the back door
    fake.clear_calls()
    quoted = ctx(tmp_path, fake, vars={"model_version": 'say "hi"'})
    assert Bundle().plan(quoted).outputs["var.model_version"] == 'say "hi"'
    # the plain case stays as it was
    assert bundle._csv("model_version=14") == "model_version=14"


def test_the_fake_cuts_an_unquoted_comma_like_the_cli_would(tmp_path: Path) -> None:
    write_bundle(tmp_path, project.BUNDLE)
    fake = project.databricks(tmp_path)
    done = fake.run(
        ["bundle", "validate", "--target", "dev", "--var=model_version=1,2"], tmp_path
    )
    assert done.returncode == 1
    assert "unexpected flag value for variable assignment: 2" in done.stderr


def test_a_bundle_path_that_isnt_there_says_so(tmp_path: Path) -> None:
    """Not "the Databricks CLI isn't installed", which is what a missing
    working directory looks like to the process that can't start."""
    with pytest.raises(LelyError) as caught:
        Bundle().plan(ctx(tmp_path, path="bundel"))
    assert str(caught.value) == (
        f"`path: bundel`: there is no directory {tmp_path / 'bundel'}"
    )

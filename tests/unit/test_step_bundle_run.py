"""`bundle.run`: a run of a bundle resource, planned as a `run`."""

import pytest

from fakes import bundle_config
from sluis.errors import SluisError
from sluis.model import Change
from sluis.steps.bundle_run import BundleRun
from sluis.testing import check_plan, context

CONFIG = bundle_config(resources={"jobs": {"backfill": {"name": "backfill"}}})


def test_plans_one_run() -> None:
    ctx = context(
        BundleRun.Options(resource="jobs.backfill", args=("--full",)), bundle=CONFIG
    )
    assert check_plan(BundleRun(), ctx).changes == (
        Change(
            "resources.jobs.backfill",
            "run",
            "runs jobs.backfill",
            detail=("with --full",),
        ),
    )


def test_a_resource_the_bundle_doesnt_have_is_an_error() -> None:
    ctx = context(
        BundleRun.Options(resource="jobs.backfil"), bundle=CONFIG, target="prod"
    )
    with pytest.raises(
        SluisError, match=r"`jobs.backfil` isn't a resource .* \(it has: jobs.backfill\)"
    ):
        BundleRun().plan(ctx)

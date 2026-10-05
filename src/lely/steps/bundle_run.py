"""`bundle.run`: run a bundle resource at its place in the order.

    - name: backfill
      uses: bundle.run
      with: {bundle: app, resource: jobs.backfill}

A job, a pipeline or an app, via `databricks bundle run <key>`. This is how a
step goes *between* things without a DAG — create the tables, then run the
backfill that fills them — and how an app's code ships, which plain
`bundle deploy` doesn't do.

The bundle step is always named, even when a project has only one: what a step
depends on is read in its options. It stands above this one, because the
resource has to be deployed before it can run.

A run isn't a difference between two states, so its plan is always one `run`
change, and it runs on every apply; `apply --from` gets past one. It deploys
nothing, so it has nothing to destroy and nothing to list, and it gives
nothing: what a run produced is not an output yet.

Docs: https://docs.databricks.com/aws/en/dev-tools/cli/bundle-commands
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lely.errors import LelyError
from lely.model import Change, Json, Linked, Outputs, StepPlan
from lely.process import failure
from lely.step import Context
from lely.steps.bundle import Bundle, open_bundle, resource_keys


class BundleRun:
    """Runs a job, pipeline or app from a bundle step."""

    @dataclass(frozen=True, slots=True)
    class Options:
        #: The bundle step the resource belongs to, by name.
        bundle: Linked
        #: The resource, as `<type>.<key>`: `jobs.backfill`, `apps.api`.
        resource: str
        #: Passed after `--`, to the job or pipeline.
        args: tuple[str, ...] = ()

    @staticmethod
    def programs(written: Mapping[str, Json]) -> tuple[str, ...]:
        return ("databricks",)

    def plan(self, ctx: Context[BundleRun.Options]) -> StepPlan:
        linked = _its_bundle(ctx)
        resource = ctx.options.resource
        declared = resource_keys(linked)
        if resource not in declared:
            known = ", ".join(sorted(declared)) or "none"
            raise LelyError(
                f"`{resource}` isn't a resource of bundle step `{linked.name}` for "
                f"target `{ctx.target}` (it has: {known})."
            )
        detail = (f"with {' '.join(ctx.options.args)}",) if ctx.options.args else ()
        return StepPlan(
            changes=(
                Change(
                    key=resource,
                    action="run",
                    summary=f"runs {resource}",
                    detail=detail,
                ),
            )
        )

    def apply(self, ctx: Context[BundleRun.Options], plan: StepPlan) -> Outputs:
        """`databricks bundle run <key>`, waiting for it to finish.

        TODO(verify): that a failed run exits non-zero, and that arguments after
        `--` reach the job or pipeline — both from the CLI's docs, not seen live.
        """
        linked = _its_bundle(ctx)
        options = linked.options
        assert isinstance(options, Bundle.Options)
        bundle = open_bundle(ctx.databricks, ctx.root, ctx.target, options)
        tail = ("--", *ctx.options.args) if ctx.options.args else ()
        ctx.log.info(f"{ctx.name}: bundle run {ctx.options.resource}")
        result = bundle.run("run", ctx.options.resource, tail=tail)
        if result.returncode != 0:
            raise failure(f"`databricks bundle run {ctx.options.resource}`", result)
        return {}


def _its_bundle(ctx: Context[BundleRun.Options]) -> Linked:
    linked = ctx.options.bundle
    if not isinstance(linked.options, Bundle.Options):
        raise LelyError(
            f"`bundle: {linked.name}` must name a bundle step; step `{linked.name}` "
            f"uses `{linked.uses}`."
        )
    return linked

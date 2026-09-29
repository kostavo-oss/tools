"""`bundle.run`: run a bundle resource at its place in the order.

A job, a pipeline or an app, via `databricks bundle run <key>`. This is how a
post step goes *between* things without a DAG — create the tables, then run
the backfill that fills them — and how an app's code ships, which plain
`bundle deploy` doesn't do.

A run isn't a difference between two states, so its plan is always one `run`
change, and it runs on every apply. `apply --from` resumes past one.
"""

from __future__ import annotations

from dataclasses import dataclass

from sluis import bundle
from sluis.errors import SluisError
from sluis.model import Change, Outputs, StepPlan
from sluis.step import Context


class BundleRun:
    """Run a job, pipeline or app from the bundle."""

    @dataclass(frozen=True, slots=True)
    class Options:
        #: The resource, as `<type>.<key>`: `jobs.backfill`, `apps.api`.
        resource: str
        #: Passed after `--`, to the job or pipeline.
        args: tuple[str, ...] = ()

    def plan(self, ctx: Context[BundleRun.Options]) -> StepPlan:
        resource = ctx.options.resource
        declared = bundle.resource_keys(ctx.bundle)
        if resource not in declared:
            known = ", ".join(sorted(declared)) or "none"
            raise SluisError(
                f"`{resource}` isn't a resource of this bundle for target "
                f"`{ctx.target}` (it has: {known})."
            )
        detail = (f"with {' '.join(ctx.options.args)}",) if ctx.options.args else ()
        return StepPlan(
            changes=(
                Change(
                    key=f"resources.{resource}",
                    action="run",
                    summary=f"runs {resource}",
                    detail=detail,
                ),
            )
        )

    def apply(self, ctx: Context[BundleRun.Options], plan: StepPlan) -> Outputs:
        raise NotImplementedError("apply is milestone 2")

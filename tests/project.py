"""A small project, written to disk: `sluis.yml`, a step in the repo, fakes.

The scenario every planner, renderer and CLI test shares: a pre step looks up
a model version and feeds it to the bundle; deltaplan plans the tables; a
command needs the id of a job this deploy creates; a backfill runs last.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fakes import FIXTURES, FakeDatabricks, bundle_config, fixture

FAKE_DELTAPLAN = Path(__file__).parent / "fake_deltaplan.py"
FAKE_DATABRICKS = Path(__file__).parent / "fake_databricks.py"

STEPS_PY = '''\
from __future__ import annotations

from dataclasses import dataclass

from sluis.model import StepPlan


class LatestModel:
    """Looks up the version a serving endpoint should get. Changes nothing."""

    @dataclass(frozen=True, slots=True)
    class Options:
        model: str
        alias: str = "candidate"

    def plan(self, ctx):
        assert ctx.options.model == "dev.ml.churn", ctx.options
        return StepPlan(outputs={"version": 14})

    def apply(self, ctx, plan):
        return {"version": 14}
'''


def sluis_yml(deltaplan_fixture: str = "deltaplan-create.json") -> str:
    executable = json.dumps(
        [sys.executable, str(FAKE_DELTAPLAN), str(FIXTURES / deltaplan_fixture)]
    )
    return f"""\
pre:
  - name: model
    uses: ./ops/steps.py:LatestModel
    with:
      model: ${{var.catalog}}.ml.churn

bundle_vars:
  model_version: ${{steps.model.version}}

post:
  - name: tables
    uses: deltaplan
    with:
      executable: {executable}
  - name: notify
    uses: command
    with:
      apply: [./notify.sh, "${{resources.jobs.bar.id}}"]
  - name: backfill
    uses: bundle.run
    with: {{resource: jobs.backfill}}
  - name: warm
    uses: command
    targets: [prod]
    with: {{apply: [./warm.sh]}}
"""


CONFIG = bundle_config(
    name="shop",
    variables={"catalog": "dev", "model_version": None},
    resources={
        "jobs": {"bar": {"name": "job bar"}, "backfill": {"name": "backfill"}},
        "pipelines": {"foo": {"name": "pipeline foo"}},
    },
)
SUMMARY = {
    **CONFIG,
    "resources": {
        "jobs": {
            "backfill": {"name": "backfill", "id": "771", "url": "https://x/jobs/771"}
        }
    },
}


def write(root: Path, text: str | None = None) -> Path:
    (root / "ops").mkdir(exist_ok=True)
    (root / "ops" / "steps.py").write_text(STEPS_PY)
    path = root / "sluis.yml"
    path.write_text(text if text is not None else sluis_yml())
    return path


def databricks() -> FakeDatabricks:
    return FakeDatabricks(
        config=CONFIG,
        plan_document=fixture("cli/plan-create.json"),
        summary_document=SUMMARY,
    )


def answers(root: Path) -> Path:
    """Recordings for `fake_databricks.py`: the same answers, as files."""
    folder = root / "answers"
    folder.mkdir()
    (folder / "validate.json").write_text(json.dumps(CONFIG))
    (folder / "plan.json").write_text(json.dumps(fixture("cli/plan-create.json")))
    (folder / "summary.json").write_text(json.dumps(SUMMARY))
    return folder

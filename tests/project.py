"""A small project, written to disk: the config, a plugin in the repo, a bundle.

The scenario every planner, runner, renderer and CLI test shares, top to
bottom: `model` looks up a model version and feeds it to the bundle; `app` is
the bundle, which creates a job and a pipeline beside a job that is deployed
already; `notify` needs the id of the job this deploy creates; `backfill` runs
the job that was there; `warm` is for another target.
"""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

from fakes import HOST, USER, FakeDatabricks, deploy, write_bundle
from lely.model import Source, Workspace

FAKE_STEVIN = Path(__file__).parent / "fake_stevin.py"
FAKE_DATABRICKS = Path(__file__).parent / "fake_databricks.py"

WORKSPACE = Workspace(HOST, USER)
SOURCE = Source()

STEPS_PY = '''\
from __future__ import annotations

from dataclasses import dataclass

from lely.model import Output, StepPlan


class LatestModel:
    """Looks up the version a serving endpoint should get. Changes nothing."""

    @dataclass(frozen=True, slots=True)
    class Options:
        model: str
        alias: str = "candidate"

    outputs = (Output("version"),)

    def plan(self, ctx):
        assert ctx.options.model == "dev.ml.churn", ctx.options
        return StepPlan(outputs={"version": 14})

    def apply(self, ctx, plan):
        return {"version": 14}
'''

LELY_YML = """\
steps:
  - name: model
    uses: ./ops/steps.py:LatestModel
    with:
      model: dev.ml.churn

  - name: app
    uses: bundle
    with:
      vars:
        model_version: ${steps.model.version}

  - name: notify
    uses: command
    with:
      apply: [./ops/notify.sh, "${steps.app.resources.jobs.bar.id}"]

  - name: backfill
    uses: bundle.run
    with: {bundle: app, resource: jobs.backfill}

  - name: warm
    uses: command
    targets: [prod]
    with: {apply: [./ops/warm.sh]}
"""

#: The same project, as a `pyproject.toml` says it.
PYPROJECT_TOML = """\
[project]
name = "shop"
version = "1.0"

[[tool.lely.steps]]
name = "model"
uses = "./ops/steps.py:LatestModel"
with = { model = "dev.ml.churn" }

[[tool.lely.steps]]
name = "app"
uses = "bundle"
with = { vars = { model_version = "${steps.model.version}" } }

[[tool.lely.steps]]
name = "notify"
uses = "command"

[tool.lely.steps.with]
apply = ["./ops/notify.sh", "${steps.app.resources.jobs.bar.id}"]

[[tool.lely.steps]]
name = "backfill"
uses = "bundle.run"
with = { bundle = "app", resource = "jobs.backfill" }

[[tool.lely.steps]]
name = "warm"
uses = "command"
targets = ["prod"]
with = { apply = ["./ops/warm.sh"] }
"""

BUNDLE: dict[str, Any] = {
    "name": "shop",
    "variables": {"catalog": "dev", "model_version": None},
    "resources": {
        "jobs": {
            "bar": {"name": "job bar", "description": "model ${var.model_version}"},
            "backfill": {"name": "backfill"},
        },
        "pipelines": {"foo": {"name": "pipeline foo", "storage": "dbfs:/my-storage"}},
    },
    "immutable": ["storage"],
}

#: What is in the workspace before the scenario's first deploy.
DEPLOYED = {"jobs.backfill": {"id": "771", "config": {"name": "backfill"}}}

NOTIFY_SH = '#!/bin/sh\necho "$1" >> notified.txt\n'
WARM_SH = "#!/bin/sh\necho warm >> warmed.txt\n"


def write(root: Path, text: str | None = None, *, toml: bool = False) -> Path:
    """The project on disk. Returns its config file."""
    (root / "ops").mkdir(exist_ok=True)
    (root / "ops" / "steps.py").write_text(STEPS_PY)
    for name, script in (("notify.sh", NOTIFY_SH), ("warm.sh", WARM_SH)):
        path = root / "ops" / name
        path.write_text(script)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    write_bundle(root, BUNDLE)
    if toml:
        path = root / "pyproject.toml"
        path.write_text(text if text is not None else PYPROJECT_TOML)
    else:
        path = root / "lely.yml"
        path.write_text(text if text is not None else LELY_YML)
    return path


def world(root: Path, *, deployed: bool = True) -> Path:
    """The simulated workspace for a project at `root`, beside it."""
    folder = root / ".world"
    if not folder.exists():
        folder.mkdir()
        if deployed:
            deploy(folder, DEPLOYED)
    return folder


def databricks(root: Path, **kwargs: Any) -> FakeDatabricks:
    return FakeDatabricks(world(root, **kwargs))

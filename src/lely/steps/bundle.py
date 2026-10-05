"""`bundle`: an Asset Bundle, planned, deployed, listed and destroyed.

    - name: app
      uses: bundle
      with:
        path: .
        vars:
          model_version: ${steps.model.version}

The bundle is the Databricks CLI's. This plugin asks it — `bundle validate`,
`plan`, `summary`, `deploy`, `destroy`, each with the step's `vars` as `--var`
— and never works out itself what the CLI resolves: targets, variables, names,
ids. `-t` is taken as the bundle's own target.

What the CLI prints is someone else's format, so it is read leniently: only
what lely uses is looked at.

Settled from the CLI's source and recorded acceptance tests, commit `e41a5c8`
(https://github.com/databricks/cli/tree/e41a5c87436a5b8fa81ce192e2aac77675d4b4c2,
see `tests/fixtures/cli/README.md`):

- `bundle validate -o json` is the resolved config. A failed validate still
  prints JSON, so the exit code decides.
- `bundle plan -o json` is the direct engine's plan. `--var` is a persistent
  flag of `bundle`, so every verb takes it.
- `bundle summary -o json` is the resolved config plus each deployed
  resource's `id` and `url`.
- `bundle deploy --plan <file>` deploys that plan, and refuses one whose state
  `lineage` or `serial` has moved on (`ValidatePlanAgainstState`).

Not tried on a real workspace — each is marked `TODO(verify)` below with its
number from `spec/004-asset-bundle.md`:

- V1: `bundle destroy` removes what `bundle summary` lists, and the files.
- V2: `--auto-approve` answers for `deploy` and `destroy` when nobody can.
- V3: the summary has an `id` and a `url` for every resource type.
- V4: the CLI refuses a target on another workspace than the credentials reach.
- V5: `bundle plan` speaks only of resources, not of files.
- V6: `deploy --plan` with no resource changes still uploads the files.
- V7: a bundle another identity deployed looks not deployed from here.
- V8 (found in review, not in the spec's list): `--var` is a list flag that
  reads its value as CSV, so a value with a comma needs quoting.

Docs: https://docs.databricks.com/aws/en/dev-tools/cli/bundle-commands
"""

from __future__ import annotations

import csv
import io
import json
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from lely.databricks import CliError, answer
from lely.errors import LelyError, Refused
from lely.model import (
    Action,
    Change,
    Item,
    Json,
    Linked,
    Output,
    Outputs,
    Overview,
    Secret,
    StepPlan,
)
from lely.process import failure
from lely.step import Cli, Context

#: The direct engine's plan format this was written against.
PLAN_VERSION = 2

#: The CLI's per-resource actions, as lely's. `update_id` gives the resource
#: a new id — for whatever refers to it, that is a replacement.
_ACTIONS: dict[str, Action | None] = {
    "skip": None,
    "create": "create",
    "update": "update",
    "resize": "update",
    "update_id": "replace",
    "recreate": "replace",
    "delete": "delete",
}

#: A deploy uploads the bundle's files even when no resource changes, and
#: `bundle plan` speaks only of resources. So every plan carries this line, and
#: a bundle step is never "nothing to do". TODO(verify): V5 and V6.
UPLOAD = Change(key="files", action="run", summary="uploads the bundle's files")

#: What the CLI says when `deploy --plan` is handed a plan the state has moved
#: on from. TODO(verify): read from `bundle/direct/bundle_plan.go`, not seen live.
_STALE = "since the plan was created"


class Bundle:
    """Deploys an Asset Bundle with the Databricks CLI."""

    @dataclass(frozen=True, slots=True)
    class Options:
        #: The directory holding `databricks.yml`, relative to the config.
        path: str = "."
        #: Passed to the bundle as `--var`, on every call. Single values only.
        vars: Mapping[str, str | None] = field(default_factory=dict)

    outputs = (
        Output("target", doc="the bundle target"),
        Output("name", doc="the bundle's name"),
        Output("workspace.<field>", doc="the workspace as the CLI resolves it"),
        Output("var.<name>", doc="every variable, resolved"),
        Output("resources.<type>.<key>.<field>", doc="a resource's own config"),
        Output("resources.<type>.<key>.id", "exists"),
        Output("resources.<type>.<key>.url", "exists"),
    )

    @staticmethod
    def programs(written: Mapping[str, Json]) -> tuple[str, ...]:
        return ("databricks",)

    def plan(self, ctx: Context[Bundle.Options]) -> StepPlan:
        bundle = open_bundle(ctx.databricks, ctx.root, ctx.target, ctx.options)
        ctx.log.info(f"{ctx.name}: resolving the bundle")
        config = bundle.answer("validate")
        _same_workspace(config, ctx)
        ctx.log.info(f"{ctx.name}: planning the bundle")
        document = bundle.answer("plan")
        found = changes(document)
        summary = bundle.answer("summary")
        outputs, later = gives(config, summary, _moving(found))
        return StepPlan(
            changes=(*found, UPLOAD), outputs=outputs, later=later, payload=document
        )

    def apply(self, ctx: Context[Bundle.Options], plan: StepPlan) -> Outputs:
        """Deploy the plan that was just made and checked.

        The core plans the step again right before this, so `plan.payload` is
        the CLI's fresh plan, not the one from a plan file — which the CLI would
        refuse as stale the moment anything had been deployed.
        """
        bundle = open_bundle(ctx.databricks, ctx.root, ctx.target, ctx.options)
        with tempfile.TemporaryDirectory(prefix="lely-bundle-") as scratch:
            path = Path(scratch) / "plan.json"
            path.write_text(json.dumps(plan.payload), encoding="utf-8")
            ctx.log.info(f"{ctx.name}: bundle deploy")
            # TODO(verify): V2 — that `--auto-approve` is what answers the CLI's
            # own questions. lely has asked already, and checked for destructive
            # changes.
            result = bundle.run("deploy", "--plan", str(path), "--auto-approve")
        if result.returncode != 0:
            said = result.stderr.strip() or result.stdout.strip()
            if _STALE in said:
                raise Refused(
                    f"The Databricks CLI refused the plan for step `{ctx.name}`:\n{said}"
                )
            raise CliError(str(failure("`databricks bundle deploy`", result)))
        summary = bundle.answer("summary")
        outputs, _ = gives(summary, summary, frozenset())
        return outputs

    def overview(self, ctx: Context[Bundle.Options]) -> Overview:
        """Every resource the bundle declares for this target, from
        `bundle summary` and nothing else: nothing is remembered."""
        bundle = open_bundle(ctx.databricks, ctx.root, ctx.target, ctx.options)
        summary = bundle.answer("summary")
        items = _items(summary)
        if any(item.deployed for item in items):
            return Overview(items, (f"as seen by {_view(summary)}",))
        return Overview(items, (_not_deployed(summary),))

    def plan_destroy(self, ctx: Context[Bundle.Options]) -> StepPlan:
        """Every resource lely can see the bundle has deployed — the same list
        as the overview. TODO(verify): V1 — whether `bundle destroy` removes
        more than the summary lists; until then the plan says so."""
        bundle = open_bundle(ctx.databricks, ctx.root, ctx.target, ctx.options)
        summary = bundle.answer("summary")
        _same_workspace(summary, ctx)
        deployed = [item for item in _items(summary) if item.deployed]
        if not deployed:
            return StepPlan(notes=(_not_deployed(summary),))
        return StepPlan(
            changes=tuple(
                Change(
                    key=item.key,
                    action="delete",
                    summary=item.key,
                    detail=(f"{item.name} · id {item.id}",),
                )
                for item in deployed
            ),
            notes=(
                "the bundle's uploaded files go with them",
                "and whatever else `bundle destroy` removes",
                f"as seen by {_view(summary)}",
            ),
        )

    def destroy(self, ctx: Context[Bundle.Options], plan: StepPlan) -> None:
        """`bundle destroy` for the target, and nothing else: the CLI knows the
        order, and what it may not delete."""
        bundle = open_bundle(ctx.databricks, ctx.root, ctx.target, ctx.options)
        ctx.log.info(f"{ctx.name}: bundle destroy")
        # TODO(verify): V2 — `--auto-approve`, as for deploy.
        result = bundle.run("destroy", "--auto-approve")
        if result.returncode != 0:
            raise CliError(str(failure("`databricks bundle destroy`", result)))


# -- asking the CLI -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OpenBundle:
    """One bundle for one target: where it is, and the `--var`s it is given."""

    cli: Cli
    cwd: Path
    target: str
    variables: tuple[tuple[str, str], ...]

    def args(self, verb: str, *extra: str, tail: tuple[str, ...] = ()) -> list[str]:
        args = ["bundle", verb, *extra, "--target", self.target]
        args += [f"--var={_csv(f'{name}={value}')}" for name, value in self.variables]
        return args + list(tail)

    def answer(self, verb: str) -> dict[str, Json]:
        return answer(self.cli, self.args(verb), self.cwd)

    def run(
        self, verb: str, *extra: str, tail: tuple[str, ...] = ()
    ) -> subprocess.CompletedProcess[str]:
        """`tail` goes last — after a `--`, it is the job's, not the CLI's."""
        return self.cli.run(self.args(verb, *extra, tail=tail), self.cwd)


def open_bundle(cli: Cli, root: Path, target: str, options: Bundle.Options) -> OpenBundle:
    """The bundle a step's options name. `bundle.run` opens its bundle step's
    the same way, so both ask the CLI the same thing."""
    folder = root / options.path
    if not folder.is_dir():
        raise LelyError(f"`path: {options.path}`: there is no directory {folder}")
    return OpenBundle(cli, folder, target, _variables(options.vars))


def _csv(pair: str) -> str:
    """One `name=value` as the CLI's `--var` reads it.

    `--var` is a list flag (`StringSlice` in `cmd/bundle/variables.go`), and
    such a flag reads its value as a line of CSV. Unquoted, a value with a comma
    would be cut in two — and `14,catalog=prod` from a step above would set a
    second variable nobody wrote. TODO(verify): V8 — from the CLI's source, not
    seen live: `databricks bundle validate --var='a=1,b=2' -o json`.
    """
    if "," not in pair and '"' not in pair:
        return pair
    line = io.StringIO()
    csv.writer(line, lineterminator="").writerow([pair])
    return line.getvalue()


def _variables(given: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    """A step's `vars` as `--var` pairs. The options have made them text
    already, and refused a secret, a list or a mapping where they were written;
    this holds when a plugin's options are built by hand, too."""
    variables: list[tuple[str, str]] = []
    for name, value in given.items():
        if isinstance(value, Secret):
            raise LelyError(
                f"bundle variable `{name}` would hold a secret, which the bundle's "
                "deployed config would then show"
            )
        if isinstance(value, dict | list | tuple):
            # TODO(verify): whether `.databricks/bundle/<target>/variable-overrides.json`
            # is the supported route for complex variables; `--var` can't carry one.
            raise LelyError(
                f"bundle variable `{name}` would be a {type(value).__name__}; lely "
                "passes single values only"
            )
        if isinstance(value, bool):
            text = "true" if value else "false"
        else:
            text = "" if value is None else str(value)
        if any(char in f"{name}{text}" for char in "\n\r"):
            # the CLI's CSV reader and Python's don't agree on a line break
            # inside a quoted field (V8), so lely doesn't send one
            raise LelyError(
                f"bundle variable `{name}` holds a line break, which `--var` can't "
                "carry reliably"
            )
        variables.append((name, text))
    return tuple(variables)


def _same_workspace(config: Mapping[str, Json], ctx: Context[Bundle.Options]) -> None:
    """One run talks to one workspace. TODO(verify): V4 — the CLI is expected to
    refuse this itself; lely doesn't wait to find out."""
    bundles = host(config)
    if bundles is None or not ctx.host:
        return
    if bundles.rstrip("/").lower() != ctx.host.rstrip("/").lower():
        raise LelyError(
            f"The bundle's target `{ctx.target}` deploys to {bundles}, and this run "
            f"talks to {ctx.host}. One run talks to one workspace: choose the "
            "profile or the environment for the bundle's."
        )


# -- reading its answers: pure ----------------------------------------------------


def host(config: Mapping[str, Json]) -> str | None:
    """The workspace the target deploys to."""
    value = _section(config, "workspace").get("host")
    return value if isinstance(value, str) else None


def resources(config: Mapping[str, Json]) -> dict[str, dict[str, Json]]:
    """Every resource in a resolved config or a summary, by `<type>.<key>`."""
    found: dict[str, dict[str, Json]] = {}
    for kind, entries in _section(config, "resources").items():
        if not isinstance(entries, dict):
            continue
        for key, entry in entries.items():
            found[f"{kind}.{key}"] = entry if isinstance(entry, dict) else {}
    return found


def changes(document: Mapping[str, Json]) -> tuple[Change, ...]:
    """The plan's resources that change, as lely changes, keyed `<type>.<key>`.

    An action this doesn't know (a newer CLI's) is kept and marked destructive:
    lely would rather ask than wave through what it can't read.
    """
    version = document.get("plan_version")
    if version is None:
        raise LelyError(
            "The Databricks CLI wrote no direct-engine plan. lely needs the direct "
            "engine: a bundle on the Terraform engine isn't supported. Check "
            "`lely doctor` for the CLI's version."
        )
    if version != PLAN_VERSION:
        raise LelyError(
            f"The Databricks CLI wrote a plan of version {version}; lely reads "
            f"version {PLAN_VERSION}. Check `lely doctor` for a supported CLI."
        )
    plan = document.get("plan")
    if not isinstance(plan, dict):
        return ()
    result: list[Change] = []
    for name in sorted(plan):
        entry = plan[name]
        if not isinstance(entry, dict):
            continue
        raw = str(entry.get("action", ""))
        key = name.removeprefix("resources.")
        if raw not in _ACTIONS:
            result.append(
                Change(
                    key=key,
                    action="update",
                    summary=key,
                    destructive=True,
                    detail=(f"the CLI plans `{raw}`, which lely doesn't know",),
                )
            )
            continue
        action = _ACTIONS[raw]
        if action is None:
            continue
        result.append(Change(key=key, action=action, summary=key, detail=_fields(entry)))
    return tuple(result)


def gives(
    config: Mapping[str, Json], summary: Mapping[str, Json], moving: frozenset[str]
) -> tuple[dict[str, Json], tuple[str, ...]]:
    """A bundle step's outputs, and the ones that exist only after the deploy.

    `moving` are the resources this deploy creates or replaces: whatever id one
    has now, it isn't the id it will have.
    """
    outputs: dict[str, Json] = {}
    later: list[str] = []
    bundle = _section(config, "bundle")
    outputs["target"] = bundle.get("target")
    outputs["name"] = bundle.get("name")
    for name, value in _section(config, "workspace").items():
        outputs[f"workspace.{name}"] = value
    for name, entry in _section(config, "variables").items():
        if isinstance(entry, dict) and "value" in entry:
            outputs[f"var.{name}"] = entry["value"]
    deployed = resources(summary)
    for key, entry in resources(config).items():
        for name, value in entry.items():
            if name not in ("id", "url"):
                outputs[f"resources.{key}.{name}"] = value
        live = deployed.get(key, {})
        for name in ("id", "url"):
            # TODO(verify): V3 — that every resource type has both in the summary.
            if key not in moving and live.get(name) is not None:
                outputs[f"resources.{key}.{name}"] = live[name]
            else:
                later.append(f"resources.{key}.{name}")
    return outputs, tuple(later)


def resource_keys(linked: Linked) -> frozenset[str]:
    """The resources of a bundle step another step names, as `<type>.<key>`:
    each has an `id`, known or still to come."""
    return frozenset(
        ".".join(parts[1:3])
        for name in (*linked.outputs, *linked.later)
        if (parts := name.split("."))[0] == "resources"
        and len(parts) == 4
        and parts[3] == "id"
    )


def _moving(found: tuple[Change, ...]) -> frozenset[str]:
    return frozenset(c.key for c in found if c.action in ("create", "replace"))


def _items(summary: Mapping[str, Json]) -> tuple[Item, ...]:
    items = []
    for key, entry in sorted(resources(summary).items()):
        kind = key.split(".")[0].removesuffix("s").replace("_", " ")
        name = entry.get("name") or entry.get("display_name") or key.split(".", 1)[1]
        identifier, url = entry.get("id"), entry.get("url")
        items.append(
            Item(
                kind=kind,
                key=key,
                name=str(name),
                deployed=identifier is not None,
                id=None if identifier is None else str(identifier),
                url=url if isinstance(url, str) else None,
            )
        )
    return tuple(items)


def _view(summary: Mapping[str, Json]) -> str:
    """Whose view a summary is. What a bundle deployed is recorded under its own
    root path, which can depend on who deploys. TODO(verify): V7."""
    workspace = _section(summary, "workspace")
    user = workspace.get("current_user")
    identity = user.get("userName") if isinstance(user, dict) else None
    return f"{identity or 'this identity'} under {workspace.get('root_path') or '?'}"


def _not_deployed(summary: Mapping[str, Json]) -> str:
    identity, _, path = _view(summary).partition(" under ")
    return f"not deployed, as far as {identity} can see under {path}"


def _fields(entry: Mapping[str, Json]) -> tuple[str, ...]:
    """Which fields change, and which of them force a replacement."""
    fields = entry.get("changes")
    if not isinstance(fields, dict):
        return ()
    causes: list[str] = []
    others: list[str] = []
    for field_name in sorted(fields):
        change = fields[field_name]
        if not isinstance(change, dict) or change.get("action") in (None, "skip"):
            continue
        if change.get("action") in ("recreate", "update_id"):
            reason = change.get("reason")
            causes.append(f"{field_name} ({reason})" if reason else field_name)
        else:
            others.append(field_name)
    lines = [f"replaced: {', '.join(causes)}"] if causes else []
    return tuple(lines + others)


def _section(config: Mapping[str, Json], key: str) -> Mapping[str, Json]:
    section = config.get(key)
    return section if isinstance(section, dict) else {}

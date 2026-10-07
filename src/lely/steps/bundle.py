"""`bundle`: an Asset Bundle, planned, deployed, listed and destroyed.

    - name: app
      uses: bundle
      with:
        path: .
        vars:
          model_version: ${steps.model.version}

The bundle is the Databricks CLI's. This plugin asks it — `bundle summary`,
`plan`, `deploy`, `destroy`, each with the step's `vars` as `--var` — and never
works out itself what the CLI resolves: targets, variables, names, ids. `-t` is
taken as the bundle's own target.

What the CLI prints is someone else's format, so it is read leniently: only
what lely uses is looked at.

**Run on a real workspace on 2026-10-06** — CLI v1.19.0, one job, a target in
development mode, a personal access token from the environment. What that
settled, by its number in `spec/004-asset-bundle.md`:

- `bundle summary -o json` is the resolved config — the same keys as
  `bundle validate -o json` — plus each deployed resource's `id` and `url`,
  and `modified_status: created` for one that isn't deployed yet.
- **`bundle validate` is not read-only**: it creates the bundle's `files`
  folder in the workspace. So planning doesn't call it; `summary` and `plan`
  create nothing, and fail on a config error in the same words.
- `bundle plan -o json` is the direct engine's plan (`plan_version: 2`), and
  holds `lineage` and `serial` once something is deployed. On the Terraform
  engine (`DATABRICKS_BUNDLE_ENGINE=terraform`) it has no `plan_version`.
- V1: `bundle destroy` removed the job and the bundle's folder with it.
- V2: without `--auto-approve` and nobody to ask, `bundle destroy` refuses
  and names the flag. `deploy --plan … --auto-approve` runs unasked.
- V5: `bundle plan` speaks only of resources, not of files.
- V6: `deploy --plan` with nothing to change succeeds and uploads the files.
- V8: `--var` reads its value as a line of CSV. `--var=a=1,b=2` set both; a
  pair in CSV quotes arrives whole.
- `deploy --plan` with a plan the state has moved on from fails with "plan
  serial 1 does not match state serial 2; the state has been modified since
  the plan was created."

**And what it corrected — V4.** The CLI does *not* refuse a bundle whose target
names another host than the credentials are for: with a token from the
environment it goes to the bundle's host and presents the token there. lely
compares the hosts itself and stops the run, but only after that first call.

Still not tried, each marked `TODO(verify)` below:

- V3: the summary has an `id` and a `url` for every resource type — seen for
  a job; pipelines in the CLI's own recordings.
- V7: a bundle another identity deployed looks not deployed from here.
- Whether `deploy` without `--auto-approve` asks before a delete.

From the CLI's source, commit `e41a5c8`: `--var` is a persistent flag of
`bundle`, so every verb takes it; `ValidatePlanAgainstState` checks `lineage`
and `serial`.

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
from html import escape
from pathlib import Path
from typing import Any

from lely.databricks import CliError, answer, heard
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
from lely.process import Said, failure, wrote
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
#: `bundle plan` speaks only of resources (V5, V6: both seen on a workspace).
#: So every plan carries this line, and a bundle step is never "nothing to do".
UPLOAD = Change(key="files", action="run", summary="uploads the bundle's files")

#: What the summary says of a resource's deployment, not of its config.
_DEPLOYED = frozenset({"id", "url", "modified_status"})

#: What the CLI says when `deploy --plan` is handed a plan the state has moved
#: on from — part of it, as CLI v1.19.0 said it on a workspace.
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
        # `summary`, not `validate`: the same resolved config, with what is
        # deployed — and unlike `validate` it creates nothing in the workspace
        summary = bundle.answer("summary")
        _same_workspace(summary, ctx)
        ctx.log.info(f"{ctx.name}: planning the bundle")
        document = bundle.answer("plan")
        found = changes(document)
        # For a destroy or a status the id a resource has now is the one that
        # counts, whatever the next deploy would do to it: a step below takes
        # down what it made for the pipeline that is there.
        moving = _moving(found) if ctx.purpose == "apply" else frozenset()
        outputs, later = gives(summary, moving)
        return StepPlan(
            changes=(*found, UPLOAD),
            outputs=outputs,
            later=later,
            payload=document,
            view=picture(_items(summary), found),
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
            # `--auto-approve` answers the CLI's own questions (V2): lely has
            # asked already, and checked for destructive changes.
            # TODO(verify): whether the CLI would ask, without it, before a delete.
            result = bundle.run(
                "deploy", "--plan", str(path), "--auto-approve", said=passing_on(ctx)
            )
        if result.returncode != 0:
            said = wrote(result)
            if _STALE in said:
                raise Refused(
                    f"The Databricks CLI refused the plan for step `{ctx.name}`:\n{said}"
                )
            raise CliError(str(failure("`databricks bundle deploy`", result)))
        summary = bundle.answer("summary")
        outputs, _ = gives(summary, frozenset())
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
        as the overview. `bundle destroy` removed exactly that and the
        bundle's folder when it was tried with one job (V1); whether it can
        remove more than the summary lists is not known, so the plan says so."""
        bundle = open_bundle(ctx.databricks, ctx.root, ctx.target, ctx.options)
        summary = bundle.answer("summary")
        _same_workspace(summary, ctx)
        items = _items(summary)
        deployed = [item for item in items if item.deployed]
        if not deployed:
            return StepPlan(notes=(_not_deployed(summary),))
        removed = tuple(
            Change(
                key=item.key,
                action="delete",
                summary=item.key,
                detail=(f"{item.name} · id {item.id}",),
            )
            for item in deployed
        )
        return StepPlan(
            changes=removed,
            notes=(
                "the bundle's uploaded files go with them",
                "and whatever else `bundle destroy` removes",
                f"as seen by {_view(summary)}",
            ),
            view=picture(items, removed),
        )

    def destroy(self, ctx: Context[Bundle.Options], plan: StepPlan) -> None:
        """`bundle destroy` for the target, and nothing else: the CLI knows the
        order, and what it may not delete."""
        bundle = open_bundle(ctx.databricks, ctx.root, ctx.target, ctx.options)
        ctx.log.info(f"{ctx.name}: bundle destroy")
        # Without `--auto-approve` and nobody to ask, the CLI refuses (V2). lely
        # has asked: the target's name typed, or `--yes` in the command.
        result = bundle.run("destroy", "--auto-approve", said=passing_on(ctx))
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
        self, verb: str, *extra: str, said: Said, tail: tuple[str, ...] = ()
    ) -> subprocess.CompletedProcess[str]:
        """A verb that changes the workspace: what the CLI writes meanwhile is
        passed to `said`, and kept. `tail` goes last — after a `--`, it is the
        job's, not the CLI's."""
        return heard(self.cli, self.args(verb, *extra, tail=tail), self.cwd, said)


def passing_on(ctx: Context[Any]) -> Said:
    """What the CLI writes while a step deploys, destroys or runs, to the
    step's log: a line at a time, under the step's name."""
    return lambda line: ctx.log.info(f"{ctx.name}: {line}")


def open_bundle(cli: Cli, root: Path, target: str, options: Bundle.Options) -> OpenBundle:
    """The bundle a step's options name. `bundle.run` opens its bundle step's
    the same way, so both ask the CLI the same thing."""
    folder = root / options.path
    if not folder.is_dir():
        raise LelyError(f"`path: {options.path}`: there is no directory {folder}")
    return OpenBundle(cli, folder, target, _variables(options.vars))


def _csv(pair: str) -> str:
    """One `name=value` as the CLI's `--var` reads it.

    `--var` is a list flag, and such a flag reads its value as a line of CSV
    (V8, seen on CLI v1.19.0: `--var=a=1,b=2` set both variables). Unquoted, a
    value with a comma would be cut in two — and `14,catalog=prod` from a step
    above would set a second variable nobody wrote.
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
    """One run talks to one workspace.

    The CLI doesn't hold a bundle to that (V4, seen on v1.19.0): with a token
    from the environment it goes to the host the bundle's target names. So
    lely compares the two — after the CLI's first call, which is the earliest
    it can know the bundle's host without reading `databricks.yml` itself.
    """
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
    summary: Mapping[str, Json], moving: frozenset[str]
) -> tuple[dict[str, Json], tuple[str, ...]]:
    """A bundle step's outputs, and the ones that exist only after the deploy.

    `summary` is `bundle summary -o json`: the resolved config, with the `id`
    and `url` of what is deployed. `moving` are the resources this deploy
    creates or replaces: whatever id one has now, it isn't the id it will have.
    """
    outputs: dict[str, Json] = {}
    later: list[str] = []
    bundle = _section(summary, "bundle")
    outputs["target"] = bundle.get("target")
    outputs["name"] = bundle.get("name")
    for name, value in _section(summary, "workspace").items():
        outputs[f"workspace.{name}"] = value
    for name, entry in _section(summary, "variables").items():
        if isinstance(entry, dict) and "value" in entry:
            outputs[f"var.{name}"] = entry["value"]
    for key, entry in resources(summary).items():
        if entry.get("modified_status") == "deleted":
            continue  # deployed, and no longer declared: this deploy removes it
        for name, value in entry.items():
            if name not in _DEPLOYED:
                outputs[f"resources.{key}.{name}"] = value
        for name in ("id", "url"):
            # TODO(verify): V3 — that every resource type has both in the summary.
            if key not in moving and entry.get(name) is not None:
                outputs[f"resources.{key}.{name}"] = entry[name]
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


def picture(items: tuple[Item, ...], found: tuple[Change, ...]) -> str | None:
    """The bundle as the page shows it (`StepPlan.view`): every resource it
    declares, by type, with what this plan does to each — the ones it leaves
    alone too, which no list of changes names.

    Keys, names and ids, and nothing of a resource's config: that can hold
    whatever the bundle holds, and a page is passed around.
    """
    happening = {change.key: change for change in found}
    by_type: dict[str, list[str]] = {}
    for item in items:
        change = happening.get(item.key)
        word = change.action if change is not None else "unchanged"
        said = word
        if change is not None and change.destructive:
            said += ' <strong class="destructive">destructive</strong>'
        now = (item.id or "") if item.deployed else "not deployed"
        by_type.setdefault(item.key.split(".")[0], []).append(
            f'<tr><td class="key">{escape(item.key)}</td><td>{escape(item.name)}</td>'
            f'<td class="{word}">{said}</td><td class="dim">{escape(now)}</td></tr>'
        )
    if not by_type:
        return None
    head = "<tr><th>resource</th><th>name</th><th>this plan</th><th>now</th></tr>"
    return "".join(
        f"<h4>{escape(kind)} <small>({len(rows)})</small></h4>"
        f"<table>{head}{''.join(rows)}</table>"
        for kind, rows in sorted(by_type.items())
    )


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

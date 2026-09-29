"""From `sluis.yml` to a plan: every step, and the bundle, in order.

`check` is what `validate` runs: every step found, every option read, every
reference allowed where it stands — with no workspace. `plan` does the rest:

1. `bundle validate`, with a placeholder for each variable `bundle_vars` sets
   — the pre steps plan before those are known, and may not read them.
2. Each pre step, in order; each one's outputs are there for the next.
3. `bundle_vars`, resolved from those outputs, then `bundle validate` again
   and `bundle plan` with them. If one is decided at apply, so is the bundle.
4. `bundle summary`, for the ids of what is deployed already.
5. Each post step. A reference to something this deploy creates is unknown,
   and a step with one in its options is planned as deferred.

Nothing changes anywhere. The steps and the CLI are the only I/O here.
"""

from __future__ import annotations

import functools
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from sluis import __version__, bundle, options, planfile, registry
from sluis.config import Config, ConfigError, Item, Map, Scalar, Seq, StepConfig
from sluis.databricks import Databricks
from sluis.errors import SluisError
from sluis.model import BundlePlan, Json, Outputs, Plan, PlannedStep, Secret, StepPlan
from sluis.refs import Position, RefError, Scope, Unknown, parse, resolve
from sluis.refs import check as check_ref
from sluis.step import Context, Log

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient

#: What a variable `bundle_vars` sets is, while the pre steps plan. Nothing
#: reads it: `check` refuses a pre step that names such a variable.
PENDING = "sluis-pending"


def check(config: Config) -> None:
    """Everything that can be known about `config` without a workspace."""
    problems: list[str] = []
    fed = _fed(config)
    names = [step.name for step in config.steps]
    for index, step in enumerate(config.steps):
        position = Position(
            where=f"step `{step.name}`",
            phase=step.phase,
            earlier=tuple(names[:index]),
            later=tuple(names[index:]),
            fed=fed,
            this=step.name,
        )
        try:
            found = registry.find(step.uses, config.root)
        except SluisError as error:
            problems.append(f"{step.loc}: {error}")
            continue
        try:
            options.build(
                found.options,
                step.options,
                _offline(position),
                _where(step),
            )
        except SluisError as error:  # located already
            problems.append(str(error))
    if config.bundle_vars is not None:
        position = Position(
            where="bundle_vars",
            phase="bundle",
            earlier=tuple(s.name for s in config.pre),
            later=tuple(s.name for s in config.post),
            fed=fed,
        )
        resolver = _offline(position)
        for entry in config.bundle_vars.entries:
            if isinstance(entry.value, Scalar) and isinstance(entry.value.value, str):
                try:
                    resolver(entry.value)
                except SluisError as error:
                    problems.append(str(error))
    if problems:
        raise ConfigError(problems)


def plan(
    config: Config,
    *,
    target: str | None,
    databricks: Databricks,
    env: Mapping[str, str],
    log: Log,
    connect: Callable[[str | None], WorkspaceClient],
) -> Plan:
    """Plan `config` for `target` (the bundle's default when `None`).

    `connect` makes a workspace client for a host; a step that asks for one
    gets it for the bundle's workspace, made once, on first use.
    """
    check(config)
    fed = _fed(config)
    log.info("resolving the bundle")
    first = databricks.validate(target, {name: PENDING for name in sorted(fed)})
    chosen = bundle.target(first)
    host = bundle.host(first)
    run = _Run(
        config, chosen, databricks, env, log, functools.cache(lambda: connect(host))
    )

    pending = {name: f"var.{name} is set from the pre steps at apply" for name in fed}
    pre = tuple(
        run.step(step, Scope(first, env=env, pending=pending, **run.so_far()))
        for step in config.pre
        if step.runs_for(chosen)
    )

    variables, unknown = run.bundle_vars(Scope(first, env=env, **run.so_far()))
    if unknown:
        deploy = BundlePlan(
            variables=tuple(variables.items()),
            deferred="its variables are decided at apply: "
            + "; ".join(f"{name} ({why})" for name, why in unknown.items()),
        )
        resolved, created = first, bundle.resource_keys(first)
    else:
        resolved = databricks.validate(chosen, variables) if fed else first
        log.info("planning the bundle")
        document = databricks.plan(chosen, variables)
        changes = bundle.changes(document)
        deploy = BundlePlan(changes, tuple(variables.items()), document)
        created = bundle.created(changes)

    post_steps = [step for step in config.post if step.runs_for(chosen)]
    deployed = databricks.summary(chosen) if post_steps else None
    post = tuple(
        run.step(
            step,
            Scope(
                resolved,
                deployed=deployed,
                created=created,
                env=env,
                pending={name: f"var.{name} is decided at apply" for name in unknown},
                **run.so_far(),
            ),
        )
        for step in post_steps
    )
    return Plan(
        tool_version=__version__,
        target=chosen,
        bundle=bundle.name(first),
        config_hash=config.digest,
        pre=pre,
        deploy=deploy,
        post=post,
    )


@dataclass
class _Run:
    config: Config
    target: str
    databricks: Databricks
    env: Mapping[str, str]
    log: Log
    connect: Callable[[], WorkspaceClient]
    outputs: dict[str, Outputs] = field(default_factory=dict)
    deferred: dict[str, str] = field(default_factory=dict)

    def so_far(self) -> dict[str, Any]:
        return {
            "outputs": MappingProxyType(dict(self.outputs)),
            "deferred": MappingProxyType(dict(self.deferred)),
        }

    def step(self, step: StepConfig, scope: Scope) -> PlannedStep:
        where = _where(step)
        found = registry.find(step.uses, self.config.root)
        built = options.build(
            found.options,
            step.options,
            lambda scalar: resolve(str(scalar.value), scope, scalar.loc),
            where,
        )
        if isinstance(built, options.Unresolved):
            self.log.info(f"{step.name}: decided at apply")
            step_plan = StepPlan(deferred="; ".join(dict.fromkeys(built.reasons)))
        else:
            self.log.info(f"planning {step.name}")
            step_plan = self._call(found.cls, step, built, scope, where)
        self.outputs[step.name] = step_plan.outputs
        if step_plan.deferred is not None:
            self.deferred[step.name] = step_plan.deferred
        return PlannedStep(
            name=step.name,
            uses=step.uses,
            phase=step.phase,
            options_hash=_options_hash(step.options, scope),
            plan=step_plan,
        )

    def _call(
        self, cls: type, step: StepConfig, built: Any, scope: Scope, where: str
    ) -> StepPlan:
        ctx = Context(
            target=self.target,
            phase=step.phase,
            name=step.name,
            options=built,
            bundle=scope.config,
            deployed=scope.deployed,
            outputs=scope.outputs,
            root=self.config.root,
            bundle_root=self.config.bundle_dir,
            env=self.env,
            databricks=self.databricks,
            log=self.log,
            connect=self.connect,
        )
        try:
            result = cls().plan(ctx)
        except SluisError as error:
            raise SluisError(f"{where}: {error}") from error
        except NotImplementedError:
            raise
        except Exception as error:
            raise SluisError(
                f"{where} failed to plan: {type(error).__name__}: {error}"
            ) from error
        if not isinstance(result, StepPlan):
            raise SluisError(
                f"{where}: `plan` returned {type(result).__name__}, not a StepPlan"
            )
        keys = [change.key for change in result.changes]
        if len(set(keys)) != len(keys):
            raise SluisError(f"{where}: two changes share a key; each must be unique")
        planfile.step_plan_to_json(result, where)  # refuses secrets in the payload
        return result

    def bundle_vars(self, scope: Scope) -> tuple[dict[str, str], dict[str, str]]:
        """The variables for the bundle, and the ones decided at apply (why)."""
        variables: dict[str, str] = {}
        unknown: dict[str, str] = {}
        block = self.config.bundle_vars
        for entry in block.entries if block else ():
            if not isinstance(entry.value, Scalar):
                continue
            raw = entry.value.value
            value = resolve(raw, scope, entry.value.loc) if isinstance(raw, str) else raw
            if isinstance(value, Unknown):
                unknown[entry.key] = value.reason
            elif isinstance(value, Secret):
                raise SluisError(
                    f"{entry.value.loc}: bundle variable `{entry.key}` would hold a "
                    "secret, which the bundle's deployed config would then show"
                )
            elif isinstance(value, dict | list):
                raise SluisError(
                    f"{entry.value.loc}: bundle variable `{entry.key}` would be a "
                    f"{type(value).__name__}; sluis passes single values only"
                )
            else:
                variables[entry.key] = _format(value)
        return variables, unknown


def _where(step: StepConfig) -> str:
    if step.name == step.uses:
        return f"step `{step.name}`"
    return f"step `{step.name}` ({step.uses})"


def _fed(config: Config) -> frozenset[str]:
    block = config.bundle_vars
    return frozenset(entry.key for entry in block.entries) if block else frozenset()


def _offline(position: Position) -> options.Resolver:
    """A resolver for `check`: references are checked for where they stand,
    and answered with `Unknown` — nothing is looked up."""

    def resolver(scalar: Scalar) -> Any:
        text = str(scalar.value)
        refs = parse(text, scalar.loc)
        for ref in refs:
            check_ref(ref, position, scalar.loc)
        return Unknown("offline") if refs else text

    return resolver


def _format(value: Json) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def _options_hash(block: Map | None, scope: Scope) -> str:
    """The step's options as resolved, environment values by name only."""

    def plain(item: Item) -> Json:
        if isinstance(item, Seq):
            return [plain(child) for child in item.items]
        if isinstance(item, Map):
            return {e.key: plain(e.value) for e in item.entries}
        if not isinstance(item.value, str):
            return item.value
        try:
            value = resolve(item.value, scope, item.loc, redact_env=True)
        except RefError:
            return item.value
        if isinstance(value, Unknown):
            return {"$unknown": value.reason}
        if isinstance(value, Secret):
            return "***"
        return value

    text = json.dumps(plain(block) if block else None, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

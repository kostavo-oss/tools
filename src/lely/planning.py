"""From the config to a plan: every step, in the order written.

`check` is what `validate` runs: every plugin found, every option read, every
reference allowed where it stands — with no workspace — and the wiring that
results: per step, what it takes and what it gives.

`plan` does the rest, top to bottom. A step's options are resolved from what
the steps above it give. When all of them are known, its plugin plans it: the
step is *ready*. When one isn't — the id of a job this deploy creates — the
plugin isn't called with half its options: the step is *waiting*, and the plan
names what for.

A `Session` is one walk down the list. `plan` uses it, and so do `apply`,
`destroy` and `status` (`running.py`): each resolves options the same way.

Nothing changes anywhere here. The plugins are the only I/O.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar

from lely import __version__, options, planfile, registry
from lely import step as contract
from lely.config import (
    Config,
    ConfigError,
    Map,
    Node,
    Scalar,
    Seq,
    StepConfig,
    spelled,
    written,
)
from lely.errors import LelyError, Refused
from lely.model import (
    KNOWN,
    Input,
    Linked,
    Output,
    Outputs,
    Overview,
    Plan,
    PlanKind,
    PlannedStep,
    Skip,
    Source,
    StepPlan,
    Workspace,
)
from lely.refs import (
    Above,
    Given,
    Position,
    Scope,
    Unknown,
    check_step,
    lookup,
    match,
    parse,
    resolve,
)
from lely.refs import check as check_ref
from lely.registry import Found
from lely.step import Cli, Context, Log, Purpose

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient

T = TypeVar("T")


# -- offline --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Wire:
    """One step in the wiring: what it takes, from where, and what it gives."""

    name: str
    uses: str
    takes: tuple[tuple[str, str], ...]
    gives: tuple[Output, ...]
    warnings: tuple[str, ...] = ()


def check(config: Config) -> tuple[Wire, ...]:
    """Everything that can be known about `config` without a workspace.

    Raises `ConfigError` with every problem found; otherwise returns the wiring.
    """
    problems: list[str] = []
    wires: list[Wire] = []
    above: dict[str, Above] = {}
    names = [step.name for step in config.steps]
    for index, step in enumerate(config.steps):
        position = Position(
            this=step.name,
            above=dict(above),
            below=tuple(names[index + 1 :]),
            targets=step.targets,
        )
        declared: tuple[Output, ...] | None = None
        takes: list[tuple[str, str]] = []
        warnings: list[str] = []
        try:
            found = registry.find(step.uses, config.root)
            declared = _declared(found, step)
        except LelyError as error:
            problems.append(f"{step.loc}: {error}")
        else:
            try:
                options.build(
                    found.options,
                    step.options,
                    _offline(step, position, takes, warnings),
                    _where(step),
                    _offline_link(step, position, takes),
                )
            except LelyError as error:  # located already
                problems.append(str(error))
        above[step.name] = Above(declared, step.targets)
        wires.append(
            Wire(step.name, step.uses, tuple(takes), declared or (), tuple(warnings))
        )
    if problems:
        raise ConfigError(problems)
    return tuple(wires)


def made_from(step: StepConfig) -> str:
    """A step's plugin, targets and options as written, as one hash.

    References stay as they were written, so a value from the environment
    counts by name and a rotated token isn't a new plan; and the config file's
    format doesn't matter, only what it says.
    """
    said = {"uses": step.uses, "targets": step.targets, "with": spelled(step.options)}
    text = json.dumps(said, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _offline(
    step: StepConfig,
    position: Position,
    takes: list[tuple[str, str]],
    warnings: list[str],
) -> options.Resolver:
    """A resolver for `check`: references are checked for where they stand,
    and answered with `Unknown` — nothing is looked up."""
    labels = _labels(step.options)

    def resolver(scalar: Scalar) -> Any:
        text = str(scalar.value)
        refs = parse(text, scalar.loc)
        secret = False
        for ref in refs:
            output = check_ref(ref, position, scalar.loc)
            if ref.namespace != "steps":
                secret = True
                continue
            source = ".".join(ref.path[1:])
            takes.append((labels.get(id(scalar), ""), source))
            if output is not None and output.known == "run":
                warnings.append(
                    f"step `{step.name}` takes `{source}`, which is known only "
                    f"{KNOWN['run']}: it waits on every deploy, and a plan applied "
                    "from a file always stops before it"
                )
        # A value from the environment is a secret whatever it turns out to
        # be, so where it may not go is known without looking it up.
        return Unknown("offline", secret=secret) if refs else text

    return resolver


def _offline_link(
    step: StepConfig, position: Position, takes: list[tuple[str, str]]
) -> options.Linker:
    labels = _labels(step.options)

    def linker(scalar: Scalar) -> Unknown:
        name = str(scalar.value)
        check_step(name, position, f"{scalar.loc}: `{name}`")
        takes.append((labels.get(id(scalar), ""), name))
        return Unknown("offline")

    return linker


def _labels(block: Map | None) -> dict[int, str]:
    """For each value in a `with:` block, the option it fills: the nearest key.
    An item of a list has none.

    By the node itself, not by where it was written: two values can share a
    position — a YAML alias, or a TOML file whose positions couldn't be found.
    """
    labels: dict[int, str] = {}

    def walk(node: Node, label: str) -> None:
        if isinstance(node, Map):
            for entry in node.entries:
                walk(entry.value, entry.key)
        elif isinstance(node, Seq):
            for child in node.items:
                walk(child, "")
        else:
            labels[id(node)] = label

    if block is not None:
        walk(block, "")
    return labels


def _declared(found: Found, step: StepConfig) -> tuple[Output, ...]:
    said = written(step.options)
    try:
        return contract.declared(found.cls, said if isinstance(said, dict) else {})
    except LelyError:
        raise
    except Exception as error:  # a plugin's `outputs` is its own code
        raise LelyError(
            f"`{step.uses}`: its `outputs` failed: {type(error).__name__}: {error}"
        ) from error


def _where(step: StepConfig) -> str:
    if step.name == step.uses:
        return f"step `{step.name}`"
    return f"step `{step.name}` ({step.uses})"


# -- one walk down the list -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class Prepared:
    """A step with its options resolved — or the outputs it is waiting for."""

    step: StepConfig
    found: Found
    declared: tuple[Output, ...]
    options: Any
    inputs: tuple[Input, ...]
    waits_for: tuple[str, ...]
    #: One of the outputs it waits for is only ever produced by a run.
    every_deploy: bool = False

    @property
    def where(self) -> str:
        return _where(self.step)


@dataclass
class Session:
    """What the steps above give so far, and how the next one is given it."""

    config: Config
    target: str
    workspace: Workspace
    env: Mapping[str, str]
    databricks: Cli
    log: Log
    connect: Callable[[], WorkspaceClient]
    given: dict[str, Given] = field(default_factory=dict)
    resolved: dict[str, Prepared] = field(default_factory=dict)
    #: Outputs another step takes, by step: these are shown in the plan.
    taken: dict[str, set[str]] = field(default_factory=dict)
    #: What the steps are planned for: each is told (`Context.purpose`).
    purpose: Purpose = "apply"

    def prepare(self, step: StepConfig) -> Prepared:
        """Resolve a step's options from what the steps above it give."""
        found = registry.find(step.uses, self.config.root)
        declared = _declared(found, step)
        scope = Scope(self.given, self.env)
        labels = _labels(step.options)
        inputs: list[Input] = []
        from_a_run: list[str] = []

        def resolver(scalar: Scalar) -> Any:
            text = str(scalar.value)
            for ref in parse(text, scalar.loc):
                if ref.namespace != "steps":
                    continue
                value = lookup(ref, scope, scalar.loc)
                label = labels.get(id(scalar), "")
                source = ".".join(ref.path[1:])
                named = match(self.given[ref.step].declared, ref.output)
                if named is not None:
                    self.taken.setdefault(ref.step, set()).add(named.name)
                if isinstance(value, Unknown):
                    if named is not None and named.output.known == "run":
                        from_a_run.append(source)
                    inputs.append(Input(label, source, None, known=False))
                else:
                    inputs.append(Input(label, source, value))
            return resolve(text, scope, scalar.loc)

        def linker(scalar: Scalar) -> Linked | Unknown:
            name = str(scalar.value)
            label = labels.get(id(scalar), "")
            given = self.given.get(name)
            if given is None:
                raise LelyError(
                    f"{scalar.loc}: `{name}`: there is no step `{name}` above"
                )
            above = self.resolved.get(name)
            if not given.planned or above is None:
                inputs.append(Input(label, name, None, known=False))
                return Unknown(name)
            inputs.append(Input(label, name))
            return Linked(
                name, above.step.uses, above.options, given.outputs, tuple(given.later)
            )

        built = options.build(found.options, step.options, resolver, _where(step), linker)
        waits_for: tuple[str, ...] = ()
        if isinstance(built, options.Unresolved):
            waits_for, built = built.waits_for, None
        prepared = Prepared(
            step, found, declared, built, tuple(inputs), waits_for, bool(from_a_run)
        )
        if not waits_for:
            self.resolved[step.name] = prepared
        return prepared

    def unplanned(self, prepared: Prepared) -> None:
        """Record a step that couldn't be planned: nothing it gives is known."""
        self.given[prepared.step.name] = Given(prepared.declared, planned=False)

    def plan(self, prepared: Prepared) -> StepPlan:
        """Ask the plugin for its plan, and hold the answer to the contract."""
        where = prepared.where
        self.log.info(f"planning {prepared.step.name}")
        result = self._call(prepared, "plan", lambda plugin, ctx: plugin.plan(ctx))
        result = _checked_plan(result, where)
        _check_outputs(result.outputs, prepared.declared, where, planning=True)
        if result.waiting is None:
            missing = [
                output.name
                for output in prepared.declared
                if output.known == "plan"
                and not output.shape
                and output.name not in result.outputs
            ]
            if missing:
                raise LelyError(
                    f"{where}: its plugin declares {_names(missing)} as known "
                    f"{KNOWN['plan']}, and its plan gave none"
                )
        for name in result.later:
            named = match(prepared.declared, tuple(name.split(".")))
            if named is None or named.rest or named.output.known == "plan":
                raise LelyError(
                    f"{where}: its plan names `{name}` as coming later, which its "
                    f"plugin doesn't declare as known {KNOWN['exists']} or "
                    f"{KNOWN['run']}"
                )
        self.given[prepared.step.name] = Given(
            prepared.declared, result.outputs, frozenset(result.later)
        )
        return result

    def apply(self, prepared: Prepared, plan: StepPlan) -> Outputs:
        """Have the plugin do what `plan` says, and take what it gives."""
        where = prepared.where
        self.log.info(f"applying {prepared.step.name}")
        returned = self._call(
            prepared, "apply", lambda plugin, ctx: plugin.apply(ctx, plan)
        )
        if returned is None:
            returned = {}
        if not isinstance(returned, Mapping):
            raise LelyError(
                f"{where}: `apply` returned {type(returned).__name__}, not its outputs"
            )
        _check_outputs(returned, prepared.declared, where, planning=False)
        returned = planfile.normalised_outputs(returned, f"{where}: `apply`")
        outputs = {**plan.outputs, **returned}
        missing = [
            output.name
            for output in prepared.declared
            if output.known == "run" and not output.shape and output.name not in outputs
        ]
        if missing:
            raise LelyError(
                f"{where}: its plugin declares {_names(missing)} as known "
                f"{KNOWN['run']}, and `apply` gave none"
            )
        self.given[prepared.step.name] = Given(prepared.declared, outputs, applied=True)
        return outputs

    def plan_destroy(self, prepared: Prepared) -> StepPlan | Skip:
        """What taking the step down would remove — or why there is nothing to."""
        where = prepared.where
        if not contract.destroys(prepared.found.cls):
            return Skip(f"`{prepared.step.uses}` has nothing to destroy")
        result = self._call(
            prepared, "plan its destroy", lambda plugin, ctx: plugin.plan_destroy(ctx)
        )
        if isinstance(result, Skip):
            return result
        result = _checked_plan(result, where, method="plan_destroy")
        # everything in a destroy is destructive, whatever the plugin marked
        return dataclasses.replace(
            result,
            changes=tuple(
                dataclasses.replace(change, destructive=True) for change in result.changes
            ),
            outputs={},
            later=(),
        )

    def destroy(self, prepared: Prepared, plan: StepPlan) -> None:
        self.log.info(f"destroying {prepared.step.name}")
        self._call(prepared, "destroy", lambda plugin, ctx: plugin.destroy(ctx, plan))

    def overview(self, prepared: Prepared) -> Overview | Skip:
        """What exists because of the step, as its plugin can show it."""
        where = prepared.where
        if not contract.lists(prepared.found.cls):
            return Skip(getattr(prepared.found.cls, "nothing_to_list", "nothing to list"))
        result = self._call(prepared, "list", lambda plugin, ctx: plugin.overview(ctx))
        if isinstance(result, Skip):
            return result
        if not isinstance(result, Overview):
            raise LelyError(
                f"{where}: `overview` returned {type(result).__name__}, not an Overview"
            )
        for item in result.items:
            named = (item.kind, item.key, item.name)
            if not all(isinstance(part, str) and part for part in named):
                raise LelyError(
                    f"{where}: an overview line needs a kind, a key and a name: {item}"
                )
            if not all(isinstance(part, str | None) for part in (item.id, item.url)):
                raise LelyError(
                    f"{where}: an overview line's id and url are text or nothing: {item}"
                )
            if not isinstance(item.deployed, bool):
                raise LelyError(
                    f"{where}: an overview line's `deployed` is true or false: {item}"
                )
        if not all(isinstance(note, str) for note in result.notes):
            raise LelyError(f"{where}: an overview's notes are text")
        return result

    def shown(self, step: PlannedStep) -> PlannedStep:
        """A planned step as the plan keeps it: with the outputs it has by name
        and the ones another step takes — not every field of every resource."""
        prepared = self.resolved.get(step.name)
        if prepared is None:
            return step
        taken = self.taken.get(step.name, set())
        plain = {output.name for output in prepared.declared if not output.shape}
        outputs = {
            name: value
            for name, value in step.plan.outputs.items()
            if name in plain or name in taken
        }
        return dataclasses.replace(
            step, plan=dataclasses.replace(step.plan, outputs=outputs, later=())
        )

    def _context(self, prepared: Prepared) -> Context[Any]:
        return Context(
            target=self.target,
            name=prepared.step.name,
            options=prepared.options,
            root=self.config.root,
            host=self.workspace.host,
            env=self.env,
            databricks=self.databricks,
            log=self.log,
            connect=self.connect,
            purpose=self.purpose,
        )

    def _call(
        self, prepared: Prepared, verb: str, call: Callable[[Any, Context[Any]], T]
    ) -> T:
        where = prepared.where
        try:
            with contract.quietly():
                return call(prepared.found.cls(), self._context(prepared))
        except Refused as error:
            raise Refused(f"{where}: {error}") from error
        except LelyError as error:
            raise LelyError(f"{where}: {error}") from error
        except Exception as error:
            raise LelyError(
                f"{where} failed to {verb}: {type(error).__name__}: {error}"
            ) from error


def _checked_plan(result: object, where: str, method: str = "plan") -> StepPlan:
    """A plugin's plan, held to its shape and made plain: as it would read back
    from a plan file, so the plan that is approved and the plan that is made
    again can be compared whether or not a file came between them."""
    if not isinstance(result, StepPlan):
        raise LelyError(
            f"{where}: `{method}` returned {type(result).__name__}, not a StepPlan"
        )
    keys = [change.key for change in result.changes]
    if len(set(keys)) != len(keys):
        raise LelyError(f"{where}: two changes share a key; each must be unique")
    for change in result.changes:
        lines = (change.key, change.summary, *change.detail)
        if not all(isinstance(line, str) for line in lines):
            raise LelyError(
                f"{where}: a change's key, summary and detail are text: {change}"
            )
    if not all(isinstance(line, str) for line in (*result.notes, *result.later)):
        raise LelyError(f"{where}: a plan's `notes` and `later` are text")
    if result.waiting is not None and not isinstance(result.waiting, str):
        raise LelyError(f"{where}: a plan's `waiting` is text")
    if result.view is not None and len(result.view) > planfile.VIEW_LIMIT:
        raise LelyError(
            f"{where}: its view is {len(result.view)} characters, and a plan keeps "
            f"at most {planfile.VIEW_LIMIT}: a view is a picture of the plan, not a "
            "copy of the data"
        )
    return planfile.normalised(result, where)  # refuses a secret in the payload


def _check_outputs(
    outputs: Outputs, declared: tuple[Output, ...], where: str, *, planning: bool
) -> None:
    """Outputs are as declared: nothing a plugin gives goes unnamed."""
    for name in outputs:
        named = match(declared, tuple(name.split(".")))
        if named is None or named.rest:
            listed = ", ".join(output.name for output in declared) or "none"
            raise LelyError(
                f"{where} gave an output `{name}` its plugin doesn't declare "
                f"(declared: {listed}). A plugin lists what it gives: "
                f'`outputs = (Output("{name}"),)`.'
            )
        if planning and named.output.known == "run":
            raise LelyError(
                f"{where}: its plugin declares `{name}` as known {KNOWN['run']}, "
                "and its plan gave it"
            )


def _names(names: list[str]) -> str:
    return ", ".join(f"`{name}`" for name in names)


# -- the plan -------------------------------------------------------------------


def plan(
    config: Config,
    *,
    target: str,
    workspace: Workspace,
    source: Source,
    env: Mapping[str, str],
    databricks: Cli,
    log: Log,
    connect: Callable[[], WorkspaceClient],
    kind: PlanKind = "apply",
) -> Plan:
    """Plan `config` for `target`: to apply it, or to destroy it.

    A destroy is planned from the top down as well: each step is planned as
    usual, for what it gives the steps below, and then asked what taking it
    down would remove. The plan keeps the order written; a destroy runs it
    from the bottom up.
    """
    check(config)
    runs_for(config, target)
    session = Session(
        config, target, workspace, env, databricks, log, connect, purpose=kind
    )
    steps: list[PlannedStep] = []
    for step in config.steps:
        if not step.runs_for(target):
            steps.append(_skipped(step, f"not for target `{target}`"))
            continue
        prepared = session.prepare(step)
        if kind == "apply":
            steps.append(_plan_step(session, prepared))
        else:
            steps.append(_plan_destroy_step(session, prepared))
    return Plan(
        tool_version=__version__,
        kind=kind,
        target=target,
        workspace=workspace,
        source=source,
        steps=tuple(session.shown(step) for step in steps),
    )


def runs_for(config: Config, target: str) -> None:
    """Refuse a target no step runs for. lely keeps no list of targets, so a
    mistyped one is otherwise caught only by a plugin that checks it — and when
    every step's `targets` leave it out, no plugin is asked."""
    if any(step.runs_for(target) for step in config.steps):
        return
    named = sorted({name for step in config.steps for name in step.targets or ()})
    raise Refused(
        f"No step runs for target `{target}`: every step's `targets` leave it out "
        f"({', '.join(named) or 'they name no target at all'})."
    )


def _skipped(step: StepConfig, why: str) -> PlannedStep:
    return PlannedStep(step.name, step.uses, made_from(step), skipped=why)


def _plan_step(session: Session, prepared: Prepared) -> PlannedStep:
    step = prepared.step
    if prepared.waits_for:
        session.log.info(f"{step.name}: waiting for {', '.join(prepared.waits_for)}")
        session.unplanned(prepared)
        return PlannedStep(
            step.name,
            step.uses,
            made_from(step),
            inputs=prepared.inputs,
            waits_for=prepared.waits_for,
            every_deploy=prepared.every_deploy,
        )
    return PlannedStep(
        step.name,
        step.uses,
        made_from(step),
        plan=session.plan(prepared),
        inputs=prepared.inputs,
    )


def _plan_destroy_step(session: Session, prepared: Prepared) -> PlannedStep:
    step = prepared.step
    if prepared.waits_for:
        session.unplanned(prepared)
        return dataclasses.replace(
            _skipped(step, missing(prepared.waits_for)), inputs=prepared.inputs
        )
    session.plan(prepared)
    result = session.plan_destroy(prepared)
    if isinstance(result, Skip):
        return dataclasses.replace(_skipped(step, result.reason), inputs=prepared.inputs)
    return PlannedStep(
        step.name, step.uses, made_from(step), plan=result, inputs=prepared.inputs
    )


def missing(waits_for: tuple[str, ...]) -> str:
    """Why a step that takes something that isn't there can't be taken down or
    listed: lely can't know what it made."""
    verb = "isn't" if len(waits_for) == 1 else "aren't"
    return f"it needs {', '.join(waits_for)}, which {verb} there"

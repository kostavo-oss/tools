"""The verbs, for a program that runs stevin as part of something larger.

Each one is what a command does, minus the arguments and the printing:

```python
project  = stevin.Project.find()
resolved = project.resolve(project.target("prod"))
conn     = stevin.Connection.from_target(resolved)

plan = stevin.plan(project, resolved, conn)
if not plan.empty and not plan.is_destructive:
    run = stevin.apply(plan, conn, project=project, target=resolved)
```

The plan comes back as the same frozen `Plan` the CLI renders, so a host can
summarise it, save it, send it somewhere else and apply it there. Everything
here raises `StevinError` and nothing else on purpose.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from fnmatch import fnmatch

from stevin.adopt import Adoption
from stevin.connect import Connection
from stevin.executor import ExecutionResult, Executor, Status
from stevin.history import DeltaHistory, HistoryStore, NoHistory
from stevin.loader import Diagnostic, Project, Specs, Target, shared_names
from stevin.manage import EVERYTHING, Manage
from stevin.model.plan import Plan, Step
from stevin.model.view import Relation
from stevin.model.volume import Volume
from stevin.planning import PlanningError, cycles, plan_tables
from stevin.probes import Result


def plan(
    project: Project,
    target: Target,
    connection: Connection,
    *,
    select: Callable[[str], bool] | Sequence[str] | str | None = None,
    check_order: bool = False,
    clone: bool = False,
    parallel: int = 8,
    specs: Specs | None = None,
) -> Plan:
    """What stevin would do to make the live objects match the specs.

    `select` narrows it to some of them, the way `--select` does: a name from
    its last part up to all three — `orders`, `sales.orders`,
    `dev.sales.orders` — or a pattern like `sales.*`, one or several, in any
    case. One that matches no spec raises `PlanningError`; a typo is not an
    empty plan. A predicate over full names is taken as it is.
    `check_order` also compares column order; `clone` takes a zero-copy backup
    of every table a risky step is about to touch.

    `specs` is for a caller that has already read them — to lint them first,
    say — so they aren't read twice.

    Raises `SpecErrors` if a spec can't be read, `PlanningError` if the specs
    can't be planned together — two files describing one name, say — and
    `IntrospectionError` if the workspace can't be read.
    """
    specs = specs if specs is not None else project.load_specs(target)
    twice = shared_names(specs.files)
    if twice:
        # Refused here rather than in `plan_tables`, which has no files to name.
        raise PlanningError("\n".join(f"{d.where}: {d.message}" for d in twice))
    chosen = _selector(select, [relation.name for relation in specs.relations])
    return plan_tables(
        specs.relations,
        connection.introspector(project.manage, parallel),
        target=target.name,
        tool_version=package_version(),
        mode_for=lambda schema: project.mode_for(target, schema),
        check_order=check_order,
        clone=clone,
        select=chosen,
        owned_elsewhere=target.owned_by_the_bundle(),
        manage=project.manage,
    )


def drift(
    project: Project,
    target: Target,
    connection: Connection,
    *,
    select: Callable[[str], bool] | Sequence[str] | str | None = None,
    parallel: int = 8,
) -> Plan:
    """The plan that would be made right now — for asking whether anything moved.

    Same work as `plan`; the name is the question. An empty plan means the
    workspace matches the specs. What a host does about a plan that isn't
    empty — fail a build, open a pull request, page someone — is its own
    business.
    """
    return plan(project, target, connection, select=select, parallel=parallel)


def validate(project: Project, target: Target) -> tuple[Diagnostic, ...]:
    """Lint every spec, without a workspace. Raises `SpecErrors` if one can't
    be read; what parses but is wrong comes back as diagnostics — and so does
    what is wrong between specs: two files for one name, objects in a cycle."""
    specs = project.load_specs(target)
    return (*specs.diagnostics, *cycles(specs.files))


def apply(
    plan: Plan,
    connection: Connection,
    *,
    project: Project | None = None,
    target: Target | None = None,
    history: HistoryStore | None = None,
    allow_destructive: bool = False,
    observer: Callable[[Step, Status, str | None], None] | None = None,
) -> ExecutionResult:
    """Run a plan, and record what it did.

    `observer` is told about each step as it resolves — and, while one runs,
    every half minute with status `running` and how long it has been going, so
    a long rewrite is never silence. Ctrl-C while a step runs asks the
    warehouse to cancel the statement before the `KeyboardInterrupt` reaches
    you, and the run is left resumable. From stevin's own runner the interrupt
    is a `stevin.introspect.Interrupted`, which says whether the statement was
    cancelled — it can't be when the interrupt comes before the warehouse has
    answered with the statement's id, and may then still be running.

    The run is written to the project's `history_schema`, unless a host passes
    its own `history` — `MemoryHistory` for a test, its own store otherwise. A
    project with no `history_schema` records nothing and takes no lock; the
    result still says what ran, and `run.restore_points` names the version each
    risky step could be put back to.

    Raises `StalePlan` if the live objects have moved since the plan was made,
    `DestructiveRefused` if it would destroy something and `allow_destructive`
    says nothing, `ExecutionError` for anything else that stops it. A step that
    fails once it is running doesn't raise: the result says which one, so the
    rest of the run is on record.
    """
    store = history if history is not None else history_for(project, target, connection)
    executor = Executor(
        # A step takes as long as it takes; only a read has a budget.
        runner=connection.patient(),
        # The same reading of live state the plan was made with: anything
        # else and the two disagree by what the project handed over.
        introspector=connection.introspector(plan.manage),
        history=store,
        observer=observer or (lambda *_: None),
    )
    return executor.apply(plan, allow_destructive=allow_destructive)


def verify(
    connection: Connection,
    where: str,
    *,
    principal: str = "account users",
    slow: bool = False,
    undrop: bool = True,
    keep: bool = False,
    observer: Callable[[Result], None] | None = None,
) -> tuple[Result, ...]:
    """Settle the Databricks behaviour stevin relies on, in this workspace.

    Unlike everything else here that reads, this one writes: it makes a scratch
    schema, makes tables, views and functions in it, and drops the schema with
    everything in it. `where` is the `catalog.schema` to make — it must not
    already exist — or just a catalog, and stevin names the schema itself.

    Each probe comes back as a `Result`: `held`, `differed` (this workspace does
    something else, and `result.probe.matters` says what that costs), or
    `unknown` (it couldn't be carried out at all). `observer` is called with
    each as it finishes, because a run takes a while.

    `slow` includes the probes that start a Databricks pipeline; `undrop`
    includes the one that needs a second schema which keeps what it drops.
    `keep` leaves the schemas behind to look at.

    Raises `StevinError` if the scratch schema can't be made — a probe that
    fails is a result, not an exception.
    """
    from contextlib import ExitStack

    from stevin import probes

    catalog = where.partition(".")[0]
    results: list[Result] = []
    with ExitStack() as stack:
        schema = stack.enter_context(probes.scratch(connection.runner, where, keep=keep))
        made: list[str] = []

        def recoverable() -> str:
            # Made only if a probe asks: a schema that keeps what it drops holds
            # the metastore's table quota for its whole recovery period.
            if not made:
                made.append(
                    stack.enter_context(
                        probes.scratch(
                            connection.runner, catalog, keeps_dropped=True, keep=keep
                        )
                    )
                )
            return made[0]

        bench = probes.Bench(
            runner=connection.runner,
            introspector=connection.introspector(),
            schema=schema,
            principal=principal,
            recoverable=recoverable if undrop else None,
        )
        for result in probes.run(bench, probes.chosen(slow=slow, keeps_dropped=undrop)):
            if observer is not None:
                observer(result)
            results.append(result)
    return tuple(results)


def adopt(
    project: Project,
    target: Target,
    connection: Connection,
    *,
    select: Callable[[str], bool] | Sequence[str] | str | None = None,
    specs: Specs | None = None,
    parallel: int = 8,
) -> tuple[Adoption, ...]:
    """Rewrite specs to say what is live — drift, back into the files.

    The other direction from `apply`: nothing in the workspace is touched, and
    what comes back is the new text of each spec whose live object has moved,
    with what changed in it. **Nothing is written** — call `adoption.write()`,
    or show the text and let someone decide.

    `select` narrows it to some of the specs, as it does for `plan`; without
    one, every spec the project has is considered, and only the ones that moved
    come back.

    Raises `CannotAdopt` for a spec no file edit can express — a `.sql` spec, or
    a live object of a different kind — `PlanningError` for a selection that
    matches no spec, and `IntrospectionError` if the workspace can't be read.
    """
    from stevin.adopt import adopt as adopt_spec
    from stevin.planning import live_schemas

    specs = specs if specs is not None else project.load_specs(target)
    chosen = _selector(select, [one.table.name for one in specs.files])
    loaded = [one for one in specs.files if chosen is None or chosen(one.table.name)]
    if not loaded:
        return ()
    schemas = live_schemas(
        [one.table for one in loaded], connection.introspector(project.manage, parallel)
    )
    adoptions: list[Adoption] = []
    for one in loaded:
        catalog, schema = one.table.parts[0], one.table.parts[1]
        live = schemas[(catalog, schema)].relation(one.table.name, kind_of(one.table))
        if live is None:
            continue  # nothing live to adopt: that is a create, and `apply` does it
        adoption = adopt_spec(
            one,
            live,
            variables=target.variables_map(),
            unresolved=target.unresolved_map(),
            manage=project.manage,
        )
        # An unchanged file with something still planned is worth handing back:
        # a seed's rows are the file's own, and nobody should have to guess why
        # the plan isn't empty.
        if adoption.changed or adoption.remaining:
            adoptions.append(adoption)
    return tuple(adoptions)


def kind_of(relation: Relation) -> str:
    """What a relation is, in the word `LiveSchema.relation` takes."""
    from stevin.model.function import Function
    from stevin.model.schema import Schema
    from stevin.model.view import View

    if isinstance(relation, View):
        return "view"
    if isinstance(relation, Function):
        return "function"
    if isinstance(relation, Volume):
        return "volume"
    if isinstance(relation, Schema):
        return "schema"
    return "table"


def is_stale(plan: Plan, connection: Connection) -> bool:
    """Whether the live objects have moved since this plan was made.

    `apply` refuses a stale plan; this asks first, so a host can plan again
    before it puts a question to a person.
    """
    from stevin.executor import stale_tables

    return bool(stale_tables(plan, connection.introspector(plan.manage)))


def history_for(
    project: Project | None, target: Target | None, connection: Connection
) -> HistoryStore:
    """Where this project records what `apply` did — or `NoHistory`.

    A project that names a `history_schema` gets Delta tables in it: a lock, a
    resume and a record of every run. One that names none gets `NoHistory`,
    which keeps nothing and locks nothing; stevin's own state lives on the
    tables themselves either way. A host that wants to insist on a record
    checks `project.history_schema_for(target)` and says so itself.
    """
    if project is None or target is None:
        return NoHistory()
    schema = project.history_schema_for(target)
    if not schema:
        return NoHistory()
    return DeltaHistory(connection.runner, schema)


def _selector(
    select: Callable[[str], bool] | Sequence[str] | str | None,
    names: Sequence[str],
) -> Callable[[str], bool] | None:
    """What a selection means — here and on the command line, which hands its
    `--select` over as it was typed.

    A name counts from its last part up to all three — `orders`,
    `sales.orders`, `dev.sales.orders` — a pattern is a shell's (`sales.*`),
    and neither minds case. One that matches none of `names` is an error, not
    an empty plan. A predicate is the caller's own idea of a match, and is
    taken as it is.
    """
    if select is None:
        return None
    if isinstance(select, str):
        select = [select]
    if not isinstance(select, Sequence):
        return select
    wanted = [pattern.lower() for pattern in select]

    def matches(name: str, pattern: str) -> bool:
        parts = name.lower().split(".")
        return any(
            fnmatch(".".join(parts[start:]), pattern) for start in range(len(parts))
        )

    for pattern in wanted:
        if not any(matches(name, pattern) for name in names):
            raise PlanningError(f"the selection {pattern!r} matches no spec")
    return lambda name: any(matches(name, pattern) for pattern in wanted)


def package_version() -> str:
    """The installed version of stevin, recorded in every plan it makes."""
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as installed

    try:
        return installed("stevin")
    except PackageNotFoundError:  # pragma: no cover - only outside an install
        return "unknown"


@dataclass(frozen=True, slots=True)
class ImportedSchema:
    """What `import_schema` found: specs to write, and what it left alone.

    Iterating gives the specs, which is what most callers want; `skipped` says
    what in the schema stevin doesn't manage and why, so a host can tell
    someone rather than leave them wondering.
    """

    specs: tuple[ImportedSpec, ...] = ()
    skipped: tuple[tuple[str, str], ...] = ()

    def __iter__(self) -> Iterator[ImportedSpec]:
        return iter(self.specs)

    def __len__(self) -> int:
        return len(self.specs)


@dataclass(frozen=True, slots=True)
class ImportedSpec:
    """One spec `import` would write, and what it is about.

    `filename` is what the CLI calls the file; a host that keeps specs
    somewhere else can ignore it and use `relation.name`.
    """

    filename: str
    text: str
    relation: Relation


def import_schema(
    connection: Connection,
    schema: str,
    *,
    manage: Manage = EVERYTHING,
    catalog_variable: str | None = None,
    owned_elsewhere: Mapping[str, str] | None = None,
    spec_format: str = "yaml",
    parallel: int = 8,
) -> ImportedSchema:
    """Specs for what already exists in `catalog.schema`, as text.

    Nothing is written: a host decides where these go, whether that is a
    directory, a pull request or a review screen. The schema's own spec comes
    first when it has anything to say, then tables, views, functions and
    volumes.

    Owners are left out — an owner is usually a person's email, and rarely the
    same in two workspaces — as is anything `manage` hands to another tool, and
    anything an Asset Bundle declares (`owned_elsewhere`, which
    `target.owned_by_the_bundle()` gives you). `catalog_variable` writes the
    catalog as `${name}`, so one spec serves every target.

    Raises `IntrospectionError` if the schema can't be read.
    """
    from stevin.loader import dump_spec
    from stevin.sqlspec import dump_sql_spec, sql_cannot_say

    catalog, _, name = schema.partition(".")
    if not name or "." in name:
        raise PlanningError(f"a schema is named catalog.schema, not {schema!r}")
    live = connection.introspector(manage, parallel).schema(catalog, name)
    owned = {key.lower(): value for key, value in (owned_elsewhere or {}).items()}

    def written(relation: Relation, stem: str) -> ImportedSpec:
        reason = sql_cannot_say(relation) if spec_format == "sql" else None
        if spec_format == "sql" and reason is None:
            return ImportedSpec(
                f"{stem}.sql",
                dump_sql_spec(relation, catalog_variable=catalog_variable),
                relation,
            )
        return ImportedSpec(
            f"{stem}.yml",
            dump_spec(relation, catalog_variable=catalog_variable, manage=manage),
            relation,
        )

    specs: list[ImportedSpec] = []
    definition = replace(live.definition, owner=None) if live.definition else None
    if (
        definition is not None
        and definition.name.lower() not in owned
        and (definition.comment or definition.tags or definition.grants)
    ):
        specs.append(written(definition, "_schema"))

    seen: set[str] = set()
    for relation in (
        *(entry.table for entry in live.tables),
        *live.views,
        *live.functions,
        *live.volumes,
    ):
        if relation.name.lower() in owned:
            continue
        stem = relation.short_name
        if stem in seen:
            # Functions and volumes don't share a namespace with tables, so one
            # may have a table's name; its file then says what it is.
            stem = f"{stem}.{'volume' if isinstance(relation, Volume) else 'function'}"
        seen.add(stem)
        specs.append(written(replace(relation, owner=None), stem))
    return ImportedSchema(tuple(specs), tuple(live.skipped))

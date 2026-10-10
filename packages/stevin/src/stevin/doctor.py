"""What is wrong with the setup, before a plan runs into it.

Everything that went wrong in this project's first week of real use was
environmental, and every time it surfaced as something unhelpful several steps
later: a warehouse that wouldn't start became "the request could not be processed
by the warehouse" halfway through an apply; a metastore counting dropped tables
became QUOTA_EXCEEDED on the fifth step; a `databricks` that was really a shim
became the SDK's own authentication failing quietly.

So this asks first. Each check says what it looked at, what it found, and — when
that isn't right — what to do about it. Nothing here changes anything: no schema
is created, no warehouse started, no grant touched. It reads, and it tells you.

One check is about something stevin only reads: the ABAC policies in scope of a
project's tables. A workspace that won't list them doesn't stop a plan, so that
is a warning, with what the manual says listing them takes.

The checks are a list rather than a script so that a host can run them too, and
so that every failure this project has actually met can be a named test.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeAlias

from stevin.advice import advice
from stevin.bundle import find_cli
from stevin.connect import Connection, NotConnected
from stevin.loader import Project, Target, project_file, spec_files
from stevin.manage import MANAGEABLE
from stevin.render.labels import count

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient

#: How a check came out. `warning` is something worth knowing that doesn't stop
#: anything; `problem` is something that will.
Verdict: TypeAlias = Literal["ok", "warning", "problem"]


@dataclass(frozen=True, slots=True)
class Finding:
    """One check: what it looked at, what it found, and what to do."""

    about: str
    verdict: Verdict
    found: str
    remedy: str | None = None

    @property
    def mark(self) -> str:
        return {"ok": "✓", "warning": "⚠", "problem": "✗"}[self.verdict]


def look(
    project: Project | None,
    target: Target | None,
    connect: Callable[[], Connection] | None = None,
) -> Iterator[Finding]:
    """Every check, in the order a run would need them to hold.

    `connect` is a callable rather than a connection so that the workspace
    checks can report a connection that can't be made, instead of failing before
    the project checks have been seen. Without it, only the project is checked —
    which is what a machine with no credentials can answer.
    """
    yield from _project_checks(project, target)
    if connect is None:
        return
    try:
        connection = connect()
    except NotConnected as error:
        yield Finding(
            "workspace", "problem", str(error).split("\n")[0], advice(str(error))
        )
        return
    yield from _workspace_checks(connection, project, target)


def _project_checks(project: Project | None, target: Target | None) -> Iterator[Finding]:
    if project is None:
        yield Finding(
            "project",
            "problem",
            "no stevin.yml here or above",
            "Run `stevin import <catalog>.<schema>` to start one.",
        )
        return
    try:
        files = spec_files(project)
    except Exception as error:  # noqa: BLE001 - a bad `specs:` entry says so itself
        yield Finding("project", "problem", str(error))
        return
    where = ", ".join(str(path) for path in project.spec_paths)
    yield Finding(
        "project",
        "ok" if files else "warning",
        f"{project_file(project.root)}, {count(len(files), 'spec')} in {where}",
        None if files else "No spec files found; `stevin import` writes some.",
    )
    if target is None:
        yield Finding(
            "target",
            "problem",
            "no target chosen and no default",
            "Pass -t, or mark one `default: true`.",
        )
        return
    yield Finding("target", "ok", f"{target.name}{_vars(target)}")
    if project.bundle is not None:
        yield _bundle_check(project, target)
    if project.manage.elsewhere:
        yield Finding(
            "manage",
            "ok",
            f"{', '.join(project.manage.elsewhere)} left to another tool",
            None,
        )
    unknown = [a for a in project.manage.elsewhere if a not in MANAGEABLE]
    if unknown:  # pragma: no cover - the loader refuses these first
        yield Finding("manage", "problem", f"unknown: {', '.join(unknown)}")


def _vars(target: Target) -> str:
    variables = target.variables_map()
    catalog = variables.get("catalog")
    return f" (catalog {catalog})" if catalog else ""


def _bundle_check(project: Project, target: Target) -> Finding:
    """Whether the Databricks CLI can answer for the bundle this project names."""
    found = find_cli()
    if found is None:
        return Finding(
            "bundle",
            "warning",
            f"{project.bundle} — no `databricks` on PATH",
            "stevin reads the file itself, and says *unknown* for what only "
            "the CLI can settle (a lookup, a development target's names). Install "
            "it, or point DATABRICKS_CLI_PATH at it.",
        )
    unknown = [name for name, _ in target.unresolved]
    if unknown:
        return Finding(
            "bundle",
            "warning",
            f"{project.bundle} — {len(unknown)} value(s) unresolved: "
            f"{', '.join(unknown[:3])}",
            "A spec that uses one will say why. `databricks bundle validate -o "
            "json -t <target>` shows what the CLI can settle.",
        )
    return Finding("bundle", "ok", f"{project.bundle} — resolved via {found}")


def _workspace_checks(
    connection: Connection, project: Project | None, target: Target | None
) -> Iterator[Finding]:
    client = connection.client
    if client is None:  # pragma: no cover - only a runner was handed in
        yield Finding("workspace", "ok", "a runner was given; nothing to check")
        return
    yield _identity(client)
    yield _warehouse(client, connection.warehouse_id)
    yield _quota(client)
    if project is not None and target is not None:
        yield _history(connection, project, target)
        yield from _policies(connection, project, target)


def _identity(client: WorkspaceClient) -> Finding:
    try:
        me = client.current_user.me()
    except Exception as error:  # noqa: BLE001 - whatever the SDK raised
        return Finding("workspace", "problem", str(error), advice(str(error)))
    host = getattr(getattr(client, "config", None), "host", "") or "the workspace"
    return Finding("workspace", "ok", f"{host} as {me.user_name}")


def _warehouse(client: WorkspaceClient, warehouse_id: str) -> Finding:
    try:
        warehouse = client.warehouses.get(warehouse_id)
    except Exception as error:  # noqa: BLE001
        return Finding(
            "warehouse",
            "problem",
            f"{warehouse_id}: {error}",
            "Check the id in SQL Warehouses → Connection details, or set "
            "`warehouse_id` on the target.",
        )
    state = getattr(warehouse.state, "value", warehouse.state)
    if str(state).upper() in {"RUNNING", "STARTING"}:
        return Finding("warehouse", "ok", f"{warehouse.name} ({state})")
    return Finding(
        "warehouse",
        "warning",
        f"{warehouse.name} ({state})",
        "It starts on the first statement. If it stays stopped, the workspace "
        "can't give it compute — that is not something stevin can fix.",
    )


def _quota(client: WorkspaceClient) -> Finding:
    """The metastore's table quota, which counts more than a catalog holds.

    Reading it is also what asks Unity Catalog to recount, so this check is
    worth running even when it passes.
    https://docs.databricks.com/aws/en/data-governance/unity-catalog/resource-quotas
    """
    try:
        metastore = client.metastores.current().metastore_id
        quota = client.resource_quotas.get_quota(
            parent_securable_type="metastore",
            parent_full_name=str(metastore),
            quota_name="table-quota",
        ).quota_info
    except Exception as error:  # noqa: BLE001 - not every workspace answers this
        return Finding("metastore", "warning", f"table quota unknown: {error}")
    if quota is None:  # pragma: no cover - the API answered without one
        return Finding("metastore", "warning", "table quota unknown")
    count, limit = quota.quota_count, quota.quota_limit
    found = f"table quota {count} of {limit}"
    if count is None or limit is None or count < limit:
        return Finding("metastore", "ok", found)
    return Finding(
        "metastore",
        "problem",
        found,
        "A dropped table counts for as long as UNDROP could bring it back, so "
        "this is often far above what the catalogs hold. Reading it asks for a "
        "recount, which lands within about half an hour; some limits can be "
        "raised on request.",
    )


def _history(connection: Connection, project: Project, target: Target) -> Finding:
    """Where `apply` would record this run, and whether it may."""
    try:
        schema = project.history_schema_for(target)
    except KeyError as error:
        return Finding("history", "problem", f"history_schema: {error.args[0]}")
    if not schema:
        return Finding(
            "history",
            "ok",
            "no history_schema: runs aren't recorded and take no lock",
        )
    catalog, _, name = schema.partition(".")
    try:
        rows = connection.runner.query(
            "SELECT schema_name FROM "
            f"{_ident(catalog)}.information_schema.schemata "
            f"WHERE schema_name = {_literal(name)}"
        )
    except Exception as error:  # noqa: BLE001
        return Finding("history", "problem", f"{schema}: {error}", advice(str(error)))
    if rows:
        return Finding("history", "ok", f"{schema} exists")
    return Finding(
        "history",
        "warning",
        f"{schema} isn't there yet",
        "`apply` creates it on the first run, which needs CREATE SCHEMA in "
        f"{catalog}. Set `history_schema` to a schema you own, or leave it out.",
    )


#: What the manual says listing policies takes — the remedy's source.
_POLICIES_DOCS = "https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-show-policies"


def _policies(
    connection: Connection, project: Project, target: Target
) -> Iterator[Finding]:
    """Whether this warehouse lists ABAC policies for this principal.

    A plan reads the policies in scope of each table it describes and shows
    them; it asks `SHOW EFFECTIVE POLICIES`, which the manual gives to
    Databricks SQL and Runtime 16.4 and above, and to a principal with `READ
    METADATA` or `MANAGE` on the securable, or who owns it. This asks the same
    statement of each schema the specs live in — the schemas that are there —
    so "not accepted here" and "not allowed here" are found before a plan says
    them. Neither stops a plan, so neither is a problem.
    """
    if not project.manage.manages("policies"):
        return  # said by the `manage` line: not read, so nothing to check
    try:
        relations = project.load_specs(target).relations
    except Exception:  # noqa: BLE001 - `validate` is where a bad spec is said
        yield Finding("policies", "warning", "not checked: the specs can't be read", None)
        return
    schemas = sorted({".".join(r.parts[:2]) for r in relations if len(r.parts) >= 2})
    accepted: list[str] = []
    in_scope = 0
    for schema in schemas:
        catalog, _, name = schema.partition(".")
        try:
            there = connection.runner.query(
                "SELECT schema_name FROM "
                f"{_ident(catalog)}.information_schema.schemata "
                f"WHERE schema_name = {_literal(name)}"
            )
            if not there:
                continue  # a fresh target: nothing is under a policy yet
            rows = connection.runner.query(
                f"SHOW EFFECTIVE POLICIES ON SCHEMA {_ident(catalog)}.{_ident(name)}"
            )
        except Exception as error:  # noqa: BLE001 - whatever the workspace said
            said = next((line for line in str(error).splitlines() if line.strip()), "")
            yield Finding(
                "policies",
                "warning",
                f"can't be listed on {schema}: {said.strip()}",
                "A plan goes on without them and says so. Listing them takes "
                "Databricks SQL or Runtime 16.4 and above, and READ METADATA or "
                f"MANAGE on the securable, or owning it ({_POLICIES_DOCS}). A plan "
                "asks per table, which a principal may be allowed where the schema "
                "isn't. `manage: {policies: false}` stops stevin asking.",
            )
            continue
        accepted.append(schema)
        in_scope += len(rows)
    if accepted:
        yield Finding(
            "policies",
            "ok",
            f"SHOW EFFECTIVE POLICIES accepted on {', '.join(accepted)} "
            f"({in_scope} in scope)",
        )


def _ident(name: str) -> str:
    from stevin.sql import quote_ident

    return quote_ident(name)


def _literal(value: str) -> str:
    from stevin.sql import quote_literal

    return quote_literal(value)


def worst(findings: list[Finding]) -> Verdict:
    """The verdict of the run: a problem anywhere is a problem."""
    if any(finding.verdict == "problem" for finding in findings):
        return "problem"
    if any(finding.verdict == "warning" for finding in findings):
        return "warning"
    return "ok"

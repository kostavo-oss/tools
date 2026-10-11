"""Set the process up for dlt, wherever it runs. The PRE, DBX and DST rules.

Everything leeghwater does for a run happens here and is returned as a `Setup`, which says
what was decided. `create_pipeline` and `run` go by that `Setup`. Four things are handed
over as environment variables, because dlt or the Databricks SDK read them there:
`DATABRICKS_CONFIG_PROFILE`, `DLT_PROJECT_DIR`, `RUNTIME__LOG_LEVEL`, and whatever `--set`
names. Everything else stays in the `Setup`.

What a call leaves outside its `Setup` is those variables and the providers it registered
with dlt. Both are written down as they are made, and the next call takes them back
before it decides anything: PRE-3.
"""

import contextlib
import importlib.util
import os
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from leeghwater._errors import LeeghwaterError
from leeghwater._hook import import_dlt
from leeghwater._where import Where, where

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LOG_LEVEL = "RUNTIME__LOG_LEVEL"
PROJECT_DIR = "DLT_PROJECT_DIR"
PROFILE = "DATABRICKS_CONFIG_PROFILE"
WAREHOUSE_ID = "DATABRICKS_WAREHOUSE_ID"
HTTP_PATH_KEY = "destination.databricks.credentials.http_path"


@dataclass
class Setup:
    """What was decided for a run. Its lines are the first lines a run prints."""

    where: Where
    destination: str | None = None
    profile: str | None = None
    """The profile the run uses, if it uses one. PRE-7."""
    name_dlt: list[str] = field(default_factory=list)
    config_dir: str | None = None
    data_dir: str | None = None
    catalog: str | None = None
    """The catalog the run loads into, if it named one and loads into Databricks."""
    schema: str | None = None
    staging_schema: str | None = None
    warehouse: str | None = None
    """The id of the warehouse the run loads through, if it named one. PRE-8."""
    http_path: str | None = None
    """What dlt will connect through, when the run or dlt's own config named it."""
    log_level: str | None = None
    limit: int = 0
    secret_scopes: list[str] = field(default_factory=list)
    pointed_secrets: dict[str, str] = field(default_factory=dict)
    key_vaults: list[str] = field(default_factory=list)
    config: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def loads_into_databricks(self) -> bool:
        return self.destination == "databricks"

    def lines(self) -> list[str]:
        """Every item of PRE-5. Names only: no secret's value and no token."""
        rows = [
            ("where", self.where.describe()),
            ("workspace", self._workspace()),
            ("destination", self.destination or "dlt's own config decides"),
            ("catalog", self.catalog),
            ("schema", self.schema),
            ("staging schema", self.staging_schema),
            ("warehouse", self.warehouse or self.http_path),
            ("the name dlt", "; ".join(self.name_dlt)),
            ("dlt's config", self.config_dir),
            ("dlt's files", self.data_dir),
            ("log level", self.log_level),
            ("limit", f"{self.limit} page(s) from each resource" if self.limit else None),
            ("secret scopes", ", ".join(self.secret_scopes) or "none read"),
            (
                "pointed secrets",
                ", ".join(
                    f"{path} is {ref}" for path, ref in self.pointed_secrets.items()
                ),
            ),
            ("key vaults", ", ".join(self.key_vaults)),
            ("config set", ", ".join(self.config)),
        ]
        width = max(len(label) for label, _ in rows)
        lines = [f"  {label:<{width}}  {value}" for label, value in rows if value]
        return lines + [f"  note: {note}" for note in self.notes]

    def _workspace(self) -> str | None:
        if self.where.on_databricks:
            return "this one, as the run's own identity"
        if self.profile:
            return f"profile {self.profile}"
        return None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# What the last prepare() in this process decided: what create_pipeline() and run() go by.
_current: Setup | None = None


def current() -> Setup:
    """The setup of this run. Raises when nothing prepared the process."""
    if _current is None:
        raise LeeghwaterError(
            "Nothing has prepared this process: call leeghwater.prepare(...) first, or"
            " run the pipeline through the project's app."
        )
    return _current


@dataclass
class _Left:
    """What a call left in the process, outside its `Setup`."""

    variables: dict[str, tuple[str | None, str]] = field(default_factory=dict)
    """A variable that was set: what it held before, and what it was set to."""
    providers: list[Any] = field(default_factory=list)
    """The providers the call added to dlt's. One that was there already is not here."""

    def set(self, name: str, value: str) -> None:
        """Set an environment variable, and remember what it held."""
        held = self.variables.get(name)
        before = held[0] if held else os.environ.get(name)
        os.environ[name] = value
        self.variables[name] = (before, value)

    def take_back(self) -> None:
        """Put the process back as it was before the call that left this."""
        for name, (before, value) in self.variables.items():
            if os.environ.get(name) != value:
                # Somebody set it again after leeghwater did: it is theirs now.
                continue
            if before is None:
                del os.environ[name]
            else:
                os.environ[name] = before
        self.variables.clear()
        if self.providers:
            # A provider can only be here when dlt was imported, by the call that made it.
            from leeghwater import _dlt

            for provider in self.providers:
                _dlt.unregister_provider(provider)
            self.providers.clear()


# What the last call left: by `prepare_process`, and by `prepare_run`. They are kept apart
# because an app prepares the process once, and a run after it.
_left_by_process = _Left()
_left_by_run = _Left()


def prepare(
    *,
    secret_scopes: Sequence[str] = (),
    secrets: Mapping[str, str] | None = None,
    profile: str | None = None,
    catalog: str | None = None,
    schema: str | None = None,
    staging_schema: str | None = None,
    warehouse: str | None = None,
    log_level: str | None = None,
    limit: int = 0,
    config: Mapping[str, str] | None = None,
    project: str | None = None,
    destination: str | None = "databricks",
    local_destination: str | None = "duckdb",
    workspace_client: Any | None = None,
    key_vaults: Sequence[str] = (),
    key_vault_client: Any | None = None,
) -> Setup:
    """Set the process up for dlt, and say what was decided.

    After it, `import dlt` is dltHub's dlt, dlt finds its secrets in the scopes named, and
    `create_pipeline` makes pipelines that load where this says. A later call starts
    from nothing: the environment variables an earlier call set are put back, and the
    scopes and vaults it registered with dlt are taken out, before this one decides.

    On Databricks, or with a `profile`, pipelines load into Databricks. On a laptop
    without a profile they load into `local_destination` and no scope is read: dlt takes
    its secrets from the environment or `.dlt/secrets.toml`.

    Args:
        secret_scopes: Secret scopes to read dlt's secrets from, asked in this order.
        secrets: Secrets under another name: dlt's path to `scope/key`.
        profile: A profile from `~/.databrickscfg`, on a laptop. Refused on Databricks.
        catalog: The catalog to load into.
        schema: The schema to load into, used exactly as given.
        staging_schema: The schema dlt stages through, by its whole name.
        warehouse: The id of the SQL warehouse to load through.
        log_level: DEBUG, INFO, WARNING, ERROR or CRITICAL, for dlt.
        limit: At most this many pages from each resource; 0 for all of them.
        config: Any other dlt config value, by dlt's dotted name.
        project: The project's package, e.g. `my_ingest`: where a wheel carries its
            `.dlt/config.toml`.
        destination: Where pipelines load on Databricks or with a profile. None leaves
            it to dlt's own config.
        local_destination: Where they load on a laptop without a profile.
        workspace_client: A `databricks.sdk.WorkspaceClient` to read secrets with, in
            place of the SDK's default sign-in.
        key_vaults: Azure Key Vaults to read dlt's secrets from, after the scopes. Needs
            the `keyvault` extra; works wherever `DefaultAzureCredential` finds a sign-in.
        key_vault_client: A `SecretClient` to read the vaults with, in place of one made
            with `DefaultAzureCredential`.
    """
    setup = prepare_process(project=project)
    return prepare_run(
        setup,
        secret_scopes=secret_scopes,
        secrets=secrets,
        profile=profile,
        catalog=catalog,
        schema=schema,
        staging_schema=staging_schema,
        warehouse=warehouse,
        log_level=log_level,
        limit=limit,
        config=config,
        destination=destination,
        local_destination=local_destination,
        workspace_client=workspace_client,
        key_vaults=key_vaults,
        key_vault_client=key_vault_client,
    )


def prepare_process(*, project: str | None = None) -> Setup:
    """The part that has to happen before a project's own modules are imported."""
    global _current
    setup = Setup(where=where())
    was_imported = "dlt" in sys.modules
    project_dir, log_level = os.environ.get(PROJECT_DIR), os.environ.get(LOG_LEVEL)

    # PRE-3: an earlier call is taken back whole, its run and then its process.
    _current = None
    _left_by_run.take_back()
    _left_by_process.take_back()

    _point_at_the_wheels_config(setup, project)
    _, setup.name_dlt = import_dlt(setup.where.on_databricks)

    from leeghwater import _dlt

    if was_imported and os.environ.get(PROJECT_DIR) != project_dir:
        # dlt made its providers before it was told where the project is.
        _dlt.reload_config_locations()
    if was_imported and os.environ.get(LOG_LEVEL) != log_level:
        # The level an earlier call set is gone from the environment, and from dlt.
        _dlt.apply_log_level()
    setup.config_dir = _existing(_dlt.settings_dir())
    # dlt picks this itself, and falls back to a temporary directory when the home
    # directory can't be written: `dlt/common/runtime/run_context.py`, `global_dir`.
    setup.data_dir = _dlt.data_dir()
    return setup


def prepare_run(
    setup: Setup,
    *,
    secret_scopes: Sequence[str] = (),
    secrets: Mapping[str, str] | None = None,
    profile: str | None = None,
    catalog: str | None = None,
    schema: str | None = None,
    staging_schema: str | None = None,
    warehouse: str | None = None,
    log_level: str | None = None,
    limit: int = 0,
    config: Mapping[str, str] | None = None,
    destination: str | None = "databricks",
    local_destination: str | None = "duckdb",
    require_warehouse: bool = False,
    workspace_client: Any | None = None,
    key_vaults: Sequence[str] = (),
    key_vault_client: Any | None = None,
) -> Setup:
    """The part that depends on a run's options. Needs `prepare_process` first."""
    global _current
    on_databricks = setup.where.on_databricks
    log_level_before = os.environ.get(LOG_LEVEL)

    # PRE-3: what an earlier run left is taken back before this one decides. Until this
    # one has decided there is no setup to go by, so a call that is refused leaves none.
    _current = None
    _left_by_run.take_back()

    if limit < 0:
        raise LeeghwaterError(f"--limit is 0 for everything, or more; got {limit}.")
    setup.limit = limit
    if profile and on_databricks:
        raise LeeghwaterError(
            "--profile is for a laptop. On Databricks the run has an identity already:"
            " take the option out of the job's parameters."
        )
    # What the user's own shell holds: an earlier call's profile is taken back by now.
    in_environment = None if on_databricks else os.environ.get(PROFILE)
    if profile:
        # dlt's Databricks destination makes its own WorkspaceClient() with the SDK's
        # default sign-in (`dlt/destinations/impl/databricks/configuration.py`), so the
        # profile is handed on the way the SDK reads it and both end up as one identity.
        _left_by_run.set(PROFILE, profile)

    remote = on_databricks or bool(profile)
    setup.destination = destination if remote else local_destination
    # PRE-7: a profile is named when the run uses it. One in the environment decides
    # nothing about where a run loads (DST-1); the SDK reads it when the run loads into
    # Databricks anyway, because the app's `local_destination` says so.
    setup.profile = profile or (in_environment if setup.loads_into_databricks else None)
    if setup.destination and not setup.loads_into_databricks:
        note = f"pipelines load into {setup.destination}"
        if not remote:
            note += ", here; "
            if in_environment:
                note += f"the profile in {PROFILE} ({in_environment}) is not used: "
            note += "give --profile to load into a workspace"
        setup.notes.append(note)

    for key, value in (config or {}).items():
        _left_by_run.set(_env_name(key), value)
        setup.config.append(key)
    # PRE-8: only a load into Databricks goes into a catalog, as `create_pipeline` has it.
    setup.catalog = (catalog or None) if setup.loads_into_databricks else None
    _set_schemas(setup, schema, staging_schema)
    _set_warehouse(setup, warehouse, require_warehouse)
    _set_log_level(setup, log_level)
    if os.environ.get(LOG_LEVEL) != log_level_before:
        # dlt makes its logger from its runtime config, so the level is given as config
        # and the runtime is made again to take it up: a level that was set, and one
        # that an earlier call set and this one did not.
        from leeghwater import _dlt

        _dlt.apply_log_level()

    if remote:
        _register_secrets(setup, secret_scopes, secrets, workspace_client)
    elif secret_scopes or secrets:
        setup.notes.append(
            "no secret scope is read on a laptop without --profile; dlt takes its secrets"
            " from the environment or .dlt/secrets.toml"
        )
    if key_vaults:
        # After the scopes, and read anywhere: a vault has a sign-in of its own.
        from leeghwater.keyvault import register_key_vault

        for url in key_vaults:
            with _registering():
                provider = register_key_vault(url, client=key_vault_client)
            if provider.url not in setup.key_vaults:
                setup.key_vaults.append(provider.url)
    _current = setup
    return setup


@contextlib.contextmanager
def _registering() -> Iterator[None]:
    """Write down the providers that are added to dlt's inside the block."""
    from leeghwater import _dlt

    before = {id(provider) for provider in _dlt.registered_providers()}
    try:
        yield
    finally:
        _left_by_run.providers.extend(
            provider
            for provider in _dlt.registered_providers()
            if id(provider) not in before
        )


def _existing(path: str) -> str:
    return path if os.path.isdir(path) else f"{path} (not there)"


def _point_at_the_wheels_config(setup: Setup, project: str | None) -> None:
    """DBX-7 and DBX-8."""
    if not project:
        return
    try:
        spec = importlib.util.find_spec(project.split(".")[0])
    except (ImportError, ValueError):
        spec = None
    if spec is None or not spec.submodule_search_locations:
        return
    package_dir = Path(next(iter(spec.submodule_search_locations)))
    carried = package_dir / ".dlt"

    if setup.where.on_databricks and (carried / "secrets.toml").exists():
        raise LeeghwaterError(
            f"The wheel of '{project}' carries a secrets.toml, at {carried}."
            " A wheel is read by everyone who can read the job. Take the file out of the"
            " wheel and put its values in a secret scope."
        )
    # dlt looks for `.dlt/` in the working directory, or in DLT_PROJECT_DIR:
    # https://dlthub.com/docs/general-usage/credentials/setup#toml-files
    if PROJECT_DIR in os.environ or Path(".dlt").is_dir():
        return
    if not (carried / "config.toml").exists():
        return
    _left_by_process.set(PROJECT_DIR, str(package_dir))


def _env_name(key: str) -> str:
    """dlt's name for a config value as an environment variable: `a.b_c` is `A__B_C`."""
    parts = [part.strip() for part in key.split(".")]
    if not all(parts):
        raise LeeghwaterError(
            f"'{key}' is not a dlt config name. One looks like"
            " destination.databricks.staging_volume_name"
        )
    return "__".join(part.upper() for part in parts)


def _set_schemas(setup: Setup, schema: str | None, staging_schema: str | None) -> None:
    """APP-7, DST-6 and DST-7."""
    if staging_schema is not None:
        if not staging_schema.strip():
            raise LeeghwaterError(
                "--staging-schema is empty. In a bundle it is the deployed name of the"
                " staging schema: ${resources.schemas.<key>.name}"
            )
        if "%s" in staging_schema:
            raise LeeghwaterError(
                f"--staging-schema is a schema's whole name, and '{staging_schema}' has"
                " a %s in it: dlt would fill that in and make a schema of its own."
            )
    if schema is not None and not schema.strip():
        raise LeeghwaterError(
            "--schema is empty. In a bundle it is the deployed name of the schema:"
            " ${resources.schemas.<key>.name}"
        )
    if schema and not staging_schema and setup.loads_into_databricks:
        raise LeeghwaterError(
            "--schema was given without --staging-schema. dlt would stage a merge through"
            f" '{schema}_staging', a schema it makes itself, outside your bundle's grants"
            " and cleanup. Declare a staging schema in the bundle and pass its name:\n"
            "  - --staging-schema\n"
            "  - ${resources.schemas.<key>_staging.name}"
        )
    setup.schema = schema or None
    setup.staging_schema = staging_schema or None


def _set_warehouse(setup: Setup, warehouse: str | None, required: bool) -> None:
    """DST-4 and DST-5: the warehouse is named, not found."""
    if not setup.loads_into_databricks:
        # PRE-8: no other load goes through a warehouse, so none is kept or said.
        return
    if warehouse:
        # https://docs.databricks.com/aws/en/integrations/compute-details
        setup.warehouse = warehouse
        setup.http_path = f"/sql/1.0/warehouses/{warehouse}"
        return
    from leeghwater import _dlt

    path = _dlt.config_value(HTTP_PATH_KEY)
    if path:
        setup.http_path = f"{path} (from dlt's config)"
    elif os.environ.get(WAREHOUSE_ID):
        setup.http_path = f"{os.environ[WAREHOUSE_ID]} (from {WAREHOUSE_ID})"
    elif required:
        raise LeeghwaterError(
            "No SQL warehouse is named, and dlt would load through the first one on the"
            " workspace's list. Name one with --warehouse <id>; in a job:\n"
            "  - --warehouse\n"
            "  - ${var.warehouse_id}"
        )
    else:
        setup.notes.append(
            "no warehouse is named: dlt takes a notebook's cluster, or else the first"
            " warehouse on the workspace's list"
        )


def _set_log_level(setup: Setup, log_level: str | None) -> None:
    if not log_level:
        return
    level = log_level.upper()
    if level not in LOG_LEVELS:
        raise LeeghwaterError(
            f"--log-level is one of {', '.join(LOG_LEVELS)}; got '{log_level}'."
        )
    _left_by_run.set(LOG_LEVEL, level)
    setup.log_level = level


def _register_secrets(
    setup: Setup,
    secret_scopes: Sequence[str],
    secrets: Mapping[str, str] | None,
    workspace_client: Any | None,
) -> None:
    # Imported here: this module must be importable before dlt is.
    from leeghwater.secrets import register_pointed_secrets, register_secret_scope

    # Pointed first, always, so that it is asked before any scope: what is pointed at
    # wins over what a scope holds under dlt's own name.
    with _registering():
        register_pointed_secrets(secrets or {}, workspace_client=workspace_client)
    setup.pointed_secrets = dict(sorted((secrets or {}).items()))
    for scope in secret_scopes:
        with _registering():
            provider = register_secret_scope(scope, workspace_client=workspace_client)
        if provider.scope not in setup.secret_scopes:
            setup.secret_scopes.append(provider.scope)

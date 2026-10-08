"""The command line leeghwater gives a project. `spec/001`.

A project makes an `App` and names it as its console script. The same command is what a
developer types and what a job's wheel task calls.

The commands are built with click, as objects: a pipeline's parameters become options of
its command, and every `run` takes the same options besides. The project's own commands
are typer commands, so a project writes them the way it would write any typer command.
"""

import functools
import importlib
import inspect
import json
import pkgutil
import types
import typing
from collections.abc import Callable, Sequence
from dataclasses import MISSING, dataclass, field, fields
from datetime import date, datetime
from typing import Any

import typer
import typer.main
from typer.core import TyperCommand, TyperGroup, TyperOption

from leeghwater import __version__
from leeghwater._errors import LeeghwaterError, RunFailed
from leeghwater._pipeline import runs_so_far
from leeghwater._prepare import Setup, prepare_process, prepare_run
from leeghwater._where import where

_MARK = "__leeghwater_pipeline__"

# typer's own command classes, so what is built here is what typer builds for the
# project's own commands. Since 0.21 typer carries its own copy of click.
try:
    from typer._click.types import ParamType
except ImportError:  # pragma: no cover - typer before its own click
    from click import ParamType  # type: ignore[assignment]


def pipeline(
    function: Callable[..., Any] | None = None, *, name: str | None = None
) -> Any:
    """Mark a function as a pipeline the app can run. Its name is the function's.

    The function makes its dlt pipeline with `create_pipeline` and runs it with `run`, and
    never calls `dlt.pipeline()` or `pipeline.run()` itself:

        @pipeline
        def github(since: str = "2024-01-01"):
            p = leeghwater.create_pipeline("github")
            return leeghwater.run(p, github_source(since=since))

    Its parameters become options of `run github`.
    """

    def mark(marked: Callable[..., Any]) -> Callable[..., Any]:
        setattr(marked, _MARK, name or marked.__name__)
        return marked

    return mark(function) if function is not None else mark


# -- how a pipeline's parameters are read ----------------------------------------------


class _YesNo(ParamType):
    """A yes or a no as a job's parameter can give it: a word, not a flag."""

    name = "true|false"

    def convert(self, value: Any, param: Any, ctx: Any) -> bool:
        if isinstance(value, bool):
            return value
        word = str(value).strip().lower()
        if word in ("true", "1", "yes", "y"):
            return True
        if word in ("false", "0", "no", "n"):
            return False
        self.fail(f"'{value}' is not one of true, 1, yes, y, false, 0, no, n", param, ctx)


class _Iso(ParamType):
    """A date or a time in ISO format."""

    def __init__(self, kind: type[date], example: str) -> None:
        self.kind, self.example, self.name = kind, example, example

    def convert(self, value: Any, param: Any, ctx: Any) -> Any:
        if isinstance(value, self.kind):
            return value
        try:
            return self.kind.fromisoformat(str(value))
        except ValueError:
            self.fail(
                f"'{value}' is not an ISO {self.kind.__name__}, like {self.example}"
            )


# What a pipeline's parameter may be, and the click type that reads it.
_TYPES: dict[type, Any] = {
    str: str,
    int: int,
    float: float,
    bool: _YesNo(),
    date: _Iso(date, "2024-06-01"),
    datetime: _Iso(datetime, "2024-06-01T12:00:00"),
}


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def _kind(parameter: str, pipeline_name: str, function: Callable[..., Any]) -> type:
    """The type of a pipeline's parameter, with `X | None` read as X."""
    signature = inspect.signature(function).parameters[parameter]
    hint = typing.get_type_hints(function).get(parameter)
    if hint is None:
        default = signature.default
        hint = str if default in (inspect.Parameter.empty, None) else type(default)
    arguments = [a for a in typing.get_args(hint) if a is not type(None)]
    if typing.get_origin(hint) in (typing.Union, types.UnionType) and len(arguments) == 1:
        hint = arguments[0]
    if hint not in _TYPES:
        allowed = ", ".join(kind.__name__ for kind in _TYPES)
        raise LeeghwaterError(
            f"Pipeline '{pipeline_name}': parameter '{parameter}' is a {hint}. One"
            f" becomes an option of the command, so it is one of: {allowed}."
        )
    return hint


def _own_options(name: str, function: Callable[..., Any]) -> list[TyperOption]:
    """A pipeline's parameters as options of its command. `spec/001`, R4."""
    options = []
    for parameter in inspect.signature(function).parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            raise LeeghwaterError(
                f"Pipeline '{name}' takes *{parameter.name}: every parameter needs a"
                " name, to be an option of the command."
            )
        flag = _flag(parameter.name)
        if flag in _EVERY_RUN:
            raise LeeghwaterError(
                f"Pipeline '{name}' has a parameter '{parameter.name}', and {flag} is an"
                " option every run takes. Give the parameter another name."
            )
        required = parameter.default is inspect.Parameter.empty
        options.append(
            TyperOption(
                param_decls=[flag],
                type=_TYPES[_kind(parameter.name, name, function)],
                required=required,
                default=None if required else parameter.default,
                show_default=not required,
            )
        )
    return options


# -- the options every run takes ---------------------------------------------------------


@dataclass
class _Options:
    """The options every run takes. `spec/001`, R5."""

    profile: str | None = None
    catalog: str | None = None
    schema: str | None = None
    staging_schema: str | None = None
    secret_scope: list[str] = field(default_factory=list)
    secret: list[str] = field(default_factory=list)
    key_vault: list[str] = field(default_factory=list)
    warehouse: str | None = None
    limit: int | None = None
    log_level: str | None = None
    set: list[str] = field(default_factory=list)

    @classmethod
    def take(cls, values: dict[str, Any]) -> "_Options":
        """Take the options out of a command's values, leaving the pipeline's own."""
        taken = {f.name: values.pop(f.name, None) for f in fields(cls)}
        given = {k: list(v) if isinstance(v, tuple) else v for k, v in taken.items()}
        return cls(**{k: v for k, v in given.items() if v is not None})


_HELP = {
    "profile": "A profile from ~/.databrickscfg: load into that workspace from a laptop."
    " Without it a laptop run loads locally. Refused on Databricks.",
    "catalog": "The catalog to load into.",
    "schema": "The schema to load into, used exactly as given.",
    "staging_schema": "The schema dlt stages through, by its whole name.",
    "secret_scope": "A secret scope to read dlt's secrets from, in place of the app's."
    " May be given more than once.",
    "secret": "Where one secret is: <dlt's name>=<scope>/<key>. May be given more than"
    " once.",
    "key_vault": "An Azure Key Vault to read dlt's secrets from, after the scopes:"
    " https://<name>.vault.azure.net. May be given more than once.",
    "warehouse": "The id of the SQL warehouse to load through.",
    "limit": "At most this many pages from each resource; 0, the default, for all. A"
    " pull-request environment runs with 1: dlt makes every table with its real columns"
    " from the rows it sees, and makes no table from no rows.",
    "log_level": "DEBUG, INFO, WARNING, ERROR or CRITICAL, for dlt.",
    "set": "Any dlt config value for this run: <dlt's name>=<value>. May be given more"
    " than once.",
}
_EVERY_RUN = [_flag(name) for name in _HELP]


def _every_run_options() -> list[TyperOption]:
    options = []
    for f in fields(_Options):
        many = f.default_factory is not MISSING  # type: ignore[comparison-overlap]
        options.append(
            TyperOption(
                param_decls=[_flag(f.name)],
                type=int if f.name == "limit" else str,
                multiple=many,
                default=() if many else None,
                help=_HELP[f.name],
            )
        )
    return options


def _pairs(items: Sequence[str], flag: str) -> dict[str, str]:
    pairs = {}
    for item in items:
        name, separator, value = item.partition("=")
        if not separator or not name.strip():
            raise LeeghwaterError(f"{flag} takes <name>=<value>; got '{item}'.")
        pairs[name.strip()] = value
    return pairs


# -- the app ---------------------------------------------------------------------------


class App:
    """A project's command line: `run`, `list`, `doctor`, and the project's own commands.

        # src/my_ingest/cli.py
        from leeghwater import App

        app = App(pipelines="my_ingest.pipelines", secret_scopes=["ingest"])

        # pyproject.toml
        [project.scripts]
        ingest = "my_ingest.cli:app"

    Args:
        pipelines: The module or package the project's pipelines are in. The app imports
            it itself, after it has prepared the process.
        secret_scopes: Secret scopes to read dlt's secrets from, asked in this order.
        secrets: Secrets under another name: dlt's path to `scope/key`. A run's
            `--secret` adds to these, and wins on the same name.
        key_vaults: Azure Key Vaults to read dlt's secrets from, after the scopes
            (`leeghwater[keyvault]`). A run's `--key-vault` names others.
        catalog: The catalog to load into, when a run names none.
        warehouse: The SQL warehouse to load through, when a run names none.
        destination: Where pipelines load on Databricks, or with `--profile`. None
            leaves it to dlt's own config.
        local_destination: Where they load on a laptop without `--profile`.
        help: The first line of `--help`.
        workspace_client: A `databricks.sdk.WorkspaceClient` to use in place of the
            SDK's default sign-in.
    """

    def __init__(
        self,
        pipelines: str,
        *,
        secret_scopes: Sequence[str] = (),
        secrets: dict[str, str] | None = None,
        key_vaults: Sequence[str] = (),
        catalog: str | None = None,
        warehouse: str | None = None,
        destination: str | None = "databricks",
        local_destination: str | None = "duckdb",
        help: str | None = None,
        workspace_client: Any | None = None,
    ) -> None:
        self.pipelines = pipelines
        self.secret_scopes = list(secret_scopes)
        self.secrets = dict(secrets or {})
        self.key_vaults = list(key_vaults)
        self.catalog = catalog
        self.warehouse = warehouse
        self.destination = destination
        self.local_destination = local_destination
        self.help = help or "Run this project's dlt pipelines, here and on Databricks."
        self.workspace_client = workspace_client
        self._own = typer.Typer(add_completion=False, rich_markup_mode=None)
        self._setup: Setup | None = None

    def command(self, *args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Any]:
        """Add a command of the project's own, beside `run`. Takes what typer's does.

        It is prepared as a pipeline is, with the app's own settings, and finds the same
        secrets.
        """

        def register(function: Callable[..., Any]) -> Callable[..., Any]:
            self._own.command(*args, **kwargs)(self._prepared(function))
            return function

        return register

    def __call__(self, argv: Sequence[str] | None = None) -> None:
        """Run the command line: the console script, and a wheel task's entry point."""
        try:
            code = self._main(argv)
        except LeeghwaterError as error:
            if where().on_databricks:
                # An exception that isn't caught fails a wheel task: run on a workspace
                # on 2026-10-07. A non-zero exit was not tried, so here it is raised.
                raise
            typer.echo(f"error: {error}", err=True)
            raise SystemExit(1) from None
        if code:
            raise SystemExit(code)

    def _main(self, argv: Sequence[str] | None) -> int:
        self._setup = prepare_process(project=self.pipelines)
        root = self._build(self._discover())
        try:
            # Standalone, so a wrong option is reported the way click reports it. Only
            # its exit is caught: a run that went well returns, it does not exit.
            root.main(args=None if argv is None else list(argv))
        except SystemExit as exit_:
            return exit_.code if isinstance(exit_.code, int) else int(bool(exit_.code))
        return 0

    # -- finding the pipelines ---------------------------------------------------------

    def _discover(self) -> dict[str, Callable[..., Any]]:
        try:
            root = importlib.import_module(self.pipelines)
        except ModuleNotFoundError as error:
            if error.name and self.pipelines.startswith(error.name):
                raise LeeghwaterError(
                    f"The app looks for pipelines in '{self.pipelines}', and there is no"
                    " such module. It is the `pipelines=` of the App."
                ) from error
            raise
        modules = [root]
        if hasattr(root, "__path__"):
            modules += [
                importlib.import_module(info.name)
                for info in pkgutil.walk_packages(root.__path__, root.__name__ + ".")
            ]
        found: dict[str, Callable[..., Any]] = {}
        for module in modules:
            for value in vars(module).values():
                if not isinstance(value, types.FunctionType) or not hasattr(value, _MARK):
                    continue
                name = getattr(value, _MARK)
                if found.setdefault(name, value) is not value:
                    raise LeeghwaterError(
                        f"Two pipelines are named '{name}': one in"
                        f" {found[name].__module__}, one in {value.__module__}."
                    )
        return dict(sorted(found.items()))

    # -- building the command line -----------------------------------------------------

    def _build(self, pipelines: dict[str, Callable[..., Any]]) -> TyperGroup:
        # The project's own commands, as typer built them; the callback keeps it a group.
        self._own.callback()(lambda: None)
        root = typer.main.get_command(self._own)
        assert isinstance(root, TyperGroup)
        root.help = self.help
        root.no_args_is_help = True

        run = TyperGroup(name="run", help="Run one pipeline.", no_args_is_help=True)
        for name, function in pipelines.items():
            run.add_command(
                TyperCommand(
                    name,
                    help=inspect.getdoc(function),
                    params=[*_own_options(name, function), *_every_run_options()],
                    callback=functools.partial(self._run_command, name, function),
                )
            )
        root.add_command(run)
        as_json = TyperOption(
            param_decls=["--json", "as_json"], is_flag=True, help="Answer as JSON."
        )
        root.add_command(
            TyperCommand(
                "list",
                help="Name the pipelines and their parameters.",
                params=[as_json],
                callback=functools.partial(self._list, pipelines),
            )
        )
        root.add_command(
            TyperCommand(
                "doctor",
                help="Say where this would run and what would be set up; change nothing.",
                params=[*_every_run_options(), as_json],
                callback=self._doctor_command,
            )
        )
        return root

    def _prepared(self, function: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(function)
        def command(*args: Any, **kwargs: Any) -> Any:
            setup = self._prepare(_Options(), require_warehouse=False)
            self._say(function.__name__, setup)
            return function(*args, **kwargs)

        return command

    # -- the commands ------------------------------------------------------------------

    def _prepare(self, options: _Options, *, require_warehouse: bool) -> Setup:
        if self._setup is None:
            self._setup = prepare_process(project=self.pipelines)
        return prepare_run(
            self._setup,
            secret_scopes=options.secret_scope or self.secret_scopes,
            secrets={**self.secrets, **_pairs(options.secret, "--secret")},
            key_vaults=options.key_vault or self.key_vaults,
            profile=options.profile,
            catalog=options.catalog or self.catalog,
            schema=options.schema,
            staging_schema=options.staging_schema,
            warehouse=options.warehouse or self.warehouse,
            log_level=options.log_level,
            limit=options.limit or 0,
            config=_pairs(options.set, "--set"),
            destination=self.destination,
            local_destination=self.local_destination,
            require_warehouse=require_warehouse,
            workspace_client=self.workspace_client,
        )

    def _say(self, what: str, setup: Setup) -> None:
        typer.echo(f"leeghwater {__version__}: {what}")
        for line in setup.lines():
            typer.echo(line)

    def _run_command(
        self, name: str, function: Callable[..., Any], **values: Any
    ) -> None:
        options = _Options.take(values)
        setup = self._prepare(options, require_warehouse=True)
        self._say(f"run {name}", setup)
        before = runs_so_far()

        function(**values)

        if runs_so_far() == before:
            # `spec/001`, R8: only a pipeline made by leeghwater loads where the run said.
            raise RunFailed(
                f"'{name}' made no load with leeghwater.run(). The schema, destination"
                " and limit of this run only reach a pipeline made with"
                " leeghwater.create_pipeline() and run with leeghwater.run(); a plain"
                " dlt.pipeline() loads wherever dlt's own config says."
            )

    def _list(self, pipelines: dict[str, Callable[..., Any]], as_json: bool) -> None:
        described = [
            {
                "name": name,
                "help": (inspect.getdoc(function) or "").split("\n")[0],
                "parameters": [
                    {
                        "name": parameter.name,
                        "option": _flag(parameter.name),
                        "type": _kind(parameter.name, name, function).__name__,
                        "required": parameter.default is inspect.Parameter.empty,
                        "default": None
                        if parameter.default is inspect.Parameter.empty
                        else parameter.default,
                    }
                    for parameter in inspect.signature(function).parameters.values()
                ],
            }
            for name, function in pipelines.items()
        ]
        if as_json:
            typer.echo(json.dumps({"pipelines": described}, indent=2, default=str))
            return
        if not described:
            typer.echo(
                f"no pipelines in {self.pipelines}: mark a function with @pipeline"
            )
        for item in described:
            typer.echo(item["name"] + (f"  {item['help']}" if item["help"] else ""))
            for parameter in item["parameters"]:
                default = (
                    "required"
                    if parameter["required"]
                    else f"default {parameter['default']!r}"
                )
                typer.echo(f"  {parameter['option']} <{parameter['type']}>  {default}")

    def _doctor_command(self, **values: Any) -> None:
        as_json = values.pop("as_json")
        setup = self._prepare(_Options.take(values), require_warehouse=False)
        checks = self._checks(setup) if setup.loads_into_databricks else []
        ok = all(check["ok"] for check in checks)
        if as_json:
            typer.echo(
                json.dumps(
                    {"setup": setup.as_dict(), "checks": checks, "ok": ok}, indent=2
                )
            )
        else:
            self._say("doctor", setup)
            if not checks:
                typer.echo(
                    "  nothing to check: this would load locally, with no workspace"
                )
            for check in checks:
                mark = "ok    " if check["ok"] else "FAILED"
                typer.echo(f"  {mark}  {check['what']}: {check['found']}")
        if not ok:
            raise SystemExit(1)

    def _checks(self, setup: Setup) -> list[dict[str, Any]]:
        """What can be checked without running a pipeline. Reads names, never a value."""
        from leeghwater.secrets import Scopes, split_pointer

        checks: list[dict[str, Any]] = []

        def check(what: str, find: Callable[[], str]) -> None:
            try:
                checks.append({"what": what, "ok": True, "found": find()})
            except Exception as error:
                found = f"{type(error).__name__}: {error}"
                checks.append({"what": what, "ok": False, "found": found})

        scopes = Scopes(self.workspace_client)
        try:
            client = scopes.client
        except Exception as error:
            return [{"what": "sign-in", "ok": False, "found": f"{error}"}]

        check("identity", scopes.identity)
        names: dict[str, set[str]] = {}

        def listed(scope: str) -> str:
            names[scope] = scopes.names(scope)
            return ", ".join(sorted(names[scope])) or "no secrets in it"

        for scope in setup.secret_scopes:
            check(f"secret scope {scope}", functools.partial(listed, scope))

        def pointed(path: str, ref: str) -> str:
            scope, key = split_pointer(path, ref)
            if scope not in names:
                listed(scope)
            if key not in names[scope]:
                raise LookupError(f"no secret '{key}' in scope '{scope}'")
            return f"{scope}/{key} is there"

        for path, ref in setup.pointed_secrets.items():
            check(f"secret {path}", functools.partial(pointed, path, ref))

        for url in setup.key_vaults:

            def listed_vault(url: str = url) -> str:
                from leeghwater.keyvault import Vault

                names = Vault(url, None).names()
                return ", ".join(sorted(names)) or "no secrets in it"

            check(f"key vault {url}", listed_vault)

        if setup.warehouse:

            def warehouse() -> str:
                found = client.warehouses.get(setup.warehouse)
                return f"{found.name} ({getattr(found.state, 'value', found.state)})"

            check(f"warehouse {setup.warehouse}", warehouse)
        return checks

"""The `lely` command.

    lely validate                 config, options, references: offline; the wiring
    lely steps                    plugins: options, outputs, what each can do
    lely plan -t <target> [--destroy] [-o plan.json] [-f rich|json]
    lely show plan.json [-f rich|json]
    lely apply [plan.json] [-t <target>] [--yes] [--allow-destructive] [--from <step>]
    lely destroy [destroy.json] -t <target> [--yes] [--from <step>]
    lely status -t <target> [-f rich|json]
    lely doctor

`-t` is always given to a command that touches a workspace: there is no default
target. The workspace comes from `--profile`, or from the variables the
Databricks CLI and SDK already read.

Nothing that changes a workspace runs unasked: `apply` and `destroy` ask, or
were given `--yes`. With no terminal and no `--yes` they refuse. To destroy at
a terminal, the answer is the target's name.

Exit codes: 0 done, 1 something failed, 2 lely refused — plan again.
"""

from __future__ import annotations

import functools
import os
import shutil
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.console import Console, Group
from rich.markup import escape
from rich.text import Text

from lely import (
    __version__,
    approval,
    config,
    options,
    planfile,
    planning,
    registry,
    running,
    source,
)
from lely import step as contract
from lely.databricks import DatabricksCli
from lely.errors import LelyError, Refused
from lely.model import KNOWN, Plan, PlannedStep, Result, Workspace
from lely.render.rich import (
    render_plan,
    result_view,
    status_view,
    step_lines,
    wiring_view,
)

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="One plan for your whole Databricks deploy.",
)
out = Console(highlight=False)
err = Console(stderr=True, highlight=False)

#: How lely runs the Databricks CLI. Tests point it at a fake.
DATABRICKS: tuple[str, ...] = ("databricks",)


class Format(StrEnum):
    rich = "rich"
    json = "json"


ConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        "-c",
        help="lely.yml, or a pyproject.toml with [tool.lely]. Found from here up "
        "when not given.",
    ),
]
TargetOption = Annotated[
    str, typer.Option("--target", "-t", help="The target. There is no default.")
]
ProfileOption = Annotated[
    str | None,
    typer.Option(
        "--profile", "-p", help="A ~/.databrickscfg profile, for the CLI and plugins."
    ),
]
FormatOption = Annotated[Format, typer.Option("--format", "-f", help="How to show it.")]
YesOption = Annotated[
    bool, typer.Option("--yes", help="Don't ask: consent is given in the command.")
]
FromOption = Annotated[
    str | None,
    typer.Option(
        "--from",
        help="Start at this step; the ones passed over are planned, not run.",
    ),
]


def _version(value: bool) -> None:
    if value:
        out.print(f"lely {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version", callback=_version, is_eager=True, help="Show the version."
        ),
    ] = None,
) -> None:
    """One plan for your whole Databricks deploy."""


class _Log:
    def info(self, message: str) -> None:
        err.print(f"[dim]… {escape(message)}[/]")


def _fail(error: Exception, *, refusals: bool = True) -> typer.Exit:
    """Say what went wrong, and end with 2 for a refusal and 1 for a failure.

    `plan`, `status`, `validate` and `doctor` change nothing, so there is
    nothing to plan again for: they end with 1.
    """
    err.print(f"[red]{escape(str(error))}[/]")
    return typer.Exit(2 if refusals and isinstance(error, Refused) else 1)


# -- the edges: the workspace, the terminal ---------------------------------------


def _whoami(profile: str | None) -> Workspace:
    """Which workspace this run talks to, and as whom — asked of the SDK, which
    reads the same profile and variables as the CLI."""
    from databricks.sdk import WorkspaceClient

    try:
        client = WorkspaceClient(profile=profile)
        me = client.current_user.me()
    except Exception as error:
        raise LelyError(
            f"Can't reach a workspace: {error}\nPass --profile, or set the variables "
            "the Databricks CLI reads. `lely doctor` shows what lely sees."
        ) from None
    return Workspace(host=client.config.host or "?", identity=me.user_name or "?")


def _connect(profile: str | None) -> WorkspaceClient:
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(profile=profile)


def _powers(profile: str | None) -> str:
    """What these credentials may do, as far as lely can tell.

    TODO(verify): no API says "read-only" in general. Being a workspace admin is
    the one thing that can be read off.
    """
    from databricks.sdk import WorkspaceClient

    me = WorkspaceClient(profile=profile).current_user.me()
    if any(group.display == "admins" for group in me.groups or []):
        return "a workspace admin: these credentials can change anything"
    return "not a workspace admin; lely can't tell what else these credentials may change"


def _interactive() -> bool:
    return sys.stdin.isatty()


#: Tests put fakes here.
WHOAMI: Callable[[str | None], Workspace] = _whoami
CONNECT: Callable[[str | None], Any] = _connect
POWERS: Callable[[str | None], str] = _powers


@dataclass(frozen=True, slots=True)
class _Run:
    """What every command that touches a workspace is given."""

    config: config.Config
    workspace: Workspace
    env: Mapping[str, str]
    databricks: DatabricksCli
    connect: Callable[[], Any]

    @property
    def edges(self) -> dict[str, Any]:
        return {
            "workspace": self.workspace,
            "env": self.env,
            "databricks": self.databricks,
            "log": _Log(),
            "connect": self.connect,
        }


def _load(path: Path | None) -> config.Config:
    return config.load(path if path is not None else config.find(Path.cwd()))


def _run(path: Path | None, profile: str | None) -> _Run:
    loaded = _load(path)
    planning.check(loaded)
    env = dict(os.environ)
    if profile:
        env["DATABRICKS_CONFIG_PROFILE"] = profile
    return _Run(
        config=loaded,
        workspace=WHOAMI(profile),
        env=env,
        databricks=DatabricksCli(DATABRICKS, profile, env),
        connect=functools.cache(lambda: CONNECT(profile)),
    )


def _consent(question: str, yes: bool) -> None:
    """Nothing that changes a workspace runs unasked."""
    if yes:
        return
    if not _interactive():
        raise Refused(
            "There is no terminal to ask at, and the command doesn't give consent. "
            "Pass --yes to run without asking."
        )
    if not _confirm(question):
        raise Refused("Not approved. Nothing was run.")


def _confirm(question: str) -> bool:
    try:
        return typer.confirm(question, default=False, err=True)
    except (typer.Abort, EOFError):
        return False


def _consent_to_destroy(plan: Plan, yes: bool) -> None:
    """To destroy at a terminal, the answer is the target's name — not `y`, so
    that `prod` is never destroyed by a reflex."""
    if yes:
        return
    if not _interactive():
        raise Refused(
            "There is no terminal to ask at, and the command doesn't give consent. "
            f"Pass --yes to destroy target `{plan.target}` without asking."
        )
    try:
        answer = typer.prompt(
            f"This destroys target `{plan.target}` on {plan.workspace}.\n"
            "Type the target's name to go on",
            default="",
            show_default=False,
            err=True,
        )
    except (typer.Abort, EOFError):
        answer = ""
    if answer.strip() != plan.target:
        raise Refused("That isn't the target's name. Nothing was destroyed.")


def _at_waiting(plan: Plan, yes: bool) -> running.AtWaiting:
    """What `apply` without a file does at a step that was waiting: `--yes`
    runs it; at a terminal lely shows it and asks once more."""

    def ask(step: PlannedStep) -> bool:
        err.print()
        err.print(Group(*step_lines(step)))
        if yes:
            return True
        if not _interactive():
            return False
        return _confirm(
            f"Run step `{step.name}` on target `{plan.target}` ({plan.workspace})?"
        )

    return ask


# -- commands that change nothing -------------------------------------------------


@app.command()
def validate(path: ConfigOption = None) -> None:
    """Check the config without a workspace, and print the wiring."""
    try:
        loaded = _load(path)
        wires = planning.check(loaded)
    except LelyError as error:
        raise _fail(error, refusals=False) from None
    count = len(loaded.steps)
    out.print(
        f"[green]✓[/] {escape(str(loaded.path))}: {count} step{'s' if count != 1 else ''}"
    )
    out.print()
    out.print(wiring_view(wires))


@app.command()
def steps(path: ConfigOption = None) -> None:
    """List the plugins: installed, and the ones this project names."""
    names = sorted(registry.installed())
    root = Path.cwd()
    try:
        loaded = _load(path)
    except LelyError as error:
        if path is not None:
            raise _fail(error, refusals=False) from None
    else:
        root = loaded.root
        names += [s.uses for s in loaded.steps if s.uses not in names]
    for name in dict.fromkeys(names):
        try:
            found = registry.find(name, root)
        except LelyError as error:
            err.print(f"[red]{escape(name)}[/]: {escape(str(error))}")
            continue
        doc = (found.cls.__doc__ or "").strip().splitlines()
        out.print(
            f"[bold]{escape(name)}[/]  [dim]{escape(found.source)}[/]"
            + (f"\n  {escape(doc[0])}" if doc else "")
        )
        for f in options.fields_of(found.options):
            default = "required" if f.required else f"default {f.default}"
            out.print(
                f"    {escape(f.name)}: {escape(f.type)}  [dim]{escape(default)}[/]"
            )
        for line in _gives(found.cls):
            out.print(f"    [dim]gives[/]  {escape(line)}")
        out.print(f"    [dim]can[/]    {escape(_can(found.cls))}")


def _gives(cls: type) -> list[str]:
    """What a plugin gives, one line per answer to "when is it known?"."""
    if callable(getattr(cls, "outputs", None)):
        return ["what a step lists, by its options"]
    declared = contract.declared(cls, {})
    lines = []
    for known, words in KNOWN.items():
        names = [output.name for output in declared if output.known == known]
        if names:
            lines.append(f"{', '.join(names)} ({words})")
    return lines or ["nothing"]


def _can(cls: type) -> str:
    can = ["plan"]
    if contract.applies(cls):
        can.append("apply")
    if contract.lists(cls):
        can.append("list")
    if contract.destroys(cls):
        can.append("destroy")
    return ", ".join(can)


@app.command()
def plan(
    target: TargetOption,
    path: ConfigOption = None,
    destroy: Annotated[
        bool, typer.Option("--destroy", help="Plan a destroy instead of an apply.")
    ] = False,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write the plan to a file.")
    ] = None,
    output_format: FormatOption = Format.rich,
    profile: ProfileOption = None,
) -> None:
    """Plan every step, in order, and show what would change. Changes nothing."""
    try:
        run = _run(path, profile)
        built = planning.plan(
            run.config,
            target=target,
            source=source.read(run.config.root),
            kind="destroy" if destroy else "apply",
            **run.edges,
        )
    except LelyError as error:
        raise _fail(error, refusals=False) from None
    _show_plan(built, output_format, output)


@app.command()
def show(
    plan_file: Annotated[Path, typer.Argument(help="A plan written by `lely plan -o`.")],
    output_format: FormatOption = Format.rich,
) -> None:
    """Show a saved plan."""
    try:
        built = _read_plan(plan_file)
    except LelyError as error:
        raise _fail(error, refusals=False) from None
    _show_plan(built, output_format, None)


@app.command()
def status(
    target: TargetOption,
    path: ConfigOption = None,
    output_format: FormatOption = Format.rich,
    profile: ProfileOption = None,
) -> None:
    """Show what is deployed right now, per step. Changes nothing."""
    try:
        run = _run(path, profile)
        found = running.status(run.config, target=target, **run.edges)
    except LelyError as error:
        raise _fail(error, refusals=False) from None
    if output_format is Format.json:
        _echo_json(planfile.status_to_json(found))
    else:
        out.print(status_view(found))


@app.command()
def doctor(path: ConfigOption = None, profile: ProfileOption = None) -> None:
    """Report whether the tools are there, and which workspace lely reaches."""
    failed = False

    def line(ok: bool | None, text: str) -> None:
        nonlocal failed
        failed = failed or ok is False
        mark = {True: "[green]✓[/]", False: "[red]✗[/]", None: "[yellow]![/]"}[ok]
        out.print(f"{mark} {escape(text)}")

    version = _program_says(DATABRICKS, "--version")
    if version is None:
        line(False, f"the Databricks CLI: `{DATABRICKS[0]}` isn't on PATH")
    else:
        line(True, f"the Databricks CLI: {version}")
        line(None, "bundles need the direct engine (GA in CLI v1.3.0)")
    try:
        workspace = WHOAMI(profile)
    except LelyError as error:
        line(False, str(error))
    else:
        line(True, f"the workspace: {workspace}")
        try:
            line(None, POWERS(profile))
        except Exception as error:
            line(None, f"what these credentials may do couldn't be read: {error}")
    line(
        None,
        "planning runs the project's own code — a plugin in the repo, a `command` "
        "step's plan command. On a pull request, give `lely plan` credentials that "
        "can read and nothing more.",
    )
    try:
        loaded = _load(path)
    except LelyError as error:
        line(None, f"no project checked: {error}")
    else:
        for step in loaded.steps:
            try:
                found = registry.find(step.uses, loaded.root)
            except LelyError as error:
                line(False, f"step `{step.name}`: {error}")
                continue
            said = config.written(step.options)
            for program in _programs(found.cls, said if isinstance(said, dict) else {}):
                there = _there(program, loaded.root)
                line(
                    there,
                    f"step `{step.name}` runs `{program}`"
                    + ("" if there else ": not found"),
                )
    if failed:
        raise typer.Exit(1)


def _programs(cls: type, written: Mapping[str, Any]) -> tuple[str, ...]:
    """The programs a step runs, as its plugin names them (`programs`)."""
    listed = getattr(cls, "programs", None)
    if not callable(listed):
        return ()
    return tuple(dict.fromkeys(listed(written)))


def _there(program: str, root: Path) -> bool:
    if program == "databricks":
        program = DATABRICKS[0]
    if "/" in program:
        return os.access(root / program, os.X_OK)
    return shutil.which(program) is not None


def _program_says(command: tuple[str, ...], *args: str) -> str | None:
    from lely.process import ProcessError
    from lely.process import run as run_program

    try:
        result = run_program([*command, *args], Path.cwd())
    except ProcessError:
        return None
    said = (result.stdout or result.stderr).strip().splitlines()
    return said[0] if said else f"exit {result.returncode}"


# -- commands that change a workspace -----------------------------------------------


@app.command()
def apply(
    plan_file: Annotated[
        Path | None,
        typer.Argument(help="A reviewed plan from `lely plan -o`. Without one: -t."),
    ] = None,
    target: Annotated[
        str | None, typer.Option("--target", "-t", help="The target, without a file.")
    ] = None,
    path: ConfigOption = None,
    yes: YesOption = False,
    allow_destructive: Annotated[
        bool,
        typer.Option("--allow-destructive", help="Apply changes marked destructive."),
    ] = False,
    from_step: FromOption = None,
    output_format: FormatOption = Format.rich,
    profile: ProfileOption = None,
) -> None:
    """Run a reviewed plan — or, with -t, plan, show, ask and run."""
    try:
        run = _run(path, profile)
        if plan_file is not None:
            approved = _read_plan(plan_file)
            if approved.kind != "apply":
                raise Refused(
                    "This is a plan to destroy, and `lely apply` only applies. Run it "
                    f"with `lely destroy {plan_file} -t {approved.target}`."
                )
            if target is not None and target != approved.target:
                raise Refused(
                    f"The plan was made for target `{approved.target}`, and the "
                    f"command says `{target}`."
                )
            _still_holds(approved, run)
            at_waiting = None
        else:
            if target is None:
                raise Refused("Give the target: `lely apply -t <target>`.")
            approved = planning.plan(
                run.config,
                target=target,
                source=source.read(run.config.root),
                **run.edges,
            )
            at_waiting = _at_waiting(approved, yes)
        render_plan(approved, err)
        approval.destructive_allowed(approved.steps, allow_destructive)
        if not approved.summary.empty:
            _consent(
                f"Apply this plan to target `{approved.target}` on {approved.workspace}?",
                yes,
            )
        result = running.apply(
            run.config,
            approved,
            allow_destructive=allow_destructive,
            from_step=from_step,
            at_waiting=at_waiting,
            **run.edges,
        )
    except LelyError as error:
        raise _fail(error) from None
    _finish(result, output_format)


@app.command()
def destroy(
    target: TargetOption,
    plan_file: Annotated[
        Path | None,
        typer.Argument(help="A reviewed plan from `lely plan --destroy -o`."),
    ] = None,
    path: ConfigOption = None,
    yes: YesOption = False,
    from_step: FromOption = None,
    output_format: FormatOption = Format.rich,
    profile: ProfileOption = None,
) -> None:
    """Take a target down again: plan the destroy, show it, ask, and run."""
    try:
        run = _run(path, profile)
        if plan_file is not None:
            approved = _read_plan(plan_file)
            if approved.kind != "destroy":
                raise Refused(
                    "This is a plan to apply, and `lely destroy` only destroys. Run "
                    f"it with `lely apply {plan_file}`."
                )
            if target != approved.target:
                raise Refused(
                    f"The plan was made for target `{approved.target}`, and the "
                    f"command says `{target}`."
                )
            _still_holds(approved, run)
        else:
            approved = planning.plan(
                run.config,
                target=target,
                source=source.read(run.config.root),
                kind="destroy",
                **run.edges,
            )
        render_plan(approved, err)
        if not approved.summary.empty:
            _consent_to_destroy(approved, yes)
        result = running.destroy(run.config, approved, from_step=from_step, **run.edges)
    except LelyError as error:
        raise _fail(error) from None
    _finish(result, output_format)


def _still_holds(approved: Plan, run: _Run) -> None:
    """A plan file is held to the workspace, the project and the tree it was
    made for, before anything runs."""
    approval.same_workspace(approved, run.workspace)
    approval.same_project(
        approved,
        [(s.name, s.uses, planning.made_from(s)) for s in run.config.steps],
    )
    approval.same_source(approved, source.read(run.config.root))


def _finish(result: Result, output_format: Format) -> None:
    if output_format is Format.json:
        _echo_json(planfile.result_to_json(result))
    else:
        out.print(result_view(result))
    if result.outcome != "done":
        raise typer.Exit(2 if result.outcome == "refused" else 1)


# -----------------------------------------------------------------------------


def _read_plan(plan_file: Path) -> Plan:
    try:
        return planfile.loads(plan_file.read_text(encoding="utf-8"))
    except OSError as error:
        raise LelyError(f"{plan_file}: {error.strerror or error}") from None


def _show_plan(built: Plan, output_format: Format, output: Path | None) -> None:
    if output_format is Format.json:
        text = planfile.dumps(built)
        if output is None:
            typer.echo(text, nl=False)
            return
    else:
        render_plan(built, out)
    if output is not None:
        output.write_text(planfile.dumps(built), encoding="utf-8")
        out.print(Text.assemble("\n", ("Wrote", "green"), f" {output}"))


def _echo_json(document: dict[str, Any]) -> None:
    import json

    typer.echo(json.dumps(document, indent=2))


def main() -> None:
    app()

"""The `sluis` command.

    sluis validate                 config, references, step options: offline
    sluis steps                    installed steps and their options
    sluis plan -t <target> [-o plan.json] [-f rich|json]
    sluis show plan.json [-f rich|json]

`apply` and `doctor` come with milestone 2.
"""

from __future__ import annotations

import functools
import os
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from rich.markup import escape

from sluis import __version__, config, options, planfile, planning, registry
from sluis.databricks import DatabricksCli
from sluis.errors import SluisError
from sluis.model import Plan
from sluis.render.rich import render_plan

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="One plan and one apply for a whole Databricks deploy.",
)
out = Console(highlight=False)
err = Console(stderr=True, highlight=False)

#: How sluis runs the Databricks CLI. Tests point it at a recording.
DATABRICKS: tuple[str, ...] = ("databricks",)


class Format(StrEnum):
    rich = "rich"
    json = "json"


ConfigOption = Annotated[Path, typer.Option("--config", "-c", help="Path to sluis.yml.")]
TargetOption = Annotated[
    str | None,
    typer.Option("--target", "-t", help="The bundle target; its default if omitted."),
]
ProfileOption = Annotated[
    str | None,
    typer.Option(
        "--profile", "-p", help="A ~/.databrickscfg profile, for the CLI and steps."
    ),
]
FormatOption = Annotated[
    Format, typer.Option("--format", "-f", help="How to show the plan.")
]


def _version(value: bool) -> None:
    if value:
        out.print(f"sluis {__version__}")
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
    """One plan and one apply for a whole Databricks deploy."""


class _Log:
    def info(self, message: str) -> None:
        err.print(f"[dim]… {escape(message)}[/]")


def _fail(error: SluisError) -> typer.Exit:
    err.print(f"[red]{escape(str(error))}[/]")
    return typer.Exit(1)


@app.command()
def validate(path: ConfigOption = Path(config.CONFIG_FILE)) -> None:
    """Check sluis.yml without a workspace: steps, options, references."""
    try:
        loaded = config.load(path)
        planning.check(loaded)
    except SluisError as error:
        raise _fail(error) from None
    out.print(
        f"[green]✓[/] {escape(str(path))}: {len(loaded.pre)} pre, "
        f"{len(loaded.post)} post step{'s' if len(loaded.post) != 1 else ''}"
        + (
            f", {len(loaded.bundle_vars.entries)} bundle variable(s)"
            if loaded.bundle_vars
            else ""
        )
    )


@app.command()
def steps() -> None:
    """List the installed steps and their options."""
    for name in sorted(registry.installed()):
        try:
            found = registry.find(name, Path.cwd())
        except SluisError as error:
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


@app.command()
def plan(
    path: ConfigOption = Path(config.CONFIG_FILE),
    target: TargetOption = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write the plan to a file.")
    ] = None,
    output_format: FormatOption = Format.rich,
    profile: ProfileOption = None,
) -> None:
    """Plan every step and the bundle, and show what would change."""
    try:
        loaded = config.load(path)
        env = dict(os.environ)
        if profile:
            env["DATABRICKS_CONFIG_PROFILE"] = profile
        built = planning.plan(
            loaded,
            target=target,
            databricks=DatabricksCli(loaded.bundle_dir, DATABRICKS, profile),
            env=env,
            log=_Log(),
            connect=functools.partial(_workspace, profile=profile),
        )
    except SluisError as error:
        raise _fail(error) from None
    _output(built, output_format, output)


@app.command()
def show(
    plan_file: Annotated[Path, typer.Argument(help="A plan written by `sluis plan -o`.")],
    output_format: FormatOption = Format.rich,
) -> None:
    """Show a saved plan."""
    try:
        built = planfile.loads(plan_file.read_text(encoding="utf-8"))
    except (OSError, SluisError) as error:
        err.print(f"[red]{escape(str(error))}[/]")
        raise typer.Exit(1) from None
    _output(built, output_format, None)


def _output(built: Plan, output_format: Format, output: Path | None) -> None:
    if output_format is Format.json:
        text = planfile.dumps(built)
        if output is None:
            typer.echo(text, nl=False)
            return
    else:
        render_plan(built, out)
    if output is not None:
        output.write_text(planfile.dumps(built), encoding="utf-8")
        out.print(f"\n[green]Wrote[/] {escape(str(output))}")


def _workspace(host: str | None, *, profile: str | None) -> WorkspaceClient:
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(host=host, profile=profile)


def main() -> None:
    app()

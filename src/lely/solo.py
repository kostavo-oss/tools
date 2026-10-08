"""A step on its own: the command line `Step.main()` gives (`spec/011`).

    uv run ops/scope.py plan -t dev --name shop_data [-o plan.json]
    uv run ops/scope.py apply plan.json | apply -t dev --name shop_data [--yes]
    uv run ops/scope.py destroy -t dev --name shop_data
    uv run ops/scope.py status -t dev --name shop_data
    uv run ops/scope.py check -t dev --name shop_data [--live]

The step is the class; the command line is derived from it. Everything here
goes through lely's own planning, running, plan file and approval, with a
config of one step made from the flags — so a plan written here is a one-step
lely plan, `lely apply plan.json` takes it, and the same checks are made
before anything runs.
"""

from __future__ import annotations

import dataclasses
import functools
import inspect
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import typer
from typer.core import TyperCommand, TyperGroup, TyperOption

from lely import approval, cli, config, planfile, planning, running, source, testing
from lely import step as contract
from lely.databricks import DatabricksCli
from lely.errors import LelyError, Refused
from lely.flags import Flag, block_from, flags_of, options_of
from lely.model import Plan, Source
from lely.render.rich import render_plan, result_view, status_view

OUT = cli.out
ERR = cli.err


def main(cls: type, argv: Sequence[str] | None = None) -> None:
    """Run the step's own command line. `Step.main()` calls this."""
    group = app_for(cls)
    try:
        group.main(args=None if argv is None else list(argv), prog_name=_prog(cls))
    except SystemExit:
        raise
    except LelyError as error:  # pragma: no cover - every command catches its own
        raise cli._fail(error) from None


def app_for(cls: type) -> TyperGroup:
    """The step's command line, as a group: what a test invokes."""
    flags = flags_of(_options_of(cls))
    name = _name(cls)
    doc = (inspect.getdoc(cls) or "").split("\n")[0]
    group = TyperGroup(
        name=name,
        help=f"{doc}\n\nA lely step, on its own: {cls.__qualname__}.",
        no_args_is_help=True,
        rich_markup_mode=None,
    )
    group.add_command(
        TyperCommand(
            "plan",
            help="Plan the step and show what would change. Changes nothing.",
            params=[*_every(flags), _output(), _format()],
            callback=functools.partial(_plan, cls, flags),
        )
    )
    group.add_command(
        TyperCommand(
            "apply",
            help="Run a reviewed plan — or, with -t, plan, show, ask and run.",
            params=[
                _plan_file("A reviewed plan from `plan -o`. Without one: -t."),
                *_every(flags, target_required=False),
                _yes(),
                TyperOption(
                    param_decls=["--allow-destructive"],
                    is_flag=True,
                    help="Apply changes marked destructive.",
                ),
                _format(),
            ],
            callback=functools.partial(_apply, cls, flags),
        )
    )
    group.add_command(
        TyperCommand(
            "destroy",
            help="Take the step down again: plan the destroy, show it, ask, and run.",
            params=[
                _plan_file("A reviewed plan from `plan --destroy -o`."),
                *_every(flags),
                _yes(),
                _format(),
            ],
            callback=functools.partial(_destroy, cls, flags),
        )
    )
    group.add_command(
        TyperCommand(
            "status",
            help="Show what exists because of the step. Changes nothing.",
            params=[*_every(flags), _format()],
            callback=functools.partial(_status, cls, flags),
        )
    )
    group.add_command(
        TyperCommand(
            "check",
            help="Hold the step to the rules: plan reading only, through a plan file"
            " and back. --live applies and destroys on the target as well.",
            params=[
                *_every(flags),
                TyperOption(
                    param_decls=["--live"],
                    is_flag=True,
                    help="Apply, plan again, destroy: makes and removes things.",
                ),
            ],
            callback=functools.partial(_check, cls, flags),
        )
    )
    return group


# -- the options every command takes ------------------------------------------------


def _every(flags: Sequence[Flag], *, target_required: bool = True) -> list[TyperOption]:
    return [
        TyperOption(
            param_decls=["--target", "-t", "target"],
            type=str,
            required=target_required,
            help="The target, as this step reads it.",
        ),
        TyperOption(
            param_decls=["--profile", "profile"],
            type=str,
            default=None,
            help="A profile from ~/.databrickscfg. Default: whatever signs the CLI in.",
        ),
        *options_of(flags),
    ]


def _output() -> TyperOption:
    return TyperOption(
        param_decls=["--output", "-o", "output"],
        type=str,
        default=None,
        help="Write the plan to a file: a one-step lely plan.",
    )


def _format() -> TyperOption:
    return TyperOption(
        param_decls=["--format", "-f", "output_format"],
        type=str,
        default="rich",
        help="rich, json or md.",
    )


def _yes() -> TyperOption:
    return TyperOption(
        param_decls=["--yes", "yes"],
        is_flag=True,
        help="Don't ask: consent is given in the command.",
    )


def _plan_file(help: str) -> TyperOption:
    return TyperOption(
        param_decls=["--plan-file", "plan_file"], type=str, default=None, help=help
    )


# -- the step as a config of one step ----------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class _Solo:
    """One step, as lely sees a project of one step."""

    config: config.Config
    step: config.StepConfig
    run: cli._Run


def _solo(cls: type, flags: Sequence[Flag], values: dict[str, Any]) -> _Solo:
    profile = values.pop("profile", None)
    block = block_from(flags, values)
    root = Path.cwd()
    step = config.StepConfig(
        name=_name(cls),
        uses=_uses(cls, root),
        options=block,
        targets=None,
        loc=config.Loc("command line", 0, 0),
    )
    loaded = config.Config(path=root / "<step on its own>", steps=(step,))
    planning.check(loaded)
    env = dict(os.environ)
    if profile:
        env["DATABRICKS_CONFIG_PROFILE"] = profile
    run = cli._Run(
        config=loaded,
        workspace=cli.WHOAMI(profile),
        env=env,
        databricks=DatabricksCli(cli.DATABRICKS, profile, env),
        connect=functools.cache(lambda: cli.CONNECT(profile)),
    )
    return _Solo(loaded, step, run)


def _uses(cls: type, root: Path) -> str:
    """How a `lely.yml` in `root` would name this class: `./path/file.py:Class`.

    The same spelling as under lely, so the plan file names the step the way
    a config would, and `made_from` agrees.
    """
    try:
        file = inspect.getsourcefile(cls)
    except TypeError:
        file = None
    if file is None:
        raise LelyError(f"{cls.__qualname__} isn't in a file lely can name.")
    relative = os.path.relpath(Path(file).resolve(), root)
    if not relative.startswith("../"):
        relative = "./" + relative
    return f"{relative}:{cls.__qualname__}"


def _name(cls: type) -> str:
    return cls.__qualname__.rsplit(".", 1)[-1].lower()


def _prog(cls: type) -> str:
    try:
        file = inspect.getsourcefile(cls)
    except TypeError:
        file = None
    return Path(file).name if file else _name(cls)


def _options_of(cls: type) -> type:
    options = getattr(cls, "Options", None)
    if not (isinstance(options, type) and dataclasses.is_dataclass(options)):
        raise LelyError(f"{cls.__qualname__} has no `Options` dataclass: not a step.")
    return options


def _fmt(output_format: str) -> cli.Format:
    try:
        return cli.Format(output_format)
    except ValueError:
        raise Refused(f"-f takes rich, json or md, not `{output_format}`.") from None


# -- the commands --------------------------------------------------------------------


def _guard(command: Callable[..., None]) -> Callable[..., None]:
    @functools.wraps(command)
    def guarded(*args: Any, **kwargs: Any) -> None:
        try:
            command(*args, **kwargs)
        except LelyError as error:
            raise cli._fail(error, refusals=isinstance(error, Refused)) from None

    return guarded


@_guard
def _plan(cls: type, flags: Sequence[Flag], **values: Any) -> None:
    output = values.pop("output", None)
    fmt = _fmt(values.pop("output_format"))
    solo = _solo(cls, flags, values)
    out = Path(output) if output else None
    built = planning.plan(
        solo.config,
        target=values["target"],
        source=source.read(solo.config.root, out),
        **solo.run.edges,
    )
    cli._show_plan(built, fmt, out)


@_guard
def _apply(cls: type, flags: Sequence[Flag], **values: Any) -> None:
    plan_file = values.pop("plan_file", None)
    yes = values.pop("yes", False)
    allow_destructive = values.pop("allow_destructive", False)
    fmt = _fmt(values.pop("output_format"))
    target = values.get("target")
    if plan_file is None and target is None:
        raise Refused("Give the target: `apply -t <target>`, or a plan file.")
    solo = _solo(cls, flags, values)
    run = solo.run
    if plan_file is not None:
        approved = _read(Path(plan_file), solo, target)
        running.check_kind(approved, "apply", plan_file)
        at_waiting = None
    else:
        assert target is not None
        running.check_applies(solo.config, target)
        approved = planning.plan(
            solo.config, target=target, source=_unsaved(solo.config.root), **run.edges
        )
        at_waiting = cli._at_waiting(approved, run, yes, None)
    render_plan(approved, ERR, saved=plan_file is not None)
    approval.destructive_allowed(approved.steps, allow_destructive)
    if not cli._nothing_in(approved):
        cli._consent(f"Apply this plan to {cli._where(approved, run)}?", yes)
    result = running.apply(
        solo.config,
        approved,
        allow_destructive=allow_destructive,
        at_waiting=at_waiting,
        **run.edges,
    )
    _finish(result, fmt)


@_guard
def _destroy(cls: type, flags: Sequence[Flag], **values: Any) -> None:
    plan_file = values.pop("plan_file", None)
    yes = values.pop("yes", False)
    fmt = _fmt(values.pop("output_format"))
    solo = _solo(cls, flags, values)
    run = solo.run
    target = values["target"]
    if plan_file is not None:
        approved = _read(Path(plan_file), solo, target)
        running.check_kind(approved, "destroy", plan_file)
    else:
        approved = planning.plan(
            solo.config,
            target=target,
            source=_unsaved(solo.config.root),
            kind="destroy",
            **run.edges,
        )
    render_plan(approved, ERR, saved=plan_file is not None)
    if not cli._nothing_in(approved):
        cli._consent_to_destroy(approved, run, yes)
    result = running.destroy(solo.config, approved, **run.edges)
    _finish(result, fmt)


@_guard
def _status(cls: type, flags: Sequence[Flag], **values: Any) -> None:
    fmt = _fmt(values.pop("output_format"))
    solo = _solo(cls, flags, values)
    found = running.status(solo.config, target=values["target"], **solo.run.edges)
    if fmt is cli.Format.json:
        cli._echo_json(planfile.status_to_json(found))
    elif fmt is cli.Format.md:
        from lely.render import markdown

        typer.echo(markdown.status_markdown(found), nl=False)
    else:
        OUT.print(status_view(found))


@_guard
def _check(cls: type, flags: Sequence[Flag], **values: Any) -> None:
    """`lely.testing`'s checks, against the real target.

    `plan` and `overview` run behind a Databricks CLI that refuses anything but
    a read; the workspace itself is reached as it is, so what a step does
    through the SDK is its own. `--live` applies and destroys on the target.
    """
    live = values.pop("live", False)
    solo = _solo(cls, flags, values)
    prepared = planning.Session(
        solo.config,
        values["target"],
        solo.run.workspace,
        solo.run.env,
        solo.run.databricks,
        cli._Log(),
        solo.run.connect,
    ).prepare(solo.step)
    if prepared.waits_for:  # pragma: no cover - refused as a reference already
        raise Refused(planning.missing(prepared.waits_for))
    ctx = testing.context(
        prepared.options,
        target=values["target"],
        name=solo.step.name,
        root=solo.config.root,
        host=solo.run.workspace.host,
        env=solo.run.env,
        databricks=solo.run.databricks,
        connect=solo.run.connect,
    )
    written = config.written(solo.step.options)
    if not isinstance(written, dict):  # pragma: no cover - a block is a mapping
        written = {}
    passed: list[str] = []
    try:
        plugin = cls()
        testing.check_plan(plugin, ctx, written=written)
        passed.append("plan changes nothing, and survives a plan file")
        if contract.lists(cls):
            testing.check_overview(plugin, ctx)
            passed.append("overview changes nothing, and every line is complete")
        if live and contract.destroys(cls):
            # plan, apply, destroy, plan again: one cycle, from a clean state
            testing.check_destroy(plugin, ctx, written=written)
            passed.append("apply does what the plan says, and destroy undoes it")
        elif live:
            testing.check_apply(plugin, ctx, written=written)
            passed.append("apply does what the plan says, and no more")
            passed.append("destroy: the step has none, and lely destroy skips it")
    except AssertionError as error:
        for line in passed:
            ERR.print(f"[green]ok[/]      {line}")
        ERR.print(f"[red]failed[/]  {error}")
        raise typer.Exit(1) from None
    for line in passed:
        ERR.print(f"[green]ok[/]      {line}")
    if not live:
        ERR.print("[dim]--live would apply, plan again and destroy on the target[/]")


# -- shared ------------------------------------------------------------------------


def _read(plan_file: Path, solo: _Solo, target: str | None) -> Plan:
    approved = cli._read_plan(plan_file, to_run=True)
    if target is not None and target != approved.target:
        raise Refused(
            f"The plan was made for target `{approved.target}`, and the command says "
            f"`{target}`."
        )
    if [s.name for s in approved.steps] != [solo.step.name]:
        raise Refused(
            f"{plan_file} is a plan for {', '.join(s.name for s in approved.steps)}, "
            f"not for this step alone (`{solo.step.name}`): `lely apply` runs it."
        )
    approval.same_workspace(approved, solo.run.workspace)
    approval.same_project(
        approved, [(s.name, s.uses, planning.made_from(s)) for s in solo.config.steps]
    )
    approval.same_source(approved, source.read(solo.config.root, plan_file))
    return approved


def _unsaved(root: Path) -> Source:
    try:
        return source.read(root)
    except source.SourceError:
        return Source()


def _finish(result: Any, fmt: cli.Format) -> None:
    if fmt is cli.Format.json:
        cli._echo_json(planfile.result_to_json(result))
    elif fmt is cli.Format.md:
        from lely.render import markdown

        typer.echo(markdown.result_markdown(result), nl=False)
    else:
        OUT.print(result_view(result))
    if result.outcome != "done":
        raise typer.Exit(2 if result.outcome == "refused" else 1)


__all__ = ["app_for", "main"]

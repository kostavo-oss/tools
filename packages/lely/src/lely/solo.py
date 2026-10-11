"""A step on its own: the command line `Step.main()` gives (SOLO-1).

    uv run ops/scope.py plan -t dev --name shop_data [-o plan.json] [--destroy]
    uv run ops/scope.py apply --plan-file plan.json --name shop_data
    uv run ops/scope.py apply -t dev --name shop_data [--yes]
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
import json
import os
import typing
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import typer
from rich.text import Text
from typer.core import TyperCommand, TyperGroup, TyperOption

from lely import approval, cli, config, planfile, planning, running, source, testing
from lely import step as contract
from lely.databricks import DatabricksCli
from lely.errors import LelyError, Refused
from lely.flags import Flag, block_from, flags_of, options_of
from lely.model import KNOWN, Plan, Secret, Source, Value
from lely.refs import Given, literal, match
from lely.render import words
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
            params=[
                *_every(flags),
                _output(),
                TyperOption(
                    param_decls=["--destroy"],
                    is_flag=True,
                    help="Plan taking the step down: what `destroy` would remove.",
                ),
                _format(),
            ],
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
            " and back. --live applies on the target as well, and destroys if the"
            " step can.",
            params=[
                *_every(flags),
                TyperOption(
                    param_decls=["--live"],
                    is_flag=True,
                    help=_LIVE[contract.destroys(cls)][0].capitalize()
                    + ": it makes things on the target, and says so first.",
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
    #: What the flags gave for an option that is a `Secret`: never printed.
    secrets: tuple[str, ...] = ()


def _solo(cls: type, flags: Sequence[Flag], values: dict[str, Any]) -> _Solo:
    profile = values.pop("profile", None)
    block = block_from(flags, values)
    secrets = _secrets(cls, values)
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
    return _Solo(loaded, step, run, secrets)


def _secrets(cls: type, values: dict[str, Any]) -> tuple[str, ...]:
    """The text every `Secret` option was given, as the flags carried it."""
    hints = typing.get_type_hints(_options_of(cls))
    found: list[str] = []
    for name, tp in hints.items():
        if not _holds_secret(tp):
            continue
        given = values.get(name)
        for one in given if isinstance(given, list | tuple) else [given]:
            text = one[1] if isinstance(one, tuple) else one
            if isinstance(text, str) and text:
                # as typed, and as the step is handed it: `$${` is a `${` there
                found += [text, literal(text)]
    return tuple(dict.fromkeys(found))


def _holds_secret(tp: Any) -> bool:
    return tp is Secret or any(_holds_secret(arg) for arg in typing.get_args(tp))


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
    destroy = values.pop("destroy", False)
    fmt = _fmt(values.pop("output_format"))
    solo = _solo(cls, flags, values)
    out = Path(output) if output else None
    given: dict[str, Given] = {}
    built = planning.plan(
        solo.config,
        target=values["target"],
        source=source.read(solo.config.root, out),
        kind="destroy" if destroy else "apply",
        given=given,
        **solo.run.edges,
    )
    cli._show_plan(built, fmt, out)
    if not destroy:  # a destroy gives nothing
        _say_gives(solo, given, fmt, later=True)


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
    given: dict[str, Given] = {}
    result = running.apply(
        solo.config,
        approved,
        allow_destructive=allow_destructive,
        at_waiting=at_waiting,
        given=given,
        **run.edges,
    )
    _finish(result, fmt, lambda: _say_gives(solo, given, fmt, later=False))


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
    does, leaves = _LIVE[contract.destroys(cls)]
    if live:
        # said before anything runs, the reading checks too: once the step is
        # applied it is too late to read what `--live` meant (SOLO-7)
        where = f"target `{values['target']}` on {solo.run.workspace}"
        _say(ERR, Text(f"--live: about to {does}, on {where}. {leaves}", "yellow"))
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
        plugin = cls  # the class: every call is made on a new one, as under lely
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
        _say(ERR, Text(f"--live would {does}, on the target. {leaves}", "dim"))


#: What `check --live` does on the target, and what it leaves there: for a
#: step that can destroy, and for one that can't.
_LIVE = {
    True: (
        "apply the step, destroy it and plan again",
        "It makes what the plan shows, and removes it.",
    ),
    False: (
        "apply the step and plan again",
        "The step has no destroy: what it makes stays.",
    ),
}


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
    approval.same_project(approved, planning.made_from_each(solo.config))
    approval.same_source(approved, source.read(solo.config.root, plan_file))
    return approved


def _unsaved(root: Path) -> Source:
    try:
        return source.read(root)
    except source.SourceError:
        return Source()


def _finish(
    result: Any, fmt: cli.Format, after: Callable[[], None] | None = None
) -> None:
    if fmt is cli.Format.json:
        cli._echo_json(planfile.result_to_json(result))
    elif fmt is cli.Format.md:
        from lely.render import markdown

        typer.echo(markdown.result_markdown(result), nl=False)
    else:
        OUT.print(result_view(result))
    if result.outcome != "done":
        raise typer.Exit(2 if result.outcome == "refused" else 1)
    if after is not None:
        after()


# -- what the step gives (SOLO-8) ----------------------------------------------------


def _say(console: Any, *lines: Text) -> None:
    """Lines of lely's own, with a plugin's words in them: shown, never obeyed,
    and without the run's token."""
    for line in lines:
        line.plain = words.clean(cli._hide(line.plain))
        console.print(line, highlight=False)


def _say_gives(
    solo: _Solo, given: dict[str, Given], fmt: cli.Format, *, later: bool
) -> None:
    """Print what the step gives: after a plan, what it knows and the names of
    what comes later; after an apply, what it returned.

    Under lely a plan shows an output where another step takes it. A step on
    its own has no other step, so it says them itself. With `-f json` or `-f
    md`, stdout holds that and nothing else, and this goes to stderr.
    """
    gives = given.get(solo.step.name)
    if gives is None:
        return
    lines = list(_gives_lines(gives, solo.secrets, later=later))
    if lines:
        console = OUT if fmt is cli.Format.rich else ERR
        _say(console, Text(), Text("Gives:", "bold"), *lines)


def _gives_lines(gives: Given, secrets: Sequence[str], *, later: bool) -> Iterator[Text]:
    for name, value in gives.outputs.items():
        yield Text.assemble(("  → ", "dim"), f"{name} = {_shown(value, secrets)}")
    if not later:
        return
    for name in sorted(gives.later):
        named = match(gives.declared, tuple(name.split(".")))
        when = KNOWN[named.output.known] if named is not None else KNOWN["exists"]
        yield Text(f"  → {name}  known {when}", "dim")
    for output in gives.declared:
        instances = [
            name
            for name in (*gives.outputs, *gives.later)
            if (named := match(gives.declared, tuple(name.split("."))))
            and named.output == output
        ]
        if instances or (output.shape and output.known == "plan"):
            continue  # said above; or a shape with nothing of it in this project
        when = f"known {KNOWN[output.known]}" if output.known != "plan" else "not yet"
        yield Text(f"  → {output.name}  {when}", "dim")


def _shown(value: Value, secrets: Sequence[str]) -> str:
    """A value as it is printed. A `Secret` is `***`, and so is a value that
    holds what a `Secret` option was given: an output that hands an option back
    is not a way round it."""
    if isinstance(value, Secret) or _holds(value, secrets):
        return "***"
    if isinstance(value, str) and len(value.splitlines()) > 1:
        return json.dumps(value)  # on one line: it can't pass for a line of lely's
    return words.shown(value)


def _holds(value: Any, secrets: Sequence[str]) -> bool:
    """Whether a value has a secret anywhere in it: in a text, a key, or a
    number written out."""
    if isinstance(value, dict):
        return any(_holds(k, secrets) or _holds(v, secrets) for k, v in value.items())
    if isinstance(value, list | tuple):
        return any(_holds(item, secrets) for item in value)
    if value is None or isinstance(value, bool):
        return False
    text = value if isinstance(value, str) else json.dumps(value)
    return any(secret in text for secret in secrets)


__all__ = ["app_for", "main"]

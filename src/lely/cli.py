"""The `lely` command.

    lely validate                 config, options, references: offline; the wiring
    lely steps                    plugins: options, outputs, what each can do
    lely schema [-o file]         a JSON Schema of the config, for editors
    lely plan -t <target> [--destroy] [-o plan.json] [-f rich|json|md] [--github]
    lely show plan.json [-f rich|json|md] [--github]
    lely apply [plan.json] [-t <target>] [--yes] [--allow-destructive] [--from <step>]
    lely destroy [destroy.json] -t <target> [--yes] [--from <step>]
                                  (both: [-o result.json] [-f rich|json|md] [--github])
    lely status -t <target> [-f rich|json|md]
    lely ui <plan.json | result.json> [-o page.html] [--no-open]
    lely doctor

`-t` is always given to a command that touches a workspace: there is no default
target. The workspace comes from `--profile`, or from the variables the
Databricks CLI and SDK already read.

Nothing that changes a workspace runs unasked: `apply` and `destroy` ask, or
were given `--yes`. With no terminal and no `--yes` they refuse. To destroy at
a terminal, the answer is the target's name.

Exit codes: 0 done, 1 something failed, 2 lely refused — plan again. A command
line lely can't make sense of ends with 2 as well, whatever the command.
"""

from __future__ import annotations

import contextlib
import errno
import functools
import json
import os
import shutil
import stat
import sys
import tempfile
import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.text import Text

from lely import (
    __version__,
    approval,
    config,
    github,
    options,
    planfile,
    planning,
    registry,
    running,
    source,
)
from lely import schema as schema_
from lely import step as contract
from lely.databricks import DatabricksCli
from lely.errors import LelyError, Refused
from lely.model import (
    KNOWN,
    Plan,
    PlanKind,
    PlannedStep,
    Result,
    Source,
    StepResult,
    Workspace,
)
from lely.render import html, markdown
from lely.render.rich import (
    clean,
    render_plan,
    result_view,
    status_view,
    step_view,
    wiring_view,
)

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    # said, because typer's own default changed (0.20.1): help is Rich markup on
    # every version, so what is escaped in it reads the same on each
    rich_markup_mode="rich",
    # An error lely didn't expect is a traceback, and typer's own (below 0.23)
    # prints every frame's local values with it: `plan` and `apply` hold the
    # run's token and the whole environment in theirs.
    pretty_exceptions_show_locals=False,
    help="One plan for your whole Databricks deploy.",
)
out = Console(highlight=False)
err = Console(stderr=True, highlight=False)

#: How lely runs the Databricks CLI. Tests point it at a fake.
DATABRICKS: tuple[str, ...] = ("databricks",)


class Format(StrEnum):
    rich = "rich"
    json = "json"
    md = "md"


ConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        "-c",
        # help is read as markup, where `[tool.lely]` would be a style: escaped
        help=escape(
            "lely.yml, or a pyproject.toml with [tool.lely]. Found from here up "
            "when not given."
        ),
    ),
]


def _a_target(value: str | None) -> str | None:
    """An empty `-t` is what an unset variable leaves behind (`-t "$TARGET"`), and
    the Databricks CLI would read it as "the default target". There is none."""
    if value is not None and not value.strip():
        raise typer.BadParameter("it is empty; there is no default target")
    return value


TargetOption = Annotated[
    str,
    typer.Option(
        "--target", "-t", callback=_a_target, help="The target. There is no default."
    ),
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
GithubOption = Annotated[
    bool,
    typer.Option(
        "--github",
        help="In a GitHub Actions run: keep the pull request's comment and the "
        "run's page up to date.",
    ),
]
RecordOption = Annotated[
    Path | None,
    typer.Option(
        "--output",
        "-o",
        help="Write the run's result to a file, to keep or to open with `lely ui`.",
    ),
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
    global _token
    _token = None  # each command finds its own run, if it is asked to


#: The token of the GitHub Actions run this is, once `--github` has found it:
#: no line lely says holds it, whatever a step or a program printed.
_token: str | None = None


def _hide(text: str) -> str:
    return github.scrub(text, _token)


class _Log:
    def info(self, message: str) -> None:
        # what a program printed is shown, never obeyed
        err.print(f"[dim]… {escape(clean(_hide(message)))}[/]")


def _fail(error: Exception, *, refusals: bool = True) -> typer.Exit:
    """Say what went wrong, and end with 2 for a refusal and 1 for a failure.

    `plan`, `status`, `validate` and `doctor` change nothing, so there is
    nothing to plan again for: they end with 1.
    """
    err.print(f"[red]{escape(clean(_hide(str(error))))}[/]")
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

    `admins` is the system group of a workspace's administrators:
    https://docs.databricks.com/aws/en/admin/users-groups/groups

    TODO(verify): no API says "read-only" in general. Being a workspace admin is
    the one thing that can be read off.
    TODO(verify): that `current_user.me()` lists `admins`, under that name, for
    every admin — one who is in it through another group too. Not seen on a
    workspace. A miss reads as "not a workspace admin; lely can't tell what
    else", which claims nothing.
    """
    from databricks.sdk import WorkspaceClient

    me = WorkspaceClient(profile=profile).current_user.me()
    if any(group.display == "admins" for group in me.groups or []):
        return "a workspace admin: these credentials can change anything"
    return "not a workspace admin; lely can't tell what else these credentials may change"


def _interactive() -> bool:
    return sys.stdin.isatty()


#: Tests put fakes here.
BROWSER: Callable[[str], bool] = webbrowser.open
GITHUB: github.Connect = github.connect
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


# -- GitHub ------------------------------------------------------------------------


def _github(asked: bool) -> github.Run | None:
    """The GitHub Actions run this is, when `--github` asks for it. It is
    never on because of where a command runs."""
    global _token
    if not asked:
        return None
    found = github.here(os.environ)
    _token = found.token if found is not None else None
    if found is None:
        _noted(
            [
                github.Note(
                    "this isn't a GitHub Actions run (`GITHUB_ACTIONS` isn't `true`), "
                    "so nothing was posted",
                    done=False,
                )
            ]
        )
    return found


def _post(hub: github.Run, notes: Callable[[], list[github.Note]]) -> None:
    """Do what `--github` asks and say how it went. Nothing here decides how
    the command ends: a plan stands on its own."""
    try:
        _noted(notes())
    except Exception as error:
        # an error may quote what it choked on: the token is not to be in it
        problem = f"couldn't be done: {type(error).__name__}: {error}"
        _noted([github.Note(github.scrub(problem, hub.token), done=False)])


def _noted(notes: list[github.Note]) -> None:
    for note in notes:
        words = escape(clean(_hide(note.words)))
        if note.done:
            err.print(f"[dim]… github: {words}[/]")
        else:
            err.print(f"[yellow]--github: {words}[/]")


def _project(path: Path | None) -> tuple[str | None, bool]:
    """Which project of its repository this is, for a plan that failed before
    it could say — as a plan names it, so its comment is found again — and
    whether that could be told at all. Its folder may be gone: a pull request
    that renames it still fails as that project."""
    try:
        file = path if path is not None else config.find(Path.cwd())
        folder = file.resolve().parent
    except (LelyError, OSError):
        folder = Path.cwd()
    try:
        return source.named(folder), True
    except (LelyError, OSError):
        return None, False


def _holds_no_token(built: Plan, hub: github.Run) -> None:
    """A plan is shown and kept — as a file, as an artifact — so it holds no
    credential. A step that prints its environment into its plan puts this
    run's token there; nothing is written then."""
    for step in built.steps:
        alone = planfile.dumps(replace(built, steps=(step,)))
        if github.scrub(alone, hub.token) != alone:
            raise LelyError(
                f"The plan of step `{step.name}` holds this run's GitHub token: "
                "something it ran printed it — its environment, most likely. A plan "
                "is shown and kept, so it may hold no credential. lely goes no further."
            )


def _no_fork(run: github.Run | None, verb: str) -> None:
    """A pull request from a fork is not applied: its code would run with a
    workspace's credentials."""
    if run is not None and run.fork is not None:
        raise Refused(
            f"This pull request comes from a fork ({run.fork}), and lely doesn't "
            f"{verb} one: its code would run with the credentials of a workspace."
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


def _consent_to_destroy(plan: Plan, run: _Run, yes: bool) -> None:
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
            f"This destroys {clean(_where(plan, run))}.\nType the target's name to go on",
            default="",
            show_default=False,
            err=True,
        )
    except (typer.Abort, EOFError):
        answer = ""
    if not plan.target or answer.strip() != plan.target:
        raise Refused("That isn't the target's name. Nothing was destroyed.")


def _where(plan: Plan, run: _Run) -> str:
    """What a question is about: the target, the workspace, and who is running
    — which, with a plan file, need not be who planned."""
    words = f"target `{plan.target}` on {run.workspace}"
    if plan.workspace.identity != run.workspace.identity:
        words += f" (the plan was made as {plan.workspace.identity})"
    return words


def _nothing_in(plan: Plan) -> bool:
    """Whether a plan can run nothing at all, so there is nothing to ask about:
    no step shows a change, and none is waiting to be planned."""
    return not any(step.plan.changes or step.state == "waiting" for step in plan.steps)


def _at_waiting(
    plan: Plan, run: _Run, yes: bool, hub: github.Run | None = None
) -> running.AtWaiting:
    """What `apply` without a file does at a step that was waiting: `--yes`
    runs it; at a terminal lely shows it and asks once more."""

    def ask(step: PlannedStep) -> bool:
        if hub is not None:
            # planned only now, and shown: held to what every shown plan is
            _holds_no_token(replace(plan, steps=(step,)), hub)
        err.print()
        err.print(step_view(step))
        if yes:
            return True
        if not _interactive():
            return False
        return _confirm(clean(f"Run step `{step.name}` on {_where(plan, run)}?"))

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
    for found in _plugins(path):
        doc = (found.cls.__doc__ or "").strip().splitlines()
        out.print(
            f"[bold]{escape(found.uses)}[/]  [dim]{escape(found.source)}[/]"
            + (f"\n  {escape(doc[0])}" if doc else "")
        )
        try:
            fields = options.fields_of(found.options)
            gives = _gives(found.cls)
        except LelyError as error:  # a default, or its outputs, that can't be made
            err.print(f"    [red]{escape(clean(str(error)))}[/]")
            continue
        for f in fields:
            default = "required" if f.required else f"default {f.default}"
            out.print(
                f"    {escape(f.name)}: {escape(f.type)}  [dim]{escape(default)}[/]"
            )
        for line in gives:
            out.print(f"    [dim]gives[/]  {escape(line)}")
        out.print(f"    [dim]can[/]    {escape(_can(found.cls))}")


def _plugins(path: Path | None) -> list[registry.Found]:
    """The plugins a config here can use: the installed ones, and the ones this
    project names. One that can't be loaded is said so and left out."""
    names = sorted(registry.installed())
    root = Path.cwd()
    try:
        loaded = _load(path)
    except config.NoConfig as error:
        # no project here: the installed plugins are all there is to list. A
        # config that is there and can't be read is not that: its plugins
        # would be silently missing.
        if path is not None:
            raise _fail(error, refusals=False) from None
    except LelyError as error:
        raise _fail(error, refusals=False) from None
    else:
        root = loaded.root
        names += [s.uses for s in loaded.steps if s.uses not in names]
    found = []
    for name in dict.fromkeys(names):
        try:
            found.append(registry.find(name, root))
        except LelyError as error:
            err.print(f"[red]{escape(name)}[/]: {escape(clean(str(error)))}")
    return found


@app.command()
def schema(
    path: ConfigOption = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write the schema to a file.")
    ] = None,
) -> None:
    """Print a JSON Schema of the config, built from the plugins, for editors.

    Point an editor at it with a first line in lely.yml:
    `# yaml-language-server: $schema=lely.schema.json`
    """
    plugins = _plugins(path)
    docs = {found.uses: registry.option_docs(found.options) for found in plugins}
    try:
        text = schema_.dumps(schema_.build(plugins, docs))
    except LelyError as error:
        raise _fail(error, refusals=False) from None
    if output is None:
        typer.echo(text, nl=False)
        return
    try:
        _write(output, text)
    except OSError as error:
        problem = LelyError(
            f"Can't write the schema to {output}: {error.strerror or error}"
        )
        raise _fail(problem, refusals=False) from None
    out.print(Text.assemble(("Wrote", "green"), f" {output}"))
    # an editor reads the path from where the config is, not from here
    beside = output
    try:
        found = config.find(Path.cwd()) if path is None else path
        beside = Path(os.path.relpath(output.resolve(), found.resolve().parent))
    except (LelyError, ValueError):
        found = None
    if found is not None and found.name == config.PYPROJECT:
        words = (
            "It is for a `lely.yml`: a `[tool.lely]` section in pyproject.toml has "
            "no schema of its own."
        )
        out.print(f"[dim]{escape(words)}[/]")
        return
    out.print(
        "[dim]As the first line of lely.yml:[/]  "
        + escape(f"# yaml-language-server: $schema={beside.as_posix()}")
    )


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
    on_github: GithubOption = False,
) -> None:
    """Plan every step, in order, and show what would change. Changes nothing."""
    kind: PlanKind = "destroy" if destroy else "apply"
    hub = _github(on_github)
    if hub is not None and hub.fork is not None:
        # before anything of the project is loaded: planning runs its code
        err.print(
            f"[yellow]This pull request comes from a fork ({escape(clean(hub.fork))}): "
            "no plan is made. Planning runs the pull request's own code, and that "
            "must not happen with the credentials of a workspace.[/]"
        )
        _post(hub, lambda: github.post_skipped(hub, kind, target))
        return
    try:
        run = _run(path, profile)
        built = planning.plan(
            run.config,
            target=target,
            source=source.read(run.config.root, output),
            kind=kind,
            **run.edges,
        )
        if hub is not None:
            _holds_no_token(built, hub)
        _show_plan(built, output_format, output)
    except LelyError as error:
        if hub is not None:
            failed, (project, placed) = str(error), _project(path)
            _post(
                hub,
                lambda: github.post_plan_failure(
                    hub, kind, target, project, failed, GITHUB, placed=placed
                ),
            )
        raise _fail(error, refusals=False) from None
    if hub is not None:
        _post(hub, lambda: github.post_plan(hub, built, GITHUB))


@app.command()
def show(
    plan_file: Annotated[Path, typer.Argument(help="A plan written by `lely plan -o`.")],
    output_format: FormatOption = Format.rich,
    on_github: GithubOption = False,
) -> None:
    """Show a saved plan."""
    hub = _github(on_github)
    try:
        built = _read_plan(plan_file)
        if hub is not None:
            _holds_no_token(built, hub)
        _show_plan(built, output_format, None)
    except LelyError as error:
        raise _fail(error, refusals=False) from None
    if hub is None:
        return
    if hub.fork is not None:
        # shown here, where it harms nobody; not posted as the plan
        err.print(
            f"[yellow]--github: this pull request comes from a fork "
            f"({escape(clean(hub.fork))}): its plan is not posted.[/]"
        )
        _post(hub, lambda: github.post_skipped(hub, built.kind, built.target))
        return
    _post(hub, lambda: github.post_plan(hub, built, GITHUB))


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
    elif output_format is Format.md:
        typer.echo(markdown.status_markdown(found), nl=False)
    else:
        out.print(status_view(found))


@app.command()
def ui(
    file: Annotated[
        Path,
        typer.Argument(
            help="A plan from `lely plan -o`, or a result from `lely apply -o`."
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Where to write the page; `-` for stdout. Beside the file by default.",
        ),
    ] = None,
    open_it: Annotated[
        bool | None,
        typer.Option(
            "--open/--no-open", help="Open it in a browser. At a terminal by default."
        ),
    ] = None,
) -> None:
    """Make a page of a plan, or of a run's result, and open it. Changes nothing.

    One HTML file with nothing to fetch and nothing that runs: it opens from
    disk, and reads the same on any machine. It needs no workspace and no
    credentials, and runs none of the project's code.
    """
    try:
        page = _page(file)
        if output is not None and str(output) == "-":
            typer.echo(page, nl=False)
            return
        written = output if output is not None else file.with_suffix(".html")
        if _same_file(written, file):
            raise LelyError(f"{file} is the file to read: the page needs another name.")
        if output is None and not _ours_to_write(written):
            # a plan file can come from anywhere, and so can what lies beside it
            raise LelyError(
                f"{written} is there already, and it isn't a page lely made. Name "
                "the page with -o."
            )
        try:
            _write(written, page)
        except OSError as error:
            raise LelyError(
                f"Can't write the page to {written}: {error.strerror or error}"
            ) from None
    except LelyError as error:
        raise _fail(error, refusals=False) from None
    out.print(Text.assemble(("Wrote", "green"), f" {written}"))
    if open_it if open_it is not None else _interactive():
        BROWSER(written.resolve().as_uri())


def _same_file(one: Path, other: Path) -> bool:
    """Whether two paths name one file, however they are spelled: in another
    case, through a link, or as a second name of the same file."""
    try:
        return os.path.samefile(one, other)
    except OSError:
        return one.resolve() == other.resolve()


def _ours_to_write(page: Path) -> bool:
    """Whether the default place for a page is free, or holds a page lely made
    before. Anything else — another file, a link to one — is not written over
    on the strength of a name."""
    if not os.path.lexists(page):
        return True
    if page.is_symlink() or not page.is_file():
        return False
    try:
        with open(page, encoding="utf-8", errors="replace") as file:
            head = file.read(2048)
    except OSError:
        return False
    made = f'<meta name="generator" content="{html.GENERATOR}">'
    return head.startswith("<!doctype html>") and made in head


#: What means "there is no room for a second file beside this one": a folder
#: that can't be written to, a file mounted on its own.
_NO_ROOM = (errno.EACCES, errno.EPERM, errno.EROFS, errno.EBUSY, errno.EXDEV)


def _write(path: Path, text: str) -> None:
    """Write `text` as the file at `path`: beside it first, then moved into
    its place. So a file is whole or as it was, never half written — and a
    link standing where the file goes is replaced, not followed: lely writes
    the file it was told to, never through to whatever a link points at.

    What is no file is written to as it is: a device, a pipe (`-o /dev/null`).
    A file marked read-only is left alone, as it always was. A second name of
    the same file (a hard link) keeps what it held. Raises `OSError`.
    """
    try:
        there = os.lstat(path)
    except OSError:
        there = None
    if _a_device(path, there):
        with open(path, "w", encoding="utf-8", errors="replace") as file:
            file.write(text)
        return
    plain = there is not None and stat.S_ISREG(there.st_mode)
    if plain and not os.access(path, os.W_OK):
        raise PermissionError(errno.EACCES, "Permission denied", str(path))
    try:
        _in_its_place(path, text, there if plain else None)
    except OSError as error:
        if not plain or error.errno not in _NO_ROOM:
            raise
        # the file itself can be written, and nothing beside it: so, in place
        flags = os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(
            os.open(path, flags), "w", encoding="utf-8", errors="replace"
        ) as file:
            file.write(text)


def _a_device(path: Path, there: os.stat_result | None) -> bool:
    """Whether `path` names something to write *to*, not a file to make: a
    pipe, a device, or anything under `/dev` — where `/dev/stdout` is a link,
    and replacing it would take it away from everything else."""
    if there is not None and not (
        stat.S_ISREG(there.st_mode)
        or stat.S_ISLNK(there.st_mode)
        or stat.S_ISDIR(there.st_mode)
    ):
        return True
    return there is not None and path.absolute().parts[:2] in (
        ("/", "dev"),
        ("/", "proc"),
    )


def _in_its_place(path: Path, text: str, replaced: os.stat_result | None) -> None:
    """`replaced` is the plain file that is there now, if one is: the new one
    is readable by whoever could read that one, and by nobody more."""
    handle, beside = tempfile.mkstemp(dir=path.parent, prefix=".lely-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", errors="replace") as file:
            file.write(text)
        if replaced is None:
            mask = os.umask(0)
            os.umask(mask)
            mode = 0o666 & ~mask
        else:
            mode = stat.S_IMODE(replaced.st_mode) & 0o777
            if os.stat(beside).st_gid != replaced.st_gid:
                try:
                    os.chown(beside, -1, replaced.st_gid)
                except OSError:
                    # it can't be given to the group the old one was for: then
                    # no group reads it, and nobody else
                    mode &= 0o700
        os.chmod(beside, mode)
        os.replace(beside, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(beside)
        raise


def _page(file: Path) -> str:
    """The page for a plan file or a run's record, whichever `file` is."""
    try:
        document = json.loads(file.read_text(encoding="utf-8"))
    except OSError as error:
        raise LelyError(f"{file}: {error.strerror or error}") from None
    except UnicodeDecodeError:
        raise LelyError(f"{file}: not a plan or a result: it isn't text.") from None
    except (ValueError, RecursionError) as error:
        raise LelyError(f"{file}: not a plan or a result: {error}") from None
    if planfile.is_result(document):
        return html.result_html(planfile.result_from_json(document))
    return html.plan_html(planfile.plan_from_json(document))


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
            try:
                programs = _programs(found.cls, said if isinstance(said, dict) else {})
            except Exception as error:  # a plugin's `programs` is its own code
                problem = str(error)
                if not isinstance(error, LelyError):
                    problem = f"{type(error).__name__}: {error}"
                where = f"step `{step.name}` ({step.uses})"
                line(False, clean(f"{where}: its `programs` failed: {problem}"))
                continue
            for program in programs:
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
    with contract.quietly():
        named = tuple(dict.fromkeys(listed(written)))
    for program in named:
        if not isinstance(program, str):
            raise LelyError(
                f"it names a program as {type(program).__name__}, not as text"
            )
    return named


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
    return clean(said[0]) if said else f"exit {result.returncode}"


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
    on_github: GithubOption = False,
    record: RecordOption = None,
) -> None:
    """Run a reviewed plan — or, with -t, plan, show, ask and run."""
    _a_target(target)
    known = _Known("apply", target)
    hub = _github(on_github)
    try:
        _no_fork(hub, "apply")
        if plan_file is None and target is None:
            # before the config is read or a workspace reached: nothing is
            # asked of either for a command that can't say what it is for
            raise Refused("Give the target: `lely apply -t <target>`.")
        run = _run(path, profile)
        known.workspace = run.workspace
        if plan_file is not None:
            approved = _read_plan(plan_file, to_run=True)
            known.target = approved.target
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
            running.check_applies(run.config, approved.target)
            running.check_from(run.config, approved.target, from_step)
            _still_holds(approved, run, plan_file)
            at_waiting = None
        else:
            assert target is not None  # refused above
            running.check_applies(run.config, target)
            running.check_from(run.config, target, from_step)
            approved = planning.plan(
                run.config,
                target=target,
                source=_unsaved(run.config.root),
                **run.edges,
            )
            at_waiting = _at_waiting(approved, run, yes, hub)
        if hub is not None:
            _holds_no_token(approved, hub)
        render_plan(approved, err, saved=plan_file is not None)
        approval.destructive_allowed(approved.steps, allow_destructive)
        if not _nothing_in(approved):
            _consent(clean(f"Apply this plan to {_where(approved, run)}?"), yes)
        result = running.apply(
            run.config,
            approved,
            allow_destructive=allow_destructive,
            from_step=from_step,
            at_waiting=at_waiting,
            **run.edges,
        )
    except LelyError as error:
        raise _stopped(known, error, output_format, hub, record) from None
    _finish(result, output_format, hub, record)


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
    on_github: GithubOption = False,
    record: RecordOption = None,
) -> None:
    """Take a target down again: plan the destroy, show it, ask, and run."""
    known = _Known("destroy", target)
    hub = _github(on_github)
    try:
        _no_fork(hub, "destroy")
        run = _run(path, profile)
        known.workspace = run.workspace
        planning.runs_for(run.config, target)
        running.check_from(run.config, target, from_step)
        if plan_file is not None:
            approved = _read_plan(plan_file, to_run=True)
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
            _still_holds(approved, run, plan_file)
        else:
            approved = planning.plan(
                run.config,
                target=target,
                source=_unsaved(run.config.root),
                kind="destroy",
                **run.edges,
            )
        if hub is not None:
            _holds_no_token(approved, hub)
        render_plan(approved, err, saved=plan_file is not None)
        if not _nothing_in(approved):
            _consent_to_destroy(approved, run, yes)
        result = running.destroy(run.config, approved, from_step=from_step, **run.edges)
    except LelyError as error:
        raise _stopped(known, error, output_format, hub, record) from None
    _finish(result, output_format, hub, record)


def _still_holds(approved: Plan, run: _Run, plan_file: Path) -> None:
    """A plan file is held to the workspace, the project and the tree it was
    made for, before anything runs."""
    approval.same_workspace(approved, run.workspace)
    approval.same_project(
        approved,
        [(s.name, s.uses, planning.made_from(s)) for s in run.config.steps],
    )
    approval.same_source(approved, source.read(run.config.root, plan_file))


def _unsaved(root: Path) -> Source:
    """What a plan that is run now, and never saved, was made on. Nothing will
    be held to it, so git failing to say is no reason to stop."""
    try:
        return source.read(root)
    except source.SourceError:
        return Source()


@dataclass
class _Known:
    """What is known of a run so far, for one that ends before its first step."""

    kind: str
    target: str | None
    workspace: Workspace | None = None


def _stopped(
    known: _Known,
    error: LelyError,
    output_format: Format,
    hub: github.Run | None = None,
    record: Path | None = None,
) -> typer.Exit:
    """A run that ended before its first step. With `-f json` that is said on
    stdout too, in the shape of a result, so whatever reads it reads something
    — and it is what the run's record holds, when one was asked for."""
    refused = isinstance(error, Refused)
    # with `--github` the run's token is known, and is in nothing lely says
    said = _without_token(str(error), hub)
    error = Refused(said) if refused else LelyError(said)
    if hub is not None:
        _post(
            hub, lambda: github.post_stopped(hub, known.kind, known.target, refused, said)
        )
    workspace = known.workspace
    document = {
        "result_format": planfile.RESULT_FORMAT,
        "kind": known.kind,
        "target": known.target,
        "workspace": (
            None
            if workspace is None
            else {"host": workspace.host, "identity": workspace.identity}
        ),
        "outcome": "refused" if refused else "failed",
        "message": str(error),
        "ran": [],
        "failed": [],
        "refused": [],
        "not_started": [],
        "rolled_back": [],
        "steps": [],
    }
    _keep(record, document, hub)
    if output_format is Format.json:
        _echo_json(document, hub)
    elif output_format is Format.md:
        stopped = markdown.stopped_markdown(known.kind, known.target, refused, str(error))
        typer.echo(_without_token(stopped, hub), nl=False)
    return _fail(error)


def _finish(
    result: Result,
    output_format: Format,
    hub: github.Run | None = None,
    record: Path | None = None,
) -> None:
    result = _scrubbed(result, hub)
    _keep(record, planfile.result_to_json(result))
    if output_format is Format.json:
        _echo_json(planfile.result_to_json(result))
    elif output_format is Format.md:
        typer.echo(markdown.result_markdown(result), nl=False)
    else:
        out.print(result_view(result))
    if hub is not None:
        _post(hub, lambda: github.post_result(hub, result))
    if result.outcome != "done":
        raise typer.Exit(2 if result.outcome == "refused" else 1)


# -----------------------------------------------------------------------------


def _read_plan(plan_file: Path, *, to_run: bool = False) -> Plan:
    """A plan from a file. For a command that would run it, a file lely can't
    read is a refusal: it takes a new plan, not another try."""
    try:
        return planfile.loads(plan_file.read_text(encoding="utf-8"))
    except OSError as error:
        raise LelyError(f"{plan_file}: {error.strerror or error}") from None
    except UnicodeDecodeError:
        error_ = planfile.PlanFileError(f"{plan_file}: not a plan file: it isn't text.")
    except planfile.PlanFileError as error:
        error_ = error
    if to_run:
        raise Refused(str(error_)) from None
    raise error_


def _show_plan(built: Plan, output_format: Format, output: Path | None) -> None:
    if output is not None:
        # first: a plan that can't be written is no use shown
        try:
            _write(output, planfile.dumps(built))
        except OSError as error:
            raise LelyError(
                f"Can't write the plan to {output}: {error.strerror or error}"
            ) from None
    if output_format is Format.json:
        if output is None:
            typer.echo(planfile.dumps(built), nl=False)
            return
    elif output_format is Format.md:
        typer.echo(markdown.plan_markdown(built), nl=False)
    else:
        render_plan(built, out)
    if output is not None:
        # with `-f json` or `-f md`, stdout is for that and nothing else
        said = out if output_format is Format.rich else err
        said.print(Text.assemble("\n", ("Wrote", "green"), f" {output}"))


def _keep(
    record: Path | None, document: dict[str, Any], hub: github.Run | None = None
) -> None:
    """Write a run's record, when one was asked for. The run has happened
    whether or not that works: a record that can't be written is said, and
    changes nothing about how the run ended.

    A record is kept and passed around, so with `--github` it is searched for
    the run's token first, as what goes on the run's page is: a step that
    failed may have printed it.
    """
    if record is None:
        return
    try:
        _write(record, _without_token(json.dumps(document, indent=2) + "\n", hub))
    except (OSError, ValueError, TypeError, RecursionError) as error:
        why = getattr(error, "strerror", None) or error
        err.print(f"[red]Can't write the result to {escape(str(record))}: {why}[/]")
    else:
        err.print(Text.assemble(("Wrote", "green"), f" {record}"))


def _without_token(text: str, hub: github.Run | None) -> str:
    return text if hub is None else github.scrub(text, hub.token)


def _scrubbed(result: Result, hub: github.Run | None) -> Result:
    """`result` without the run's token, wherever a step that failed may have
    printed it: what it says in a terminal, as JSON, as Markdown, in its
    record and on the run's page is then the same, and none of it holds the
    token. Only with `--github`: that is when lely knows of one."""
    if hub is None or hub.token is None:
        return result
    try:
        written = json.dumps(planfile.result_to_json(result))
        cleaned = github.scrub(written, hub.token)
        if cleaned == written:
            return result
        return planfile.result_from_json(json.loads(cleaned))
    except (LelyError, TypeError, ValueError, RecursionError):
        # a result that can't be searched is not shown as it is: how each
        # step ended is lely's own word, and the rest is left out
        return Result(
            result.kind,
            result.target,
            result.workspace,
            tuple(
                StepResult(step.name, step.uses, step.outcome) for step in result.steps
            ),
            result.outcome,
            "What this run said is left out: it could not be searched for the run's "
            "token."
            if result.outcome != "done"
            else "",
        )


def _echo_json(document: dict[str, Any], hub: github.Run | None = None) -> None:
    typer.echo(_without_token(json.dumps(document, indent=2), hub))


def main() -> None:
    # A stream that can't write `✓` or `←` — a redirected one on Windows —
    # writes `?` instead of ending the command with a traceback.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="replace")
    app()

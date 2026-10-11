"""stevin, as a fake: a program that plans from a recorded plan and applies it.

    python fake_stevin.py <world> plan --target T --config C --output OUT --format json
    python fake_stevin.py <world> apply PLAN --config C [--allow-destructive]
    python fake_stevin.py <world> list --target T --config C --json [--select S]

`<world>` is a folder that stands for a workspace and a stevin project. Every
call is appended to `<world>/calls.jsonl`.

`<world>/plan.json` is the plan stevin would make before anything is applied:
one of the recordings in `fixtures/`, which stevin's own CLI wrote against its
own in-memory warehouse. `<world>/state.json` is what the workspace remembers:
the steps that were applied. `<world>/handed.json` is a copy of the plan file
`apply` was last handed. What it does is what stevin's command line was
read to do (`packages/stevin`: `cli.py`, `executor.py`, `render/json.py`), and,
for S1 to S6 and S8, what the CLI of stevin 0.4.0a2 was seen to do against that
in-memory warehouse on 2026-10-11: what it printed, and how it exited. S10 was
seen the same way on the same day, from stevin's branch `stevin/not-yet-exit-code`,
which is what 0.4.0a3 is to hold. None of it was seen on a workspace.

- S1  `plan --output OUT --format json` writes the plan file and prints
      `Wrote <file>`. Steps that were applied are left out of the next plan.
- S2  `apply PLAN` runs that plan. Its target is the file's: `--target` or
      `--select` beside a file is refused, exit 1. It does not ask.
- S3  A plan that holds a `destructive` step is refused without
      `--allow-destructive`, before anything runs, exit 4.
- S4  A plan the live tables have moved on from is refused as stale, exit 3,
      in the words "the live tables have changed since this plan was made
      (<tables>). Plan again and review the new plan." A plan that already ran
      is stale by its own doing. The fake's fingerprint is the steps applied
      and the text of `<world>/moved`.
- S5  A plan file of another format is refused, exit 3: "plan format version
      9 — this stevin writes and reads version 1. Re-run `stevin plan`." So is
      a file that is no JSON. A file that can't be read at all is a failure,
      exit 1.
- S6  A step without SQL is one stevin can't run: the plan is refused, exit 3.
- S7  A failed step ends the run with exit 1; the steps before it stay applied.
- S8  `list --target T --config C --json [--select S]` prints
      `{"target": T, "objects": [{"name", "kind", "exists"}]}`, one object per
      spec, in the order the specs were found, and plans nothing. The fake's
      specs are the tables of `<world>/plan.json`, by their short names, which
      is the order of the files the recordings were made from. A selection
      that matches no spec is a failure, exit 1.
- S9  Exit 2 is the command line's own answer to what it does not know: an
      older stevin answers `list` with "No such command 'list'." and exit 2
      (seen from stevin 0.3.0a1). No outcome of `apply` exits 2.
- S10 A plan that needs what another tool has yet to make is not made: `plan`
      writes no file and nothing on stdout, and exits 5 (stevin's rule PLAN-5).
      Two cases. A table whose schema the bundle declares and has not deployed:
      the last line on stderr is "<schema> is the bundle's schema '<key>', and
      isn't there yet — run `databricks bundle deploy` first; stevin won't
      create it". A table a spec only governs that its owner has not made: the
      last line is "<table> isn't there yet, and its spec only governs it — it
      is <owner>'s, and whoever owns it makes it first; stevin won't create a
      table it doesn't shape". The schema is looked at first. stevin may write
      other lines before that one. Once the thing is there, `plan` is S1,
      without a step that creates the bundle's schema. `list` is S8 either
      way: it makes no plan, says `"exists": false` for what is not there, and
      exits 0. The fake's `list` does not look at either; that the real one
      answers was seen from stevin's command.

Every plan says which stevin wrote it, in `tool_version`. The recordings say
0.4.0a2, the first with S3 to S6 as exit codes and with S8. The fake writes
0.4.0a3 over it, the first with S10: the plan file is the same in both.

A test tells it what to do with files in `<world>`:

- `fail-plan`, `fail-apply`, `fail-list`: the verb fails with that text, exit 1.
- `refuse-apply`: `apply` refuses with that text, exit 3, whatever the words.
- `version`: the next plan says this stevin wrote it.
- `fail-step`: a number; `apply` fails at that step, after the ones before it.
- `moved`: someone changed a table since the plan was made (S4). Write it
  after planning.
- `risk`: every step of the next plan carries this risk class, which need not
  be one stevin has.
- `bundle`: the tables' schema is the bundle's (S10). Two lines: the
  `state.json` of a `fake_databricks.py` world, and a resource of it such as
  `schemas.sales`. The schema is there once a bundle in that world has
  deployed the resource.
- `job`: the first table of the plan is one a spec only governs, and
  another tool's to make (S10). Two lines, or three: the `state.json` of a
  `fake_databricks.py` world, a resource of it such as `jobs.load`, and the
  owner as stevin's project file names it, `dlt` when left out. The table is
  there once that world has run the resource. Use it with the recording
  `stevin-governed.json`, whose first table is a governed one in a schema of
  its own: stevin shapes no table in a schema dlt loads into.
- `notice`: `plan` writes this on stderr before anything else it says there.

Anything else exits 2 and says so, like a command line that was not
understood: an unknown verb, an unknown flag, a missing one.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

FORMAT_VERSION = 1

_PLAN_FLAGS = ("--target", "--config", "--output", "--format", "--select")
_APPLY_FLAGS = ("--config",)
_APPLY_SWITCHES = ("--allow-destructive",)
_LIST_FLAGS = ("--target", "--config", "--select")
_LIST_SWITCHES = ("--json",)

#: `apply`'s exit codes for a plan it refuses before anything runs (stevin's
#: rule APL-8): one that will never run, and one that was not allowed.
PLAN_AGAIN, NOT_ALLOWED = 3, 4
#: `plan`'s exit code when it needs what another tool has yet to make
#: (stevin's rule PLAN-5, S10).
NOT_YET = 5

#: The stevin this stands for: the first with S10.
WRITES = "0.4.0a3"


class _Fails(Exception):
    """stevin's own way of failing: a red line on stderr, exit 1."""


class _Refuses(Exception):
    """stevin's own way of refusing a plan: a red line on stderr, exit 3 or 4,
    or 5 for a plan it can't make yet."""

    def __init__(self, said: str, code: int = PLAN_AGAIN) -> None:
        super().__init__(said)
        self.code = code


class _Unknown(Exception):
    """A command line the fake does not know: exit 2, loudly."""


def main(argv: list[str]) -> int:
    if not argv:
        print("fake stevin: no world given", file=sys.stderr)
        return 2
    world, args = Path(argv[0]), argv[1:]
    world.mkdir(parents=True, exist_ok=True)
    with (world / "calls.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\n")
    try:
        if args[:1] == ["plan"]:
            print(_plan(world, args[1:]))
        elif args[:1] == ["apply"]:
            print(_apply(world, args[1:]))
        elif args[:1] == ["list"]:
            print(_list(world, args[1:]))
        else:
            raise _Unknown(f"can't answer {args!r}")
    except _Unknown as error:
        print(f"fake stevin: {error}", file=sys.stderr)
        return 2
    except _Fails as error:
        print(str(error), file=sys.stderr)
        return 1
    except _Refuses as error:
        print(str(error), file=sys.stderr)
        return error.code
    return 0


# -- plan ---------------------------------------------------------------------------


def _plan(world: Path, args: list[str]) -> str:
    flags, rest = _flags(args, _PLAN_FLAGS, ())
    if rest:
        raise _Unknown(f"`plan` takes no argument: {rest!r}")
    for name in ("--target", "--config", "--output", "--format"):
        if name not in flags:
            raise _Unknown(f"`plan` without {name}")
    if flags["--format"] != ["json"]:
        raise _Unknown(f"`plan --format {flags['--format'][0]}`: only json is faked")
    notice = _read(world / "notice")
    if notice:
        print(notice, file=sys.stderr)
    _told_to_fail(world, "plan")
    _bundle_has_deployed(world)  # S10
    _owner_has_made(world)  # S10
    out = Path(flags["--output"][0])
    out.write_text(json.dumps(planned(world), indent=2) + "\n", encoding="utf-8")
    return f"Wrote {out.name}"  # S1


def _bundle_has_deployed(world: Path) -> None:
    """S10: refuse to plan a table whose schema the bundle has yet to deploy."""
    told = _read(world / "bundle").splitlines()
    if not told:
        return
    state, resource = Path(told[0]), told[1]
    bundles: dict[str, Any] = {}
    if state.exists():
        bundles = json.loads(state.read_text(encoding="utf-8")).get("bundles", {})
    if any(resource in bundle.get("deployed", {}) for bundle in bundles.values()):
        return
    tables = json.loads((world / "plan.json").read_text(encoding="utf-8"))["tables"]
    schema = tables[0]["table"].rsplit(".", 1)[0]
    raise _Refuses(
        f"{schema} is the bundle's schema {resource.split('.', 1)[1]!r}, and isn't "
        "there yet \u2014 run `databricks bundle deploy` first; stevin won't create it",
        NOT_YET,
    )


def _owner_has_made(world: Path) -> None:
    """S10: refuse to plan a governed table its owner has yet to make."""
    told = _read(world / "job").splitlines()
    if not told:
        return
    state, resource = Path(told[0]), told[1]
    runs: list[dict[str, Any]] = []
    if state.exists():
        runs = json.loads(state.read_text(encoding="utf-8")).get("runs", [])
    if any(run.get("key") == resource for run in runs):
        return
    tables = json.loads((world / "plan.json").read_text(encoding="utf-8"))["tables"]
    owner = told[2] if len(told) > 2 else "dlt"
    raise _Refuses(
        f"{tables[0]['table']} isn't there yet, and its spec only governs it \u2014 "
        f"it is {owner}'s, and whoever owns it makes it first; stevin won't create "
        "a table it doesn't shape",
        NOT_YET,
    )


def planned(world: Path) -> dict[str, Any]:
    """The plan as stevin would make it now: the recording, without the steps
    that were applied, with the fingerprint of the workspace as it is."""
    document = json.loads((world / "plan.json").read_text(encoding="utf-8"))
    done = set(_state(world)["applied"])
    steps = [step for step in document["steps"] if _key(step) not in done]
    if _read(world / "bundle"):
        # S10: the schema is the bundle's, and stevin never creates it
        steps = [s for s in steps if not s["title"].startswith("CREATE SCHEMA")]
    risk = _read(world / "risk")
    for number, step in enumerate(steps, start=1):
        step["id"] = number
        if risk:
            step["risk"] = risk
    left = {step["table"] for step in steps}
    for table in document["tables"]:
        if table["table"] not in left:
            # nothing left to do to it: it is there, and as its spec says
            table["changes"] = []
            table["facts"]["exists"] = True
    document["steps"] = steps
    document["state_fingerprint"] = _fingerprint(world)
    document["tool_version"] = _read(world / "version") or WRITES
    return document


# -- list ---------------------------------------------------------------------------


def _list(world: Path, args: list[str]) -> str:
    flags, rest = _flags(args, _LIST_FLAGS, _LIST_SWITCHES)
    if rest:
        raise _Unknown(f"`list` takes no argument: {rest!r}")
    for name in ("--target", "--config", "--json"):
        if name not in flags:
            raise _Unknown(f"`list` without {name}: only its JSON is faked")
    _told_to_fail(world, "list")
    tables = sorted(planned(world)["tables"], key=lambda t: t["table"].split(".")[-1])
    objects: list[dict[str, Any]] = [
        {
            "name": table["table"],
            "kind": table["facts"].get("kind") or "table",
            "exists": bool(table["facts"].get("exists")),
        }
        for table in tables
    ]
    selected = flags.get("--select")
    if selected is not None:
        objects = [
            one
            for one in objects
            if any(one["name"].endswith(f".{pattern}") for pattern in selected)
        ]
        if not objects:
            raise _Fails(f"the selection {selected[0]!r} matches no spec")
    return json.dumps({"target": flags["--target"][0], "objects": objects}, indent=2)


# -- apply --------------------------------------------------------------------------


def _apply(world: Path, args: list[str]) -> str:
    flags, rest = _flags(args, _APPLY_FLAGS, _APPLY_SWITCHES, refused=_PLAN_FLAGS)
    if len(rest) != 1:
        raise _Unknown(f"`apply` is faked for one plan file, not {rest!r}")
    if "--config" not in flags:
        raise _Unknown("`apply` without --config")
    if "--target" in flags or "--select" in flags:  # S2
        raise _Fails(
            "A saved plan already says what it does: --target and --select are "
            "for planning now."
        )
    name = Path(rest[0]).name
    try:
        text = Path(rest[0]).read_text(encoding="utf-8")
    except OSError as error:
        raise _Fails(f"cannot read {name}: {error}") from None
    try:
        document = json.loads(text)
    except ValueError as error:  # S5
        raise _Refuses(f"{name}: not valid JSON: {error}") from None
    (world / "handed.json").write_text(json.dumps(document), encoding="utf-8")
    version = document.get("format_version")
    if version != FORMAT_VERSION:  # S5
        raise _Refuses(
            f"{name}: plan format version {version!r} — this stevin writes and "
            f"reads version {FORMAT_VERSION}. Re-run `stevin plan`."
        )
    _told_to_fail(world, "apply")
    refusal = _read(world / "refuse-apply")
    if refusal:
        raise _Refuses(refusal)
    steps = document["steps"]
    said = [f"{document['target']} · {len(steps)} steps"]
    unrunnable = [step for step in steps if step.get("sql") is None]
    if unrunnable:  # S6
        raise _Refuses(
            f"this plan has {len(unrunnable)} step(s) stevin can't run:\n"
            + "\n".join(f"  {s['id']}. {s['title']} on {s['table']}" for s in unrunnable)
        )
    destructive = [step for step in steps if step.get("risk") == "destructive"]
    if destructive and "--allow-destructive" not in flags:  # S3
        titles = ", ".join(
            f"{s['id']}. {s['title']} on {s['table']}" for s in destructive
        )
        raise _Refuses(
            f"this plan destroys something ({titles}). Allow it explicitly if that "
            "is what you want. Re-run with --allow-destructive.",
            NOT_ALLOWED,
        )
    if document.get("state_fingerprint") != _fingerprint(world):  # S4
        moved = ", ".join(dict.fromkeys(step["table"] for step in steps))
        raise _Refuses(
            f"the live tables have changed since this plan was made ({moved}). "
            "Plan again and review the new plan."
        )
    stop_at = int(_read(world / "fail-step") or 0)
    state = _state(world)
    for step in steps:
        line = f"  {step['id']}. {step['title']} [{step['risk']}]"
        if step["id"] == stop_at:  # S7
            _save(world, state)
            print("\n".join([*said, f"{line} failed"]))
            raise _Fails(
                f"     the warehouse said no\n\nFailed at step {stop_at} of "
                f"{len(steps)} · run a41c9e07d2b5\nFix the cause and run `stevin "
                f"apply {name}` again — it resumes from here rather than starting over."
            )
        state["applied"].append(_key(step))
        said.append(f"{line} ok")
    _save(world, state)
    said.append(f"\nApplied {len(steps)} steps, skipped 0 · run a41c9e07d2b5")
    return "\n".join(said)


# -- the world ----------------------------------------------------------------------


def _key(step: dict[str, Any]) -> str:
    """A step across plans: its number shifts when the ones before it are done."""
    return f"{step['table']}|{step['title']}|{step.get('path') or ''}"


def _state(world: Path) -> dict[str, Any]:
    path = world / "state.json"
    if not path.exists():
        return {"applied": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(world: Path, state: dict[str, Any]) -> None:
    (world / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def _fingerprint(world: Path) -> str:
    """What a plan was made from: the steps applied, and whatever else moved."""
    seen = json.dumps([_state(world)["applied"], _read(world / "moved")])
    return hashlib.sha256(seen.encode()).hexdigest()[:16]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def _told_to_fail(world: Path, verb: str) -> None:
    text = _read(world / f"fail-{verb}")
    if text:
        raise _Fails(text)


def _flags(
    args: list[str],
    with_value: tuple[str, ...],
    switches: tuple[str, ...],
    refused: tuple[str, ...] = (),
) -> tuple[dict[str, list[str]], list[str]]:
    """Flags and what is left. A flag the verb doesn't have is not understood;
    `refused` are flags stevin knows and answers itself."""
    flags: dict[str, list[str]] = {}
    rest: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in with_value or arg in refused:
            if index + 1 >= len(args):
                raise _Unknown(f"{arg} needs a value")
            flags.setdefault(arg, []).append(args[index + 1])
            index += 2
        elif arg in switches:
            flags[arg] = []
            index += 1
        elif arg.startswith("-"):
            raise _Unknown(f"no such option: {arg}")
        else:
            rest.append(arg)
            index += 1
    return flags, rest


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

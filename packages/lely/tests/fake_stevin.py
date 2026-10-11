"""stevin, as a fake: a program that plans from a recorded plan and applies it.

    python fake_stevin.py <world> plan --target T --config C --output OUT --format json
    python fake_stevin.py <world> apply PLAN --config C [--allow-destructive]

`<world>` is a folder that stands for a workspace and a stevin project. Every
call is appended to `<world>/calls.jsonl`.

`<world>/plan.json` is the plan stevin would make before anything is applied:
one of the recordings in `fixtures/`, which stevin's own CLI wrote against its
own in-memory warehouse. `<world>/state.json` is what the workspace remembers:
the steps that were applied. `<world>/handed.json` is a copy of the plan file
`apply` was last handed. What it does is what stevin's command line was
read to do (`packages/stevin`: `cli.py`, `executor.py`, `render/json.py`), and,
for S1 to S5, what its CLI was seen to do against that in-memory warehouse on
2026-10-11. None of it was seen on a workspace.

- S1  `plan --output OUT --format json` writes the plan file and prints
      `Wrote <file>`. Steps that were applied are left out of the next plan.
- S2  `apply PLAN` runs that plan. Its target is the file's: `--target` or
      `--select` beside a file is refused, exit 1. It does not ask.
- S3  A plan that holds a `destructive` step is refused without
      `--allow-destructive`, before anything runs, exit 1.
- S4  A plan the live tables have moved on from is refused as stale, exit 1,
      in the words "the live tables have changed since this plan was made
      (<tables>). Plan again and review the new plan." A plan that already ran
      is stale by its own doing. The fake's fingerprint is the steps applied
      and the text of `<world>/moved`.
- S5  A plan file of another format is refused, exit 1: "plan format version
      9 — this stevin writes and reads version 1. Re-run `stevin plan`."
- S6  A step without SQL is one stevin can't run: the plan is refused, exit 1.
- S7  A failed step ends the run with exit 1; the steps before it stay applied.

A test tells it what to do with files in `<world>`:

- `fail-plan`, `fail-apply`: the verb fails with that text, exit 1.
- `fail-step`: a number; `apply` fails at that step, after the ones before it.
- `moved`: someone changed a table since the plan was made (S4). Write it
  after planning.
- `risk`: every step of the next plan carries this risk class, which need not
  be one stevin has.

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


class _Fails(Exception):
    """stevin's own way of failing: a red line on stderr, exit 1."""


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
        else:
            raise _Unknown(f"can't answer {args!r}")
    except _Unknown as error:
        print(f"fake stevin: {error}", file=sys.stderr)
        return 2
    except _Fails as error:
        print(str(error), file=sys.stderr)
        return 1
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
    _told_to_fail(world, "plan")
    out = Path(flags["--output"][0])
    out.write_text(json.dumps(planned(world), indent=2) + "\n", encoding="utf-8")
    return f"Wrote {out.name}"  # S1


def planned(world: Path) -> dict[str, Any]:
    """The plan as stevin would make it now: the recording, without the steps
    that were applied, with the fingerprint of the workspace as it is."""
    document = json.loads((world / "plan.json").read_text(encoding="utf-8"))
    done = set(_state(world)["applied"])
    steps = [step for step in document["steps"] if _key(step) not in done]
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
    return document


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
        document = json.loads(Path(rest[0]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise _Fails(f"cannot read {name}: {error}") from None
    (world / "handed.json").write_text(json.dumps(document), encoding="utf-8")
    version = document.get("format_version")
    if version != FORMAT_VERSION:  # S5
        raise _Fails(
            f"{name}: plan format version {version!r} — this stevin writes and "
            f"reads version {FORMAT_VERSION}. Re-run `stevin plan`."
        )
    _told_to_fail(world, "apply")
    steps = document["steps"]
    said = [f"{document['target']} · {len(steps)} steps"]
    unrunnable = [step for step in steps if step.get("sql") is None]
    if unrunnable:  # S6
        raise _Fails(
            f"this plan has {len(unrunnable)} step(s) stevin can't run:\n"
            + "\n".join(f"  {s['id']}. {s['title']} on {s['table']}" for s in unrunnable)
        )
    destructive = [step for step in steps if step.get("risk") == "destructive"]
    if destructive and "--allow-destructive" not in flags:  # S3
        titles = ", ".join(
            f"{s['id']}. {s['title']} on {s['table']}" for s in destructive
        )
        raise _Fails(
            f"this plan destroys something ({titles}). Allow it explicitly if that "
            "is what you want. Re-run with --allow-destructive."
        )
    if document.get("state_fingerprint") != _fingerprint(world):  # S4
        moved = ", ".join(dict.fromkeys(step["table"] for step in steps))
        raise _Fails(
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

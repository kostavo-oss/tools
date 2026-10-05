"""The Databricks CLI, as a fake: a program, and a function tests call in process.

    python fake_databricks.py <world> bundle <verb> [flags…]

`<world>` is a folder that stands for a workspace. Every call is appended to
`<world>/calls.jsonl`. A verb is answered in one of two ways:

**From a recording.** `<world>/<verb>.json` is printed for
`bundle validate|plan|summary`, with each `--var name=value` written into the
variable's `value` for validate, as the CLI resolves it. The recordings in
`tests/fixtures/cli/` are the CLI's own.

**By simulating a bundle.** When the directory the call runs in holds a
`fake-bundle.json`, that is the bundle, and `<world>/state.json` is what the
workspace remembers of it: what was deployed, under which root path, with which
ids. `plan`, `deploy`, `summary`, `destroy` and `run` then behave the way the
real CLI was seen to on 2026-10-06 (v1.19.0, one job, a development target) —
or, where that run couldn't show it, the way lely believes it does:

- V1  `destroy` removes what `summary` lists as deployed, and the files. Seen.
- V2  `destroy` refuses without `--auto-approve` when nobody can be asked, in
      the CLI's own words. Seen. That `deploy` does the same for a delete or a
      recreate is believed.
- V3  `summary` has an `id` and a `url` for every deployed resource. Seen for
      a job.
- V4  not simulated: the fake has no credentials. The real CLI does *not*
      refuse a target on another host; lely's own check is what is tested.
- V5  `plan` speaks only of resources. Seen.
- V6  `deploy --plan` with no resource changes still uploads the files. Seen.
- V7  what was deployed is recorded under the bundle's root path, which holds
      the deploying user's name: another identity sees nothing deployed.
      Believed; the root path was seen to hold the name.
- V8  `--var` is a list flag whose value is read as a line of CSV. Seen.
-     `validate` creates the bundle's `files` folder. Seen: it is recorded in
      `state.json` under `folders`, so a test can hold lely to not calling it.

Anything it can't answer exits 1 — loudly, like the CLI would.
"""

from __future__ import annotations

import copy
import csv
import json
import sys
from pathlib import Path
from typing import Any

HOST = "https://dbc-example.cloud.databricks.com"
USER = "jane@example.com"
BUNDLE_FILE = "fake-bundle.json"

_FLAGS_WITH_VALUE = ("--target", "--output", "--profile", "--plan")
_FLAGS = ("--auto-approve",)


class _Fails(Exception):
    """The CLI's own way of failing: a message on stderr, exit 1."""


def answer(world: Path, args: list[str], cwd: Path) -> tuple[int, str, str]:
    """One call of `databricks <args>` in `cwd`: exit code, stdout, stderr."""
    world.mkdir(parents=True, exist_ok=True)
    with (world / "calls.jsonl").open("a", encoding="utf-8") as calls:
        calls.write(json.dumps(args) + "\n")
    try:
        return 0, _answer(world, args, cwd), ""
    except _Fails as error:
        return 1, "", f"Error: {error}\n"


def _answer(world: Path, args: list[str], cwd: Path) -> str:
    if args[:1] == ["--version"]:
        return "Databricks CLI v1.18.0\n"
    if len(args) < 2 or args[0] != "bundle":
        raise _Fails(f"unknown command {args!r}")
    verb, rest = args[1], args[2:]
    call = _Call.read(rest)
    if (cwd / BUNDLE_FILE).exists():
        return _Simulated(world, cwd, call).answer(verb)
    return _recorded(world, verb, call)


class _Call:
    def __init__(self) -> None:
        self.flags: dict[str, str] = {}
        self.variables: dict[str, str] = {}
        self.positional: list[str] = []
        self.tail: list[str] = []

    @classmethod
    def read(cls, rest: list[str]) -> _Call:
        call = cls()
        i = 0
        while i < len(rest):
            word = rest[i]
            if word == "--":
                call.tail = rest[i + 1 :]
                break
            if word.startswith("--var="):
                # a list flag: its value is a line of CSV (V8)
                for pair in next(csv.reader([word.removeprefix("--var=")])):
                    name, equals, value = pair.partition("=")
                    if not equals:
                        raise _Fails(
                            f"unexpected flag value for variable assignment: {pair}"
                        )
                    call.variables[name] = value
            elif word in _FLAGS_WITH_VALUE:
                i += 1
                call.flags[word] = rest[i]
            elif word in _FLAGS:
                call.flags[word] = "true"
            elif word.startswith("-"):
                raise _Fails(f"unknown flag: {word}")
            else:
                call.positional.append(word)
            i += 1
        return call


# -- recordings -------------------------------------------------------------------


def _recorded(world: Path, verb: str, call: _Call) -> str:
    recording = world / f"{verb}.json"
    if not recording.exists():
        raise _Fails(f"no recording for `bundle {verb}`")
    document = json.loads(recording.read_text(encoding="utf-8"))
    if verb == "validate":
        for name, value in call.variables.items():
            document["variables"][name]["value"] = value
    return json.dumps(document) + "\n"


# -- a bundle, simulated ----------------------------------------------------------


class _Simulated:
    def __init__(self, world: Path, cwd: Path, call: _Call) -> None:
        self.world = world
        self.call = call
        self.bundle: dict[str, Any] = json.loads(
            (cwd / BUNDLE_FILE).read_text(encoding="utf-8")
        )
        self.target = call.flags.get("--target")
        if not self.target:
            raise _Fails("the fake needs --target: lely always names one")
        targets = self.bundle.get("targets")
        if targets is not None and self.target not in targets:
            raise _Fails(f"{self.target}: no such target. Available targets: {targets}")
        profile = call.flags.get("--profile")
        self.user = self.bundle.get("profiles", {}).get(profile, USER)
        self.host = self.bundle.get("host", HOST)
        self.root_path = (
            f"/Workspace/Users/{self.user}/.bundle/{self.bundle['name']}/{self.target}"
        )

    def answer(self, verb: str) -> str:
        if (self.world / f"fail-{verb}").exists():
            raise _Fails((self.world / f"fail-{verb}").read_text().strip())
        handler = getattr(self, f"_{verb}", None)
        if handler is None:
            raise _Fails(f"the fake can't answer `bundle {verb}`")
        return handler()

    # what the workspace remembers

    def _load(self) -> dict[str, Any]:
        path = self.world / "state.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _save(self, state: dict[str, Any]) -> None:
        (self.world / "state.json").write_text(json.dumps(state, indent=1))

    def _mine(self, state: dict[str, Any]) -> dict[str, Any]:
        """This bundle's own record: kept under its root path (V7)."""
        return state.setdefault("bundles", {}).setdefault(
            self.root_path, {"lineage": None, "serial": 0, "deployed": {}, "uploads": 0}
        )

    # the verbs

    def _config(self) -> dict[str, Any]:
        declared = self.bundle.get("variables", {})
        for name in self.call.variables:
            if name not in declared:
                raise _Fails(f"variable {name} has not been defined")
        values = {**declared, **self.call.variables}
        for name, value in values.items():
            if value is None:
                raise _Fails(f"no value assigned to required variable {name}")
        return {
            "bundle": {
                "name": self.bundle["name"],
                "target": self.target,
                "environment": self.target,
            },
            "variables": {
                name: {"default": declared[name], "value": values[name]}
                for name in declared
            },
            "resources": _substitute(self.bundle.get("resources", {}), values),
            "workspace": {
                "host": self.host,
                "current_user": {
                    "userName": self.user,
                    "short_name": self.user.split("@")[0],
                },
                "root_path": self.root_path,
                "state_path": f"{self.root_path}/state",
            },
        }

    def _validate(self) -> str:
        # not read-only: the real CLI creates the bundle's `files` folder
        # (seen on v1.19.0). lely's planning must not call this.
        state = self._load()
        config = self._config()
        state.setdefault("folders", []).append(f"{self.root_path}/files")
        self._save(state)
        return json.dumps(config) + "\n"

    def _planned(self) -> dict[str, Any]:
        mine = self._mine(self._load())
        declared = _flat(self._config()["resources"])
        deployed: dict[str, Any] = mine["deployed"]
        immutable = set(self.bundle.get("immutable", []))
        plan: dict[str, Any] = {}
        for key, config in declared.items():
            name = f"resources.{key}"
            if key not in deployed:
                plan[name] = {"action": "create", "new_state": {"value": config}}
                continue
            was = deployed[key]["config"]
            fields = sorted(f for f in {*was, *config} if was.get(f) != config.get(f))
            if not fields:
                plan[name] = {"action": "skip", "remote_state": was}
                continue
            recreate = any(f in immutable for f in fields)
            plan[name] = {
                "action": "recreate" if recreate else "update",
                "new_state": {"value": config},
                "remote_state": was,
                "changes": {
                    f: {
                        "action": "recreate" if f in immutable else "update",
                        **({"reason": "immutable"} if f in immutable else {}),
                        "old": was.get(f),
                        "new": config.get(f),
                    }
                    for f in fields
                },
            }
        for key in deployed:
            if key not in declared:
                plan[f"resources.{key}"] = {
                    "action": "delete",
                    "remote_state": deployed[key]["config"],
                }
        document: dict[str, Any] = {"plan_version": 2, "cli_version": "1.18.0"}
        if mine["lineage"] is not None:
            document |= {"lineage": mine["lineage"], "serial": mine["serial"]}
        return document | {"plan": plan}  # V5: resources only, nothing about files

    def _plan(self) -> str:
        return json.dumps(self._planned()) + "\n"

    def _deploy(self) -> str:
        state = self._load()
        mine = self._mine(state)
        if "--plan" in self.call.flags:
            document = json.loads(Path(self.call.flags["--plan"]).read_text())
            was = (document.get("lineage"), document.get("serial", 0))
            if was != (mine["lineage"], mine["serial"]):
                # the real CLI's words for a serial that moved on (v1.19.0)
                raise _Fails(
                    f"plan serial {was[1]} does not match state serial "
                    f"{mine['serial']}; the state has been modified since the plan "
                    "was created. Please run 'bundle plan' again"
                )
        else:
            document = self._planned()
        actions = {
            name.removeprefix("resources."): entry
            for name, entry in document["plan"].items()
        }
        risky = [k for k, e in actions.items() if e["action"] in ("delete", "recreate")]
        if risky and "--auto-approve" not in self.call.flags:  # V2
            raise _Fails(
                f"the deployment would delete or recreate {', '.join(risky)}; "
                "use --auto-approve to proceed"
            )
        deployed = mine["deployed"]
        for key, entry in actions.items():
            action = entry["action"]
            if action == "delete":
                deployed.pop(key, None)
            elif action in ("create", "recreate"):
                state["next_id"] = state.get("next_id", 1000) + 1
                deployed[key] = {
                    "id": str(state["next_id"]),
                    "config": entry["new_state"]["value"],
                }
            elif action == "update":
                deployed[key]["config"] = entry["new_state"]["value"]
        mine["uploads"] += 1  # V6: the files go up whatever the plan holds
        mine["serial"] += 1
        mine["lineage"] = mine["lineage"] or f"lineage-{self.bundle['name']}"
        self._save(state)
        return "Deployment complete!\n"

    def _summary(self) -> str:
        document = self._config()
        mine = self._mine(self._load())
        resources: dict[str, Any] = document["resources"]
        for kind, entries in resources.items():
            for key, entry in entries.items():
                if f"{kind}.{key}" not in mine["deployed"]:
                    entry["modified_status"] = "created"
        for name, record in mine["deployed"].items():
            kind, key = name.split(".", 1)
            entry = resources.setdefault(kind, {}).setdefault(
                key, {**record["config"], "modified_status": "deleted"}
            )
            entry["id"] = record["id"]  # V3: every type has both
            entry["url"] = f"{self.host}/{kind}/{record['id']}"
        return json.dumps(document) + "\n"

    def _destroy(self) -> str:
        state = self._load()
        mine = self._mine(state)
        if "--auto-approve" not in self.call.flags:  # V2
            # the real CLI's words, with nobody to ask (v1.19.0)
            raise _Fails(
                "this command will destroy all resources deployed by this bundle, "
                "including workspace files in the deployment directory.\n"
                "To proceed, use --auto-approve."
            )
        # V1: what the summary lists as deployed, and the files with them
        state["bundles"].pop(self.root_path)
        state.setdefault("destroyed", []).append(
            {"root_path": self.root_path, "resources": sorted(mine["deployed"])}
        )
        self._save(state)
        return "Destroy complete!\n"

    def _run(self) -> str:
        state = self._load()
        mine = self._mine(state)
        if len(self.call.positional) != 1:
            raise _Fails("expected a KEY of the resource to run")
        key = self.call.positional[0]
        if key not in mine["deployed"]:
            raise _Fails(f"resource {key} is not deployed; run `bundle deploy` first")
        state.setdefault("runs", []).append({"key": key, "args": self.call.tail})
        self._save(state)
        return f"Run of {key} finished: SUCCESS\n"


def _flat(resources: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        f"{kind}.{key}": entry
        for kind, entries in resources.items()
        for key, entry in entries.items()
    }


def _substitute(value: Any, variables: dict[str, Any]) -> Any:
    """`${var.<name>}` in a resource's config, as the CLI resolves it."""
    if isinstance(value, dict):
        return {k: _substitute(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, variables) for v in value]
    if isinstance(value, str):
        for name, given in variables.items():
            value = value.replace(f"${{var.{name}}}", str(given))
        return value
    return copy.deepcopy(value)


if __name__ == "__main__":
    code, said, complained = answer(Path(sys.argv[1]), sys.argv[2:], Path.cwd())
    sys.stdout.write(said)
    sys.stderr.write(complained)
    sys.exit(code)

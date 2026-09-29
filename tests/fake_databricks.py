"""The Databricks CLI, as a program that answers from recordings.

    python fake_databricks.py <answers-dir> bundle <verb> [flags…]

Prints `<answers-dir>/<verb>.json` for `bundle validate|plan|summary`, with each
`--var name=value` written into the variable's `value` for validate, as the CLI
resolves it. Every call is appended to `<answers-dir>/calls.jsonl`. A verb with
no recording, or a flag it doesn't know, exits 1 — loudly, like the CLI would.
"""

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    answers = Path(argv[0])
    args = argv[1:]
    with (answers / "calls.jsonl").open("a", encoding="utf-8") as calls:
        calls.write(json.dumps(args) + "\n")
    if len(args) < 2 or args[0] != "bundle":
        print(f"Error: unknown command {args!r}", file=sys.stderr)
        return 1
    verb, rest = args[1], args[2:]
    variables: dict[str, str] = {}
    i = 0
    while i < len(rest):
        flag = rest[i]
        if flag.startswith("--var="):
            name, _, value = flag.removeprefix("--var=").partition("=")
            variables[name] = value
        elif flag in ("--target", "--output", "--profile"):
            i += 1
        else:
            print(f"Error: unknown flag: {flag}", file=sys.stderr)
            return 1
        i += 1
    answer = answers / f"{verb}.json"
    if not answer.exists():
        print(f"Error: no recording for `bundle {verb}`", file=sys.stderr)
        return 1
    document = json.loads(answer.read_text(encoding="utf-8"))
    if verb == "validate":
        for name, value in variables.items():
            document["variables"][name]["value"] = value
    print(json.dumps(document))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

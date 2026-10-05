"""stevin, as a program that answers `plan` with a recorded plan file.

    python fake_stevin.py <plan.json> plan --target T --output OUT --format json

Copies the recording to OUT. The recordings in `fixtures/` are real: stevin
wrote them, against its own fake warehouse. When `FAKE_STEVIN_CALLS` is set,
the arguments are appended to that file.
"""

import json
import os
import shutil
import sys


def main(argv: list[str]) -> int:
    recording, args = argv[0], argv[1:]
    if calls := os.environ.get("FAKE_STEVIN_CALLS"):
        with open(calls, "a", encoding="utf-8") as log:
            log.write(json.dumps(args) + "\n")
    if not args or args[0] != "plan" or "--output" not in args:
        print(f"fake stevin: can't answer {args!r}", file=sys.stderr)
        return 2
    if os.environ.get("FAKE_STEVIN_FAIL"):
        print("Error: sales.orders: can't reach the warehouse", file=sys.stderr)
        return 1
    shutil.copyfile(recording, args[args.index("--output") + 1])
    print("Wrote plan.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""A package that has a `RULES.md` keeps it true: one place per fact.

The rules of a package are in one file, each with an identifier such as `APP-3`. This
holds, for every package that has the file: an identifier cited anywhere in the package
is a rule that exists; a rule is cited by the tests its `Held by:` line names, and by no
other test, or says `Not tested:` and why; no identifier is used twice; and the `spec/`
folder the rules came from is gone. A package without the file is not checked.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = sorted(p.name for p in (ROOT / "packages").iterdir() if p.is_dir())
WITH_RULES = [p for p in PACKAGES if (ROOT / "packages" / p / "RULES.md").is_file()]

#: A rule in `RULES.md`: `- **APP-3** — what must be true`.
RULE = re.compile(r"^- \*\*([A-Z]{2,5}-[0-9]+)\*\* — \S", re.MULTILINE)
#: Where a block of `RULES.md` ends: at the next item or the next heading.
NEXT = re.compile(r"^(?:- |#)", re.MULTILINE)
#: A test, as `Held by:` names it: `tests/test_app.py::test_it_runs`.
TEST = re.compile(r"`(tests/[\w/]+\.py::[\w:]+)`")
#: A citation of one of the numbered specs a `RULES.md` replaces: `spec/002`.
OLD_SPEC = re.compile(r"spec/[0-9]{3}")


def rules(text: str) -> list[tuple[str, str]]:
    """Every rule of a `RULES.md`, in order: its identifier and its whole block."""
    found = []
    for match in RULE.finditer(text):
        after = NEXT.search(text, match.end())
        found.append(
            (match.group(1), text[match.start() : after.start() if after else None])
        )
    return found


def cited(text: str, areas: set[str]) -> set[str]:
    """The identifiers a text cites. Only the areas `RULES.md` has count, so that
    `UTF-8` is not taken for a rule."""
    if not areas:
        return set()
    pattern = rf"(?<![\w-])(?:{'|'.join(sorted(areas))})-[0-9]+(?![\w-])"
    return set(re.findall(pattern, text))


FUNCTION = (ast.FunctionDef, ast.AsyncFunctionDef)


def every_test(here: Path) -> dict[str, str]:
    """Every test of a package, as `tests/<file>.py::<test>`, with its source."""
    found = {}
    for file in sorted((here / "tests").rglob("*.py")):
        text = file.read_text(encoding="utf-8")
        lines = text.splitlines()
        todo = [(f"{file.relative_to(here).as_posix()}::", ast.parse(text).body)]
        while todo:
            prefix, body = todo.pop()
            for node in body:
                if isinstance(node, ast.ClassDef):
                    todo.append((f"{prefix}{node.name}::", node.body))
                elif isinstance(node, FUNCTION) and node.name.startswith("test"):
                    # whole lines, so a comment at the end of one counts
                    source = lines[node.lineno - 1 : node.end_lineno]
                    found[prefix + node.name] = "\n".join(source)
    return found


def citing_files(here: Path) -> list[Path]:
    """Where a package may cite a rule: its code, its tests and its documents. Not its
    changelog, which is history and keeps the words of its day."""
    files = [here / name for name in ("RULES.md", "DECISIONS.md", "README.md")]
    files += [here / "CLAUDE.md", here / "CONTRIBUTING.md"]
    for folder, pattern in (("src", "*.py"), ("tests", "*.py"), ("docs", "*.md")):
        files += sorted((here / folder).rglob(pattern))
    return [file for file in files if file.is_file()]


def problems(here: Path) -> list[str]:
    """What is wrong between a package's `RULES.md` and the rest of it. Empty when the
    file is true."""
    wrong = []
    text = (here / "RULES.md").read_text(encoding="utf-8")
    found = rules(text)
    names = [name for name, _ in found]
    areas = {name.split("-")[0] for name in names}

    for name in sorted({name for name in names if names.count(name) > 1}):
        wrong.append(f"{name} is the identifier of more than one rule")
    for line in text.splitlines():
        if line.startswith("- **") and not RULE.match(line):
            wrong.append(f"not a rule as `- **AREA-1** — text`: {line}")

    for file in citing_files(here):
        where = file.relative_to(here).as_posix()
        body = file.read_text(encoding="utf-8")
        for name in sorted(cited(body, areas) - set(names)):
            wrong.append(f"{where} cites {name}, and RULES.md has no such rule")
        if OLD_SPEC.search(body):
            wrong.append(f"{where} cites a numbered spec; cite a rule of RULES.md")
    if (here / "spec").exists():
        wrong.append("there is a spec/ folder beside RULES.md: one place per fact")

    tests = every_test(here)
    citing = {test: cited(source, areas) for test, source in tests.items()}
    for name, block in found:
        held = "Held by:" in block
        reason = re.search(r"^\s+Not tested: *(.*)", block, re.MULTILINE)
        if held == bool(reason):
            wrong.append(f"{name} needs `Held by:` or `Not tested:`, and one of them")
            continue
        if reason:
            if len(reason.group(1).split()) < 3:
                wrong.append(f"{name} says `Not tested:` and not why")
            named = set()
        else:
            named = set(TEST.findall(block.split("Held by:", 1)[1]))
            if not named:
                wrong.append(f"{name} says `Held by:` and names no test")
        for test in sorted(named):
            if test not in tests:
                wrong.append(f"{name} is held by {test}, and there is no such test")
            elif name not in citing[test]:
                wrong.append(f"{name} is held by {test}, which does not cite {name}")
        for test in sorted(
            t for t, ids in citing.items() if name in ids and t not in named
        ):
            wrong.append(
                f"{test} cites {name}, and {name} does not name it as `Held by:`"
            )
    return wrong


def test_leeghwater_keeps_its_rules_in_one_file() -> None:
    # the first package to do so; the others follow, one pull request each
    assert "leeghwater" in WITH_RULES


@pytest.mark.parametrize("package", WITH_RULES)
def test_a_package_with_rules_keeps_them_true(package: str) -> None:
    here = ROOT / "packages" / package
    assert rules((here / "RULES.md").read_text(encoding="utf-8")), "no rule in RULES.md"
    assert problems(here) == []


# -- that the check bites: a made-up package, broken once in each way -------------------

GOOD = {
    "RULES.md": (
        "# Rules\n\n## APP\n\n"
        "- **APP-1** — It runs.\n"
        "  Held by: `tests/test_app.py::test_it_runs`,\n"
        "  `tests/test_app.py::TestMore::test_it_runs_twice`.\n"
        "- **APP-2** — It reads no token.\n"
        "  Not tested: it is an absence.\n"
    ),
    "README.md": "It runs, UTF-8 and all: APP-1.\n",
    "src/made_up/__init__.py": '"""APP-1 and APP-2."""\n',
    "tests/test_app.py": (
        "def test_it_runs():\n"
        '    """APP-1."""\n\n\n'
        "class TestMore:\n"
        "    def test_it_runs_twice(self):\n"
        "        pass  # APP-1\n\n\n"
        "def test_something_else():\n"
        "    pass\n"
    ),
}


def made_up(tmp_path: Path, changed: dict[str, str]) -> Path:
    for name, text in {**GOOD, **changed}.items():
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
    return tmp_path


def test_a_made_up_package_that_is_true_has_no_problems(tmp_path: Path) -> None:
    assert problems(made_up(tmp_path, {})) == []


RULES_MD = GOOD["RULES.md"]
TESTS_PY = GOOD["tests/test_app.py"]


@pytest.mark.parametrize(
    ("changed", "problem"),
    [
        pytest.param(
            {"src/made_up/__init__.py": '"""APP-3."""\n'},
            "src/made_up/__init__.py cites APP-3, and RULES.md has no such rule",
            id="a rule that does not exist is cited in the code",
        ),
        pytest.param(
            {"docs/index.md": "See APP-12.\n"},
            "docs/index.md cites APP-12, and RULES.md has no such rule",
            id="a rule that does not exist is cited in the docs",
        ),
        pytest.param(
            {"tests/test_app.py": TESTS_PY.replace('"""APP-1."""', '"""It runs."""')},
            "APP-1 is held by tests/test_app.py::test_it_runs, which does not cite APP-1",
            id="a test that is named does not cite its rule",
        ),
        pytest.param(
            {
                "tests/test_app.py": TESTS_PY.replace(
                    "def test_it_runs()", "def test_it()"
                )
            },
            "APP-1 is held by tests/test_app.py::test_it_runs, and there is no such test",
            id="a test that is named is not there",
        ),
        pytest.param(
            {"tests/test_app.py": TESTS_PY + '    """APP-2."""\n'},
            "tests/test_app.py::test_something_else cites APP-2, and APP-2 does not name"
            " it as `Held by:`",
            id="a test cites a rule that does not name it",
        ),
        pytest.param(
            {"RULES.md": RULES_MD.replace("  Not tested: it is an absence.\n", "")},
            "APP-2 needs `Held by:` or `Not tested:`, and one of them",
            id="a rule with no test and no reason",
        ),
        pytest.param(
            {"RULES.md": RULES_MD.replace("it is an absence", "no")},
            "APP-2 says `Not tested:` and not why",
            id="a rule that is not tested and does not say why",
        ),
        pytest.param(
            {"RULES.md": RULES_MD.replace("**APP-2**", "**APP-1**")},
            "APP-1 is the identifier of more than one rule",
            id="an identifier used twice",
        ),
        pytest.param(
            {"RULES.md": RULES_MD.replace("**APP-2** —", "**APP-2**:")},
            "not a rule as `- **AREA-1** — text`: - **APP-2**: It reads no token.",
            id="a rule that is not written as one",
        ),
        pytest.param(
            {"spec/000-what-it-is.md": "# 000\n"},
            "there is a spec/ folder beside RULES.md: one place per fact",
            id="a spec folder beside the rules",
        ),
        pytest.param(
            {"src/made_up/__init__.py": '"""`spec/002`, R3."""\n'},
            "src/made_up/__init__.py cites a numbered spec; cite a rule of RULES.md",
            id="a citation of a spec that is gone",
        ),
    ],
)
def test_each_way_a_rules_file_goes_stale_is_a_problem(
    tmp_path: Path, changed: dict[str, str], problem: str
) -> None:
    assert problem in problems(made_up(tmp_path, changed))

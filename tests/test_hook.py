"""`import dlt` on a made-up Databricks. `spec/002`, R3, R3b and R4.

A stand-in `dlt` and a stand-in import hook play Databricks' part. Each case runs in a
process of its own: it takes dlt out of `sys.modules`, which no other test should see.

TODO(verify): the real hook, on a real runtime. `spec/002`, "To verify on a workspace".
"""

import subprocess
import sys
import textwrap
import types

import dlt

from leeghwater._hook import _holders, _is_hook, is_dlthub

# What every case starts with: Databricks' own `dlt` as a package in a folder, and a
# finder that serves it for the name `dlt`, the way the hook in dlt's docs does.
STAND_IN = """
import importlib.machinery, importlib.util, os, sys, tempfile

folder = tempfile.mkdtemp()
os.makedirs(os.path.join(folder, "dlt"))
with open(os.path.join(folder, "dlt", "__init__.py"), "w") as file:
    file.write("def table(): 'Delta Live Tables'\\n")

class PostImportHook:
    def find_spec(self, name, path=None, target=None):
        if name == "dlt":
            return importlib.util.spec_from_file_location(
                "dlt", os.path.join(folder, "dlt", "__init__.py"),
                submodule_search_locations=[os.path.join(folder, "dlt")],
            )
        return None

hook = PostImportHook()
from leeghwater._hook import import_dlt, is_dlthub
"""


def _run(case: str) -> str:
    code = STAND_IN + textwrap.dedent(case)
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_with_the_hook_in_the_way_import_dlt_is_still_dlthubs():
    said = _run(
        """
        sys.meta_path.insert(0, hook)
        module, lines = import_dlt(True)
        import dlt
        print(is_dlthub(module), dlt is module, sys.meta_path[0] is hook)
        print(*lines, sep="\\n")
        again, lines = import_dlt(True)
        print(again is module, *lines)
        """
    )

    assert said.startswith("True True True\n")
    assert "took 1 import hook(s) out while importing dlt" in said
    assert "import dlt is dltHub's" in said
    assert "True dlt was imported already, and it is dltHub's" in said


def test_what_databricks_had_loaded_under_the_name_is_dropped_and_said():
    said = _run(
        """
        sys.meta_path.insert(0, hook)
        import dlt as theirs
        import types
        holder = types.ModuleType("my_ingest_cli"); holder.dlt = theirs
        sys.modules["my_ingest_cli"] = holder
        print(is_dlthub(theirs))
        module, lines = import_dlt(True)
        print(is_dlthub(module), sys.modules["dlt"] is module)
        print(*lines, sep="\\n")
        """
    )

    assert said.startswith("False\nTrue True\n")
    assert (
        "Databricks' own dlt was imported before leeghwater prepared the process" in said
    )
    assert "these modules hold it: my_ingest_cli" in said
    assert "dropped 1 module(s) Databricks had loaded as dlt" in said


def test_without_a_hook_it_goes_on_and_says_what_it_got():
    """Databricks' `dlt` is a folder too. Ahead on `sys.path` it wins, and that is said:
    `spec/002`, R3b. leeghwater moves no path entries, only the hook."""
    said = _run(
        """
        sys.path.insert(0, folder)
        module, lines = import_dlt(True)
        print(is_dlthub(module), sys.path[0] == folder)
        print(*lines, sep="\\n")
        """
    )

    assert said.startswith("False True\n")
    assert "found no import hook where dlt's docs expect one" in said
    assert "import dlt is NOT dltHub's after all of that" in said


def test_on_a_laptop_nothing_is_touched():
    said = _run(
        """
        sys.meta_path.insert(0, hook)
        before = list(sys.meta_path)
        sys.modules["dlt"] = sentinel = object()
        module, lines = import_dlt(False)
        print(sys.meta_path == before, module is sentinel, *lines)
        """
    )

    assert said.strip() == "True True nothing to do off Databricks"


def test_dlthubs_dlt_is_told_from_databricks_own():
    theirs = types.ModuleType("dlt")
    theirs.__file__ = "/databricks/spark/python/dlt/__init__.py"
    theirs.pipeline = object()

    assert is_dlthub(dlt)
    assert not is_dlthub(theirs)
    assert not is_dlthub(types.ModuleType("dlt"))
    assert not is_dlthub(None)


def test_a_hook_is_known_by_the_names_in_dlts_docs():
    class PostImportHook:
        pass

    class Finder:
        pass

    assert _is_hook(PostImportHook())
    assert not _is_hook(Finder())
    assert not any(_is_hook(finder) for finder in sys.meta_path)


def test_the_modules_that_hold_a_dlt_are_named():
    holder = types.ModuleType("holds_it")
    holder.dlt = dlt
    sys.modules["holds_it"] = holder
    try:
        assert "holds_it" in _holders(dlt)
    finally:
        del sys.modules["holds_it"]

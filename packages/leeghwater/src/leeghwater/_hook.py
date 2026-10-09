"""Make `import dlt` mean dltHub's dlt on Databricks. `spec/002`, R3, R3b and R4.

Databricks has a module of its own named `dlt` (Delta Live Tables), and an import hook
that comes with it. dlt's docs give the workarounds this module does:
https://dlthub.com/docs/dlt-ecosystem/destinations/databricks#troubleshooting

- on serverless: take the hook out of `sys.meta_path` while importing, then put it back;
- on a cluster: drop the hook, and drop what Databricks already loaded under the name.

The docs call both fragile and say the hook's place moved between runtimes. So nothing
here is silent: every step returns a line that the first lines of a run print.

Run on a workspace on 2026-10-07, in a serverless wheel task (runtime `client.2.5`):

- the hook is there, as `dbruntime.PostImportHook.ImportHookFinder` in `sys.meta_path`,
  and Databricks' `dlt` is a folder at `/databricks/spark/python/dlt`;
- a plain `import dlt` gets dltHub's dlt all the same: that folder is not on `sys.path`
  in a wheel task. So there the workaround is not needed, and it does no harm;
- with the hook taken out for the import, as below, the import is dltHub's too.

TODO(verify): a notebook and a classic cluster, which is where dlt's docs say it bites.
"""

import importlib
import sys
from types import ModuleType

# Where Databricks keeps its own `dlt`, per dlt's docs.
DATABRICKS_DLT_DIR = "/databricks/spark/python/dlt"
# The names dlt's docs find the hook by: its class is a `PostImportHook`, and it lives in
# `dbruntime/DeltaLiveTablesHook.py`.
HOOK_MARKS = ("PostImportHook", "DeltaLiveTables")


def is_dlthub(module: ModuleType | None) -> bool:
    """Whether a module named `dlt` is dltHub's and not Databricks'."""
    if module is None:
        return False
    file = getattr(module, "__file__", None) or ""
    return hasattr(module, "pipeline") and not file.startswith(DATABRICKS_DLT_DIR)


def _is_hook(finder: object) -> bool:
    text = f"{type(finder).__module__}.{type(finder).__qualname__} {finder!r}"
    return any(mark in text for mark in HOOK_MARKS)


def _holders(module: ModuleType) -> list[str]:
    """The modules that did `import dlt` and got `module`."""
    return sorted(
        name
        for name, other in list(sys.modules.items())
        if isinstance(other, ModuleType)
        and name != "dlt"
        and not name.startswith("dlt.")
        and other.__dict__.get("dlt") is module
    )


def import_dlt(on_databricks: bool) -> tuple[ModuleType, list[str]]:
    """Import dltHub's dlt. Returns the module, and lines that say what it took."""
    if not on_databricks:
        return importlib.import_module("dlt"), ["nothing to do off Databricks"]

    lines: list[str] = []
    loaded = sys.modules.get("dlt")
    if is_dlthub(loaded):
        return loaded, ["dlt was imported already, and it is dltHub's"]

    if loaded is not None:
        # Something imported `dlt` before this ran and got Databricks' module.
        holders = _holders(loaded)
        lines.append(
            "Databricks' own dlt was imported before leeghwater prepared the process"
            + (f"; these modules hold it: {', '.join(holders)}" if holders else "")
        )
    dropped = [
        name for name in list(sys.modules) if name == "dlt" or name.startswith("dlt.")
    ]
    for name in dropped:
        del sys.modules[name]
    if dropped:
        lines.append(f"dropped {len(dropped)} module(s) Databricks had loaded as dlt")

    before = list(sys.meta_path)
    hooks = [finder for finder in before if _is_hook(finder)]
    if hooks:
        lines.append(f"took {len(hooks)} import hook(s) out while importing dlt")
    else:
        lines.append(
            "found no import hook where dlt's docs expect one; importing dlt as it is"
        )

    try:
        sys.meta_path[:] = [finder for finder in before if finder not in hooks]
        importlib.invalidate_caches()
        module = importlib.import_module("dlt")
    finally:
        sys.meta_path[:] = before

    if is_dlthub(module):
        lines.append("import dlt is dltHub's")
    else:
        lines.append(
            "import dlt is NOT dltHub's after all of that"
            f" (it came from {getattr(module, '__file__', 'nowhere')});"
            " this runtime is untried ground, see the docs for the ones that were tried"
        )
    return module, lines

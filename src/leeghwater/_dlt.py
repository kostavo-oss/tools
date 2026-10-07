"""Every place leeghwater reaches into dlt beyond its documented API, in one file.

Each function here rests on something read in dlt's source, named in its docstring, and
has a test in `tests/test_dlt.py` that fails when dlt moves it. A dlt upgrade that breaks
leeghwater should break this file and nothing else. Nothing here patches dlt.

This module imports dlt. On Databricks, import it after `leeghwater.prepare()` has run.
"""

from collections.abc import Sequence
from typing import Any

import dlt
from dlt.common.configuration.container import Container
from dlt.common.configuration.providers.provider import ConfigProvider
from dlt.common.configuration.specs.pluggable_run_context import PluggableRunContext
from dlt.common.destination import Destination


def _run_context() -> PluggableRunContext:
    # dlt keeps its providers and its runtime config on the run context in its container:
    # `dlt/common/configuration/specs/pluggable_run_context.py`.
    return Container()[PluggableRunContext]


def reload_config_locations() -> None:
    """Make dlt look for `.dlt/` again, after `DLT_PROJECT_DIR` changed.

    dlt reads the variable when it makes its providers
    (`dlt/common/runtime/run_context.py`, `settings_dir`). When dlt was imported before
    `prepare()` ran, they exist already.
    """
    _run_context().reload_providers()


def settings_dir() -> str:
    """Where dlt looks for `config.toml` and `secrets.toml` right now."""
    return _run_context().context.settings_dir


def data_dir() -> str:
    """Where dlt keeps its working files right now."""
    return _run_context().context.data_dir


def apply_log_level() -> None:
    """Make dlt take up a changed `RUNTIME__LOG_LEVEL`.

    dlt makes its logger from its runtime config (`dlt/common/runtime/init.py`), and
    resolves that config once per run context; this throws the cached one away.
    """
    context = _run_context()
    context.context.reset_config()
    context.initialize_runtime()


def config_value(key: str) -> Any:
    """A dlt config value by its dotted name, or None. `dlt.config.get` is dlt's own."""
    return dlt.config.get(key, str)


def registered_providers() -> Sequence[ConfigProvider]:
    """dlt's config providers, in the order dlt asks them. `dlt.secrets` is dlt's own."""
    return dlt.secrets.config_providers


def register_provider(provider: ConfigProvider) -> None:
    """Add a provider after the ones dlt has. `register_provider` is dlt's own API.

    It raises on a provider whose name is registered already; callers look first.
    """
    dlt.secrets.register_provider(provider)


def destination(name: str, **config: Any) -> Any:
    """A destination factory by dlt's short name, with config fields set in the call.

    `Destination.from_reference` takes the config fields of the destination as keyword
    arguments (`dlt/common/destination/reference.py`, `from_reference` and `__init__`),
    and what is set in the call wins over dlt's config: tried in `tests/test_dlt.py` for
    `staging_dataset_name_layout` and `enable_dataset_name_normalization`.
    """
    return Destination.from_reference(name, **config)


def failed_jobs(load_info: Any) -> list[Any]:
    """The failed jobs of every package in a `LoadInfo`.

    `LoadPackageInfo.jobs` is a dict by job state (`dlt/common/storages/load_package.py`).
    """
    return [
        job for package in load_info.load_packages for job in package.jobs["failed_jobs"]
    ]

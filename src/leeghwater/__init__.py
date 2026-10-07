"""leeghwater: your dlt pipeline, the same on your laptop and in a Databricks job.

Importing this package changes nothing and does not import dlt: everything happens in
`prepare()`, which an `App` calls for you. `spec/002`, R2.
"""

from importlib.metadata import version

__version__ = version("leeghwater")

from leeghwater._app import App, pipeline  # noqa: E402
from leeghwater._errors import LeeghwaterError, RunFailed  # noqa: E402
from leeghwater._pipeline import create_pipeline, run  # noqa: E402
from leeghwater._prepare import Setup, prepare  # noqa: E402

__all__ = [
    "App",
    "LeeghwaterError",
    "RunFailed",
    "Setup",
    "__version__",
    "create_pipeline",
    "pipeline",
    "prepare",
    "run",
]

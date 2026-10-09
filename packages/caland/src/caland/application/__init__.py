"""Application layer — use-cases that orchestrate the domain.

Depends on `domain`; never on infrastructure, the SDK or the UI. The read model
(`WorkspaceCache`) is pure in-memory app state, so it lives here too. One
library is used here: `cryptography`, by `files`, to say what a file somebody
picked is — bytes in, facts out, no I/O.
"""

from . import files
from .dotenv import DotenvError, format_dotenv, parse_dotenv
from .loading import Loader, Progress
from .onboarding import Connection, OnboardingService
from .read_model import WorkspaceCache
from .workspace import WorkspaceService

__all__ = [
    "Connection",
    "DotenvError",
    "Loader",
    "OnboardingService",
    "Progress",
    "WorkspaceCache",
    "WorkspaceService",
    "files",
    "format_dotenv",
    "parse_dotenv",
]

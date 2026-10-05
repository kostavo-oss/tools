"""JSON-file settings adapter — persisted UI preferences, never secrets.

Lives at `$XDG_CONFIG_HOME/maeslant/settings.json` (default
`~/.config/maeslant/settings.json`). Deliberately forgiving: a missing,
corrupt, or partial file yields defaults instead of an error, so a bad write
can never keep the app from starting.

Until there is a file there, the one the app kept under its former name is
read instead (`formerly`), so a rename doesn't cost anyone their preferences.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from pathlib import Path

from .. import formerly
from ..domain import Settings


def _config_home() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base).expanduser()


def settings_path() -> Path:
    return _config_home() / "maeslant" / "settings.json"


def former_settings_path() -> Path:
    """Where the file was under the app's former name. Read, never written."""
    return _config_home() / formerly.CONFIG_DIR / "settings.json"


class JsonSettingsStore:
    """`SettingsStore` backed by a small JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or settings_path()
        # only the default location has a former one; a path that was asked
        # for is the whole answer
        self._former = None if path else former_settings_path()

    def load(self) -> Settings:
        raw = self._read(self._path)
        if raw is None and self._former is not None:
            raw = self._read(self._former)
        if raw is None:
            return Settings()
        defaults = Settings()
        kwargs = {
            f.name: raw[f.name]
            for f in fields(Settings)
            if isinstance(raw.get(f.name), type(getattr(defaults, f.name)))
        }
        settings = Settings(**kwargs)
        settings.theme = formerly.theme(settings.theme)
        return settings

    @staticmethod
    def _read(path: Path) -> dict | None:
        """The file as a dict, or None for one that is missing or unusable."""
        try:
            raw = json.loads(path.read_text())
        except (OSError, ValueError):
            return None
        return raw if isinstance(raw, dict) else None

    def save(self, settings: Settings) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(asdict(settings), indent=2) + "\n")
        except OSError:
            pass  # preferences are best-effort; never crash the app over them

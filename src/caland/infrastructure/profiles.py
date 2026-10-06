"""DatabricksCfgProfileStore — the `ProfileStore` port over ~/.databrickscfg.

That file holds tokens. So it is written one writer at a time, never half — a
copy beside it is written and moved into its place — and never left readable by
anybody but its owner. A profile that is added is added to the end of what is
there, which is left exactly as it was; and a profile that is there is never
written over by `add`: it keeps its own way of signing in, and under another
address that would be sent there.
"""

from __future__ import annotations

import configparser
import contextlib
import os
import tempfile
import threading
from pathlib import Path

from ..domain import Exists, Workspace, normalize_host
from .config import config_path

#: One writer at a time, in this process.
_WRITING = threading.Lock()


def _read(path: Path) -> configparser.ConfigParser:
    """The file as it is, forgiving what the Databricks CLI forgives: a profile
    that is there twice is one profile."""
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    if path.exists():
        parser.read(path)
    return parser


def _replace(path: Path, text: str) -> None:
    """Put `text` in the file's place: whole, or not at all. A file that was
    there keeps who may read it; a new one is its owner's alone."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = (path.stat().st_mode & 0o777) if path.exists() else 0o600
    handle, beside = tempfile.mkstemp(dir=path.parent, prefix=".databrickscfg-")
    try:
        with os.fdopen(handle, "w") as copy:
            copy.write(text)
        os.chmod(beside, mode)
        os.replace(beside, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(beside)
        raise


class DatabricksCfgProfileStore:
    def discover(self) -> list[Workspace]:
        """Parse ~/.databrickscfg into a list of Workspace profiles.

        Falls back to an env-var 'DEFAULT' workspace if DATABRICKS_HOST is set
        but no config file exists.
        """
        path = config_path()
        workspaces: list[Workspace] = []

        if path.exists():
            # Databricks uses 'DEFAULT' as a real profile, not just the ini default.
            parser = _read(path)
            seen: set[str] = set()
            for name in [parser.default_section, *parser.sections()]:
                if name in seen:
                    continue
                seen.add(name)
                if not parser.has_section(name) and name != parser.default_section:
                    continue
                host = parser.get(name, "host", fallback="").strip()
                if host:
                    workspaces.append(Workspace(profile=name, host=host))

        if not workspaces:
            env_host = os.environ.get("DATABRICKS_HOST", "").strip()
            if env_host:
                workspaces.append(Workspace(profile="DEFAULT", host=env_host))

        return workspaces

    def names(self) -> list[str]:
        """Every profile the file has a heading for — with an address or not."""
        parser = _read(config_path())
        return [parser.default_section, *parser.sections()]

    def add(self, name: str, host: str) -> None:
        """Keep an address under a new name: the address and that signing in is
        through the browser, as `databricks auth login` writes it. No secret.

        Raises `Exists` when the file has a profile of that name, whatever its
        case and whether it has an address or not — and nothing is written."""
        name, host = name.strip(), normalize_host(host)
        if not name or any(c in name for c in "[]\r\n") or name != name.strip():
            raise Exists(f"“{name}” is no name for a profile.")
        path = config_path()
        with _WRITING:
            taken = [
                other for other in self.names() if other.casefold() == name.casefold()
            ]
            if taken:
                raise Exists(f"There is a profile “{taken[0]}” already.")
            before = path.read_text() if path.exists() else ""
            if before and not before.endswith("\n"):
                before += "\n"
            added = f"[{name}]\nhost = {host}\nauth_type = external-browser\n"
            _replace(path, before + ("\n" if before else "") + added)

    def save(
        self,
        name: str,
        host: str,
        account_id: str | None = None,
        auth_type: str = "external-browser",
    ) -> None:
        """Write a reusable profile into ~/.databrickscfg (mirrors
        `databricks auth login`): host + auth_type, no secret stored. Writes
        over a profile of that name — the terminal version's way; the page
        uses `add`, which does not."""
        path = config_path()
        with _WRITING:
            parser = _read(path)
            name = name.strip() or "caland"
            if name != parser.default_section and not parser.has_section(name):
                parser.add_section(name)
            parser.set(name, "host", normalize_host(host))
            parser.set(name, "auth_type", auth_type)
            if account_id:
                parser.set(name, "account_id", account_id.strip())
            import io

            text = io.StringIO()
            parser.write(text)
            _replace(path, text.getvalue())

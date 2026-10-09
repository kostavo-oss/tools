"""GitHub's API for a pull request's comments, in memory.

What it simulates is what lely *believes* GitHub does: a comment is by
whoever the token is; a run's own token is a bot's and can't ask who it is;
comments are listed a page at a time, oldest first.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lely.github import Api, GitHubError

REPOSITORY = "acme/shop"
TOKEN = "ghs_0123456789abcdefTOKEN"
RUN = "https://github.com/acme/shop/actions/runs/7"
HEAD = "0123456789abcdef0123456789abcdef01234567"

#: Every variable of a run that lely reads; a test's environment has no other.
VARIABLES = (
    "GITHUB_ACTIONS",
    "GITHUB_API_URL",
    "GITHUB_EVENT_NAME",
    "GITHUB_EVENT_PATH",
    "GITHUB_REPOSITORY",
    "GITHUB_RUN_ID",
    "GITHUB_SERVER_URL",
    "GITHUB_SHA",
    "GITHUB_STEP_SUMMARY",
    "GITHUB_TOKEN",
    "GH_TOKEN",
)


class FakeGitHub:
    """`login` is whose token it is; `None` is a run's own token."""

    def __init__(self, login: str | None = None) -> None:
        self.login = login
        self.comments: list[dict[str, Any]] = []
        self.calls: list[tuple[str, str]] = []
        self.connected: list[tuple[str, str]] = []
        #: Methods GitHub refuses, as a job without the permission is refused.
        self.refused: set[str] = set()
        #: What the next calls end in, one each, before anything is answered.
        self.failing: list[GitHubError] = []
        #: The most characters a comment may hold.
        self.longest = 65_536
        self._next = 100

    def connect(self, token: str, base: str) -> Api:
        self.connected.append((token, base))
        return self

    def comment(self, body: str, login: str = "someone", kind: str = "User") -> int:
        """A comment that is there already, by someone."""
        self._next += 1
        self.comments.append(
            {"id": self._next, "body": body, "user": {"login": login, "type": kind}}
        )
        return self._next

    @property
    def bodies(self) -> list[str]:
        return [comment["body"] for comment in self.comments]

    def __call__(self, method: str, path: str, payload: Mapping[str, Any] | None) -> Any:
        self.calls.append((method, path))
        if (method, path) == ("GET", "/user"):
            if self.login is None:
                raise GitHubError("403 Resource not accessible by integration", 403)
            return {"login": self.login}
        if self.failing:
            raise self.failing.pop(0)
        if method in self.refused:
            raise GitHubError("403 Resource not accessible by integration", 403)
        if payload is not None and len(payload["body"]) > self.longest:
            raise GitHubError("422 Validation Failed", 422)
        listed = re.fullmatch(
            rf"/repos/{REPOSITORY}/issues/(\d+)/comments\?per_page=(\d+)&page=(\d+)", path
        )
        if method == "GET" and listed:
            size, page = int(listed[2]), int(listed[3])
            return json.loads(json.dumps(self.comments[(page - 1) * size : page * size]))
        if method == "POST" and re.fullmatch(
            rf"/repos/{REPOSITORY}/issues/\d+/comments", path
        ):
            assert payload is not None
            if self.login is None:
                return {"id": self.comment(payload["body"], "github-actions[bot]", "Bot")}
            return {"id": self.comment(payload["body"], self.login)}
        changed = re.fullmatch(rf"/repos/{REPOSITORY}/issues/comments/(\d+)", path)
        if method == "PATCH" and changed:
            assert payload is not None
            for comment in self.comments:
                if comment["id"] == int(changed[1]):
                    comment["body"] = payload["body"]
                    return {"id": comment["id"]}
            raise GitHubError("404 Not Found")
        raise AssertionError(f"lely asked GitHub for something else: {method} {path}")


def event(
    folder: Path,
    *,
    number: int | None = 12,
    head: str | None = REPOSITORY,
    base: str = REPOSITORY,
) -> Path:
    """The payload of the event a run was started by: a pull request from
    `head` into `base`, or — with no `number` — a push."""
    payload: dict[str, Any] = {"ref": "refs/heads/main"}
    if number is not None:
        payload = {
            "number": number,
            "pull_request": {
                "number": number,
                "head": {
                    "sha": HEAD,
                    "repo": None if head is None else {"full_name": head},
                },
                "base": {"repo": {"full_name": base}},
            },
        }
    path = folder / "event.json"
    path.write_text(json.dumps(payload))
    return path


def environment(folder: Path, *, number: int | None = 12, **pull: Any) -> dict[str, str]:
    """What a run's environment says, with a summary file in `folder`."""
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_API_URL": "https://api.github.com",
        "GITHUB_EVENT_NAME": "pull_request" if number is not None else "push",
        "GITHUB_EVENT_PATH": str(event(folder, number=number, **pull)),
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_RUN_ID": "7",
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_SHA": "f" * 40,
        "GITHUB_STEP_SUMMARY": str(folder / "summary.md"),
        "GITHUB_TOKEN": TOKEN,
    }


def outside(monkeypatch: Any) -> None:
    """No run at all — whatever the machine the tests run on says."""
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)


def inside(monkeypatch: Any, folder: Path, **said: Any) -> Path:
    """A run's environment, set. Returns its summary file."""
    outside(monkeypatch)
    for name, value in environment(folder, **said).items():
        monkeypatch.setenv(name, value)
    return Path(os.environ["GITHUB_STEP_SUMMARY"])

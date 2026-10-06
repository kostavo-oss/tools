"""lely on GitHub: the plan on the pull request, the run on its page.

    lely plan -t dev --github

An edge: it reads what a GitHub Actions run says about itself — its
environment, the event that started it — writes the run's summary file, and
talks to GitHub's API. It is asked for with `--github` and is never on
because of where a command runs.

- **One comment per plan, kept current.** A plan is posted as one comment on
  the pull request and updated in place on the next push. lely finds its own
  comment by the marker on its first line (`<!-- lely:plan:dev -->`): the
  memory is GitHub's, not lely's. A plan that could not be made takes the
  place of the last one, so an old plan never stands there as the new one.
- **Only a comment lely could have written is updated.** Anyone can write a
  comment that starts with the marker. Were lely to put the plan in it, the
  plan would sit in a comment its author can change afterwards. So the
  comment has to be by whoever the token is — or, for a run's own token, which
  is nobody's, by a bot.
- **The run's page.** The plan, and after an apply what each step did and
  what exists now, are written to the job summary.
- **A pull request from a fork gets no plan.** Planning runs the pull
  request's own code, and that must not happen with a workspace's
  credentials. The summary says so. A run that is about a pull request and
  doesn't say where it comes from — one started by a comment — is treated as
  one from a fork.
- **Nothing here decides how a command ends.** Outside a run, without a
  token, without permission: it says what it couldn't do and why, and the
  plan stands on its own.
- **The token goes to GitHub's API and nowhere else.** Only over https, not
  along with a redirect, and never into an error, a comment or a summary:
  what is posted is searched for it first, as it is written and as
  `actions/checkout` keeps it. That is a net, not a wall: a token printed in
  another spelling passes.

What GitHub does, as assumed here:

- A run sets `GITHUB_ACTIONS=true`, and names its event's payload, its
  summary file, its repository and its API:
  https://docs.github.com/en/actions/reference/workflows-and-actions/variables
- A comment on a pull request is an issue comment, of at most 65,536
  characters: https://docs.github.com/en/rest/issues/comments
- A step's summary may be 1 MiB, and one that is larger is dropped whole:
  https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands
- `GET /user` answers for a person's token and refuses a run's own. Seen for
  a person's token; for a run's own, what was seen (2026-10-06, a real run)
  is the outcome: lely found the comment it had posted as
  `github-actions[bot]` and updated it, twice. Read in GitHub's forum, not in
  its docs, that the refusal is a 403.
"""

from __future__ import annotations

import base64
import http.client
import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lely import __version__
from lely.errors import LelyError
from lely.model import Plan, PlanKind, Result
from lely.render import markdown

#: GitHub's API as a function: a method, a path, and what to send. Tests give
#: a fake.
Api = Callable[[str, str, Mapping[str, Any] | None], Any]

#: How an `Api` is made from a token and the API's address.
Connect = Callable[[str, str], Api]

_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_PER_PAGE = 100
#: Where the search for lely's comment gives up: this many comments.
_PAGES = 30

_PERMISSION = "the job needs `permissions: pull-requests: write`"

#: The most characters GitHub takes as a comment.
_COMMENT = 65_536
#: The most bytes GitHub takes as one step's summary.
_STEP_SUMMARY = 1024 * 1024
#: What GitHub answers when it is the body it won't take.
_BODY_REFUSED = (413, 422)
#: A token shorter than this is no token, and is not searched for: "a" would
#: be found in every word.
_SHORTEST = 8


class GitHubError(LelyError):
    """GitHub couldn't be reached, or refused. `status` is what it answered
    with, when it answered."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True, slots=True)
class Note:
    """One thing `--github` did, or couldn't do and why."""

    words: str
    done: bool = True


@dataclass(frozen=True, slots=True)
class Run:
    """What a GitHub Actions run says about itself.

    `fork` names the repository a pull request comes from when that is not
    the repository the run is in. `commit` is the pull request's last commit,
    or the commit the run is for.
    """

    repository: str | None = None
    pull_request: int | None = None
    fork: str | None = None
    commit: str | None = None
    link: str | None = None
    summary: Path | None = None
    token: str | None = None
    api_url: str = "https://api.github.com"


def here(env: Mapping[str, str]) -> Run | None:
    """The run this is, or `None` outside GitHub Actions."""
    if env.get("GITHUB_ACTIONS") != "true":
        return None
    repository = env.get("GITHUB_REPOSITORY") or None
    if repository is not None and not _REPOSITORY.match(repository):
        repository = None
    number, fork, head = _pull_request(env, repository)
    link = None
    if repository and env.get("GITHUB_RUN_ID", "").isdigit():
        server = env.get("GITHUB_SERVER_URL") or "https://github.com"
        link = f"{server}/{repository}/actions/runs/{env['GITHUB_RUN_ID']}"
    summary = env.get("GITHUB_STEP_SUMMARY")
    # a secret pasted with the line break after it is still that secret
    token = (env.get("GITHUB_TOKEN") or env.get("GH_TOKEN") or "").strip()
    return Run(
        repository=repository,
        pull_request=number,
        fork=fork,
        commit=head or env.get("GITHUB_SHA") or None,
        link=link,
        summary=Path(summary) if summary else None,
        token=token or None,
        api_url=env.get("GITHUB_API_URL") or "https://api.github.com",
    )


_UNNAMED = "a repository the run doesn't name"


def _pull_request(
    env: Mapping[str, str], repository: str | None
) -> tuple[int | None, str | None, str | None]:
    """A pull request's number, the fork it comes from if any, and its last
    commit — from the payload of the event that started the run.

    Whenever the run is about a pull request and the payload doesn't say
    where that comes from, it is a fork: lely can't tell that it isn't. That
    is so for a run started by a comment on a pull request (`issue_comment`),
    whose payload never says.
    """
    for_one = env.get("GITHUB_EVENT_NAME", "").startswith("pull_request")
    unknown = _UNNAMED if for_one else None
    try:
        with open(env["GITHUB_EVENT_PATH"], encoding="utf-8") as file:
            event = json.load(file)
    except (KeyError, OSError, ValueError, RecursionError):
        return None, unknown, None
    if not isinstance(event, dict):
        return None, unknown, None
    request = event.get("pull_request")
    if isinstance(request, dict):
        head = request.get("head") if isinstance(request.get("head"), dict) else {}
        base = request.get("base") if isinstance(request.get("base"), dict) else {}
        target = _name(base.get("repo")) or repository
        return (
            _number(request.get("number")),
            _fork(_name(head.get("repo")), target),
            _text(head.get("sha")),
        )
    issue = event.get("issue")
    if isinstance(issue, dict) and issue.get("pull_request") is not None:
        return _number(issue.get("number")), _UNNAMED, None
    earlier = event.get("workflow_run")
    if isinstance(earlier, dict):
        # a run started by another run: where that one's code came from
        target = (
            _name(earlier.get("repository"))
            or _name(event.get("repository"))
            or repository
        )
        requests = earlier.get("pull_requests")
        first = requests[0] if isinstance(requests, list) and requests else {}
        return (
            _number(first.get("number") if isinstance(first, dict) else None),
            _fork(_name(earlier.get("head_repository")), target),
            _text(earlier.get("head_sha")),
        )
    return None, unknown, None


def _fork(source: str | None, target: str | None) -> str | None:
    """The repository the code comes from, when it is not the one it goes to."""
    if source is None or target is None:
        return "a repository that is gone, or that the run doesn't name"
    return source if source.lower() != target.lower() else None


def _name(repo: object) -> str | None:
    name = repo.get("full_name") if isinstance(repo, dict) else None
    return name if isinstance(name, str) and name else None


def _number(value: object) -> int | None:
    return value if type(value) is int else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


# -- what `--github` does ------------------------------------------------------------


def post_plan(
    run: Run, plan: Plan, connect: Connect, *, saved: bool = True
) -> list[Note]:
    """The plan on the run's page, and as the pull request's comment.

    A plan that can't be shown there — it is too long for a comment whatever
    is left out, or GitHub refuses it — is still a new plan: a note that says
    so takes the last plan's place.
    """
    notice = markdown.unshown_markdown(
        plan.kind, plan.target, plan.source.root, link=run.link
    )
    try:
        footer = markdown.footer(
            version=__version__, commit=run.commit, tree=plan.source.tree, link=run.link
        )
        room = markdown.COMMENT_LIMIT - len(footer.encode("utf-8")) - 1
        comment = markdown.plan_markdown(plan, saved=saved, limit=room) + "\n" + footer
        page = markdown.plan_markdown(plan, saved=saved, limit=markdown.SUMMARY_LIMIT)
    except Exception as error:
        # what a plan holds is anyone's to write; one lely can't write down
        # must not leave the last one standing
        return [
            Note(f"the plan couldn't be written down: {type(error).__name__}", False),
            _summarise(run, notice),
            _comment(run, notice, connect),
        ]
    if len(comment) > _COMMENT:
        comment = notice
    return [_summarise(run, page), _comment(run, comment, connect, instead=notice)]


def post_plan_failure(
    run: Run,
    kind: PlanKind,
    target: str,
    root: str | None,
    message: str,
    connect: Connect,
    *,
    placed: bool = True,
) -> list[Note]:
    """In place of a plan that couldn't be made. What went wrong is on the
    run's page, where GitHub hides a run's secrets; the comment only links
    there — what a failing program printed is not posted where nothing does.

    `placed` is false when lely couldn't tell which project of the repository
    this is: the comment of one project is not written over for another's.
    """
    page = _summarise(run, markdown.failure_markdown(kind, target, root, message=message))
    if not placed:
        unplaced = "no comment: lely couldn't tell which project of the repository it is"
        return [page, Note(unplaced, False)]
    comment = markdown.failure_markdown(kind, target, root, link=run.link)
    return [page, _comment(run, comment, connect)]


def post_skipped(run: Run, kind: PlanKind, target: str) -> list[Note]:
    """For a pull request from a fork: the run's page says there is no plan."""
    return [_summarise(run, markdown.skipped_markdown(kind, target, run.fork or "?"))]


def post_result(run: Run, result: Result) -> list[Note]:
    """What a run did and what exists now, on its page."""
    page = markdown.result_markdown(result, limit=markdown.SUMMARY_LIMIT)
    return [_summarise(run, page)]


def post_stopped(
    run: Run, kind: str, target: str | None, refused: bool, message: str
) -> list[Note]:
    """A run that ended before its first step, on its page."""
    return [_summarise(run, markdown.stopped_markdown(kind, target, refused, message))]


def scrub(text: str, token: str | None) -> str:
    """`text` without the token, should anything have printed it: as it is
    written, and as `actions/checkout` keeps it in git's config. Other
    spellings of it are not looked for."""
    if not token or len(token) < _SHORTEST:
        return text
    kept = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return text.replace(token, "***").replace(kept, "***")


def _summarise(run: Run, text: str) -> Note:
    if run.summary is None:
        return Note(
            "no summary on the run's page: `GITHUB_STEP_SUMMARY` isn't set", False
        )
    text = scrub(text, run.token) + "\n"
    if len(text.encode("utf-8", "replace")) > _STEP_SUMMARY:
        # GitHub drops the whole summary of a step that wrote more
        text = "> lely's summary was too long for the run's page. The log has it.\n\n"
    try:
        with open(run.summary, "a", encoding="utf-8", errors="replace") as file:
            file.write(text)
    except OSError as error:
        return Note(f"no summary on the run's page: {error.strerror or error}", False)
    return Note("wrote the run's summary")


def _comment(
    run: Run, body: str, connect: Connect, *, instead: str | None = None
) -> Note:
    """`instead` is what to put there when GitHub won't take `body` itself."""
    if run.pull_request is None:
        return Note("no comment: this run is not for a pull request")
    if run.repository is None:
        return Note("no comment: `GITHUB_REPOSITORY` doesn't name a repository", False)
    if run.token is None:
        # not a failure: the job that plans may well be given no token, and
        # the plan be posted by one that runs none of the project's code
        return Note(
            "no comment: there is no token "
            "(`env: GITHUB_TOKEN: ${{ github.token }}` gives the step one)"
        )
    where = f"pull request #{run.pull_request}"
    try:
        api = connect(run.token, run.api_url)
        try:
            did = upsert(api, run.repository, run.pull_request, scrub(body, run.token))
        except GitHubError as error:
            if instead is None or error.status not in _BODY_REFUSED:
                raise
            upsert(api, run.repository, run.pull_request, instead)
            said = scrub(str(error), run.token)
            return Note(
                f"GitHub wouldn't take the plan as a comment ({said}); {where} "
                "says so, and the run's page has the plan",
                False,
            )
    except GitHubError as error:
        return Note(f"couldn't comment on {where}: {scrub(str(error), run.token)}", False)
    return Note(f"{did} the comment on {where}")


# -- the comment ---------------------------------------------------------------------


def upsert(api: Api, repository: str, pull_request: int, body: str) -> str:
    """Put `body` in the comment that carries its marker, or in a new one.
    Returns `updated` or `created`."""
    marker = body.split("\n", 1)[0]
    existing = find_comment(api, repository, pull_request, marker, author(api))
    try:
        if existing is None:
            comments = f"/repos/{repository}/issues/{pull_request}/comments"
            api("POST", comments, {"body": body})
            return "created"
        api("PATCH", f"/repos/{repository}/issues/comments/{existing}", {"body": body})
        return "updated"
    except GitHubError as error:
        if error.status in (403, 404):
            raise GitHubError(f"{error} ({_PERMISSION})", error.status) from None
        raise


def author(api: Api) -> str | None:
    """Whose token this is — or `None` for one that is nobody's, as a run's
    own token is: `GET /user` refuses it with a 403. Any other failure is a
    failure: taken for "nobody's", it would make lely pass over its own
    comment and write a second one."""
    try:
        answer = api("GET", "/user", None)
    except GitHubError as error:
        if error.status == 403:
            return None
        raise
    login = answer.get("login") if isinstance(answer, dict) else None
    return login if isinstance(login, str) and login else None


def find_comment(
    api: Api, repository: str, pull_request: int, marker: str, login: str | None
) -> int | None:
    """The first comment that starts with `marker` and that lely could have
    written: by `login`, or by a bot when the token is nobody's."""
    for page in range(1, _PAGES + 1):
        comments = api(
            "GET",
            f"/repos/{repository}/issues/{pull_request}/comments"
            f"?per_page={_PER_PAGE}&page={page}",
            None,
        )
        if not isinstance(comments, list):
            raise GitHubError("GitHub's list of comments is not a list")
        for comment in comments:
            if not isinstance(comment, dict) or type(comment.get("id")) is not int:
                continue
            body = comment.get("body")
            if not isinstance(body, str) or body.split("\n", 1)[0].rstrip("\r") != marker:
                continue
            if _could_be_ours(comment, login):
                return comment["id"]
        if len(comments) < _PER_PAGE:
            break
    return None


def _could_be_ours(comment: Mapping[str, Any], login: str | None) -> bool:
    user = comment.get("user")
    if not isinstance(user, dict):
        return False
    if login is not None:
        return user.get("login") == login
    return user.get("type") == "Bot"


# -- the API -------------------------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is not followed: the token would go along with it."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def connect(token: str, base: str, send: Callable[..., Any] | None = None) -> Api:
    """GitHub's API at `base`, with `token`. `send` is how a request is sent:
    tests give their own."""
    if not base.startswith("https://"):
        raise GitHubError(
            f"`GITHUB_API_URL` is not an https address ({base!r}): no token is sent there"
        )
    if not token or any(char.isspace() or not char.isprintable() for char in token):
        raise GitHubError("the token holds a space or a line break: it is not sent")
    send = send or urllib.request.build_opener(_NoRedirect).open

    def call(method: str, path: str, payload: Mapping[str, Any] | None) -> Any:
        try:
            request = urllib.request.Request(
                base.rstrip("/") + path,
                method=method,
                data=None if payload is None else json.dumps(payload).encode("utf-8"),
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": f"lely/{__version__}",
                    **({} if payload is None else {"Content-Type": "application/json"}),
                },
            )
            with send(request, timeout=30) as response:
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            raise GitHubError(f"{error.code} {_said(error)}", error.code) from None
        except (urllib.error.URLError, OSError) as error:
            reason = getattr(error, "reason", None) or error
            raise GitHubError(f"GitHub couldn't be reached: {reason}") from None
        except (ValueError, http.client.HTTPException) as error:
            # in its own words this one may repeat the request, token and all
            raise GitHubError(
                f"the request to GitHub couldn't be made ({type(error).__name__})"
            ) from None
        try:
            return json.loads(text) if text.strip() else None
        except ValueError:
            raise GitHubError("GitHub answered with something that isn't JSON") from None

    return call


def _said(error: urllib.error.HTTPError) -> str:
    """GitHub's own word for a refusal, or the status line's."""
    if 300 <= error.code < 400:
        return "GitHub answered with a redirect, which lely doesn't follow"
    try:
        message = json.loads(error.read().decode("utf-8")).get("message")
    except (OSError, ValueError, AttributeError):
        message = None
    return str(message or error.reason or "refused")

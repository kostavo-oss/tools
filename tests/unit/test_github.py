"""lely on GitHub (008): the comment that is kept current, the run's page,
and everything it says instead of failing. Against a fake GitHub."""

from __future__ import annotations

import io
import json
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

import fake_github
import project
from fake_github import HEAD, REPOSITORY, RUN, TOKEN, FakeGitHub
from lely import github
from lely.github import GitHubError, Note, Run
from lely.model import Change, Plan, PlannedStep, Result, Source, StepPlan, StepResult

TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def plan(*names: str, target: str = "dev", kind: Any = "apply", root: str = ".") -> Plan:
    step = PlannedStep(
        "app",
        "bundle",
        "h",
        StepPlan(tuple(Change(name, "create", name) for name in names or ("jobs.bar",))),
    )
    return Plan(
        "0.1.0", kind, target, project.WORKSPACE, Source(TREE, root=root), (step,)
    )


def run(folder: Path, **said: Any) -> Run:
    found = github.here(fake_github.environment(folder, **said))
    assert found is not None
    return found


# -- what a run says about itself ------------------------------------------------------


def test_outside_a_run_there_is_none(tmp_path: Path) -> None:
    assert github.here({}) is None
    assert github.here({"GITHUB_ACTIONS": "false", "GITHUB_TOKEN": TOKEN}) is None


def test_a_run_for_a_pull_request(tmp_path: Path) -> None:
    assert run(tmp_path) == Run(
        repository=REPOSITORY,
        pull_request=12,
        fork=None,
        commit=HEAD,  # the pull request's last commit, not the merge the run is on
        link=RUN,
        summary=tmp_path / "summary.md",
        token=TOKEN,
        api_url="https://api.github.com",
    )


def test_a_run_for_a_push_has_no_pull_request(tmp_path: Path) -> None:
    found = run(tmp_path, number=None)
    assert (found.pull_request, found.fork, found.commit) == (None, None, "f" * 40)


def test_a_token_by_its_other_name(tmp_path: Path) -> None:
    env = fake_github.environment(tmp_path)
    env["GH_TOKEN"] = env.pop("GITHUB_TOKEN")
    found = github.here(env)
    assert found is not None and found.token == TOKEN


def test_a_pull_request_from_another_repository_is_a_fork(tmp_path: Path) -> None:
    """008/R4a. The repository the pull request is *in* is the base, whatever
    the event: `pull_request_target` runs with the base's secrets."""
    assert run(tmp_path, head="someone/shop").fork == "someone/shop"
    assert run(tmp_path, head="ACME/Shop").fork is None  # the same, spelled otherwise
    assert run(tmp_path, head=None).fork is not None  # the fork was deleted


def test_a_pull_request_lely_cant_place_is_a_fork(tmp_path: Path) -> None:
    """A run for a pull request whose payload can't be read: lely can't tell
    that it isn't from a fork, so it is treated as one."""
    env = fake_github.environment(tmp_path)
    Path(env["GITHUB_EVENT_PATH"]).write_text("{not json")
    found = github.here(env)
    assert found is not None and found.fork is not None and found.pull_request is None
    del env["GITHUB_EVENT_PATH"]
    found = github.here({**env, "GITHUB_EVENT_NAME": "pull_request_target"})
    assert found is not None and found.fork is not None
    found = github.here({**env, "GITHUB_EVENT_NAME": "push"})
    assert found is not None and found.fork is None


def test_a_repository_that_isnt_a_name_is_none(tmp_path: Path) -> None:
    env = fake_github.environment(tmp_path, number=None)
    found = github.here({**env, "GITHUB_REPOSITORY": "acme/shop/../../user"})
    assert found is not None and found.repository is None and found.link is None


# -- the comment (008/R2) --------------------------------------------------------------


def test_the_plan_is_one_comment_updated_in_place(tmp_path: Path) -> None:
    hub = FakeGitHub()
    first = github.post_plan(run(tmp_path), plan("jobs.bar"), hub.connect)
    assert first[1] == Note("created the comment on pull request #12")
    second = github.post_plan(run(tmp_path), plan("jobs.bar", "jobs.new"), hub.connect)
    assert second[1] == Note("updated the comment on pull request #12")
    [body] = hub.bodies
    assert body.startswith("<!-- lely:plan:dev -->\n### lely plan · target `dev`\n")
    assert "\n+     create   jobs.new\n" in body
    assert hub.connected == [(TOKEN, "https://api.github.com")] * 2


def test_under_the_plan_what_it_was_made_from(tmp_path: Path) -> None:
    hub = FakeGitHub()
    github.post_plan(run(tmp_path), plan(), hub.connect)
    assert hub.bodies[0].endswith(
        f"<sub>lely `{github.__version__}` · commit `0123456789ab` · "
        f"tree `4b825dc642cb` · [the run](<{RUN}>)</sub>\n"
    )


def test_one_comment_per_target_kind_and_project(tmp_path: Path) -> None:
    hub = FakeGitHub()
    here = run(tmp_path)
    for one in (
        plan(target="dev"),
        plan(target="prod"),
        plan(target="dev", kind="destroy"),
        plan(target="dev", root="team-a"),
        plan("jobs.other", target="prod"),  # … and again: the second one's
    ):
        github.post_plan(here, one, hub.connect)
    assert [body.split("\n", 1)[0] for body in hub.bodies] == [
        "<!-- lely:plan:dev -->",
        "<!-- lely:plan:prod -->",
        "<!-- lely:destroy:dev -->",
        "<!-- lely:plan:dev:team-a -->",
    ]
    assert "jobs.other" in hub.bodies[1]


def test_its_comment_is_found_however_many_came_before(tmp_path: Path) -> None:
    hub = FakeGitHub()
    for number in range(150):
        hub.comment(f"comment {number}")
    github.post_plan(run(tmp_path), plan("jobs.bar"), hub.connect)
    for number in range(150):
        hub.comment(f"later comment {number}")
    github.post_plan(run(tmp_path), plan("jobs.new"), hub.connect)
    assert len(hub.comments) == 301 and "jobs.new" in hub.bodies[150]


def test_only_a_comment_that_starts_with_the_marker_is_lelys(tmp_path: Path) -> None:
    hub = FakeGitHub()
    quoted = hub.comment("> <!-- lely:plan:dev -->\nlooks fine to me", "bot[bot]", "Bot")
    github.post_plan(run(tmp_path), plan(), hub.connect)
    assert len(hub.comments) == 2 and hub.comments[0]["id"] == quoted
    assert hub.bodies[0].startswith("> ")


def test_a_comment_someone_else_wrote_is_never_updated(tmp_path: Path) -> None:
    """Anyone can write a comment that starts with the marker. A plan put in
    it would sit in a comment its author can change afterwards."""
    forged = "<!-- lely:plan:dev -->\n### lely plan · target `dev`\n\nNo changes."
    hub = FakeGitHub()  # a run's own token: nobody's, and its comments a bot's
    hub.comment(forged, "mallory", "User")
    github.post_plan(run(tmp_path), plan("jobs.bar"), hub.connect)
    github.post_plan(run(tmp_path), plan("jobs.new"), hub.connect)
    assert hub.bodies[0] == forged
    assert len(hub.comments) == 2 and "jobs.new" in hub.bodies[1]

    hub = FakeGitHub(login="deployer")  # a person's token: only that person's
    hub.comment(forged, "mallory", "User")
    hub.comment(forged, "some-app[bot]", "Bot")
    github.post_plan(run(tmp_path), plan("jobs.bar"), hub.connect)
    github.post_plan(run(tmp_path), plan("jobs.new"), hub.connect)
    assert hub.bodies[:2] == [forged, forged]
    assert len(hub.comments) == 3 and "jobs.new" in hub.bodies[2]
    assert hub.comments[2]["user"]["login"] == "deployer"


def test_a_plan_too_long_for_a_comment_is_told_shorter(tmp_path: Path) -> None:
    hub = FakeGitHub()
    long = plan(*(f"jobs.{'x' * 60}{number}" for number in range(2000)))
    github.post_plan(run(tmp_path), long, hub.connect)
    [body] = hub.bodies
    assert len(body) <= 65_536 and "> Shortened to fit: " in body
    assert "**2000 changes · 0 runs · 0 destructive**" in body
    assert body.endswith("</sub>\n")
    # the run's page takes more: there it is whole
    page = (tmp_path / "summary.md").read_text()
    assert "Shortened" not in page and page.count("create   jobs.x") == 2000


# -- the run's page (008/R3) -----------------------------------------------------------


def test_the_plan_goes_on_the_runs_page(tmp_path: Path) -> None:
    hub = FakeGitHub()
    notes = github.post_plan(run(tmp_path), plan(), hub.connect)
    assert notes[0] == Note("wrote the run's summary")
    github.post_plan(run(tmp_path), plan(target="prod"), hub.connect)
    page = (tmp_path / "summary.md").read_text()  # added to, not written over
    assert page.count("### lely plan · target ") == 2
    assert "<sub>" not in page  # the page is the run's own: no link to itself


def test_a_run_and_what_exists_go_on_its_page(tmp_path: Path) -> None:
    done = Result(
        "apply",
        "dev",
        project.WORKSPACE,
        (StepResult("app", "bundle", "done", "", (Change("jobs.bar", "create", "x"),)),),
        "done",
        "",
    )
    assert github.post_result(run(tmp_path), done) == [Note("wrote the run's summary")]
    github.post_stopped(run(tmp_path), "destroy", "dev", True, "Not approved.")
    page = (tmp_path / "summary.md").read_text()
    assert "### lely apply · target `dev`\n" in page and "**Applied: 1 step.**" in page
    assert "### lely destroy · target `dev` · refused\n\n**Nothing was run.**" in page


def test_a_fork_is_told_on_the_runs_page_and_nowhere_else(tmp_path: Path) -> None:
    """008/R4a."""
    here = run(tmp_path, head="someone/shop")
    assert github.post_skipped(here, "apply", "dev") == [Note("wrote the run's summary")]
    page = (tmp_path / "summary.md").read_text()
    assert "### lely plan · target `dev` · skipped" in page
    assert "comes from a fork, `someone/shop`. lely makes no plan" in page


# -- a plan that failed ----------------------------------------------------------------


def test_a_plan_that_failed_takes_the_last_ones_place(tmp_path: Path) -> None:
    """An old plan must not stand there as the plan of what is pushed now.
    What went wrong is on the run's page, where GitHub hides a run's secrets;
    the comment only links there."""
    hub = FakeGitHub()
    here = run(tmp_path)
    github.post_plan(here, plan("jobs.bar"), hub.connect)
    said = "step `seed`'s plan command failed (exit 1):\npassword=hunter2"
    notes = github.post_plan_failure(here, "apply", "dev", ".", said, hub.connect)
    assert notes[1] == Note("updated the comment on pull request #12")
    [body] = hub.bodies
    assert body.startswith(
        "<!-- lely:plan:dev -->\n### lely plan · target `dev` · failed"
    )
    assert "jobs.bar" not in body and "hunter2" not in body
    assert f"[The run's log](<{RUN}>) says what went wrong." in body
    assert "password=hunter2" in (tmp_path / "summary.md").read_text()
    # and the next plan takes its place again
    github.post_plan(here, plan("jobs.bar"), hub.connect)
    assert len(hub.comments) == 1 and "· failed" not in hub.bodies[0]


# -- what it says instead of failing (008/R5) ------------------------------------------


def test_without_a_pull_request_there_is_a_summary_and_no_comment(tmp_path: Path) -> None:
    hub = FakeGitHub()
    notes = github.post_plan(run(tmp_path, number=None), plan(), hub.connect)
    assert notes == [
        Note("wrote the run's summary"),
        Note("no comment: this run is not for a pull request"),
    ]
    assert hub.calls == [] and hub.connected == []


def test_without_a_token_it_says_how_to_give_one(tmp_path: Path) -> None:
    """Not a failure: the job that plans may be given no token on purpose,
    and the plan be posted by a job that runs none of the project's code."""
    hub = FakeGitHub()
    env = fake_github.environment(tmp_path)
    del env["GITHUB_TOKEN"]
    here = github.here(env)
    assert here is not None
    summary, comment = github.post_plan(here, plan(), hub.connect)
    assert summary.done and comment == Note(
        "no comment: there is no token "
        "(`env: GITHUB_TOKEN: ${{ github.token }}` gives the step one)"
    )
    assert hub.calls == []


def test_without_permission_it_says_which_one(tmp_path: Path) -> None:
    hub = FakeGitHub()
    hub.refused = {"POST"}
    _, comment = github.post_plan(run(tmp_path), plan(), hub.connect)
    assert comment == Note(
        "couldn't comment on pull request #12: 403 Resource not accessible by "
        "integration (the job needs `permissions: pull-requests: write`)",
        done=False,
    )
    hub.refused = {"GET"}  # can't even read them
    _, comment = github.post_plan(run(tmp_path), plan(), hub.connect)
    assert not comment.done and "403 Resource not accessible" in comment.words


def test_without_a_summary_file_it_says_so(tmp_path: Path) -> None:
    env = fake_github.environment(tmp_path)
    del env["GITHUB_STEP_SUMMARY"]
    here = github.here(env)
    assert here is not None
    summary, comment = github.post_plan(here, plan(), FakeGitHub().connect)
    assert summary == Note(
        "no summary on the run's page: `GITHUB_STEP_SUMMARY` isn't set", False
    )
    assert comment.done
    blocked = github.here({**env, "GITHUB_STEP_SUMMARY": str(tmp_path / "no" / "s.md")})
    assert blocked is not None
    [note] = github.post_result(blocked, Result("apply", "dev", project.WORKSPACE, ()))
    assert not note.done and note.words.startswith("no summary on the run's page: ")


# -- the token (008/R6) ----------------------------------------------------------------


def test_the_token_is_never_posted_whatever_printed_it(tmp_path: Path) -> None:
    """A plan command that prints its environment puts the token in the plan.
    A run's log and its page hide it; a comment hides nothing."""
    hub = FakeGitHub()
    leaking = plan(f"jobs.bar with {TOKEN}")
    github.post_plan(run(tmp_path), leaking, hub.connect)
    github.post_plan_failure(
        run(tmp_path), "destroy", "dev", ".", f"env: GITHUB_TOKEN={TOKEN}", hub.connect
    )
    posted = "".join(hub.bodies) + (tmp_path / "summary.md").read_text()
    assert TOKEN not in posted and "jobs.bar with ***" in posted
    assert "GITHUB_TOKEN=***" in posted


def test_a_refusal_never_repeats_the_token(tmp_path: Path) -> None:
    def echoing(token: str, base: str) -> Any:
        raise GitHubError(f"401 Bad credentials for {token}")

    _, comment = github.post_plan(run(tmp_path), plan(), echoing)
    assert comment.words == (
        "couldn't comment on pull request #12: 401 Bad credentials for ***"
    )


# -- the API itself --------------------------------------------------------------------


class Answer(io.BytesIO):
    def __enter__(self) -> Answer:
        return self


def test_a_request_is_githubs_api_as_documented() -> None:
    sent: list[Any] = []

    def send(request: Any, timeout: float) -> Answer:
        sent.append(request)
        return Answer(b'{"id": 1}')

    api = github.connect(TOKEN, "https://api.github.com/", send)
    assert api("POST", "/repos/acme/shop/issues/12/comments", {"body": "hi"}) == {"id": 1}
    [request] = sent
    assert request.full_url == "https://api.github.com/repos/acme/shop/issues/12/comments"
    assert request.get_method() == "POST"
    assert json.loads(request.data) == {"body": "hi"}
    assert request.get_header("Authorization") == f"Bearer {TOKEN}"
    assert request.get_header("Accept") == "application/vnd.github+json"
    assert request.get_header("X-github-api-version") == "2022-11-28"
    api("GET", "/user", None)
    assert sent[1].data is None and sent[1].get_method() == "GET"


def test_the_token_goes_to_https_and_not_along_with_a_redirect() -> None:
    with pytest.raises(GitHubError, match="not an https address") as caught:
        github.connect(TOKEN, "http://api.github.example")
    assert TOKEN not in str(caught.value)
    with pytest.raises(GitHubError, match="not an https address"):
        github.connect(TOKEN, "file:///etc/passwd")
    # a redirect is answered with "no", so the request is never sent on
    assert (
        github._NoRedirect().redirect_request(None, None, 302, "Found", {}, "x") is None
    )

    def redirected(request: Any, timeout: float) -> Answer:
        raise urllib.error.HTTPError(
            request.full_url, 302, "Found", Message(), io.BytesIO(b"")
        )

    api = github.connect(TOKEN, "https://api.github.com", redirected)
    with pytest.raises(GitHubError, match="302 GitHub answered with a redirect"):
        api("GET", "/user", None)


def test_a_refusal_is_said_in_githubs_words_without_the_token() -> None:
    def refused(request: Any, timeout: float) -> Answer:
        body = io.BytesIO(b'{"message": "Resource not accessible by integration"}')
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", Message(), body)

    def unreachable(request: Any, timeout: float) -> Answer:
        raise urllib.error.URLError("nodename nor servname provided")

    def not_json(request: Any, timeout: float) -> Answer:
        return Answer(b"<html>")

    with pytest.raises(GitHubError) as caught:
        github.connect(TOKEN, "https://api.github.com", refused)("GET", "/x", None)
    assert str(caught.value) == "403 Resource not accessible by integration"
    with pytest.raises(GitHubError, match="GitHub couldn't be reached: nodename"):
        github.connect(TOKEN, "https://api.github.com", unreachable)("GET", "/x", None)
    with pytest.raises(GitHubError, match="isn't JSON"):
        github.connect(TOKEN, "https://api.github.com", not_json)("GET", "/x", None)


# -- found in the fifth review ---------------------------------------------------------


def event_of(tmp_path: Path, name: str, payload: dict[str, Any]) -> Run:
    env = fake_github.environment(tmp_path, number=None)
    Path(env["GITHUB_EVENT_PATH"]).write_text(json.dumps(payload))
    found = github.here({**env, "GITHUB_EVENT_NAME": name})
    assert found is not None
    return found


def test_a_run_about_a_pull_request_that_doesnt_say_where_it_is_from(
    tmp_path: Path,
) -> None:
    """A run started by a comment on a pull request ("/plan") is told the
    number and nothing else. lely can't tell that it isn't from a fork."""
    commented = event_of(
        tmp_path, "issue_comment", {"issue": {"number": 12, "pull_request": {"url": "x"}}}
    )
    assert commented.pull_request == 12 and commented.fork is not None
    on_an_issue = event_of(tmp_path, "issue_comment", {"issue": {"number": 3}})
    assert (on_an_issue.pull_request, on_an_issue.fork) == (None, None)


def test_a_run_started_by_another_run_is_placed_by_that_ones_code(
    tmp_path: Path,
) -> None:
    def started_by(head: str | None) -> Run:
        earlier: dict[str, Any] = {
            "head_sha": HEAD,
            "repository": {"full_name": REPOSITORY},
            "pull_requests": [{"number": 12}],
        }
        if head is not None:
            earlier["head_repository"] = {"full_name": head}
        return event_of(tmp_path, "workflow_run", {"workflow_run": earlier})

    assert started_by("someone/shop").fork == "someone/shop"
    assert started_by(None).fork is not None
    ours = started_by(REPOSITORY)
    assert (ours.fork, ours.pull_request, ours.commit) == (None, 12, HEAD)


def test_a_token_pasted_with_its_line_break_is_still_that_token(tmp_path: Path) -> None:
    """It ended up on stderr, in urllib's words for a header it wouldn't send."""
    env = fake_github.environment(tmp_path)
    found = github.here({**env, "GITHUB_TOKEN": f"  {TOKEN}\n"})
    assert found is not None and found.token == TOKEN
    for broken in (f"{TOKEN}\nmore", f"{TOKEN} more", f"{TOKEN}\x00", ""):
        with pytest.raises(GitHubError) as caught:
            github.connect(broken, "https://api.github.com")
        assert (
            str(caught.value) == "the token holds a space or a line break: it is not sent"
        )


def test_an_error_that_quotes_the_request_is_not_repeated() -> None:
    def choking(request: Any, timeout: float) -> Any:
        raise ValueError(f"Invalid header value b'Bearer {TOKEN}'")

    api = github.connect(TOKEN, "https://api.github.com", choking)
    with pytest.raises(GitHubError) as caught:
        api("GET", "/user", None)
    assert str(caught.value) == "the request to GitHub couldn't be made (ValueError)"


def test_the_token_is_searched_for_as_checkout_keeps_it_too() -> None:
    import base64

    kept = base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()
    text = f"extraheader = AUTHORIZATION: basic {kept}\ntoken {TOKEN}"
    assert (
        github.scrub(text, TOKEN) == "extraheader = AUTHORIZATION: basic ***\ntoken ***"
    )
    # one too short to be a token is in every word: nothing is searched for
    assert github.scrub("<!-- lely:plan:dev -->", "l") == "<!-- lely:plan:dev -->"
    assert github.scrub("as it was", None) == "as it was"


def test_github_failing_for_a_moment_makes_no_second_comment(tmp_path: Path) -> None:
    """A 502 where lely asks whose token it has was read as "nobody's": lely
    then passed over its own comment and wrote a second one, never updated."""
    hub = FakeGitHub(login="deployer")
    github.post_plan(run(tmp_path), plan("jobs.bar"), hub.connect)

    def failing(method: str, path: str, payload: Any) -> Any:
        if path == "/user":
            raise GitHubError("502 Bad Gateway", 502)
        return hub(method, path, payload)

    _, comment = github.post_plan(
        run(tmp_path), plan("jobs.new"), lambda token, base: failing
    )
    assert comment == Note(
        "couldn't comment on pull request #12: 502 Bad Gateway", done=False
    )
    assert len(hub.comments) == 1
    github.post_plan(run(tmp_path), plan("jobs.new"), hub.connect)
    assert len(hub.comments) == 1 and "jobs.new" in hub.bodies[0]


def test_a_plan_github_wont_take_says_so_where_the_last_one_stood(tmp_path: Path) -> None:
    """A new plan that can't be posted must not leave the last one standing as
    if it were this one: the reviewer would read the wrong plan under a green
    run."""
    hub = FakeGitHub()
    github.post_plan(run(tmp_path), plan("jobs.bar"), hub.connect)
    hub.longest = 400  # GitHub's own limit, made small
    longer = plan("jobs.gone", *(f"jobs.j{number}" for number in range(30)))
    _, comment = github.post_plan(run(tmp_path), longer, hub.connect)
    assert not comment.done
    assert comment.words.startswith("GitHub wouldn't take the plan as a comment (422 ")
    [body] = hub.bodies
    assert body.startswith(
        "<!-- lely:plan:dev -->\n### lely plan · target `dev` · not shown"
    )
    assert "jobs.bar" not in body and f"[The run's page](<{RUN}>) has the plan." in body
    assert "create   jobs.gone" in (tmp_path / "summary.md").read_text()


def test_a_plan_lely_cant_write_down_says_so_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hub = FakeGitHub()
    github.post_plan(run(tmp_path), plan("jobs.bar"), hub.connect)

    def broken(*args: Any, **kwargs: Any) -> str:
        raise UnicodeEncodeError("utf-8", "x", 0, 1, "surrogates not allowed")

    monkeypatch.setattr(github.markdown, "plan_markdown", broken)
    notes = github.post_plan(run(tmp_path), plan("jobs.gone"), hub.connect)
    assert notes[0] == Note(
        "the plan couldn't be written down: UnicodeEncodeError", done=False
    )
    assert "· not shown\n" in hub.bodies[0] and "jobs.bar" not in hub.bodies[0]
    assert "· not shown\n" in (tmp_path / "summary.md").read_text()


def test_a_summary_too_long_for_the_page_is_not_written_whole(tmp_path: Path) -> None:
    """GitHub drops the whole summary of a step that wrote more than 1 MiB."""
    here = run(tmp_path)
    assert github._summarise(here, "x" * 2_000_000).done
    assert (tmp_path / "summary.md").read_text() == (
        "> lely's summary was too long for the run's page. The log has it.\n\n"
    )
    # … and what a failing program printed is cut long before that
    github.post_stopped(here, "apply", "dev", False, "E" * 5_000_000)
    assert (tmp_path / "summary.md").stat().st_size < 30_000


def test_a_failure_lely_cant_place_is_not_filed_under_another_project(
    tmp_path: Path,
) -> None:
    hub = FakeGitHub()
    github.post_plan(run(tmp_path), plan("jobs.bar"), hub.connect)  # the top's own
    notes = github.post_plan_failure(
        run(tmp_path), "apply", "dev", None, "no config", hub.connect, placed=False
    )
    assert notes[1] == Note(
        "no comment: lely couldn't tell which project of the repository it is", False
    )
    assert "jobs.bar" in hub.bodies[0]
    assert "no config" in (tmp_path / "summary.md").read_text()


def test_only_a_number_is_a_comments_id(tmp_path: Path) -> None:
    hub = FakeGitHub()
    hub.comment("<!-- lely:plan:dev -->\nx", "github-actions[bot]", "Bot")
    hub.comments[0]["id"] = True
    github.post_plan(run(tmp_path), plan(), hub.connect)
    assert len(hub.comments) == 2

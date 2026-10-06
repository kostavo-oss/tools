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
    hub = FakeGitHub()
    env = fake_github.environment(tmp_path)
    del env["GITHUB_TOKEN"]
    here = github.here(env)
    assert here is not None
    summary, comment = github.post_plan(here, plan(), hub.connect)
    assert summary.done and not comment.done
    assert comment.words == (
        "no comment: there is no token. Give the step "
        "`env: GITHUB_TOKEN: ${{ github.token }}`"
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

"""lely as Markdown: snapshots of the shared scenario, and the rule that
nothing a plan says is Markdown (008/R1)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pytest
from syrupy.assertion import SnapshotAssertion

import project
from fakes import FakeDatabricks, deploy
from lely import planning, running
from lely.config import Config, load
from lely.model import (
    Change,
    Input,
    Item,
    Overview,
    Plan,
    PlanKind,
    PlannedStep,
    Result,
    Source,
    Status,
    StepPlan,
    StepResult,
    StepStatus,
    Workspace,
)
from lely.render.markdown import (
    failure_markdown,
    footer,
    marker,
    plan_markdown,
    result_markdown,
    skipped_markdown,
    status_markdown,
    stopped_markdown,
)
from lely.step import NullLog

#: What the scenario's pipeline was deployed with before: another storage.
MOVED = {
    **project.DEPLOYED,
    "pipelines.foo": {
        "id": "42",
        "config": {"name": "pipeline foo", "storage": "dbfs:/old-storage"},
    },
}


def edges(fake: FakeDatabricks) -> dict[str, Any]:
    return {
        "workspace": project.WORKSPACE,
        "env": {},
        "databricks": fake,
        "log": NullLog(),
        "connect": lambda: cast(Any, None),
    }


def planned(
    config: Config, fake: FakeDatabricks, kind: PlanKind = "apply", **source: Any
) -> Plan:
    return planning.plan(
        config, target="dev", source=Source(**source), kind=kind, **edges(fake)
    )


# -- the shared scenario -----------------------------------------------------------


def test_a_first_deploy(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    config = load(project.write(tmp_path))
    built = planned(config, project.databricks(tmp_path), tree="4b825dc6", root=".")
    assert plan_markdown(built) == snapshot


def test_a_destructive_change_is_named_above_the_plan(
    tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    config = load(project.write(tmp_path))
    fake = FakeDatabricks(project.world(tmp_path, deployed=False))
    deploy(fake.world, MOVED)
    built = planned(config, fake, tree="4b825dc6", dirty=True, root="team-a")
    shown = plan_markdown(built)
    assert shown == snapshot
    assert "**Destructive:** `app: pipelines.foo`\n" in shown
    assert "\n-     replace  pipelines.foo  destructive\n" in shown


def test_a_destroy_plan_runs_from_the_bottom_up(
    tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    config = load(project.write(tmp_path))
    built = planned(
        config, project.databricks(tmp_path), "destroy", tree="4b825dc6", root="."
    )
    shown = plan_markdown(built)
    assert shown == snapshot
    assert shown.startswith("<!-- lely:destroy:dev -->\n### lely destroy plan · ")
    assert "**Destructive:**" not in shown  # a destroy is nothing but


def test_nothing_to_destroy(tmp_path: Path) -> None:
    config = load(project.write(tmp_path))
    fake = FakeDatabricks(project.world(tmp_path, deployed=False))
    shown = plan_markdown(planned(config, fake, "destroy", tree="4b82", root="."))
    assert "\n**Nothing to destroy.**\n" in shown


def test_an_apply_and_what_exists_after_it(
    tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    """008/R3: what each step did, and what now exists, with links."""
    config = load(project.write(tmp_path))
    fake = project.databricks(tmp_path)
    approved = planned(config, fake)
    result = running.apply(config, approved, at_waiting=lambda step: True, **edges(fake))
    shown = result_markdown(result)
    assert shown == snapshot
    assert (
        "| `app` | `job` | `jobs.bar` | `job bar` | `1001` | `created` | "
        f"[open](<{project.WORKSPACE.host}/jobs/1001>) |\n"
    ) in shown


def test_a_run_that_failed(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    config = load(project.write(tmp_path))
    (tmp_path / "ops" / "notify.sh").write_text(
        "#!/bin/sh\necho 'no route' >&2; exit 7\n"
    )
    fake = project.databricks(tmp_path)
    approved = planned(config, fake)
    result = running.apply(config, approved, at_waiting=lambda step: True, **edges(fake))
    shown = result_markdown(result)
    assert shown == snapshot
    assert shown.startswith("### lely apply · target `dev` · failed\n")
    assert "**Nothing was rolled back.**" in shown


def test_status(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    config = load(project.write(tmp_path))
    found = running.status(config, target="dev", **edges(project.databricks(tmp_path)))
    assert status_markdown(found) == snapshot


def test_a_plan_that_is_never_saved_says_nothing_about_files(tmp_path: Path) -> None:
    config = load(project.write(tmp_path))
    built = planned(config, project.databricks(tmp_path))
    saved = plan_markdown(built)
    assert "> Applied from a file, this stops before `notify`: " in saved
    assert "> Not in a git repository: " in saved
    unsaved = plan_markdown(built, saved=False)
    assert "from a file" not in unsaved and "git" not in unsaved


# -- the marker (008/R2) ---------------------------------------------------------------


def test_the_first_line_says_whose_plan_this_is() -> None:
    assert marker("apply", "dev") == "<!-- lely:plan:dev -->"
    assert marker("destroy", "dev") == "<!-- lely:destroy:dev -->"
    assert marker("apply", "dev", ".") == "<!-- lely:plan:dev -->"
    assert marker("apply", "dev", "teams/a") == "<!-- lely:plan:dev:teams/a -->"


def test_no_target_ends_the_marker_or_reads_as_another() -> None:
    """One target's marker never starts another's, and nothing in a name ends
    the comment the marker is."""
    assert not marker("apply", "dev-eu").startswith(marker("apply", "dev")[:-4] + " ")
    hostile = marker("apply", "dev --> @everyone", "a:b")
    assert hostile == "<!-- lely:plan:dev%20-%2D%3E%20%40everyone:a%3Ab -->"
    assert hostile.count("-->") == 1 and hostile.count(":") == 3
    assert "--" not in marker("apply", "a---b")[4:-3]
    # a project named like a target is not that target
    assert marker("apply", "dev", "eu") != marker("apply", "dev:eu")


# -- nothing a plan says is Markdown ---------------------------------------------------

EVIL = (
    "@everyone ![x](https://example.com/p.png) <img src=x> [click](https://example.com)"
    " </code> ``` ```` | <!-- -->"
)


def outside(markdown: str) -> str:
    """What is left of `markdown` without its fenced blocks and its code spans,
    as CommonMark reads them: what a reader's browser is given to obey."""
    kept: list[str] = []
    fence = ""
    for line in markdown.split("\n"):
        if fence:
            closing = re.fullmatch(r" {0,3}(`{3,}) *", line)
            if closing and len(closing[1]) >= len(fence):
                fence = ""
            continue
        opening = re.match(r" {0,3}(`{3,})[^`]*$", line)
        if opening:
            fence = opening[1]
            continue
        kept.append(_without_spans(line))
    assert not fence, "a block was never closed"
    return "\n".join(kept)


def _without_spans(line: str) -> str:
    runs = list(re.finditer("`+", line))
    kept, at, index = [], 0, 0
    while index < len(runs):
        opening = runs[index]
        closing = next(
            (run for run in runs[index + 1 :] if len(run[0]) == len(opening[0])),
            None,
        )
        if closing is None:
            index += 1
            continue
        kept.append(line[at : opening.start()])
        at = closing.end()
        index = runs.index(closing) + 1
    kept.append(line[at:])
    return "".join(kept)


def hostile_plan() -> Plan:
    step = PlannedStep(
        f"app {EVIL}",
        f"bundle {EVIL}",
        "h",
        StepPlan(
            (
                Change(
                    "k",
                    "create",
                    f"jobs.a {EVIL}",
                    detail=("```", "````diff", f"   ```\n{EVIL}"),
                ),
                Change("k2", "delete", f"x\n```\n# {EVIL}\n~~~", destructive=True),
            ),
            notes=(f"note\n`````\n{EVIL}",),
            outputs={"id": f"`{EVIL}`"},
        ),
        inputs=(Input(f"v {EVIL}", "model.v", EVIL),),
    )
    waiting = PlannedStep(
        f"no`tify\n{EVIL}",
        "command",
        "h",
        inputs=(Input("", f"app {EVIL}.id", None, known=False),),
        waits_for=(f"app {EVIL}.id",),
        every_deploy=True,
    )
    return Plan(
        "0.1.0",
        "apply",
        f"dev {EVIL}",
        Workspace(f"https://h {EVIL}", f"me {EVIL}"),
        Source("4b82", dirty=True, root=f"team {EVIL}"),
        (step, waiting),
    )


def test_nothing_a_plan_says_is_markdown() -> None:
    """A plan is made from a pull request's own files. What it names must not
    notify anyone, load anything or link anywhere where it is shown — nor end
    the block it is shown in."""
    shown = plan_markdown(hostile_plan())
    left = outside(shown)
    for obeyed in ("@", "![", "<img", "](", "</code>", "~~~", "# @"):
        assert obeyed not in left.split("\n", 1)[1], obeyed
    # the first line is the marker: one comment, and the names in it are spelled out
    first = shown.split("\n", 1)[0]
    assert first.startswith("<!-- lely:plan:dev%20%40everyone") and "@" not in first
    assert first.count("<!--") == 1 and first.endswith(" -->") and "-->" not in first[:-3]
    # and all of it is still there to read
    assert shown.count("@everyone") >= 12
    assert "\n+     create   jobs.a @everyone " in shown
    assert "\n-     delete   x  destructive\n-              ```\n" in shown


def test_no_shorter_plan_is_markdown_either() -> None:
    plan = hostile_plan()
    told = [plan_markdown(plan, limit=limit) for limit in (3400, 3000, 2100, 10)]
    assert [text.count("Shortened to fit") for text in told] == [1, 1, 1, 1]
    assert len(set(told)) == 3  # each way of telling it shorter
    for text in told:
        assert "@" not in outside(text).split("\n", 1)[1]


def test_nothing_a_run_says_is_markdown() -> None:
    changes = hostile_plan().steps[0].plan.changes
    overview = Overview(
        (
            Item(f"job {EVIL}", f"jobs.a {EVIL}", f"n\n{EVIL}", True, EVIL, EVIL),
            Item("job", "jobs.b", "b", True, "2", "javascript:alert(1)"),
            Item(
                "job", "jobs.c", "c", True, "3", "https://e.example/a b>)](https://x.y)"
            ),
            Item("job", "jobs.d", "d", True, "4", "https://dbc.example/jobs/4?o=1#top"),
        ),
        (f"note {EVIL}",),
    )
    result = Result(
        "apply",
        f"dev {EVIL}",
        Workspace(f"https://h {EVIL}", f"me {EVIL}"),
        (
            StepResult(
                f"app {EVIL}",
                f"bundle {EVIL}",
                "failed",
                f"boom {EVIL}",
                changes,
                overview,
                {f"jobs.a {EVIL}": "created", f"gone {EVIL}": "deleted"},
            ),
        ),
        "failed",
        f"it failed {EVIL}\n```\n{EVIL}",
    )
    shown = result_markdown(result)
    left = outside(shown)
    for obeyed in ("@", "![", "<img", "</code>", "javascript", "x.y"):
        assert obeyed not in left, obeyed
    # the one address a reader can follow is the one link; the rest is text
    assert (
        left.count("](") == 1 and "[open](<https://dbc.example/jobs/4?o=1#top>)" in left
    )
    assert "`javascript:alert(1)`" in shown
    # a `|` in a name doesn't end its cell: every row has as many as the first
    rows = [line for line in shown.split("\n") if line.startswith("| ")]
    assert len(rows) == 7
    assert len({len(re.findall(r"(?<!\\)\|", row)) for row in rows}) == 1


def test_the_notes_beside_a_plan_are_not_markdown_either() -> None:
    for text in (
        failure_markdown(
            "apply", f"dev {EVIL}", f"team {EVIL}", message=f"no\n```\n{EVIL}"
        ),
        skipped_markdown("apply", f"dev {EVIL}", f"someone/{EVIL}"),
        footer(version=f"0.1 {EVIL}", commit=EVIL, link=f"https://x.example/{EVIL}"),
    ):
        left = outside(text)
        left = left.split("\n", 1)[1] if text.startswith("<!--") else left
        for obeyed in ("@", "![", "<img", "](", "</code>"):
            assert obeyed not in left, (obeyed, text)


def test_what_a_plan_says_is_shown_never_obeyed() -> None:
    """Control characters and what reorders the text around it, as in a terminal."""
    step = PlannedStep(
        "app",
        "bundle",
        "h",
        StepPlan((Change("k", "create", "jobs.‮elbat‬\x1b[2K\r"),)),
    )
    plan = Plan("0", "apply", "dev\x07", project.WORKSPACE, Source(), (step,))
    shown = plan_markdown(plan)
    assert not re.search("[\x00-\x09\x0b-\x1f‮‬]", shown)
    assert "+     create   jobs.�elbat��[2K�" in shown
    assert "target `dev�`" in shown


# -- what fits (008/R2) ----------------------------------------------------------------


def long_plan() -> Plan:
    steps = tuple(
        PlannedStep(
            f"step{number}",
            "bundle",
            "h",
            StepPlan(
                tuple(
                    Change(
                        f"jobs.j{index}",
                        "update" if index else "delete",
                        f"jobs.j{index}",
                        destructive=not index,
                        detail=("tasks: " + "x" * 200,),
                    )
                    for index in range(40)
                )
            ),
        )
        for number in range(12)
    )
    return Plan("0", "apply", "dev", project.WORKSPACE, Source("4b82", root="."), steps)


def size(text: str) -> int:
    return len(text.encode("utf-8"))


def test_a_plan_too_long_for_a_comment_is_told_shorter_and_says_so() -> None:
    plan = long_plan()
    whole = plan_markdown(plan)
    assert size(whole) > 100_000 and "Shortened" not in whole
    assert plan_markdown(plan, limit=size(whole)) == whole

    no_detail = plan_markdown(plan, limit=60_000)
    assert size(no_detail) <= 60_000
    assert "> Shortened to fit: the details of each change are left out." in no_detail
    assert "\n!     update   jobs.j39\n" in no_detail and "tasks: " not in no_detail

    counted = plan_markdown(plan, limit=3_000)
    assert size(counted) <= 3_000
    assert "> Shortened to fit: each step's changes are counted, not listed." in counted
    assert "\n  step11  bundle\n      40 changes · 0 runs · 1 destructive\n" in counted

    head = plan_markdown(plan, limit=900)
    assert "> Shortened to fit: the steps are left out." in head and "```" not in head
    # what a reviewer must not miss is in every one of them
    for shown in (whole, no_detail, counted, head, plan_markdown(plan, limit=1)):
        assert shown.startswith("<!-- lely:plan:dev -->\n### lely plan · target `dev`\n")
        assert "**480 changes · 0 runs · 12 destructive**" in shown
        assert "**Destructive:** `step0: jobs.j0`, " in shown
        assert "`step9: jobs.j0`, and 2 more\n" in shown


def test_a_run_too_long_for_its_page_is_told_shorter_and_says_so() -> None:
    plan = long_plan()
    listed = Overview(
        tuple(Item("job", f"jobs.j{n}", "n" * 300, True, str(n)) for n in range(40))
    )
    result = Result(
        "apply",
        "dev",
        project.WORKSPACE,
        tuple(
            StepResult(step.name, step.uses, "done", "", step.plan.changes, listed)
            for step in plan.steps
        ),
        "done",
        "",
    )
    whole = result_markdown(result)
    assert "#### What exists now" in whole and "Shortened" not in whole
    shorter = result_markdown(result, limit=size(whole) - 1)
    assert "#### What exists now" not in shorter
    assert "> Shortened to fit: `lely status` shows what exists now." in shorter
    assert "\n!       update   jobs.j39\n" in shorter
    shortest = result_markdown(result, limit=2_000)
    assert "update" not in shortest and "\n  ✓ step11  bundle\n" in shortest
    assert "**Applied: 12 steps.**" in shortest


# -- beside a plan ---------------------------------------------------------------------


def test_a_plan_that_failed_takes_the_place_of_the_last_one() -> None:
    """008/R2: found by the same marker, so the plan of an earlier push doesn't
    stand there as if it were this one's."""
    link = "https://github.com/acme/shop/actions/runs/7"
    shown = failure_markdown("apply", "dev", "team-a", link=link)
    assert shown.startswith(
        "<!-- lely:plan:dev:team-a -->\n"
        "### lely plan · project `team-a` · target `dev` · failed\n"
    )
    assert "**The plan could not be made, so there is none to review.**" in shown
    assert f"[The run's log](<{link}>) says what went wrong." in shown
    assert "```" not in shown
    told = failure_markdown("destroy", "dev", message="bundle: no such target")
    assert "### lely destroy plan · target `dev` · failed" in told
    assert "```text\nbundle: no such target\n```" in told


def test_a_fork_is_told_why_there_is_no_plan() -> None:
    """008/R4a."""
    shown = skipped_markdown("apply", "dev", "someone/shop")
    assert shown.startswith("### lely plan · target `dev` · skipped\n")
    assert "comes from a fork, `someone/shop`. lely makes no plan" in shown
    assert not shown.startswith("<!--")  # it is no plan, and takes no plan's place


def test_a_run_that_never_started_says_so() -> None:
    shown = stopped_markdown("apply", "dev", True, f"Plan again.\n```\n{EVIL}")
    assert shown.startswith(
        "### lely apply · target `dev` · refused\n\n**Nothing was run.**"
    )
    assert "@" not in outside(shown)
    assert "### lely destroy · target `?` · failed" in stopped_markdown(
        "destroy", None, False, "no config"
    )


def test_under_a_plan_what_made_it_and_from_what() -> None:
    link = "https://github.com/acme/shop/actions/runs/7"
    sha = "0123456789abcdef0123456789abcdef01234567"
    assert footer(version="0.1.0", commit=sha, tree="4b825dc642cb6eb9", link=link) == (
        "<sub>lely `0.1.0` · commit `0123456789ab` · tree `4b825dc642cb` · "
        f"[the run](<{link}>)</sub>\n"
    )
    assert footer(version="0.1.0") == "<sub>lely `0.1.0`</sub>\n"
    assert "the run" not in footer(version="0.1.0", link="http://plain.example/x")


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "http://plain.example/jobs/1",
        "https://dbc.example/jobs/1 onmouseover=x",
        "https://dbc.example/jobs/1>",
        "https://dbc.example/jobs/1\n",
        "https://dbc.example/a\\b",
        "",
    ],
)
def test_only_an_address_a_reader_can_follow_is_a_link(url: str) -> None:
    item = Item("job", "jobs.a", "a", True, "1", url)
    step = StepStatus("app", "bundle", Overview((item,)))
    status = Status("dev", project.WORKSPACE, (step,))
    assert "](" not in status_markdown(status)

"""lely as a page (007): the shared scenario, the rule that nothing a plan says
is markup, and a plugin's view inside a frame lely owns."""

from __future__ import annotations

import re
from html.parser import HTMLParser
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
    StepPlan,
    StepResult,
    Workspace,
)
from lely.render.html import POLICY, framed, plan_html, result_html
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


def body(page: str) -> str:
    """The page without its style sheet: what a snapshot is for."""
    return page[page.index("<body>") : page.index("</body>")]


class Read(HTMLParser):
    """A page as a browser reads it: its elements, their attributes, its text."""

    def __init__(self, page: str) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []
        self.feed(page)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))

    def handle_data(self, data: str) -> None:
        self.text.append(data)

    def named(self, *tags: str) -> list[dict[str, str | None]]:
        return [attrs for tag, attrs in self.elements if tag in tags]


# -- the shared scenario ---------------------------------------------------------------


def test_a_plan_with_a_destructive_change(
    tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    """007/R1, R3: every step in order; the destructive change is counted where
    the page opens, named there, and carries the word where it stands."""
    config = load(project.write(tmp_path))
    fake = FakeDatabricks(project.world(tmp_path, deployed=False))
    deploy(fake.world, MOVED)
    page = plan_html(planned(config, fake, tree="4b825dc642cb6eb9", root="team-a"))
    assert body(page) == snapshot
    opening = page[page.index("<header>") : page.index("</header>")]
    assert '<span class="destructive">1 destructive</span>' in opening
    assert "<li><code>app</code>: replace <code>pipelines.foo</code></li>" in opening
    assert (
        'pipelines.foo <strong class="destructive">destructive</strong>'
        '<div class="detail">replaced: storage (immutable)</div>'
    ) in page
    assert '<span class="state waiting">waiting</span>' in page
    assert '<p class="warning">waiting for app.resources.jobs.bar.id</p>' in page
    order = re.findall(r'<span class="name">([^<]+)</span>', page)
    assert order == ["model", "app", "notify", "backfill", "warm"]


def test_a_destroy_plan_runs_from_the_bottom_up(
    tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    """007/R5."""
    config = load(project.write(tmp_path))
    built = planned(
        config, project.databricks(tmp_path), "destroy", tree="4b825dc6", root="."
    )
    page = plan_html(built)
    assert body(page) == snapshot
    assert "<title>lely destroy plan · dev</title>" in page
    order = re.findall(r'<span class="name">([^<]+)</span>', page)
    assert order == ["warm", "backfill", "notify", "app", "model"]
    assert 'jobs.backfill <strong class="destructive">destructive</strong>' in page


def test_a_run_and_what_exists_after_it(
    tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    """007/R6: what each step did, and what exists, with links."""
    config = load(project.write(tmp_path))
    fake = project.databricks(tmp_path)
    result = running.apply(
        config, planned(config, fake), at_waiting=lambda step: True, **edges(fake)
    )
    page = result_html(result)
    assert body(page) == snapshot
    assert '<p class="outcome done">Applied: 3 steps.</p>' in page
    assert (
        "<td>jobs.bar</td><td>job bar</td><td>1001</td><td>created</td>"
        f'<td><a href="{project.WORKSPACE.host}/jobs/1001" '
        'rel="noopener noreferrer">open</a></td>'
    ) in page


def test_a_run_that_failed(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    config = load(project.write(tmp_path))
    (tmp_path / "ops" / "notify.sh").write_text(
        "#!/bin/sh\necho 'no route' >&2; exit 7\n"
    )
    fake = project.databricks(tmp_path)
    result = running.apply(
        config, planned(config, fake), at_waiting=lambda step: True, **edges(fake)
    )
    page = result_html(result)
    assert body(page) == snapshot
    assert '<strong class="failed">Failed.</strong> Nothing was rolled back.' in page
    assert "<li>failed: <code>notify</code></li>" in page
    assert "no route" in page


# -- one file, nothing fetched, nothing run (007/R4, R8) -------------------------------


def test_the_page_is_one_file_that_fetches_and_runs_nothing(tmp_path: Path) -> None:
    config = load(project.write(tmp_path))
    fake = project.databricks(tmp_path)
    built = planned(config, fake, tree="4b82", root=".")
    page = plan_html(built)
    assert page == plan_html(built)  # the same plan, the same page: no clock in it
    read = Read(page)
    assert read.named("script", "link", "img", "iframe", "object", "form", "button") == []
    assert read.named("input", "base", "embed", "video", "audio", "a") == []
    [policy] = [
        attrs["content"]
        for attrs in read.named("meta")
        if attrs.get("http-equiv") == "Content-Security-Policy"
    ]
    assert policy == POLICY and "default-src 'none'" in policy
    assert "script-src" not in policy  # so none is allowed
    assert not any("style" in attrs or "onclick" in attrs for _, attrs in read.elements)
    assert "url(" not in page and "@import" not in page
    assert "This page only shows" in page


# -- nothing a plan says is markup -----------------------------------------------------

EVIL = "<script>alert(1)</script><img src=x onerror=alert(2)>\"'&amp;</details></main>"


def test_nothing_a_plan_says_is_markup() -> None:
    step = PlannedStep(
        f"app{EVIL}",
        f"bundle{EVIL}",
        "h",
        StepPlan(
            (Change(f"k{EVIL}", "delete", f"jobs{EVIL}", detail=(f"line{EVIL}",)),),
            notes=(f"note{EVIL}",),
            outputs={f"id{EVIL}": f"v{EVIL}"},
        ),
        inputs=(Input(f"label{EVIL}", f"model{EVIL}", f"value{EVIL}"),),
    )
    waiting = PlannedStep("notify", "command", "h", waits_for=(f"app{EVIL}.id",))
    skipped = PlannedStep("warm", "command", "h", skipped=f"why{EVIL}")
    plan = Plan(
        f"0{EVIL}",
        "apply",
        f"dev{EVIL}",
        Workspace(f"https://h{EVIL}", f"me{EVIL}"),
        Source(f"4b82{EVIL}", root=f"team{EVIL}"),
        (step, waiting, skipped),
    )
    read = Read(plan_html(plan))
    assert read.named("script", "img") == []
    assert not any("onerror" in attrs for _, attrs in read.elements)
    assert sum(1 for tag, _ in read.elements if tag == "details") == 3
    assert sum(1 for tag, _ in read.elements if tag == "main") == 1
    # … and all of it is there to read, as it was written
    assert "".join(read.text).count(EVIL) >= 12


def test_nothing_a_run_says_is_markup() -> None:
    overview = Overview(
        (
            Item(f"job{EVIL}", f"jobs.a{EVIL}", f"n{EVIL}", True, f"1{EVIL}", EVIL),
            Item("job", "jobs.b", "b", True, "2", "javascript:alert(1)"),
            Item("job", "jobs.c", "c", True, "3", 'https://x.example/"onmouseover="x'),
            Item("job", "jobs.d", "d", True, "4", "https://dbc.example/jobs/4?o=1#top"),
        ),
        (f"note{EVIL}",),
    )
    result = Result(
        "apply",
        f"dev{EVIL}",
        Workspace("https://dbc.example", f"me{EVIL}"),
        (
            StepResult(
                f"app{EVIL}",
                f"bundle{EVIL}",
                "failed",
                f"boom{EVIL}",
                (Change("k", "create", f"jobs{EVIL}"),),
                overview,
                {f"gone{EVIL}": "deleted"},
            ),
        ),
        "failed",
        f"it failed{EVIL}",
    )
    read = Read(result_html(result))
    assert read.named("script", "img") == []
    # the one address a reader can follow is the one link
    assert read.named("a") == [
        {"href": "https://dbc.example/jobs/4?o=1#top", "rel": "noopener noreferrer"}
    ]
    assert "javascript:alert(1)" in "".join(read.text)


def test_what_a_reader_cant_see_is_made_visible() -> None:
    step = PlannedStep(
        "app",
        "bundle",
        "h",
        StepPlan((Change("k", "create", "jobs.\u202eelbat\x1b[2K"),)),
    )
    page = plan_html(
        Plan("0", "apply", "dev\udc80", project.WORKSPACE, Source(), (step,))
    )
    page.encode("utf-8")
    assert "jobs.�elbat�[2K" in page and "target <b>dev�</b>" in page


# -- a plugin's own view, inside a frame lely owns (007/R2, R9) ------------------------


def with_view(view: str) -> str:
    step = PlannedStep(
        "app",
        "bundle",
        "h",
        StepPlan((Change("jobs.bar", "create", "jobs.bar"),), view=view),
    )
    return plan_html(Plan("0", "apply", "dev", project.WORKSPACE, Source(), (step,)))


def test_a_plugins_view_is_shown_under_the_changes_never_in_their_place() -> None:
    view = (
        "<h2>Jobs</h2><table><tr><th>resource</th><th class='num'>tasks</th></tr>"
        "<tr><td class='key create'>jobs.bar</td><td class='num'>3</td></tr></table>"
    )
    page = with_view(view)
    changes = page.index('<table class="changes">')
    frame = page.index('<div class="frame">')
    assert changes < frame
    assert "<h2>From the plugin, <code>bundle</code></h2>" in page
    assert (
        '<div class="frame"><h4>Jobs</h4><table><tr><th>resource</th>'
        '<th class="num">tasks</th></tr><tr><td class="key create">jobs.bar</td>'
        '<td class="num">3</td></tr></table></div>'
    ) in page
    # a step whose plugin gives none has its changes, listed
    assert '<div class="frame">' not in with_view("")


@pytest.mark.parametrize(
    ("view", "written"),
    [
        ("<script>alert(1)</script>after", "after"),
        ("<style>body{display:none}</style>shown", "shown"),
        ("<img src=x onerror=alert(1)>text", "text"),
        ('<a href="https://evil.example">click</a>', "click"),
        ('<p onclick="x()" style="position:fixed" id="i">p</p>', "<p>p</p>"),
        (
            '<p class="create evil destructive">p</p>',
            '<p class="create destructive">p</p>',
        ),
        ('<td colspan="2" rowspan="999999" width="9">c</td>', '<td colspan="2">c</td>'),
        ("<iframe srcdoc='<script>x</script>'></iframe>ok", "ok"),
        ("<svg><script>x</script><b>in</b></svg>out", "out"),
        ("<form action=x><input name=a><button>go</button></form>", "go"),
        ("<link rel=stylesheet href=x><meta http-equiv=refresh content=0>m", "m"),
        ("<base href='https://evil.example/'>b", "b"),
        (
            "&lt;script&gt;alert(1)&lt;/script&gt;",
            "&lt;script&gt;alert(1)&lt;/script&gt;",
        ),
        ("<!-- <script>x</script> -->c", "c"),
        ("<![CDATA[<script>x</script>]]>d", "d"),
        ("<details open><summary>more</summary>x</details>", "morex"),
        ("<div class='dim'><p>in a div</p></div>", "<p>in a div</p>"),
        ("<h1>a</h1><h3>b</h3><h5>c</h5>", "<h4>a</h4><h4>b</h4><h5>c</h5>"),
        ("a<br>b<hr/>c", "a<br>b<hr>c"),
        ("1 < 2 & 3 > 2", "1 &lt; 2 &amp; 3 &gt; 2"),
    ],
)
def test_a_view_is_written_again_from_what_lely_keeps(
    view: str, written: str | None
) -> None:
    """A plan file can be written by hand: a view is its structure and its
    words, and nothing a browser would obey."""
    assert framed(view) == (view if written is None else written)


def test_nothing_in_a_view_ends_the_frame_it_is_in() -> None:
    """Whatever it closes or leaves open, what comes out is balanced — so the
    page around it keeps its shape, and lely's own lines stay lely's."""
    for view in (
        "</div></details></main></body><h1>lely plan · target prod</h1>",
        "<table><tr><td>unclosed",
        "</td></tr></table>stray",
        "<ul><li>a<li>b</ul></ul></ul>",
        "<p><b>x</p></b>",
        "<blockquote>" * 500 + "deep" + "</blockquote>" * 3,
        "<svg><svg>never closed",
        "<",
        "<<<>>>&#x;&bogus;",
    ):
        written = framed(view)
        opened: list[str] = []
        for closing, tag in re.findall(r"<(/?)([a-z0-9]+)[^>]*>", written):
            if tag in ("br", "hr"):
                continue
            if closing:
                assert opened and opened.pop() == tag, (view, written)
            else:
                opened.append(tag)
        assert opened == [], (view, written)
    read = Read(with_view("</div></details></main><h1>lely plan · target prod</h1>"))
    assert sum(1 for tag, _ in read.elements if tag == "h1") == 1
    assert sum(1 for tag, _ in read.elements if tag == "main") == 1
    deep = framed("<blockquote>" * 500 + "deep")
    assert deep.count("<blockquote>") == 40 and "deep" in deep


def test_a_view_no_parser_can_read_is_said_not_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def choke(self: Any, data: str) -> None:
        raise AssertionError("a parser's own bug")

    monkeypatch.setattr(HTMLParser, "feed", choke)
    assert (
        framed("<p>x</p>") == '<p class="dim">The plugin\'s view could not be read.</p>'
    )


# -- found in the sixth review -----------------------------------------------------------


def test_a_view_holds_no_element_the_page_around_it_is_built_from() -> None:
    """A browser doesn't close elements where a count of tags says they
    close: a `<li>` ends the one before it through whatever stands between, a
    table throws out what doesn't belong in it. Each of these views, written
    again "balanced", ended the frame — and some the step, and the list of
    steps — in a real browser, and put its own words among lely's.

    So a view keeps no `div`, no `details` and no `summary`: with no end tag
    of theirs to write, nothing in a view can end the `div` it is in.
    `tests/browser` asks a real browser, thousands of times.
    """
    got_out = (
        "<ul><li><div><li>x</li></div>after</li></ul>",
        "<li><div><div><li>x</li></div></div>after</li>",
        "<table><div><table></table></div>after</table>",
        "<table><details><table></table></details>after</table>",
        "<dl><dd><div><dd>x</dd></div>after</dd></dl>",
    )
    for view in got_out:
        written = framed(view)
        assert "after" in written
        for built_from in ("div", "details", "summary", "main", "body", "html"):
            assert f"<{built_from}" not in written and f"</{built_from}" not in written


def test_the_frame_stands_in_nothing_a_view_could_end() -> None:
    """The other half: the frame is a `div` in a `div` in the step's fold —
    in no list, no paragraph, no table and no heading, whose end tags a view
    may well hold."""
    read = Read(with_view("<p>x</p>"))
    opened: list[str] = []
    around: list[str] | None = None

    class Walk(HTMLParser):
        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            nonlocal around
            if dict(attrs).get("class") == "frame":
                around = list(opened)
            if tag not in ("meta", "br", "hr"):
                opened.append(tag)

        def handle_endtag(self, tag: str) -> None:
            while opened and opened.pop() != tag:
                pass

    Walk().feed(with_view("<p>x</p>"))
    assert around == ["html", "body", "main", "details", "div"]
    assert len(read.named("div")) == 2  # the step's body, and the frame


@pytest.mark.parametrize(
    ("url", "linked"),
    [
        ("https://dbc.example/jobs/1", True),
        ("https://DBC.example/jobs/1?o=2#x", True),
        ("https://other.example/jobs/1", False),  # found in review: any https host was
        ("https://dbc.example.evil.example/jobs/1", False),
        ("https://dbc.example@evil.example/jobs/1", False),
        ("https://user@dbc.example/jobs/1", False),
        ("https://dbc.example:8443/jobs/1", False),
        ("http://dbc.example/jobs/1", False),
        ("//dbc.example/jobs/1", False),
        ("javascript:alert(1)", False),
        ("", False),
    ],
)
def test_open_leads_into_the_runs_own_workspace_and_nowhere_else(
    url: str, linked: bool
) -> None:
    """007/R6 says "links into the workspace". What a result file says a
    thing's address is becomes a link only when it is one."""
    from lely.render.markdown import result_markdown

    result = Result(
        "apply",
        "dev",
        Workspace("https://dbc.example", "jane"),
        (
            StepResult(
                "app",
                "bundle",
                "done",
                "",
                (),
                Overview((Item("job", "jobs.a", "a", True, "1", url),)),
            ),
        ),
    )
    assert bool(Read(result_html(result)).named("a")) is linked
    assert ("[open](<" in result_markdown(result)) is linked
    nowhere = Result("apply", "dev", Workspace("?", "?"), result.steps)
    assert Read(result_html(nowhere)).named("a") == []


def test_a_view_cut_short_by_what_lely_drops_says_so() -> None:
    """An element lely leaves out, never closed, takes all after it along —
    as it would in a browser. The reader is told."""
    written = framed("<p>shown</p><svg><p>and this is gone")
    assert written.startswith("<p>shown</p>") and "gone" not in written
    assert "The rest of this view is left out" in written
    assert "left out" not in framed("<p>a</p><svg><p>x</p></svg><p>b</p>")

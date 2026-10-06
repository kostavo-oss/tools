"""A plugin's view, as a real browser reads it.

`lely.render.html.framed` writes a view again from a short list of elements.
Whether what it writes stays inside the frame it is put in is not something
this code can say about itself: a browser's parser moves and closes elements
by rules of its own. So this asks one. It makes thousands of views at random,
puts each in a page as `lely ui` would, has Chrome parse the page, and holds
the result to four things:

- there is one frame, and every word of the view is inside it;
- the page outside the frame is what it is around a harmless view — the
  header, the step's own lines, the steps after it, the footer;
- inside the frame there is no element and no attribute lely doesn't keep;
- no script ran.

It needs Chrome and is skipped without it, so it is not part of the gate:

    uv run pytest tests/browser

(The check an independent review built to find the way out of the frame, on
2026-10-06 — with `div` and `details` among the kept elements, nine views in
ten got out.)
"""

from __future__ import annotations

import html
import json
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from lely.model import Change, Plan, PlannedStep, Source, StepPlan, Workspace
from lely.render.html import CLASSES, framed, plan_html

CHROME = next(
    (
        path
        for path in (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            shutil.which("google-chrome") or "",
            shutil.which("chromium") or "",
            shutil.which("chromium-browser") or "",
        )
        if path and Path(path).exists()
    ),
    None,
)
pytestmark = pytest.mark.skipif(CHROME is None, reason="needs Chrome")

#: What a view is made of here: what lely keeps, what it once kept, what it
#: drops whole, and what it has never kept.
KEPT = (
    "p",
    "span",
    "pre",
    "code",
    "blockquote",
    "hr",
    "br",
    "ul",
    "ol",
    "li",
    "dl",
    "dt",
    "dd",
    "h4",
    "h5",
    "h6",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "caption",
    "strong",
    "b",
    "em",
    "i",
    "small",
    "kbd",
    "samp",
    "sub",
    "sup",
    "del",
    "ins",
    "mark",
    "abbr",
    "h1",
    "h2",
    "h3",
)
#: The ones a browser's parser has rules of its own for.
HOT = (
    "table",
    "tr",
    "td",
    "th",
    "caption",
    "tbody",
    "li",
    "dd",
    "dt",
    "p",
    "b",
    "strong",
    "h4",
    "ul",
    "dl",
    "pre",
    "code",
    "small",
    "em",
    "i",
)
ONCE = ("div", "details", "summary")
DROPPED = (
    "script",
    "style",
    "svg",
    "math",
    "select",
    "textarea",
    "title",
    "template",
    "noscript",
    "xmp",
    "iframe",
)
NEVER = (
    "a",
    "form",
    "button",
    "input",
    "img",
    "body",
    "html",
    "main",
    "section",
    "frameset",
    "col",
    "colgroup",
    "option",
    "plaintext",
    "nobr",
    "font",
    "marquee",
    "object",
    "applet",
)

#: Views that got out, before: each is the start of some of the random ones.
STARTS = (
    "",
    "<li><div><li></li></div>",
    "<li><div><div><li></li></div></div>",
    "<table><details><table></table></details>",
    "<table><div><table></table></div>",
    "<dl><dd><div><dd>x</dd></div>",
    "<b><table><details><table></table></details>",
    '<table><b class="destructive"><details><table></table></details>',
)


def a_view(rng: random.Random, longest: int) -> str:
    tokens = [rng.choice(STARTS)]
    for index in range(rng.randint(3, longest)):
        roll = rng.random()
        if roll < 0.45:
            tag = rng.choice(HOT if rng.random() < 0.7 else (*KEPT, *ONCE))
            given = rng.choice(["", "", "", ' class="destructive dim"', " open", " id=x"])
            tokens.append(f"<{tag}{given}>")
        elif roll < 0.78:
            tokens.append(
                f"</{rng.choice(HOT if rng.random() < 0.7 else (*KEPT, *ONCE))}>"
            )
        elif roll < 0.83:
            tokens.append(f"<{rng.choice(DROPPED)}>")
        elif roll < 0.86:
            tokens.append(f"</{rng.choice(DROPPED)}>")
        elif roll < 0.90:
            tag = rng.choice(NEVER)
            tokens.append(rng.choice([f"<{tag}>", f"</{tag}>", f"<{tag} onclick=x()>"]))
        elif roll < 0.92:
            tokens.append("<script>document.title = 'a script ran'</script>")
        else:
            tokens.append(f"WORD{index} ")
    return "".join(tokens) + "WORDLAST"


def a_plan(view: str) -> Plan:
    """A plan whose first step has a view, with steps after it to disturb."""
    return Plan(
        "0",
        "apply",
        "prod",
        Workspace("https://dbc-example.cloud.databricks.com", "jane@example.com"),
        Source(),
        (
            PlannedStep(
                "app",
                "bundle",
                "h",
                StepPlan((Change("jobs.bar", "create", "jobs.bar"),), view=view),
            ),
            PlannedStep(
                "tables",
                "command",
                "h",
                StepPlan((Change("customers", "delete", "customers"),)),
            ),
            PlannedStep("notify", "command", "h", StepPlan()),
        ),
    )


HARNESS = """<!doctype html><meta charset=utf-8><title>running</title>
<pre id=out></pre>
<script>
const BEFORE = %(before)s, AFTER = %(after)s, WRITTEN = %(written)s;
const KEPT = new Set(%(kept)s), CLASSES = new Set(%(classes)s);
const parser = new DOMParser();
function around(doc) {
  // the page with its frame emptied: what must not depend on the view
  const copy = doc.documentElement.cloneNode(true);
  const frame = copy.querySelector('div.frame');
  if (!frame) return 'no frame';
  frame.textContent = '';
  return copy.outerHTML;
}
const harmless = around(parser.parseFromString(BEFORE + 'x' + AFTER, 'text/html'));
const wrong = [];
WRITTEN.forEach((written, index) => {
  const doc = parser.parseFromString(BEFORE + written + AFTER, 'text/html');
  const why = new Set();
  const frames = doc.querySelectorAll('div.frame');
  if (frames.length !== 1) why.add('frames: ' + frames.length);
  const frame = frames[0];
  const walker = doc.createTreeWalker(doc.documentElement, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode()))
    if (/WORD/.test(node.data) && !(frame && frame.contains(node)))
      why.add('words outside the frame');
  if (around(doc) !== harmless) why.add('the page around the frame changed');
  if (frame) for (const element of frame.querySelectorAll('*')) {
    if (!KEPT.has(element.localName)) why.add('element ' + element.localName);
    for (const attribute of element.attributes) {
      if (!['class', 'colspan', 'rowspan'].includes(attribute.name))
        why.add('attribute ' + attribute.name);
      if (attribute.name === 'class')
        for (const name of attribute.value.split(' '))
          if (!CLASSES.has(name)) why.add('class ' + name);
    }
  }
  if (why.size) wrong.push([index, [...why].join('; ')]);
});
document.getElementById('out').textContent = JSON.stringify(wrong);
document.title = document.title === 'running' ? 'done' : document.title;
</script>
"""


def in_chrome(views: list[str], folder: Path) -> list[tuple[str, str, str]]:
    """What Chrome makes of each view in a page: the ones that went wrong, as
    the view, what lely wrote for it, and why."""
    mark = "@@THE VIEW@@"
    page = plan_html(a_plan("x")).replace(
        '<div class="frame">x</div>', f'<div class="frame">{mark}</div>'
    )
    before, after = page.split(mark)
    written = [framed(view) for view in views]

    def quoted(value: object) -> str:
        return json.dumps(value).replace("</", "<\\/")

    kept = sorted({*KEPT, "tbody"} - {"h1", "h2", "h3"})
    harness = folder / "harness.html"
    harness.write_text(
        HARNESS
        % {
            "before": quoted(before),
            "after": quoted(after),
            "written": quoted(written),
            "kept": quoted(kept),
            "classes": quoted(sorted(CLASSES)),
        },
        encoding="utf-8",
    )
    done = subprocess.run(
        [
            str(CHROME),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--disable-background-networking",
            "--dump-dom",
            harness.resolve().as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert "<title>done</title>" in done.stdout, done.stdout[:300] + done.stderr[-300:]
    found = re.search(r'<pre id="out">(.*?)</pre>', done.stdout, re.S)
    assert found is not None
    return [
        (views[index], written[index], why)
        for index, why in json.loads(html.unescape(found[1]))
    ]


@pytest.mark.parametrize(
    ("seed", "longest"), [(1, 12), (2, 12), (3, 30), (4, 30), (5, 60)]
)
def test_nothing_in_a_view_gets_out_of_its_frame(
    seed: int, longest: int, tmp_path: Path
) -> None:
    rng = random.Random(seed)
    views = [a_view(rng, longest) for _ in range(2000)]
    wrong = in_chrome(views, tmp_path)
    shortest = min(wrong, key=lambda one: len(one[0]), default=None)
    assert wrong == [], f"{len(wrong)} of {len(views)}; the shortest: {shortest!r}"


def test_the_views_that_got_out_before() -> None:
    """Each of these ended the frame — and some the step, and the list of
    steps — in a browser, while lely's own count called it balanced."""
    for view in (
        "<ul><li><div><li>x</li></div>WORD1</li></ul>",
        "<li><div><div><li>x</li></div></div>WORD2</li>",
        "<table><div><table></table></div>WORD3</table>",
        "<table><details><table></table></details>WORD4</table>",
        "<dl><dd><div><dd>x</dd></div>WORD5</dd></dl>",
    ):
        written = framed(view)
        assert "div" not in written and "details" not in written, written


def test_the_views_that_got_out_before_stay_in(tmp_path: Path) -> None:
    views = [
        "<ul><li><div><li>x</li></div>WORD1</li></ul>",
        "<li><div><div><li>x</li></div></div>WORD2</li>",
        "<table><div><table></table></div>WORD3</table>",
        "<table><details><table></table></details>WORD4</table>",
        "<dl><dd><div><dd>x</dd></div>WORD5</dd></dl>",
        "</div></div></details></main></body><h1>lely plan · target dev</h1>WORD6",
        "<table><tr><td>WORD7",
    ]
    assert in_chrome(views, tmp_path) == []

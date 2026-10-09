"""lely as a page: one plan, or one run, as a single HTML file.

    lely ui plan.json

One file, nothing fetched, nothing run. The style sheet is inline and there is
no script; the page tells the browser as much, with a policy that allows the
style sheet and nothing else. It opens from disk, survives being attached to a
pull request, and reads the same on any machine with the network off.

**It only shows.** There is no button that applies or destroys, no server and
no credentials: a page is a way of reading a plan.

Every step has a section of its own, in the order the steps run: what it
takes, what it would change, what it gives. The changes are always lely's own
list — they are what `apply` holds the step to. Destructive changes are
counted where the page opens, named there, and carry the word on every line,
not only a colour.

**A plugin's own view is HTML, inside a frame lely owns.** A step's plan may
hold the plugin's picture of it — the bundle's resources by type, say. It is
shown under the changes and never in place of them. A plan file can be written
by hand, so that HTML is not trusted: it is taken apart and written again from
a short list of elements — tables, lists, text — with every word escaped. No
script, no style, no link, no image and no attribute but a class from lely's
own list comes through, and nothing in it can end the frame it is in.

Pure: a plan or a result in, text out.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from html import escape
from html.parser import HTMLParser

from lely import __version__
from lely.model import (
    Change,
    Input,
    Overview,
    Plan,
    PlannedStep,
    Result,
    StepResult,
)
from lely.render import words
from lely.render.words import clean

SYMBOLS = {"create": "+", "update": "~", "delete": "−", "replace": "±", "run": "▶"}

#: How a page says what made it: `lely ui` writes over a page of its own, and
#: over nothing else it wasn't told to.
GENERATOR = "lely"

#: What the page lets a browser do: show the one style sheet. No script, no
#: image, no font, no frame, no form — whatever were to end up in it.
POLICY = (
    "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
)

_CSS = """\
:root { color-scheme: light dark; --edge: #8884; --dim: #888c; --sunk: #8881;
  --green: #2e8b57; --amber: #b8860b; --red: #c0392b; --blue: #3b7dd8; }
* { box-sizing: border-box; }
body { margin: 0 auto; padding: 2rem 1.5rem 4rem; max-width: 64rem;
  font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
code, pre, .mono, table.changes, ul.takes, ul.gives { font-size: 13px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
h1 { font-size: 1.35rem; margin: 0 0 .2rem; font-weight: 600; }
h2 { font-size: .78rem; text-transform: uppercase; letter-spacing: .05em;
  color: var(--dim); font-weight: 600; margin: 1.1rem 0 .3rem; }
.dim, .meta, footer { color: var(--dim); }
.meta { margin: 0 0 1rem; font-size: .85rem; overflow-wrap: anywhere; }
.counts { font-weight: 600; margin: .8rem 0; }
.destructive { color: var(--red); font-weight: 700; }
.alert { border: 1px solid var(--red); border-left-width: .4rem; border-radius: .4rem;
  padding: .6rem .9rem; margin: .8rem 0; }
.alert ul { margin: .3rem 0 0; padding-left: 1.2rem; }
.warning { border-left: .25rem solid var(--amber); padding: .1rem .7rem;
  margin: .5rem 0; }
.quiet { border-left: .25rem solid var(--edge); padding: .1rem .7rem; margin: .5rem 0;
  color: var(--dim); }
.outcome { font-weight: 600; margin: .8rem 0; }
.outcome.done, .counts.done, .state.done { color: var(--green); }
.state.done { border-color: var(--green); }
.state.failed, .state.refused, strong.failed, strong.refused { color: var(--red); }
.state.failed, .state.refused { border-color: var(--red); }
details.step { border-top: 1px solid var(--edge); padding: .7rem 0; }
details.step > summary { cursor: pointer; display: flex; flex-wrap: wrap; gap: .7rem;
  align-items: baseline; }
.name { font-weight: 600; font-size: 1.02rem; overflow-wrap: anywhere; }
.uses, .tally { color: var(--dim); overflow-wrap: anywhere; }
.state { font-size: .75rem; border: 1px solid var(--edge); border-radius: 1rem;
  padding: 0 .55rem; }
.state.waiting { border-color: var(--amber); color: var(--amber); }
.tally { margin-left: auto; font-size: .85rem; }
.body { padding: .2rem 0 .4rem 1.1rem; }
.body > p { margin: .4rem 0; }
ul.takes, ul.gives, ul.notes { list-style: none; margin: .3rem 0; padding: 0;
  overflow-wrap: anywhere; }
ul.notes { color: var(--dim); }
table.changes { border-collapse: collapse; margin: .4rem 0; width: 100%; }
table.changes td { padding: .12rem .6rem .12rem 0; vertical-align: top; }
td.sym { width: 1.4rem; text-align: center; }
td.action { width: 5.2rem; }
td.what { overflow-wrap: anywhere; white-space: pre-wrap; }
.detail { color: var(--dim); white-space: pre-wrap; padding-left: 1.2rem; }
tr.create .sym, tr.create .action { color: var(--green); }
tr.update .sym, tr.update .action { color: var(--amber); }
tr.delete .sym, tr.delete .action, tr.replace .sym, tr.replace .action {
  color: var(--red); }
tr.run .sym, tr.run .action { color: var(--blue); }
table.exists { border-collapse: collapse; margin: .4rem 0; width: 100%; }
table.exists th { text-align: left; font-size: .75rem; text-transform: uppercase;
  letter-spacing: .04em; color: var(--dim); border-bottom: 1px solid var(--edge);
  padding: .25rem .6rem .25rem 0; }
table.exists td { padding: .2rem .6rem .2rem 0; vertical-align: top;
  overflow-wrap: anywhere; }
pre.said { background: var(--sunk); padding: .7rem .9rem; border-radius: .4rem;
  overflow-x: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
.frame { border: 1px solid var(--edge); border-radius: .4rem; padding: .5rem .9rem;
  margin: .3rem 0; overflow-x: auto; }
.frame table { border-collapse: collapse; }
.frame th, .frame td { text-align: left; padding: .15rem .9rem .15rem 0;
  vertical-align: top; }
.frame th { font-size: .75rem; text-transform: uppercase; letter-spacing: .04em;
  color: var(--dim); border-bottom: 1px solid var(--edge); }
.frame h4, .frame h5, .frame h6 { margin: .7rem 0 .2rem; font-size: .9rem; }
.frame .create { color: var(--green); }
.frame .update { color: var(--amber); }
.frame .delete, .frame .replace { color: var(--red); }
.frame .run { color: var(--blue); }
.frame .unchanged, .frame .dim { color: var(--dim); }
.frame .num { text-align: right; }
.frame .key { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px; }
footer { margin-top: 2.5rem; border-top: 1px solid var(--edge); padding-top: .8rem;
  font-size: .82rem; }
"""


# -- a plan -----------------------------------------------------------------------


def plan_html(plan: Plan, *, saved: bool = True) -> str:
    """A plan as a page. `saved` is false for a plan that was never written."""
    project = plan.source.root
    title = [words.title(plan)]
    if project not in (None, "", "."):
        title.append(f"project <b>{_t(project or '')}</b>")
    title.append(f"target <b>{_t(plan.target)}</b>")
    host, identity = _t(plan.workspace.host), _t(plan.workspace.identity)
    made_on = [f"<code>{host}</code> as <code>{identity}</code>"]
    if plan.source.tree is not None:
        made_on.append(f"git tree <code>{_t(plan.source.tree[:12])}</code>")
    made_on.append(f"lely {_t(plan.tool_version)}")
    head = [
        f"<h1>{_dotted(title)}</h1>",
        f'<p class="meta">{_dotted(made_on)}</p>',
        _counts(plan),
        _destructive(plan),
        *(
            f'<p class="{"warning" if warning.loud else "quiet"}">{_t(warning.words)}</p>'
            for warning in words.warnings(plan, saved)
        ),
    ]
    taken = words.taken(plan)
    steps = [_step(step, taken) for step in words.in_order(plan)]
    about = (
        "This page only shows: nothing on it applies or destroys anything, and "
        "nothing was fetched to make it. It was made from a plan"
        + (" file" if saved else "")
        + f" by lely {_t(__version__)}; what <code>lely apply</code> runs is the "
        "changes listed for each step."
    )
    return _page(" · ".join((words.title(plan), plan.target)), head, steps, about)


def _counts(plan: Plan) -> str:
    if plan.summary.empty:
        return f'<p class="counts done">{_t(words.nothing(plan))}</p>'
    parts = []
    for part in words.counts(plan):
        loud = part.endswith(" destructive") and plan.summary.destructive
        parts.append(f'<span class="destructive">{_t(part)}</span>' if loud else _t(part))
    return f'<p class="counts">{_dotted(parts)}</p>'


def _destructive(plan: Plan) -> str:
    """Every destructive change of a plan to apply, by name, where the page
    opens. A plan to destroy is nothing but, and its count says so."""
    if plan.kind != "apply":
        return ""
    found = [
        f"<li><code>{_t(step.name)}</code>: {_t(change.action)} "
        f"<code>{_t(change.summary)}</code></li>"
        for step in plan.steps
        if step.state != "skipped"
        for change in step.plan.changes
        if change.destructive
    ]
    if not found:
        return ""
    return (
        '<div class="alert"><strong class="destructive">Destructive</strong> — '
        f"{_t(words.count(len(found), 'change'))} that can't be taken back:"
        f"<ul>{''.join(found)}</ul></div>"
    )


def _step(step: PlannedStep, taken: Iterable[str]) -> str:
    changes = step.plan.changes
    tally = [
        words.count(sum(1 for c in changes if c.action != "run"), "change"),
        words.count(sum(1 for c in changes if c.action == "run"), "run"),
    ]
    destructive = sum(1 for c in changes if c.destructive)
    summary = [
        f'<span class="name">{_t(step.name)}</span>',
        f'<span class="uses">{_t(step.uses)}</span>',
        f'<span class="state {step.state}">{step.state}</span>',
    ]
    if step.state == "ready":
        counted = _t(" · ".join(tally))
        if destructive:
            counted += f' · <span class="destructive">{destructive} destructive</span>'
        summary.append(f'<span class="tally">{counted}</span>')
    body: list[str] = []
    if step.skipped is not None:
        body.append(f'<p class="dim">skipped: {_t(step.skipped)}</p>')
    else:
        known = [one for one in step.inputs if one.known]
        if known:
            body.append("<h2>Takes</h2>" + _list("takes", map(_input, known)))
        if step.waiting is not None:
            body.append(f'<p class="warning">{_t(step.waiting)}</p>')
        if changes:
            body.append("<h2>Would do</h2>" + _changes(changes))
        if step.plan.notes:
            body.append(_list("notes", map(_t, step.plan.notes)))
        given = words.given(step, taken)
        if given:
            gives = (
                f"→ {_t(name)} = {_t(words.shown(value))}"
                for name, value in given.items()
            )
            body.append("<h2>Gives</h2>" + _list("gives", gives))
        if step.waiting is None and not changes and not given and not step.plan.notes:
            body.append('<p class="dim">no changes</p>')
        if step.plan.view:
            body.append(
                f"<h2>From the plugin, <code>{_t(step.uses)}</code></h2>"
                f'<div class="frame">{framed(step.plan.view)}</div>'
            )
    # a step with nothing to read stays folded; the rest are open to be read
    opened = "" if step.skipped is not None else " open"
    return (
        f'<details class="step {step.state}"{opened}>'
        f"<summary>{''.join(summary)}</summary>"
        f'<div class="body">{"".join(body)}</div></details>'
    )


def _input(taken: Input) -> str:
    """`model_version = 14  ← model.version`; an item of a list has no name."""
    shown = "" if taken.value is None else words.shown(taken.value)
    source = f'<span class="dim">← {_t(taken.source)}</span>'
    if taken.label and shown:
        return f"{_t(taken.label)} = {_t(shown)}  {source}"
    if taken.label or shown:
        return f"{_t(taken.label or shown)}  {source}"
    return source


def _changes(changes: Iterable[Change]) -> str:
    rows = []
    for change in changes:
        word = (
            ' <strong class="destructive">destructive</strong>'
            if change.destructive
            else ""
        )
        detail = "".join(
            f'<div class="detail">{_t(line)}</div>' for line in change.detail
        )
        rows.append(
            f'<tr class="{change.action}"><td class="sym">{SYMBOLS[change.action]}</td>'
            f'<td class="action">{change.action}</td>'
            f'<td class="what">{_t(change.summary)}{word}{detail}</td></tr>'
        )
    return f'<table class="changes">{"".join(rows)}</table>'


# -- a run ------------------------------------------------------------------------


def result_html(result: Result) -> str:
    """What a run did, and what exists after it."""
    title = "lely apply" if result.kind == "apply" else "lely destroy"
    heading = [title, f"target <b>{_t(result.target)}</b>"]
    head = [
        f"<h1>{_dotted(heading)}</h1>",
        f'<p class="meta"><code>{_t(result.workspace.host)}</code> as '
        f"<code>{_t(result.workspace.identity)}</code></p>",
    ]
    if result.outcome == "done":
        head.append(f'<p class="outcome done">{_t(words.done(result))}</p>')
    else:
        lists = "".join(
            f"<li>{_t(what)}: <code>{_t(names)}</code></li>"
            for what, names in words.stopped(result)
        )
        head.append(
            f'<div class="alert"><strong class="{result.outcome}">'
            f"{_t(result.outcome.capitalize())}.</strong> Nothing was rolled back."
            f"<ul>{lists}</ul></div>"
        )
        if result.message:
            head.append(f'<pre class="said">{_t(words.said(result.message))}</pre>')
    steps = [_step_result(step, result.workspace.host) for step in result.steps]
    about = (
        "This page only shows: it is a record of one run, made from the result that "
        f"run wrote, by lely {_t(__version__)}. Nothing was fetched to make it, and "
        "lely never reads a result back to decide anything."
    )
    return _page(" · ".join((title, result.target)), head, steps, about)


def _step_result(step: StepResult, workspace: str) -> str:
    said = words.outcome(step)
    summary = [
        f'<span class="name">{_t(step.name)}</span>',
        f'<span class="uses">{_t(step.uses)}</span>',
        f'<span class="state {_class(step.outcome)}">'
        f"{words.MARKS[step.outcome]} {_t(step.outcome)}</span>",
    ]
    if said and said != step.outcome:
        summary.append(f'<span class="tally">{_t(said)}</span>')
    body: list[str] = []
    if step.changes:
        body.append("<h2>Did</h2>" + _changes(step.changes))
    if step.overview is not None:
        exists = _exists(step.overview, step.happened, workspace)
        body.append("<h2>What exists now</h2>" + exists)
    opened = " open" if body else ""
    return (
        f'<details class="step {_class(step.outcome)}"{opened}>'
        f"<summary>{''.join(summary)}</summary>"
        f'<div class="body">{"".join(body)}</div></details>'
    )


def _exists(
    overview: Overview, happened: Mapping[str, str] | None, workspace: str
) -> str:
    rows = words.rows(overview, happened)
    parts = []
    if rows:
        head = "".join(
            f"<th>{name}</th>" for name in ("kind", "key", "name", "id", "this run", "")
        )
        body = "".join(
            "<tr>"
            + "".join(f"<td>{_t(cell)}</td>" for cell in row[:5])
            + f"<td>{_link(row.url, workspace)}</td></tr>"
            for row in rows
        )
        parts.append(f'<table class="exists"><tr>{head}</tr>{body}</table>')
    else:
        parts.append('<p class="dim">nothing declared</p>')
    if overview.notes:
        parts.append(_list("notes", map(_t, overview.notes)))
    return "".join(parts)


# -- a plugin's own view, inside a frame lely owns ------------------------------------

#: The elements of a view that are kept. Everything else is left out and its
#: text kept — but for `_DROPPED`, which go with all they hold.
#:
#: **None of them is an element the page around a view is built from** — no
#: `div`, no `details`, no `summary`. A browser does not close elements where
#: this file's own count says they close: a `<li>` ends the one before it
#: through whatever stands between, a table throws out what doesn't belong in
#: it. Written again "balanced", a view with a `div` in it still ended the
#: frame, the step and the list of steps in a real browser (found in review,
#: 2026-10-06). With no `</div>` and no `</details>` to write, nothing a view
#: holds can end the `div` it is put in, however the browser reads it: every
#: other end tag stops at that `div`. `tests/browser` asks a real browser.
_KEPT = (
    frozenset({"p", "span", "pre", "code", "blockquote", "hr", "br"})
    | {"ul", "ol", "li", "dl", "dt", "dd", "h4", "h5", "h6"}
    | {"table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption"}
    | {"strong", "b", "em", "i", "small", "kbd", "samp", "sub", "sup", "del", "ins"}
    | {"mark", "abbr"}
)
_VOID = frozenset({"hr", "br"})
#: A view has no heading above lely's own.
_RENAMED = {"h1": "h4", "h2": "h4", "h3": "h4"}
_DROPPED = (
    frozenset({"script", "style", "template", "iframe", "object", "svg", "math"})
    | {"noscript", "title", "head", "textarea", "select", "audio", "video", "canvas"}
    | {"noembed", "noframes", "xmp", "applet", "frameset"}
)
#: The classes a view may use: the ones the page has a style for.
CLASSES = frozenset({"create", "update", "delete", "replace", "run"}) | {
    "destructive",
    "unchanged",
    "dim",
    "num",
    "key",
}
#: How deep a view may nest; what is deeper is written at this depth.
_DEPTH = 40


def framed(view: str) -> str:
    """A plugin's view, written again from the elements lely keeps: its
    structure and its words, and nothing a browser would obey. Nothing in what
    comes out can end the frame it is put in — not because it is balanced,
    which a browser doesn't go by, but because it holds no element that could
    (see `_KEPT`). The frame is a `div` that stands in no list, no paragraph
    and no table: that is the other half of it."""
    writer = _Frame()
    try:
        writer.feed(view)
        writer.close()
    except Exception:  # whatever a parser chokes on is no view
        return '<p class="dim">The plugin\'s view could not be read.</p>'
    return writer.written()


class _Frame(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._open: list[str] = []
        self._dropping = 0

    def written(self) -> str:
        while self._open:
            self._out.append(f"</{self._open.pop()}>")
        if self._dropping:
            # an element lely leaves out, never closed: all after it went too
            self._out.append(
                '<p class="dim">The rest of this view is left out: it stands in an '
                "element lely doesn't show, which was never closed.</p>"
            )
        return "".join(self._out)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = _RENAMED.get(tag, tag)
        if tag in _DROPPED:
            self._dropping += 1
            return
        if self._dropping or tag not in _KEPT:
            return
        if tag in _VOID:
            self._out.append(f"<{tag}>")
            return
        if len(self._open) >= _DEPTH:
            return
        self._out.append(f"<{tag}{_attributes(tag, attrs)}>")
        self._open.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = _RENAMED.get(tag, tag)
        if tag in _DROPPED:
            self._dropping = max(0, self._dropping - 1)
            return
        if self._dropping or tag not in self._open:
            return
        while self._open:
            closing = self._open.pop()
            self._out.append(f"</{closing}>")
            if closing == tag:
                break

    def handle_data(self, data: str) -> None:
        if not self._dropping:
            self._out.append(_t(data))


def _attributes(tag: str, attrs: list[tuple[str, str | None]]) -> str:
    """The few attributes that are kept, written by lely: a class from its own
    list, and how many cells a cell spans."""
    given = dict(attrs)
    kept = ""
    classes = [name for name in (given.get("class") or "").split() if name in CLASSES]
    if classes:
        kept += f' class="{" ".join(dict.fromkeys(classes))}"'
    if tag in ("td", "th"):
        for span in ("colspan", "rowspan"):
            value = given.get(span) or ""
            if re.fullmatch(r"[1-9][0-9]{0,2}", value):
                kept += f' {span}="{value}"'
    return kept


# -- text that is shown, never obeyed ---------------------------------------------------


def _t(text: str) -> str:
    """`text` as text: nothing in it is markup, and nothing a reader can't see."""
    return escape(clean(text), quote=True)


def _class(outcome: str) -> str:
    return outcome.replace(" ", "-")


def _dotted(parts: Iterable[str]) -> str:
    return ' <span class="dim">·</span> '.join(parts)


def _list(kind: str, items: Iterable[str]) -> str:
    return f'<ul class="{kind}">{"".join(f"<li>{item}</li>" for item in items)}</ul>'


def _link(url: str, workspace: str) -> str:
    """A link, when `url` leads into the workspace the run was in; text
    otherwise."""
    if words.into(url, workspace):
        return f'<a href="{escape(url, quote=True)}" rel="noopener noreferrer">open</a>'
    return _t(url)


def _page(
    title: str, head: Iterable[str], steps: Iterator[str] | list[str], about: str
) -> str:
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{POLICY}">\n'
        '<meta name="referrer" content="no-referrer">\n'
        f'<meta name="generator" content="{GENERATOR}">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_t(title)}</title>\n<style>\n{_CSS}</style>\n</head>\n<body>\n"
        "<header>\n" + "\n".join(part for part in head if part) + "\n</header>\n"
        "<main>\n" + "\n".join(steps) + "\n</main>\n"
        f"<footer>{about}</footer>\n</body>\n</html>\n"
    )

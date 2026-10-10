"""What the workspace actually answered, kept.

`fake_warehouse.py` proves that stevin's SQL matches stevin's *reading* of
the manual. Where that reading is wrong the fake is wrong in the same direction,
and the offline suite agrees with the mistake. The live suite is the only answer
to that — and it costs a workspace, forty minutes, and some weeks it can't run at
all.

A transcript is one live run written down: every statement stevin sent, and the
rows or the error that came back. Replayed, the same assertions run offline
against answers Databricks really gave. That is one thing more than the fake can
say, and one less than the live suite: a transcript says what was true **when it
was recorded**, on that runtime, on that day.

Recording one, against a workspace (see `docs/testing.md`):

    STEVIN_RECORD=tests/transcripts \\
      uv run pytest -m integration tests/integration/test_live_assumptions.py

Replaying: `tests/unit/test_transcripts.py` runs every transcript in
`tests/transcripts/`, so a recording is checked from the moment it lands, with no
credentials.

Two rules keep a transcript honest:

- **A statement the transcript hasn't got fails**, loudly, with the statement in
  the message — the same discipline as `FakeSqlError`. A recording that no longer
  covers what stevin sends is a failing test, not a silent pass.
- **Only what is incidental is masked**, in the statements and in the answers
  alike. That is two kinds of thing. What is new on every run: the schemas a run
  makes, the principal a grant names (`masking()`), and the suffix of a backup
  clone, which is a fingerprint of the schema it was made in. And what says whose
  workspace answered, which a public file has no business keeping: who ran it,
  where the workspace stores its tables, and which warehouse it was. Everything
  else — the rows, the error classes, the types as the catalog spells them — is
  kept as it came.

A replay puts its own names back into the answers, so a probe reads them as the
workspace would have given them in the schema the replay works in.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from stevin.introspect import Row, SqlRunner

#: The table a `--clone` plan leaves behind ends in this, and then in a
#: fingerprint. Spelled out rather than imported: a transcript is evidence about
#: what stevin sends, and should notice if that name changes.
_BACKUP_NAME = "__deltaplan_backup_"

#: What a recording puts in place of the names that are new on every run: the
#: scratch schema — whole, and its two parts, because statements name them
#: separately — the second schema the UNDROP probe asks for, and the principal a
#: grant names. A replay puts its own back.
SCHEMA = "<schema>"
CATALOG = "<catalog>"
BARE = "<bare>"
OTHER = "<other>"
OTHER_BARE = "<other-bare>"
PRINCIPAL = "<principal>"

#: The suffix of a backup clone's name: the first eight characters of a
#: fingerprint of the live schema, name included — so it is new on every run, and
#: another one again in the schema a replay works in. A replay learns its own
#: from the statement that makes the clone, and puts that back.
BACKUP = "<backup>"

#: What a recording puts in place of whose workspace it was. None of it is new on
#: every run, and no assumption rests on any of it; it is left out because a
#: transcript is a public file. Whoever ran it — an owner, the author of a
#: commit in a table's history — by e-mail address and by the number the
#: workspace gives them; the cloud storage a managed table sits in, which names
#: the workspace's bucket and its metastore; and the warehouse. A replay has
#: nothing of its own to put back for these, and leaves them as they are.
USER = "<user>"
USER_ID = "<user-id>"
LOCATION = "<location>"
WAREHOUSE = "<warehouse>"

#: The columns that hold a user's number: a run of digits says nothing about what
#: it is, so these are masked by where they are. `DESCRIBE HISTORY` has the one.
USER_ID_COLUMNS = frozenset({"userId"})

_USER = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
_LOCATION = r"\b(?:s3a?|abfss?|wasbs?|gs|r2|dbfs)://[^\s'\"`\\,;)]+"
_BACKUP = rf"(?<={_BACKUP_NAME})[0-9a-f]{{8}}\b"

#: The placeholders for a schema's own name, without its catalog — the names
#: that are new on every run, and that an error message may quote only the end of.
_SCHEMAS = frozenset({BARE, OTHER_BARE})


def masking(*schemas: str, principal: str = "") -> dict[str, str]:
    """The names that are new on every run, and what stands in for each.

    Every schema is masked whole *and* in parts, because a statement names them
    separately as often as together — a quoted three-part name, but also
    `WHERE schema_name = 'schema'`. The first schema is the run's own; a second
    is the one the `UNDROP` probe asks for, which keeps what it drops.

    A recording and the replay of it must build this the same way, from their own
    names, or the two never match.
    """
    named: dict[str, str] = {}
    for index, full in enumerate(name for name in schemas if name):
        catalog, _, bare = full.partition(".")
        named.setdefault(full, SCHEMA if index == 0 else OTHER)
        named.setdefault(bare, BARE if index == 0 else OTHER_BARE)
        named.setdefault(catalog, CATALOG)
    if principal:
        named.setdefault(principal, PRINCIPAL)
    return named


class TranscriptMiss(Exception):
    """The transcript has no answer for this statement.

    Loud on purpose: a recording that doesn't cover what stevin now sends has
    stopped being evidence about it.
    """


@dataclass(frozen=True, slots=True)
class Exchange:
    """One statement and what came back: rows, or the error."""

    sql: str
    rows: tuple[Row, ...] | None = None
    error: str | None = None

    def as_json(self) -> dict[str, object]:
        body: dict[str, object] = {"sql": self.sql}
        if self.error is not None:
            body["error"] = self.error
        else:
            body["rows"] = [dict(row) for row in self.rows or ()]
        return body

    @classmethod
    def from_json(cls, body: dict[str, object]) -> Exchange:
        rows = body.get("rows")
        return cls(
            sql=str(body["sql"]),
            rows=tuple(rows) if isinstance(rows, list) else None,  # type: ignore[arg-type]
            error=str(body["error"]) if body.get("error") is not None else None,
        )


@dataclass(frozen=True, slots=True)
class Transcript:
    """One live run, as a file a person can read and review the diff of."""

    about: str
    recorded: str
    exchanges: tuple[Exchange, ...] = ()
    #: What the workspace said it was, when it was asked.
    runtime: str | None = None
    warehouse: str | None = None
    #: The principal the run granted to, so a replay can name the same one.
    principal: str | None = None

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "about": self.about,
            "recorded": self.recorded,
            "runtime": self.runtime,
            "warehouse": self.warehouse,
            "principal": self.principal,
            "statements": [exchange.as_json() for exchange in self.exchanges],
        }
        path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Transcript:
        body = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            about=body["about"],
            recorded=body["recorded"],
            exchanges=tuple(
                Exchange.from_json(one) for one in body.get("statements", ())
            ),
            runtime=body.get("runtime"),
            warehouse=body.get("warehouse"),
            principal=body.get("principal"),
        )

    @property
    def filename(self) -> str:
        """`a replace keeps tags` -> `a-replace-keeps-tags.json`."""
        keep = [c if c.isalnum() else "-" for c in self.about.lower()]
        slug = "".join(keep)
        while "--" in slug:
            slug = slug.replace("--", "-")
        return f"{slug.strip('-')}.json"


def normalise(statement: str, mask: Mapping[str, str] | None = None) -> str:
    """One statement as a transcript keys it.

    Whitespace collapsed — stevin writes some statements over several lines,
    and a recording shouldn't depend on where they wrap — and every name in
    `mask` (from `masking()`) replaced by what stands in for it.

    Whole words only, so a catalog called `main` doesn't turn `maintenance` into
    a placeholder; longest name first, so `main.place` wins over either of its
    parts; and one pass, so a placeholder is never masked again — a schema called
    `schema` would otherwise turn `<schema>` into `<<bare>>`.
    """
    return _masked(" ".join(statement.split()), mask or {}, answer=False)


def kept_out(answer: str, mask: Mapping[str, str] | None = None) -> str:
    """One answer — a value in a row, or an error — as a transcript keeps it.

    The names in `mask` are replaced as `normalise` replaces them, because the
    workspace says them back: a row of `information_schema` holds the schema's
    name, and an error quotes the statement it refuses. Three things more, which
    only an answer holds:

    - an e-mail address becomes `<user>`, and a storage location `<location>`;
    - the end of a schema's name after `...` is masked as the whole name would
      be: an error that points into a long statement quotes a window of it, and
      the window starts wherever it starts — `...n_it_abc123`.`t`.

    The whitespace stays: an answer is evidence, and `SHOW CREATE TABLE` answers
    over several lines.
    """
    return _masked(answer, mask or {}, answer=True)


def _masked(text: str, named: Mapping[str, str], *, answer: bool) -> str:
    tails = _tails(named) if answer else {}
    parts: list[str] = []
    if answer:
        parts += [f"(?P<location>{_LOCATION})", f"(?P<user>{_USER})"]
    if tails:
        ends = "|".join(re.escape(end) for end in sorted(tails, key=len, reverse=True))
        parts.append(rf"(?P<tail>(?<=\.\.\.)(?:{ends})\b)")
    if named:
        order = sorted(named, key=len, reverse=True)
        names = "|".join(rf"\b{re.escape(name)}\b" for name in order)
        parts.append(f"(?P<name>{names})")
    parts.append(f"(?P<backup>{_BACKUP})")

    def stand_in(found: re.Match[str]) -> str:
        match found.lastgroup:
            case "name":
                return named[found.group(0)]
            case "tail":
                return tails[found.group(0)]
            case "location":
                return LOCATION
            case "user":
                return USER
            case _:
                return BACKUP

    return re.compile("|".join(parts)).sub(stand_in, text)


def _tails(named: Mapping[str, str]) -> dict[str, str]:
    """Every end of a schema's name that is still recognisably part of it.

    Three characters or more: shorter than that says nothing about the name, and
    would match the end of any word.
    """
    tails: dict[str, str] = {}
    for name, stands in named.items():
        if stands not in _SCHEMAS:
            continue
        for start in range(1, len(name) - 2):
            tails.setdefault(name[start:], stands)
    return tails


@dataclass
class Recorder:
    """A `SqlRunner` that runs statements and writes down the answers.

    Wraps the real runner rather than replacing it: a recording is a live run
    that also left a record, so anything it says is something the workspace said.
    """

    inner: SqlRunner
    about: str
    #: What `masking()` built from this run's own names. A recorder may be handed
    #: a name mid-run — the `UNDROP` probe's second schema is only made if that
    #: probe runs — and statements are masked as they go, so it takes effect.
    mask: dict[str, str] = field(default_factory=dict)
    exchanges: list[Exchange] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def client(self) -> object:
        """Whatever the wrapped runner talks to — a recorder adds nothing."""
        return getattr(self.inner, "client", None)

    def query(self, statement: str) -> tuple[Row, ...]:
        named = self._named()
        keyed = normalise(statement, named)
        try:
            rows = self.inner.query(statement)
        except Exception as error:
            with self._lock:
                self.exchanges.append(Exchange(keyed, error=kept_out(str(error), named)))
            raise
        kept = tuple(self._kept(row, named) for row in rows)
        with self._lock:
            self.exchanges.append(Exchange(keyed, rows=kept))
        # The probe gets what the workspace said; only the record is masked.
        return rows

    def _named(self) -> dict[str, str]:
        """The run's own names, and the warehouse it runs on."""
        warehouse = getattr(self.inner, "warehouse_id", None)
        return {**self.mask, warehouse: WAREHOUSE} if warehouse else self.mask

    @staticmethod
    def _kept(row: Row, named: Mapping[str, str]) -> Row:
        kept: Row = {}
        for column, value in row.items():
            if value is None:
                kept[column] = None
            elif column in USER_ID_COLUMNS:
                kept[column] = USER_ID
            else:
                kept[column] = kept_out(value, named)
        return kept

    def transcript(self, *, runtime: str | None = None) -> Transcript:
        return Transcript(
            about=self.about,
            recorded=datetime.now(UTC).date().isoformat(),
            exchanges=tuple(self.exchanges),
            runtime=runtime,
            warehouse=self._warehouse(),
            principal=next(
                (name for name, stands in self.mask.items() if stands == PRINCIPAL),
                None,
            ),
        )

    def _warehouse(self) -> str | None:
        """That a warehouse answered, and not which: its id is the workspace's."""
        return WAREHOUSE if getattr(self.inner, "warehouse_id", None) else None


@dataclass
class Replay:
    """A `SqlRunner` that answers from a transcript, and refuses to guess.

    Answers come back in the order they were recorded for each statement, so a
    query asked before and after a change gives the two answers it really gave.
    """

    transcript: Transcript
    #: What `masking()` builds from the names *this* replay uses, where the
    #: recording had its own. Built the same way, or the two never match.
    mask: dict[str, str] = field(default_factory=dict)
    #: Statements that have been answered, in order — what a test can assert on.
    asked: list[str] = field(default_factory=list)
    _left: dict[str, list[Exchange]] = field(default_factory=dict)
    #: The suffix of the backup clone this replay's own plan named, once a
    #: statement has said it.
    _backup: str | None = None
    client: None = None

    def __post_init__(self) -> None:
        for exchange in self.transcript.exchanges:
            self._left.setdefault(exchange.sql, []).append(exchange)

    def query(self, statement: str) -> tuple[Row, ...]:
        from stevin.introspect import IntrospectionError

        keyed = normalise(statement, self.mask)
        named = re.search(_BACKUP, statement)
        if named:
            self._backup = named.group(0)
        self.asked.append(keyed)
        waiting = self._left.get(keyed)
        if not waiting:
            recorded = "recorded" if self.transcript.exchanges else "empty"
            raise TranscriptMiss(
                f"the transcript {self.transcript.about!r} ({recorded} "
                f"{self.transcript.recorded}) has no answer for:\n  {keyed}\n"
                "Re-record it: see docs/testing.md."
            )
        # The last answer stands for every later ask of the same statement: a
        # transcript is evidence, not a script, and running out of a repeated
        # read should not be what fails a test.
        exchange = waiting.pop(0) if len(waiting) > 1 else waiting[0]
        if exchange.error is not None:
            raise IntrospectionError(self._put_back(exchange.error))
        return tuple(
            {
                column: value if value is None else self._put_back(value)
                for column, value in row.items()
            }
            for row in exchange.rows or ()
        )

    def _put_back(self, answer: str) -> str:
        """An answer with this replay's own names where the recording's were.

        The other way round from `kept_out`: the workspace named the schema it
        was asked about, so a replay names the one *it* asks about. What stands
        for whose workspace it was — `<user>`, `<location>` — has nothing to go
        back to, and stays.
        """
        own = {stands: name for name, stands in self.mask.items()}
        if self._backup:
            own[BACKUP] = self._backup
        if not own:
            return answer
        pattern = re.compile("|".join(re.escape(stands) for stands in own))
        return pattern.sub(lambda found: own[found.group(0)], answer)

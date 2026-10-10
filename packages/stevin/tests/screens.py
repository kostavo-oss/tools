"""The terminal screenshots in the docs, made by running the real CLI.

Every picture on the docs site is stevin's own output. A scene writes a small
project, applies its "before" specs through the CLI into an in-memory warehouse
(`fake_warehouse.py`), then runs the command it shows and records what the CLI
printed as an SVG terminal window. The spec files a page quotes are written next
to the pictures, so the YAML beside a plan is the YAML that produced it.

    uv run python tests/screens.py docs/assets/screens

`tests/unit/test_screens.py` fails when a committed picture no longer matches what
the CLI prints: rerun the line above after changing anything a user sees.
"""

from __future__ import annotations

import contextlib
import functools
import io
import os
import re
import shlex
import shutil
import sys
import tempfile
import textwrap
import unittest.mock
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.text import Text
from typer.testing import CliRunner

from fake_warehouse import FakeWarehouse
from helpers import offline_environment
from stevin import api, cli
from stevin.connect import Connection
from stevin.executor import Executor
from stevin.history import MemoryHistory
from stevin.model.policy import Policy

#: Columns in every picture: a docs page scales a wider terminal down until its
#: text is too small to read, so this is a standard terminal's width.
WIDTH = 80
#: What changes from run to run is pinned, so a picture changes only when the
#: output does.
RUN_ID = "a41c9e07d2b5"
VERSION = "0.1.0"

GB = 1024**3

PROJECT = """\
version: 1
specs: [tables]
history_schema: ${catalog}.stevin

targets:
  dev:
    vars:
      catalog: dev
"""


@dataclass
class Studio:
    """One scene's project directory, warehouse and pictures."""

    root: Path
    out: Path
    fake: FakeWarehouse = field(default_factory=FakeWarehouse)
    history: MemoryHistory = field(default_factory=MemoryHistory)
    exit_code: int = 0

    def write(self, path: str, text: str) -> None:
        """Write a project file; a spec's leading indentation is dropped."""
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")

    def remove(self, path: str) -> None:
        (self.root / path).unlink()

    def quote(self, path: str, name: str) -> None:
        """Copy a project file next to the pictures, for a page to include."""
        shutil.copyfile(self.root / path, self.out / name)

    def run(self, command: str) -> str:
        """Run a command without taking a picture — setting the scene."""
        console = _console()
        self._invoke(command, console)
        return console.export_text()

    def apply(self) -> None:
        """Bring the warehouse in line with the specs, off camera."""
        self.run("stevin plan -o plan.json")
        self.run("stevin apply plan.json --allow-destructive")
        assert self.exit_code == 0, self.run("stevin plan")
        # Real tables have data; the fake's are empty, and "(0 B)" reads oddly.
        for name in self.fake.tables:
            self.fake.sizes.setdefault(name, 24 * GB)

    def shoot(self, name: str, command: str, *, answer: str | None = None) -> str:
        """Run a command and save what it printed as `<name>.svg`. `answer` is
        what gets typed at a prompt, shown after it as a terminal would."""
        console = _console()
        console.print(
            Text.assemble(("$ ", "bold green"), (command, "bold")), highlight=False
        )
        self._invoke(command, console, answer=answer)
        text = console.export_text(clear=False)
        svg = console.export_svg(title="stevin", unique_id=f"dp-{name}")
        (self.out / f"{name}.svg").write_text(svg, encoding="utf-8")
        return text

    def _invoke(
        self, command: str, console: Console, *, answer: str | None = None
    ) -> None:
        words = shlex.split(command)
        assert words[0] == "stevin", command

        def typed(*_args: object) -> str:
            # Rich reads a prompt's answer with input(), which a recording never
            # sees; echo it, as the terminal would have.
            if answer is None:
                raise EOFError
            console.print(answer, highlight=False)
            return answer

        with (
            _patched(self, console),
            contextlib.chdir(self.root),
            unittest.mock.patch("builtins.input", typed),
        ):
            result = CliRunner().invoke(cli.app, words[1:], catch_exceptions=False)
        self.exit_code = result.exit_code
        if result.stdout.strip():
            # What the CLI writes with typer.echo rather than through Rich.
            console.print(Text(result.stdout.rstrip("\n")), highlight=False)


def _console() -> Console:
    return Console(
        record=True,
        width=WIDTH,
        file=io.StringIO(),
        force_terminal=True,
        color_system="truecolor",
        legacy_windows=False,
    )


@contextlib.contextmanager
def _patched(studio: Studio, console: Console) -> Generator[None]:
    """Point the CLI at the scene's warehouse and console.

    And take the Databricks CLI and workspace out of the environment: a
    picture must show what stevin does, not what happens to be installed or
    logged in on the machine that took it.
    """
    replacements: dict[str, object] = {
        "out": console,
        "err": console,
        "_connect": lambda *_args, **_kwargs: Connection(runner=studio.fake),
        "_history": lambda *_args, **_kwargs: studio.history,
    }
    # The library's side of the same scene: a fixed run id and version, so a
    # picture is the same one tomorrow.
    library: dict[str, object] = {
        "Executor": functools.partial(Executor, new_run_id=lambda: RUN_ID),
        "package_version": lambda: VERSION,
    }
    saved = {name: getattr(cli, name) for name in replacements}
    saved_library = {name: getattr(api, name) for name in library}
    for name, value in replacements.items():
        setattr(cli, name, value)
    for name, value in library.items():
        setattr(api, name, value)
    offline = offline_environment(dict(os.environ), studio.root / "no-databrickscfg")
    try:
        with unittest.mock.patch.dict(os.environ, offline, clear=True):
            yield
    finally:
        for name, value in saved.items():
            setattr(cli, name, value)
        for name, value in saved_library.items():
            setattr(api, name, value)


Scene = Callable[[Studio], None]
SCENES: list[Scene] = []


def scene(function: Scene) -> Scene:
    SCENES.append(function)
    return function


def make(out: Path) -> list[Path]:
    """Every scene, into `out`. Returns the files written."""
    out.mkdir(parents=True, exist_ok=True)
    for old in out.iterdir():
        old.unlink()
    for play in SCENES:
        with tempfile.TemporaryDirectory() as root:
            studio = Studio(Path(root), out)
            studio.write("stevin.yml", PROJECT)
            play(studio)
    return sorted(out.iterdir())


# ---------------------------------------------------------------------------
# the tour: one project, from nothing to CI
# ---------------------------------------------------------------------------

ORDERS = """\
    table: ${catalog}.sales.orders
    comment: Order facts, one row per order
    cluster_by: [order_date]
    tags:
      domain: sales
    columns:
      - name: order_id
        type: bigint
        nullable: false
      - name: order_date
        type: date
        nullable: false
      - name: cust_id
        type: string
      - name: amount
        type: decimal(10,2)
      - name: address
        type:
          struct:
            - {name: street, type: string}
            - {name: zip, type: string}
    constraints:
      - primary_key: [order_id]
"""

ORDERS_CHANGED = """\
    table: ${catalog}.sales.orders
    comment: Order facts, one row per order
    cluster_by: [order_date]
    tags:
      domain: sales
    grants:
      - principal: analysts
        privileges: [SELECT]
    columns:
      - name: order_id
        type: bigint
        nullable: false
      - name: order_date
        type: date
        nullable: false
      - name: customer_ref
        type: string
        renamed_from: cust_id
        tags: {pii: "true"}
      - name: amount
        type: decimal(18,2)
      - name: status
        type: string
        nullable: false
        using: "'open'"
      - name: address
        type:
          struct:
            - {name: street, type: string}
            - {name: zip, type: string}
            - {name: country, type: string}
    constraints:
      - primary_key: [order_id]
      - check: {name: positive_amount, expression: "amount >= 0"}
"""

BIG_ORDERS = """\
    view: ${catalog}.sales.big_orders
    comment: Orders over 1000
    query: |
      SELECT order_id, order_date, amount
      FROM ${catalog}.sales.orders
      WHERE amount > 1000
"""

CUSTOMERS = """\
    -- A SQL spec: the same model as YAML, written as the CREATE you'd write anyway.
    CREATE TABLE ${catalog}.sales.customers (
      customer_id BIGINT NOT NULL COMMENT 'Surrogate key',
      name        STRING,
      country     STRING,
      CONSTRAINT customers_pk PRIMARY KEY (customer_id)
    )
    COMMENT 'One row per customer'
    CLUSTER BY AUTO;
"""


def _tour_project(studio: Studio) -> None:
    studio.write("tables/orders.yml", ORDERS)
    studio.write("tables/big_orders.yml", BIG_ORDERS)
    studio.write("tables/customers.sql", CUSTOMERS)


@scene
def tour_first_plan(studio: Studio) -> None:
    _tour_project(studio)
    studio.quote("stevin.yml", "tour-project.yml")
    studio.quote("tables/orders.yml", "tour-orders.yml")
    studio.quote("tables/customers.sql", "tour-customers.sql")
    studio.shoot("tour-version", "stevin --version")
    studio.shoot("tour-validate", "stevin validate")
    studio.shoot("tour-plan-create", "stevin plan -o plan.json")
    studio.shoot("tour-apply-create", "stevin apply plan.json")
    studio.shoot("tour-plan-clean", "stevin plan")


@scene
def tour_apply_now(studio: Studio) -> None:
    _tour_project(studio)
    studio.apply()
    studio.write(
        "tables/orders.yml",
        ORDERS.replace(
            "      - name: amount\n",
            "      - name: channel\n        type: string\n      - name: amount\n",
        ),
    )
    studio.shoot("tour-apply-now", "stevin apply", answer="y")


@scene
def tour_validate_errors(studio: Studio) -> None:
    studio.write(
        "tables/orders.yml",
        """\
        table: ${catalog}.sales.orders
        columns:
          - name: order_id
            type: bigint
            nulable: false
        """,
    )
    studio.write(
        "tables/customers.yml",
        """\
        table: ${catalog}.sales.customers
        cluster_by: [country]
        columns:
          - name: customer_id
            type: bigint
          - name: name
            type: string
        constraints:
          - primary_key: [customer_id]
        """,
    )
    studio.shoot("tour-validate-errors", "stevin validate")


@scene
def tour_change(studio: Studio) -> None:
    _tour_project(studio)
    studio.run("stevin plan -o plan.json")
    studio.run("stevin apply plan.json")
    studio.fake.sizes["dev.sales.orders"] = 412 * GB
    studio.write("tables/orders.yml", ORDERS_CHANGED)
    studio.quote("tables/orders.yml", "tour-orders-changed.yml")
    studio.shoot("tour-plan-change", "stevin plan -o plan.json")
    studio.shoot("tour-apply-change", "stevin apply plan.json")


def _tour_changed(studio: Studio) -> None:
    _tour_project(studio)
    studio.apply()
    studio.fake.sizes["dev.sales.orders"] = 412 * GB
    studio.write("tables/orders.yml", ORDERS_CHANGED)
    studio.apply()


@scene
def tour_rewrite(studio: Studio) -> None:
    _tour_changed(studio)
    studio.write(
        "tables/orders.yml",
        ORDERS_CHANGED.replace(
            "      - name: customer_ref\n        type: string\n",
            "      - name: customer_ref\n        type: bigint\n",
        ),
    )
    studio.shoot("tour-plan-rewrite", "stevin plan --clone -o plan.json")


@scene
def tour_destroy(studio: Studio) -> None:
    _tour_changed(studio)
    studio.write(
        "tables/orders.yml",
        ORDERS_CHANGED.replace(
            """      - name: address
        type:
          struct:
            - {name: street, type: string}
            - {name: zip, type: string}
            - {name: country, type: string}
""",
            "",
        ),
    )
    studio.shoot("tour-plan-destroy", "stevin plan -o plan.json")
    studio.shoot("tour-apply-refused", "stevin apply plan.json")


@scene
def tour_drift(studio: Studio) -> None:
    _tour_changed(studio)
    # Someone fixes something by hand, in the catalog explorer.
    studio.fake.query(
        "ALTER TABLE `dev`.`sales`.`orders` ALTER COLUMN `amount` "
        "COMMENT 'Gross, incl. VAT'"
    )
    studio.fake.query(
        "ALTER TABLE `dev`.`sales`.`orders` DROP CONSTRAINT `positive_amount`"
    )
    studio.shoot("tour-drift", "stevin drift")


@scene
def tour_pull_request(studio: Studio) -> None:
    _tour_project(studio)
    studio.apply()
    studio.fake.sizes["dev.sales.orders"] = 412 * GB
    studio.write("tables/orders.yml", ORDERS_CHANGED)
    studio.run("stevin plan -f md -o comment.md")
    comment = (studio.root / "comment.md").read_text(encoding="utf-8")
    (studio.out / "tour-comment.txt").write_text(for_the_site(comment), encoding="utf-8")


#: GitHub's alerts, as the docs site's admonitions.
ALERTS = {
    "NOTE": "note",
    "TIP": "tip",
    "IMPORTANT": "info",
    "WARNING": "warning",
    "CAUTION": "danger",
}


def for_the_site(comment: str) -> str:
    """The PR comment as the docs site can render it, looking as it does on GitHub.

    GitHub renders Markdown inside `<details>` and turns `> [!WARNING]` into an
    alert; Python-Markdown needs `markdown` on the tag and has admonitions
    instead. Nothing else changes, so the page shows the real comment.
    """
    lines: list[str] = []
    alert: str | None = None
    for line in comment.splitlines():
        if alert is not None and line.startswith("> "):
            lines.append(f"    {line[2:]}")
            continue
        alert = None
        if line.startswith("> [!") and line.rstrip().endswith("]"):
            alert = ALERTS[line.strip()[4:-1]]
            lines += [f"!!! {alert}", ""]
            continue
        if line.startswith("### "):
            # As HTML, so the comment's own heading stays out of the page's contents.
            title = re.sub(r"`([^`]+)`", r"<code>\1</code>", line[4:])
            lines.append(f"<h3>{title}</h3>")
            continue
        lines.append(line.replace("<details", "<details markdown"))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# the feature gallery: one spec change each, and the plan it makes
# ---------------------------------------------------------------------------


def _feature(
    studio: Studio,
    name: str,
    before: dict[str, str],
    after: dict[str, str],
    *,
    show: str = "tables/orders.yml",
    command: str = "stevin plan",
) -> None:
    """Apply `before`, write `after` over it, quote `show`, and shoot `command`."""
    for path, text in before.items():
        studio.write(path, text)
    if before:
        studio.apply()
    for path, text in after.items():
        if text:
            studio.write(path, text)
        else:
            studio.remove(path)
    studio.quote(show, f"feature-{name}{Path(show).suffix}")
    studio.shoot(f"feature-{name}", command)


@scene
def feature_columns(studio: Studio) -> None:
    before = """\
        table: ${catalog}.sales.orders
        columns:
          - {name: order_id, type: bigint, nullable: false}
          - {name: amount, type: "decimal(10,2)"}
          - name: address
            type:
              struct:
                - {name: street, type: string}
    """
    after = """\
        table: ${catalog}.sales.orders
        columns:
          - {name: order_id, type: bigint, nullable: false}
          - {name: amount, type: "decimal(10,2)", comment: "Gross, incl. VAT"}
          - {name: status, type: string}
          - name: address
            type:
              struct:
                - {name: street, type: string}
                - {name: zip, type: string, comment: Postal code}
    """
    _feature(
        studio, "columns", {"tables/orders.yml": before}, {"tables/orders.yml": after}
    )


@scene
def feature_renames(studio: Studio) -> None:
    before = """\
        table: ${catalog}.sales.order_facts
        columns:
          - {name: order_id, type: bigint, nullable: false}
          - {name: cust_id, type: string}
    """
    after = """\
        table: ${catalog}.sales.orders
        renamed_from: order_facts
        columns:
          - {name: order_id, type: bigint, nullable: false}
          - {name: customer_ref, type: string, renamed_from: cust_id}
    """
    _feature(
        studio, "renames", {"tables/orders.yml": before}, {"tables/orders.yml": after}
    )


@scene
def feature_widening(studio: Studio) -> None:
    before = """\
        table: ${catalog}.sales.orders
        columns:
          - {name: quantity, type: int}
          - {name: amount, type: "decimal(10,2)"}
          - {name: lines, type: "array<struct<sku:string,qty:int>>"}
    """
    after = """\
        table: ${catalog}.sales.orders
        columns:
          - {name: quantity, type: bigint}
          - {name: amount, type: "decimal(18,2)"}
          - {name: lines, type: "array<struct<sku:string,qty:bigint>>"}
    """
    _feature(
        studio, "widening", {"tables/orders.yml": before}, {"tables/orders.yml": after}
    )


@scene
def feature_rewrite(studio: Studio) -> None:
    before = """\
        table: ${catalog}.sales.orders
        columns:
          - {name: order_id, type: bigint, nullable: false}
          - {name: placed, type: string}
    """
    after = """\
        table: ${catalog}.sales.orders
        columns:
          - {name: order_id, type: bigint, nullable: false}
          - name: placed
            type: date
            using: "to_date(placed, 'yyyy-MM-dd')"
    """
    studio.fake.sizes["dev.sales.orders"] = 1_300 * GB
    _feature(
        studio, "rewrite", {"tables/orders.yml": before}, {"tables/orders.yml": after}
    )


@scene
def feature_not_null(studio: Studio) -> None:
    before = """\
        table: ${catalog}.sales.orders
        columns:
          - {name: order_id, type: bigint, nullable: false}
          - name: address
            type:
              struct:
                - {name: street, type: string}
                - {name: zip, type: string}
    """
    after = """\
        table: ${catalog}.sales.orders
        columns:
          - {name: order_id, type: bigint, nullable: false}
          - name: region
            type: string
            nullable: false
            using: "'unknown'"
          - name: address
            type:
              struct:
                - {name: street, type: string}
                - {name: zip, type: string, nullable: false}
    """
    studio.fake.sizes["dev.sales.orders"] = 38 * GB
    _feature(
        studio, "not-null", {"tables/orders.yml": before}, {"tables/orders.yml": after}
    )


@scene
def feature_partitioning(studio: Studio) -> None:
    before = """\
        table: ${catalog}.sales.events
        partitioned_by: [event_date]
        columns:
          - {name: event_id, type: bigint}
          - {name: event_date, type: date}
          - {name: customer_id, type: bigint}
    """
    after = """\
        table: ${catalog}.sales.events
        cluster_by: [event_date, customer_id]
        columns:
          - {name: event_id, type: bigint}
          - {name: event_date, type: date}
          - {name: customer_id, type: bigint}
    """
    studio.fake.sizes["dev.sales.events"] = 2_100 * GB
    _feature(
        studio,
        "partitioning",
        {"tables/events.yml": before},
        {"tables/events.yml": after},
        show="tables/events.yml",
    )


@scene
def feature_constraints(studio: Studio) -> None:
    customers = """\
        table: ${catalog}.sales.customers
        columns:
          - {name: customer_id, type: bigint, nullable: false}
        constraints:
          - primary_key: [customer_id]
    """
    before = """\
        table: ${catalog}.sales.orders
        columns:
          - {name: order_id, type: bigint, nullable: false}
          - {name: customer_id, type: bigint}
          - {name: amount, type: "decimal(18,2)"}
    """
    after = """\
        table: ${catalog}.sales.orders
        columns:
          - {name: order_id, type: bigint, nullable: false}
          - {name: customer_id, type: bigint}
          - {name: amount, type: "decimal(18,2)"}
        constraints:
          - primary_key: [order_id]
          - check: {name: positive_amount, expression: "amount > 0"}
          - foreign_key:
              columns: [customer_id]
              references: ${catalog}.sales.customers
              referenced_columns: [customer_id]
    """
    _feature(
        studio,
        "constraints",
        {"tables/customers.yml": customers, "tables/orders.yml": before},
        {"tables/orders.yml": after},
    )


@scene
def feature_clustering(studio: Studio) -> None:
    before = """\
        table: ${catalog}.sales.orders
        cluster_by: [order_date]
        columns:
          - {name: order_id, type: bigint}
          - {name: order_date, type: date}
          - {name: region, type: string}
    """
    after = """\
        table: ${catalog}.sales.orders
        cluster_by: [region, order_date]
        columns:
          - {name: order_id, type: bigint}
          - {name: order_date, type: date}
          - {name: region, type: string}
    """
    _feature(
        studio, "clustering", {"tables/orders.yml": before}, {"tables/orders.yml": after}
    )


@scene
def feature_tags_and_grants(studio: Studio) -> None:
    before = """\
        table: ${catalog}.sales.customers
        tags: {legacy: "true"}
        columns:
          - {name: customer_id, type: bigint}
          - {name: email, type: string}
    """
    after = """\
        table: ${catalog}.sales.customers
        owner: crm-team
        tags: {domain: crm, legacy: null}
        grants:
          - {principal: analysts, privileges: [SELECT]}
          - {principal: etl, privileges: [SELECT, MODIFY]}
        columns:
          - {name: customer_id, type: bigint}
          - {name: email, type: string, tags: {pii: email}}
    """
    studio.write("tables/customers.yml", before)
    studio.apply()
    # Someone else's business: a grant to a principal the spec doesn't name.
    studio.fake.query("GRANT SELECT ON TABLE `dev`.`sales`.`customers` TO `finance`")
    _feature(
        studio,
        "tags-and-grants",
        {},
        {"tables/customers.yml": after},
        show="tables/customers.yml",
    )


MASK_FUNCTIONS = """\
    function: ${catalog}.security.mask_email
    parameters:
      - {name: email, type: string}
    returns: string
    body: |
      CASE WHEN is_account_group_member('pii') THEN email ELSE '***' END
"""

ROW_FILTER_FUNCTION = """\
    function: ${catalog}.security.by_region
    parameters:
      - {name: region, type: string}
    returns: boolean
    body: is_account_group_member(region) OR is_account_group_member('admins')
"""


@scene
def feature_masks(studio: Studio) -> None:
    after = """\
        table: ${catalog}.sales.customers
        columns:
          - {name: customer_id, type: bigint}
          - {name: email, type: string, mask: "${catalog}.security.mask_email"}
          - {name: region, type: string}
        row_filter:
          function: ${catalog}.security.by_region
          columns: [region]
    """
    before = """\
        table: ${catalog}.sales.customers
        columns:
          - {name: customer_id, type: bigint}
          - {name: email, type: string}
          - {name: region, type: string}
    """
    # The functions arrive with the masks that name them — a function spec is
    # only for a mask or a row filter — and are created first, in the same plan.
    _feature(
        studio,
        "masks",
        {"tables/customers.yml": before},
        {
            "tables/customers.yml": after,
            "tables/mask_email.yml": MASK_FUNCTIONS,
            "tables/by_region.yml": ROW_FILTER_FUNCTION,
        },
        show="tables/customers.yml",
    )


@scene
def feature_policies(studio: Studio) -> None:
    """A table under ABAC policies somebody else wrote: read, shown, left alone."""
    before = """\
        table: ${catalog}.sales.customers
        columns:
          - {name: customer_id, type: bigint}
          - {name: email, type: string}
          - {name: region, type: string}
    """
    studio.write("tables/customers.yml", before)
    studio.apply()
    # Written with Terraform, say: one on the schema, one on the whole catalog.
    studio.fake.under(
        Policy(
            "mask_pii",
            "column_mask",
            "dev.sales",
            "schema",
            function="dev.governance.redact",
            to=("account users",),
            except_=("data_admins",),
            match_columns="has_tag('pii') AS c",
            on_column="c",
        ),
        Policy(
            "own_region",
            "row_filter",
            "dev",
            "catalog",
            function="dev.governance.in_region",
            to=("analysts",),
            when="has_tag('regional')",
        ),
    )
    added = before.rstrip(" ") + "          - {name: signed_up, type: date}\n"
    studio.write("tables/customers.yml", added)
    studio.quote("tables/customers.yml", "feature-policies.yml")
    studio.shoot("feature-policies", "stevin plan")
    # The spec puts a mask of its own on a column: both are there now, and a
    # reader both reach is refused by Databricks. The plan says so.
    studio.write(
        "tables/customers.yml",
        added.replace(
            "{name: email, type: string}",
            '{name: email, type: string, mask: "${catalog}.security.mask_email"}',
        ),
    )
    studio.write("tables/mask_email.yml", MASK_FUNCTIONS)
    studio.shoot("feature-policies-conflict", "stevin plan")


@scene
def feature_views(studio: Studio) -> None:
    orders = """\
        table: ${catalog}.sales.orders
        columns:
          - {name: order_id, type: bigint}
          - {name: amount, type: "decimal(18,2)"}
    """
    before = """\
        view: ${catalog}.sales.big_orders
        comment: Orders over 1000
        tags: {domain: sales}
        grants:
          - {principal: analysts, privileges: [SELECT]}
        query: SELECT order_id, amount FROM ${catalog}.sales.orders WHERE amount > 1000
    """
    after = before.replace("1000", "5000")
    _feature(
        studio,
        "views",
        {"tables/orders.yml": orders, "tables/big_orders.yml": before},
        {"tables/big_orders.yml": after},
        show="tables/big_orders.yml",
    )


@scene
def feature_schemas_and_volumes(studio: Studio) -> None:
    schema = """\
        schema: ${catalog}.sales
        comment: Sales data
        tags: {domain: sales}
        grants:
          - {principal: analysts, privileges: [USE SCHEMA, SELECT]}
    """
    volume = """\
        volume: ${catalog}.sales.landing
        comment: Raw files from the source systems
        grants:
          - {principal: etl, privileges: [READ VOLUME, WRITE VOLUME]}
    """
    studio.write("tables/_schema.yml", schema)
    studio.quote("tables/_schema.yml", "feature-schema.yml")
    _feature(
        studio, "volumes", {}, {"tables/landing.yml": volume}, show="tables/landing.yml"
    )


@scene
def feature_generated(studio: Studio) -> None:
    before = """\
        table: ${catalog}.sales.orders
        columns:
          - {name: order_id, type: bigint, identity: always}
          - {name: placed_at, type: timestamp}
          - {name: status, type: string}
    """
    after = """\
        table: ${catalog}.sales.orders
        columns:
          - {name: order_id, type: bigint, identity: always}
          - {name: placed_at, type: timestamp}
          - {name: status, type: string, default: "'new'"}
          - {name: placed_on, type: date, generated: CAST(placed_at AS DATE)}
    """
    _feature(
        studio, "generated", {"tables/orders.yml": before}, {"tables/orders.yml": after}
    )


@scene
def feature_ownership(studio: Studio) -> None:
    from dataclasses import replace

    from stevin.model.table import MANAGED_PROPERTY

    spec = """\
        table: ${catalog}.sales.orders
        columns:
          - {name: order_id, type: bigint}
          - {name: amount, type: "decimal(18,2)"}
    """
    studio.write("tables/orders.yml", spec)
    studio.apply()
    # Made by hand before stevin arrived: the same shape, but not ours.
    orders = studio.fake.tables["dev.sales.orders"]
    studio.fake.tables["dev.sales.orders"] = replace(
        orders,
        properties=tuple(p for p in orders.properties if p[0] != MANAGED_PROPERTY),
    )
    studio.fake.tables["dev.sales.scratch"] = replace(
        studio.fake.tables["dev.sales.orders"], name="dev.sales.scratch"
    )
    _feature(studio, "ownership", {}, {})


@scene
def feature_govern(studio: Studio) -> None:
    """A dlt pipeline landed the customers; stevin only says who may see them."""
    from stevin.model.table import Table
    from stevin.model.types import Field
    from stevin.typeparser import parse_type

    def landed(name: str, *columns: tuple[str, str]) -> None:
        studio.fake.tables[f"dev.raw.{name}"] = Table(
            name=f"dev.raw.{name}",
            columns=tuple(Field(n, parse_type(kind)) for n, kind in columns),
            comment="Landed by the crm pipeline" if name == "customers" else None,
        )
        studio.fake.sizes[f"dev.raw.{name}"] = 3 * GB

    landed("customers", ("id", "bigint"), ("email", "string"), ("region", "string"))
    landed("_dlt_loads", ("load_id", "string"), ("status", "bigint"))
    landed("_dlt_version", ("version", "bigint"))
    spec = """\
        table: ${catalog}.raw.customers      # dlt lands it; stevin says who may see it
        tags: {domain: sales, source: crm}
        columns:                             # names only — the shape is dlt's
          - {name: email, mask: "${catalog}.security.mask_email", tags: {pii: email}}
        grants:
          - {principal: analysts, privileges: [SELECT]}
    """
    _feature(
        studio,
        "govern",
        {},
        {"tables/customers.yml": spec, "tables/mask_email.yml": MASK_FUNCTIONS},
        show="tables/customers.yml",
    )


@scene
def feature_owned(studio: Studio) -> None:
    """dbt's tables take no spec: a plan says so, naming the file."""
    studio.write(
        "stevin.yml", PROJECT + "\nowned_elsewhere:\n  ${catalog}.silver.*: dbt\n"
    )
    orders = """\
        table: ${catalog}.silver.orders
        columns:
          - {name: order_id, type: bigint}
          - {name: amount, type: "decimal(18,2)"}
        grants:
          - {principal: analysts, privileges: [SELECT]}
    """
    _feature(studio, "owned", {}, {"tables/orders.yml": orders}, show="stevin.yml")


CONTRACT = """\
    apiVersion: v3.1.0
    kind: DataContract
    id: 2f9e3c1a-5b77-4c1e-9f0e-6d1c7a2b8e44
    name: orders
    version: 2.0.0
    status: active
    schema:
      - name: orders
        description: Order facts, one row per order
        properties:
          - {name: order_id, logicalType: integer, physicalType: bigint, primaryKey: true}
          - {name: customer_ref, logicalType: string, required: true}
          - {name: email, logicalType: string, classification: pii}
          - {name: amount, logicalType: number, physicalType: "decimal(18,2)"}
          - {name: status, logicalType: string, enum: [{value: open}, {value: shipped}]}
          - {name: placed, logicalType: date}
"""


@scene
def feature_contract(studio: Studio) -> None:
    """The producer wrote the contract; the spec points at it and adds the rest."""
    spec = """\
        table: ${catalog}.sales.orders
        from_contract: ../contracts/orders.odcs.yaml   # the shape lives there
        cluster_by: [placed]
        columns:                                       # only what a contract doesn't say
          - {name: email, mask: "${catalog}.security.mask_email"}
        grants:
          - {principal: analysts, privileges: [SELECT]}
    """
    _feature(
        studio,
        "contract",
        {},
        {
            "contracts/orders.odcs.yaml": CONTRACT,
            "tables/orders.yml": spec,
            "tables/mask_email.yml": MASK_FUNCTIONS,
        },
    )
    studio.quote("contracts/orders.odcs.yaml", "feature-contract.odcs.yaml")


@scene
def feature_adopt(studio: Studio) -> None:
    orders = """\
        # Orders, from the ingest pipeline
        table: ${catalog}.sales.orders
        comment: Order facts

        columns:
          - {name: order_id, type: bigint}
          - {name: amount, type: "decimal(18,2)"}
    """
    studio.write("stevin.yml", PROJECT)
    studio.write("tables/orders.yml", orders)
    studio.apply()
    # Someone added a column by hand at 2am to unblock a load.
    studio.fake.query(
        "ALTER TABLE `dev`.`sales`.`orders` "
        "ADD COLUMNS (region STRING COMMENT 'ISO 3166 code')"
    )
    studio.shoot("feature-adopt", "stevin adopt")
    # The file as adopt left it: the comment and the variable are still there.
    studio.quote("tables/orders.yml", "feature-adopt.yml")


@scene
def feature_strict(studio: Studio) -> None:
    studio.write("stevin.yml", PROJECT + "\nschemas:\n  ${catalog}.sales: strict\n")
    orders = """\
        table: ${catalog}.sales.orders
        columns:
          - {name: order_id, type: bigint}
    """
    legacy = """\
        table: ${catalog}.sales.orders_v1
        columns:
          - {name: order_id, type: bigint}
    """
    studio.fake.sizes["dev.sales.orders_v1"] = 96 * GB
    _feature(
        studio,
        "strict",
        {"tables/orders.yml": orders, "tables/orders_v1.yml": legacy},
        {"tables/orders_v1.yml": ""},
        show="stevin.yml",
    )


@scene
def feature_manage(studio: Studio) -> None:
    """Handing grants and tags to the tool that already owns them."""
    studio.write("stevin.yml", PROJECT + "\nmanage:\n  grants: false\n  tags: false\n")
    spec = (
        "table: ${catalog}.sales.orders\n"
        "columns:\n"
        "  - {name: order_id, type: bigint, nullable: false}\n"
        '  - {name: amount, type: "decimal(18,2)"}\n'
    )
    studio.write("tables/orders.yml", spec)
    studio.apply()
    # Someone sets a grant anyway: the spec is refused, and says who owns it.
    studio.write(
        "tables/orders.yml",
        spec + "grants:\n  - {principal: analysts, privileges: [SELECT]}\n",
    )
    studio.quote("stevin.yml", "feature-manage.yml")
    studio.shoot("feature-manage", "stevin validate")
    # And a plan says what it could not have touched.
    studio.write("tables/orders.yml", spec + "comment: Order facts\n")
    studio.shoot("feature-manage-plan", "stevin plan")


@scene
def start(studio: Studio) -> None:
    """The getting-started page: an empty directory, a schema made by hand."""
    from helpers import col, table
    from stevin.model.table import Grant

    studio.remove("stevin.yml")
    studio.fake = FakeWarehouse.of(
        table(
            col("customer_id", "bigint", nullable=False),
            col("email", "string", comment="Primary contact"),
            col("country", "string"),
            name="main.crm.customers",
            comment="One row per customer",
            grants=(Grant("analysts", ("SELECT",)),),
        ),
        table(
            col("event_id", "bigint"),
            col("customer_id", "bigint"),
            col("payload", "string"),
            name="main.crm.events",
        ),
        sizes={"main.crm.customers": 3 * GB, "main.crm.events": 870 * GB},
    )
    studio.shoot("start-import", "stevin import main.crm")
    studio.quote("stevin.yml", "start-project.yml")
    studio.quote("tables/customers.yml", "start-customers.yml")
    studio.shoot("start-plan", "stevin plan")
    studio.shoot("start-apply", "stevin apply", answer="y")
    studio.write(
        "tables/customers.yml",
        (studio.root / "tables" / "customers.yml")
        .read_text(encoding="utf-8")
        .replace(
            "- name: country\n  type: string\n",
            "- name: country\n  type: string\n- name: segment\n  type: string\n"
            "  comment: B2B or B2C\n",
        ),
    )
    studio.shoot("start-change", "stevin apply", answer="y")


#: Named the way the bundle names it, so it is written in one place only.
BUNDLE_ORDERS = """\
table: ${resources.schemas.sales.catalog_name}.${resources.schemas.sales.name}.orders
comment: Order facts
columns:
  - {name: order_id, type: bigint, nullable: false}
  - {name: amount, type: "decimal(18,2)"}
"""


@scene
def bundle(studio: Studio) -> None:
    """A project whose targets, variables and schema come from a bundle."""
    studio.write(
        "databricks.yml",
        """\
        bundle:
          name: shop

        variables:
          catalog:
            default: dev

        resources:
          schemas:
            sales:
              catalog_name: ${var.catalog}
              name: sales
              comment: Sales data

        targets:
          dev:
            default: true
          prod:
            variables:
              catalog: prod
    """,
    )
    studio.write(
        "stevin.yml",
        """\
        version: 1
        specs: [tables]
        bundle: databricks.yml
        history_schema: ${catalog}.stevin
    """,
    )
    studio.write("tables/orders.yml", BUNDLE_ORDERS)
    studio.quote("databricks.yml", "bundle-databricks.yml")
    studio.quote("stevin.yml", "bundle-project.yml")
    studio.quote("tables/orders.yml", "bundle-orders.yml")
    # Before the bundle has deployed its schema, and after.
    studio.shoot("bundle-undeployed", "stevin plan")
    studio.fake.schemas.add("dev.sales")
    studio.shoot("bundle-plan", "stevin plan")


@scene
def feature_import(studio: Studio) -> None:
    from helpers import col, table
    from stevin.model.table import Grant

    # A schema built by hand, the way most start.
    studio.fake = FakeWarehouse.of(
        table(
            col("customer_id", "bigint", nullable=False),
            col("email", "string", comment="Primary contact"),
            col("address", "struct<street:string,zip:string>"),
            name="dev.crm.customers",
            comment="One row per customer",
            tags=(("domain", "crm"),),
            grants=(Grant("analysts", ("SELECT",)),),
        ),
        table(col("event_id", "bigint"), col("payload", "string"), name="dev.crm.events"),
        sizes={"dev.crm.customers": 3 * GB, "dev.crm.events": 870 * GB},
    )
    studio.shoot("feature-import", "stevin import dev.crm -o tables")
    studio.quote("tables/customers.yml", "feature-import.yml")
    studio.shoot("feature-import-plan", "stevin plan")


@scene
def feature_sql_limits(studio: Studio) -> None:
    studio.write(
        "tables/customers.sql",
        """\
        CREATE TABLE ${catalog}.crm.customers (
          customer_id BIGINT NOT NULL,
          email STRING MASK ${catalog}.security.mask_email
        );
        """,
    )
    studio.quote("tables/customers.sql", "feature-sql-limits.sql")
    studio.shoot("feature-sql-limits", "stevin validate")


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/assets/screens")
    for path in make(out):
        print(path)


if __name__ == "__main__":
    main()

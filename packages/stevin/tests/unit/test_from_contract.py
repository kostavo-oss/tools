"""A table's shape, read from a data contract.

A producer who wrote an ODCS contract has said what the table looks like. A
spec that says `from_contract:` takes the columns, their types, the key and the
descriptions from there, and adds only what a contract doesn't say: clustering,
grants, masks, a row filter, an owner. The shape has one source, and `adopt`
won't write over it.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from helpers import plan_against
from stevin.adopt import CannotAdopt, adopt
from stevin.contract import ContractError, read_contract
from stevin.loader import (
    LoadedSpec,
    SpecError,
    dump_spec,
    load_table,
    validate_table,
)
from stevin.model.table import Check, ForeignKey, PrimaryKey
from stevin.model.types import Mask, Primitive, render_type

CONTRACT = """\
apiVersion: v3.1.0
kind: DataContract
id: 2f9e3c1a-5b77-4c1e-9f0e-6d1c7a2b8e44
name: sales
version: 2.0.0
status: active
servers:
  - server: prod
    type: databricks
    host: adb-123.azuredatabricks.net
    catalog: prod
    schema: sales
schema:
  - name: orders
    physicalName: orders
    logicalType: object
    physicalType: table
    description: Order facts, one row per order
    tags: [domain:sales, golden]
    properties:
      - name: order_id
        logicalType: integer
        physicalType: bigint
        primaryKey: true
        primaryKeyPosition: 2
      - name: shop_id
        logicalType: integer
        primaryKey: true
        primaryKeyPosition: 1
      - name: customer_ref
        logicalType: string
        required: true
        description: The customer, as the CRM knows them
        tags: [pii:indirect]
      - name: email
        logicalType: string
        physicalType: varchar(254)
        classification: pii
      - name: amount
        logicalType: number
        physicalType: decimal(18,2)
        description: Gross, incl. VAT
      - name: discount
        logicalType: number
      - name: placed
        logicalType: timestamp
      - name: address
        logicalType: object
        properties:
          - {name: street, logicalType: string, required: true}
          - {name: zip, logicalType: string, description: Postal code}
      - name: lines
        logicalType: array
        items:
          logicalType: object
          properties:
            - {name: sku, logicalType: string}
            - {name: qty, logicalType: integer, physicalType: int}
      - name: customer_id
        logicalType: integer
        physicalType: bigint
        relationships:
          - {to: customers.id}
      - name: status
        logicalType: string
        enum:
          - {value: open}
          - {value: shipped}
      - name: attrs
        logicalType: map
        map:
          key: {logicalType: string}
          value: {logicalType: string}
      - name: embedding
        logicalType: vector
        logicalTypeOptions: {dimensions: 384}
  - name: customers
    properties:
      - {name: id, logicalType: integer, physicalType: bigint, primaryKey: true}
      - {name: name, logicalType: string}
"""

#: The same orders table, written out as a spec by hand.
TWIN = """\
table: dev.sales.orders
comment: Order facts, one row per order
tags: {domain: sales, golden: ""}
cluster_by: [placed]
columns:
  - {name: order_id, type: bigint, nullable: false}
  - {name: shop_id, type: bigint, nullable: false}
  - name: customer_ref
    type: string
    nullable: false
    comment: The customer, as the CRM knows them
    tags: {pii: indirect}
  - {name: email, type: varchar(254), tags: {classification: pii}}
  - {name: amount, type: "decimal(18,2)", comment: "Gross, incl. VAT"}
  - {name: discount, type: double}
  - {name: placed, type: timestamp}
  - name: address
    type:
      struct:
        - {name: street, type: string, nullable: false}
        - {name: zip, type: string, comment: Postal code}
  - name: lines
    type:
      array:
        element:
          struct:
            - {name: sku, type: string}
            - {name: qty, type: int}
  - {name: customer_id, type: bigint}
  - {name: status, type: string}
  - {name: attrs, type: "map<string,string>"}
  - {name: embedding, type: "array<float>"}
constraints:
  - primary_key: {columns: [shop_id, order_id]}
  - check:
      name: status_enum
      expression: status IS NULL OR status IN ('open', 'shipped')
  - foreign_key:
      columns: [customer_id]
      references: dev.sales.customers
      referenced_columns: [id]
grants:
  - {principal: analysts, privileges: [SELECT]}
"""

SPEC = """\
table: ${catalog}.sales.orders
from_contract: ../contracts/sales.odcs.yaml
cluster_by: [placed]
grants:
  - {principal: analysts, privileges: [SELECT]}
"""


def project(tmp_path: Path, spec: str = SPEC, contract: str = CONTRACT) -> Path:
    """A contracts folder beside a tables folder, as a repo would have them."""
    (tmp_path / "contracts").mkdir(exist_ok=True)
    (tmp_path / "contracts" / "sales.odcs.yaml").write_text(contract, encoding="utf-8")
    (tmp_path / "tables").mkdir(exist_ok=True)
    path = tmp_path / "tables" / "orders.yml"
    path.write_text(textwrap.dedent(spec), encoding="utf-8")
    return path


def loaded(tmp_path: Path, spec: str = SPEC, contract: str = CONTRACT):
    return load_table(project(tmp_path, spec, contract), {"catalog": "dev"})


# ---------------------------------------------------------------------------
# the shape is the contract's
# ---------------------------------------------------------------------------


def test_a_contract_gives_the_table_its_shape(tmp_path: Path) -> None:
    """Columns, types, NOT NULL, the key in position order, descriptions, tags
    and classification — the same table as the spec written out by hand, so
    the same plan."""
    from_contract = loaded(tmp_path)
    (tmp_path / "tables" / "twin.yml").write_text(TWIN, encoding="utf-8")
    twin = load_table(tmp_path / "tables" / "twin.yml")

    assert from_contract == twin
    assert from_contract.primary_key() == PrimaryKey(("shop_id", "order_id"))
    assert from_contract.from_contract == "../contracts/sales.odcs.yaml"
    _, planned = plan_against(from_contract)
    _, planned_twin = plan_against(twin)
    assert [s.sql for s in planned.steps] == [s.sql for s in planned_twin.steps]
    assert any("CREATE TABLE" in (s.sql or "") for s in planned.steps)


def test_a_key_column_is_not_null_whatever_the_contract_says(tmp_path: Path) -> None:
    """Unity Catalog wants a primary key's columns NOT NULL; `primaryKey: true`
    without `required: true` is read that way rather than refused later."""
    found = loaded(tmp_path)
    assert found.column("shop_id") is not None
    assert found.column("shop_id").nullable is False


def test_the_tables_own_name_picks_the_object_and_port_overrides_it(
    tmp_path: Path,
) -> None:
    found = loaded(
        tmp_path,
        "table: ${catalog}.sales.crm_customers\n"
        "from_contract: ../contracts/sales.odcs.yaml\n"
        "port: customers\n",
    )
    assert found.name == "dev.sales.crm_customers"
    assert found.column_names == ("id", "name")
    assert found.primary_key() == PrimaryKey(("id",))
    assert found.contract_port == "customers"


def test_a_contract_with_one_object_needs_no_port(tmp_path: Path) -> None:
    only = "apiVersion: v3.2.0\nkind: DataContract\nid: x\nversion: 1.0.0\nschema:\n"
    only += (
        "  - name: things\n    properties:\n      - {name: id, logicalType: integer}\n"
    )
    found = loaded(
        tmp_path,
        "table: ${catalog}.sales.anything\nfrom_contract: ../contracts/sales.odcs.yaml\n",
        only,
    )
    assert found.column_names == ("id",)


def test_the_spec_adds_governance_on_top(tmp_path: Path) -> None:
    """A mask, a tag, a comment per column; a table tag that wins over the
    contract's; a row filter and an owner. Nothing about the shape."""
    found = loaded(
        tmp_path,
        """\
        table: ${catalog}.sales.orders
        from_contract: ../contracts/sales.odcs.yaml
        comment: Orders, as the shop sees them
        tags: {domain: shop}
        owner: data-eng
        columns:
          - {name: email, mask: "${catalog}.security.mask_email", tags: {pii: direct}}
          - {name: Amount, comment: Gross}
        row_filter: {function: "${catalog}.security.by_shop", columns: [shop_id]}
        """,
    )
    email = found.column("email")
    assert email is not None
    assert email.mask == Mask("dev.security.mask_email")
    assert email.tags == (("classification", "pii"), ("pii", "direct"))
    assert found.column("amount").comment == "Gross", "the spec's comment wins"
    assert found.comment == "Orders, as the shop sees them"
    assert found.tags_map() == {"domain": "shop", "golden": ""}
    assert found.owner == "data-eng"
    assert found.row_filter is not None
    assert found.column_names[:2] == ("order_id", "shop_id"), "the contract's order"


def test_a_dumped_contract_spec_reads_back_the_same(tmp_path: Path) -> None:
    """`dump_spec` writes the pointer and the governance, never the shape."""
    found = loaded(
        tmp_path,
        """\
        table: dev.sales.orders
        from_contract: ../contracts/sales.odcs.yaml
        columns:
          - {name: email, mask: dev.security.mask_email}
        grants:
          - {principal: analysts, privileges: [SELECT]}
        """,
    )
    written = dump_spec(found)
    assert "from_contract: ../contracts/sales.odcs.yaml" in written
    assert "type:" not in written, "the shape stays in the contract"
    assert "constraints" not in written
    (tmp_path / "tables" / "again.yml").write_text(written, encoding="utf-8")
    assert load_table(tmp_path / "tables" / "again.yml") == found


def test_adopt_refuses_to_write_over_a_contract(tmp_path: Path) -> None:
    path = project(tmp_path)
    found = load_table(path, {"catalog": "dev"})
    with pytest.raises(CannotAdopt, match="shape lives in the contract"):
        adopt(LoadedSpec(path, found), found, variables={"catalog": "dev"})


# ---------------------------------------------------------------------------
# partitioning, enums, relationships, maps and vectors
# ---------------------------------------------------------------------------

HEAD = "apiVersion: v3.2.0\nkind: DataContract\nid: x\nversion: 1.0.0\nschema:\n"

EVENTS = (
    HEAD
    + """\
  - name: events
    properties:
      - {name: id, logicalType: integer, primaryKey: true}
      - {name: day, logicalType: date, partitioned: true, partitionKeyPosition: 2}
      - {name: country, logicalType: string, partitioned: true, partitionKeyPosition: 1}
      - {name: kind, logicalType: string, required: true, enum: [click, view]}
      - {name: weight, logicalType: integer, enum: [{value: 1}, {value: 2}]}
"""
)
EVENTS_SPEC = "table: dev.web.events\nfrom_contract: ../contracts/sales.odcs.yaml\n"


def test_the_contracts_partitioning_is_the_tables_unless_the_spec_says(
    tmp_path: Path,
) -> None:
    """Layout is the spec's to decide. The contract's partition columns, in
    position order, are the default; a spec that clusters, or names its own
    partitioning, has the last word."""
    assert loaded(tmp_path, EVENTS_SPEC, EVENTS).partitioned_by == ("country", "day")
    clustered = loaded(tmp_path, EVENTS_SPEC + "cluster_by: [day]\n", EVENTS)
    assert clustered.partitioned_by is None
    assert clustered.cluster_by == ("day",)
    own = loaded(tmp_path, EVENTS_SPEC + "partitioned_by: [day]\n", EVENTS)
    assert own.partitioned_by == ("day",)
    assert not [d for d in validate_table(clustered, "x") if d.severity == "error"]


def test_an_enum_is_a_check(tmp_path: Path) -> None:
    """`IN (...)` over the allowed values — text quoted, numbers bare — and a
    column that may be null says so, so the constraint means the same whether
    a CHECK that evaluates to NULL passes or fails."""
    found = loaded(tmp_path, EVENTS_SPEC, EVENTS)
    assert found.checks() == (
        Check("kind_enum", "kind IN ('click', 'view')"),
        Check("weight_enum", "weight IS NULL OR weight IN (1, 2)"),
    )
    assert not [d for d in validate_table(found, "x") if d.severity == "error"]


RELATED = (
    HEAD
    + """\
  - name: order_lines
    id: lines_obj
    relationships:
      - {from: [order_lines.shop_id, order_lines.order_id], to: [orders.shop, orders.id]}
      - {from: order_lines.sku, to: schema/products_obj/properties/sku_prop}
      - {from: order_lines.sku, to: "catalogue.odcs.yaml#/schema/x/properties/y"}
    properties:
      - {name: shop_id, logicalType: integer}
      - {name: order_id, logicalType: integer}
      - {name: sku, logicalType: string}
      - name: warehouse
        logicalType: string
        relationships:
          - {to: warehouses.code}
  - name: orders
    physicalName: fct_orders
    properties:
      - {name: shop, logicalType: integer, primaryKey: true}
      - {name: id, logicalType: integer, primaryKey: true}
  - name: products
    id: products_obj
    properties:
      - {name: sku, id: sku_prop, logicalType: string, primaryKey: true}
"""
)


def test_relationships_are_foreign_keys_into_the_same_schema(tmp_path: Path) -> None:
    """A composite key by shorthand, to the other object's physical name; a
    reference by ids. What points into another file, or at an object the
    contract doesn't have, isn't an error: it is left out, and said."""
    found = loaded(
        tmp_path,
        "table: dev.sales.order_lines\nfrom_contract: ../contracts/sales.odcs.yaml\n",
        RELATED,
    )
    assert found.foreign_keys() == (
        ForeignKey(("shop_id", "order_id"), "dev.sales.fct_orders", ("shop", "id")),
        ForeignKey(("sku",), "dev.sales.products", ("sku",)),
    )
    warnings = [d.message for d in validate_table(found, "x") if d.severity == "warning"]
    assert len(warnings) == 2
    assert all("../contracts/sales.odcs.yaml" in w for w in warnings)
    assert "from warehouse to warehouses.code isn't made a foreign key" in warnings[0]
    assert "catalogue.odcs.yaml#/schema/x/properties/y" in warnings[1]


@pytest.mark.parametrize(
    ("element", "expected"),
    [
        (None, "array<float>"),
        ("float64", "array<double>"),
        ("int8", "array<tinyint>"),
        ("uint8", "array<smallint>"),
        ("binary", "binary"),
    ],
)
def test_a_vector_is_an_array_of_its_element_type(
    tmp_path: Path, element: str | None, expected: str
) -> None:
    options = f", logicalTypeOptions: {{elementType: {element}}}" if element else ""
    contract = (
        HEAD
        + "  - name: docs\n    properties:\n"
        + f"      - {{name: embedding, logicalType: vector{options}}}\n"
    )
    found = loaded(
        tmp_path,
        "table: dev.rag.docs\nfrom_contract: ../contracts/sales.odcs.yaml\n",
        contract,
    )
    assert render_type(found.columns[0].type) == expected


# ---------------------------------------------------------------------------
# what is refused, and how it is said
# ---------------------------------------------------------------------------


def refused(tmp_path: Path, spec: str, contract: str = CONTRACT) -> str:
    with pytest.raises(SpecError) as caught:
        loaded(tmp_path, spec, contract)
    return str(caught.value)


def test_a_spec_cannot_say_the_shape_twice(tmp_path: Path) -> None:
    message = refused(
        tmp_path,
        """\
        table: dev.sales.orders
        from_contract: ../contracts/sales.odcs.yaml
        columns:
          - {name: order_id, type: bigint}
        """,
    )
    assert "tables/orders.yml:3" in message
    assert "the shape lives in the contract ../contracts/sales.odcs.yaml" in message
    assert "no type" in message
    message = refused(
        tmp_path,
        """\
        table: dev.sales.orders
        from_contract: ../contracts/sales.odcs.yaml
        constraints:
          - primary_key: {columns: [order_id]}
        """,
    )
    assert "can't say 'constraints'" in message
    message = refused(
        tmp_path,
        "table: dev.sales.orders\nfrom_contract: ../contracts/sales.odcs.yaml\n"
        "renamed_from: old_orders\n",
    )
    assert "can't say 'renamed_from'" in message


def test_port_goes_with_from_contract(tmp_path: Path) -> None:
    message = refused(
        tmp_path,
        "table: dev.sales.orders\nport: orders\ncolumns:\n  - {name: id, type: bigint}\n",
    )
    assert "tables/orders.yml:2" in message
    assert "goes with `from_contract`" in message


def test_a_governed_column_must_be_in_the_contract(tmp_path: Path) -> None:
    message = refused(
        tmp_path,
        """\
        table: dev.sales.orders
        from_contract: ../contracts/sales.odcs.yaml
        columns:
          - {name: phone, tags: {pii: direct}}
        """,
    )
    assert "column 'phone' isn't in the contract's 'orders'" in message
    assert "order_id, shop_id" in message


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        (
            "table: dev.sales.nothing\nfrom_contract: ../contracts/sales.odcs.yaml\n",
            "describes no table 'nothing' (it has: orders, customers) — name the "
            "contract's object with `port:`",
        ),
        (
            "table: dev.sales.orders\nfrom_contract: ../contracts/sales.odcs.yaml\n"
            "port: returns\n",
            "describes no table 'returns'",
        ),
        (
            "table: dev.sales.orders\nfrom_contract: ../contracts/missing.odcs.yaml\n",
            "the data contract ../contracts/missing.odcs.yaml can't be read",
        ),
    ],
)
def test_what_the_contract_cannot_answer(tmp_path: Path, spec: str, message: str) -> None:
    found = refused(tmp_path, spec)
    assert message in found
    assert "tables/orders.yml:2" in found, "the error sits on the from_contract line"
    assert "\\" not in found.split(": ", 1)[1], "forward slashes, on every platform"


@pytest.mark.parametrize(
    ("contract", "message"),
    [
        ("kind: DataContract\n  - broken: [", "isn't YAML"),
        ("just: text\n", "has kind None; a data contract says `kind: DataContract`"),
        ("kind: DataProduct\napiVersion: v3.1.0\n", "has kind 'DataProduct'"),
        (
            "kind: DataContract\napiVersion: v2.2.2\nschema: []\n",
            "is apiVersion 'v2.2.2'; stevin reads ODCS v3.0, v3.1, v3.2",
        ),
        ("kind: DataContract\napiVersion: v3.1.0\n", "has no `schema` objects"),
        (
            "kind: DataContract\napiVersion: v3.1.0\nschema:\n  - properties: []\n",
            "schema object 1 has no name",
        ),
        (
            "kind: DataContract\napiVersion: v3.1.0\nschema:\n  - name: orders\n",
            "object 'orders' has no properties",
        ),
        (
            "kind: DataContract\napiVersion: v3.1.0\nschema:\n  - name: orders\n"
            "    properties:\n      - {name: at, logicalType: time}\n",
            "property 'at': no Databricks type for logicalType 'time'; give a "
            "`physicalType`",
        ),
        (
            "kind: DataContract\napiVersion: v3.1.0\nschema:\n  - name: orders\n"
            "    properties:\n      - {name: lines, logicalType: array}\n",
            "property 'lines' is an array with no `items`",
        ),
        (
            "kind: DataContract\napiVersion: v3.1.0\nschema:\n  - name: orders\n"
            "    properties:\n"
            "      - {name: a, logicalType: string, physicalType: nvarchar2}\n",
            None,  # an unknown physical type falls back to the logical one
        ),
        (
            "kind: DataContract\napiVersion: v3.2.0\nschema:\n  - name: orders\n"
            "    properties:\n      - {name: attrs, logicalType: map}\n",
            "property 'attrs': no Databricks type for logicalType 'map'",
        ),
        (
            "kind: DataContract\napiVersion: v3.2.0\nschema:\n  - name: orders\n"
            "    properties:\n"
            "      - {name: m, logicalType: map, map: {key: {logicalType: string}}}\n",
            "property 'm' is a map that needs a `key` and a `value`",
        ),
        (
            "kind: DataContract\napiVersion: v3.2.0\nschema:\n  - name: orders\n"
            "    properties:\n      - {name: kind, logicalType: string, enum: []}\n",
            "property 'kind': `enum` must be a list of values",
        ),
    ],
)
def test_what_a_contract_must_say(
    tmp_path: Path, contract: str, message: str | None
) -> None:
    path = tmp_path / "c.odcs.yaml"
    path.write_text(contract, encoding="utf-8")
    if message is None:
        found = read_contract(path)
        assert found.objects[0].columns[0].type == Primitive("string")
        return
    with pytest.raises(ContractError, match="c.odcs.yaml") as caught:
        read_contract(path)
    assert message in str(caught.value)


def test_a_contract_is_refused_where_the_spec_names_it(tmp_path: Path) -> None:
    """A contract that can't be read is the spec's error, on its line, so the
    message says both files."""
    message = refused(
        tmp_path,
        "table: dev.sales.orders\nfrom_contract: ../contracts/sales.odcs.yaml\n",
        "kind: Recipe\n",
    )
    assert message.startswith(f"{(tmp_path / 'tables' / 'orders.yml').as_posix()}:2:")
    assert "sales.odcs.yaml has kind 'Recipe'" in message

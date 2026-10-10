"""A table's shape, read from a data contract.

A producer who writes an [ODCS](https://bitol-io.github.io/open-data-contract-standard/)
data contract has already said what the table looks like: its columns, their
types, which are required, which make the key, what each one means. Writing
that out a second time in a spec would be a second source of truth, and the
two would drift. So a spec may point at the contract instead —

```yaml
table: ${catalog}.sales.orders
from_contract: ../contracts/orders.odcs.yaml
grants:
  - {principal: analysts, privileges: [SELECT]}
```

— and take its shape from there, adding only what a contract doesn't say and
stevin does: clustering, grants, masks, a row filter, an owner. The contract
is read, never written: `adopt` refuses to change one.

What is read, and what it becomes:

| in the contract                          | in the table                               |
|------------------------------------------|--------------------------------------------|
| a `schema` object (the *port*)           | the table; `physicalName` or `name` is its |
| `properties[].name`                      | a column                                   |
| `physicalType`, when stevin can parse it | the column's type                          |
| otherwise `logicalType`                  | the counterpart in `LOGICAL_TYPES`         |
| `logicalType: object` + `properties`     | a struct                                   |
| `logicalType: array` + `items`           | an array                                   |
| `logicalType: map` + `map: {key, value}` | a map                                      |
| `logicalType: vector`                    | an array of its `elementType` (`float`)    |
| `required: true`, or `primaryKey: true`  | `nullable: false`                          |
| `primaryKey: true`, `primaryKeyPosition` | the primary key                            |
| `partitioned`, `partitionKeyPosition`    | the partitioning, unless the spec clusters |
| `enum`                                   | a CHECK: `status IN ('open', 'shipped')`   |
| `relationships`                          | foreign keys, into the same schema         |
| `description`                            | the comment                                |
| `tags` (`key:value`, or just `key`)      | tags                                       |
| `classification`                         | the tag `classification`                   |

`unique`, `quality`, `servers` and the rest are the contract's business, not a
table's shape, and are left alone. Only ODCS v3 (3.0 to 3.2) is read, and only
the fields above — checked here, by hand, so a contract from a newer minor
version still reads for what it has. A relationship stevin can't follow — into
another file, or to a nested property — is not an error: it is left out and
said, as a warning at `validate`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from stevin.errors import StevinError
from stevin.model.table import Check, PrimaryKey
from stevin.model.types import Array, Column, DataType, Field, Map, Primitive, Struct
from stevin.sql import maybe_quote_ident, quote_literal
from stevin.typeparser import TypeParseError, parse_type

#: The `kind` a contract declares, and the standard's major version stevin reads.
KIND = "DataContract"
API_VERSIONS = ("v3.0", "v3.1", "v3.2")

#: What a logical type becomes when the contract names no physical type stevin
#: can parse. `time` has no Databricks type and needs a `physicalType`; an
#: object, an array, a map and a vector are spelled out by the contract itself.
LOGICAL_TYPES: dict[str, str] = {
    "string": "string",
    "date": "date",
    "timestamp": "timestamp",
    "integer": "bigint",
    "number": "double",
    "boolean": "boolean",
}

#: A vector (ODCS 3.2) is an array of numbers on Databricks: `elementType` says
#: of what. Half-precision floats have no Databricks type and widen to `float`;
#: an unsigned byte needs a `smallint` to hold 255. A binary-quantized vector,
#: one bit an element, is the bytes it is packed into.
#: https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-datatypes
VECTOR_ELEMENTS: dict[str, str] = {
    "float32": "float",
    "float64": "double",
    "float16": "float",
    "bfloat16": "float",
    "int8": "tinyint",
    "uint8": "smallint",
}
VECTOR_DEFAULT = "float32"


class ContractError(StevinError):
    """A data contract that can't be read as a table's shape."""


@dataclass(frozen=True, slots=True)
class Reference:
    """A relationship in the contract: these columns point at those columns of
    another of the contract's objects — a foreign key, once the loader knows
    which schema the tables are in."""

    columns: tuple[str, ...]
    #: The other object, by its physical name.
    to: str
    to_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContractTable:
    """One of a contract's schema objects, in a table's terms."""

    #: `physicalName` when the contract gives one, else `name`.
    name: str
    columns: tuple[Column, ...]
    primary_key: PrimaryKey | None = None
    comment: str | None = None
    tags: tuple[tuple[str, str], ...] = ()
    #: `partitioned: true` properties, in `partitionKeyPosition` order.
    partitioned_by: tuple[str, ...] = ()
    #: A property's `enum`, as the CHECK that enforces it.
    checks: tuple[Check, ...] = ()
    #: `relationships`, at the object's level and its properties'.
    references: tuple[Reference, ...] = ()
    #: What the contract says that stevin couldn't make part of the table — a
    #: relationship into another file — said once each, as a warning.
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Contract:
    """A data contract, read for the tables it describes."""

    path: Path
    api_version: str
    objects: tuple[ContractTable, ...]
    id: str | None = None
    version: str | None = None
    #: The path as a message says it: as the spec wrote it, forward slashes on
    #: every platform.
    shown: str = ""

    def object(self, name: str) -> ContractTable:
        """The schema object a spec means, by its physical or logical name.
        Raises `ContractError` naming what there is."""
        wanted = name.casefold()
        for found in self.objects:
            if found.name.casefold() == wanted:
                return found
        raise ContractError(
            f"{self.shown} describes no table {name!r} (it has: {self._names()})"
        )

    def object_or_only(self, name: str) -> ContractTable:
        """The only object there is, or the one called `name` — what a spec
        without `port:` means: the table's own name, unless there is nothing
        to choose between."""
        if len(self.objects) == 1:
            return self.objects[0]
        return self.object(name)

    def _names(self) -> str:
        return ", ".join(found.name for found in self.objects)


def read_contract(path: Path, shown: str | None = None) -> Contract:
    """Read an ODCS contract for the tables it describes.

    Raises `ContractError` — naming the path, as `shown` when given — when the
    file can't be read, isn't YAML, isn't a `DataContract`, is a version stevin
    doesn't read, or describes a shape stevin can't make a table from.
    """
    shown = shown if shown is not None else path.as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ContractError(
            f"the data contract {shown} can't be read ({error.strerror or error})"
        ) from error
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ContractError(f"the data contract {shown} isn't YAML: {error}") from error
    if not isinstance(document, dict):
        raise ContractError(f"the data contract {shown} isn't a mapping")
    kind = document.get("kind")
    if kind != KIND:
        raise ContractError(
            f"{shown} has kind {kind!r}; a data contract says `kind: {KIND}`"
        )
    version = document.get("apiVersion")
    if not isinstance(version, str) or not version.startswith(API_VERSIONS):
        supported = ", ".join(API_VERSIONS)
        raise ContractError(
            f"{shown} is apiVersion {version!r}; stevin reads ODCS {supported}"
        )
    objects = document.get("schema")
    if not isinstance(objects, list) or not objects:
        raise ContractError(f"{shown} has no `schema` objects to make a table from")
    index_of = _Index.of(objects)
    tables = tuple(
        _read_object(entry, index, shown, index_of)
        for index, entry in enumerate(objects, 1)
    )
    return Contract(
        path,
        version,
        tables,
        id=_optional_string(document, "id"),
        version=_optional_string(document, "version"),
        shown=shown,
    )


@dataclass(frozen=True, slots=True)
class _Index:
    """What a relationship's reference can name: the contract's objects by
    their `name` (the shorthand `object.property`) and by their `id` (the fully
    qualified `schema/<id>/properties/<id>`)."""

    #: object `name`, lower case → its physical name
    by_name: dict[str, str]
    #: object `id` → (its physical name, property `id` → property name)
    by_id: dict[str, tuple[str, dict[str, str]]]

    @classmethod
    def of(cls, objects: list[object]) -> _Index:
        by_name: dict[str, str] = {}
        by_id: dict[str, tuple[str, dict[str, str]]] = {}
        for entry in objects:
            if not isinstance(entry, dict):
                continue
            physical = entry.get("physicalName") or entry.get("name")
            if not isinstance(physical, str) or not physical:
                continue
            for key in (entry.get("name"), entry.get("physicalName")):
                if isinstance(key, str) and key:
                    by_name[key.casefold()] = physical
            properties = entry.get("properties")
            ids = {
                prop["id"]: prop["name"]
                for prop in (properties if isinstance(properties, list) else [])
                if isinstance(prop, dict)
                and isinstance(prop.get("id"), str)
                and isinstance(prop.get("name"), str)
            }
            if isinstance(entry.get("id"), str):
                by_id[entry["id"]] = (physical, ids)
        return cls(by_name, by_id)

    def resolve(self, reference: object) -> tuple[str, str] | None:
        """`(object's physical name, property name)` for a reference into this
        contract, or None when it points somewhere stevin can't follow: another
        file, a nested property, an object that isn't here."""
        if not isinstance(reference, str) or "#" in reference:
            return None
        if "/" in reference:
            parts = reference.strip("/").split("/")
            if len(parts) != 4 or parts[0] != "schema" or parts[2] != "properties":
                return None
            found = self.by_id.get(parts[1])
            if found is None or parts[3] not in found[1]:
                return None
            return found[0], found[1][parts[3]]
        parts = reference.split(".")
        if len(parts) != 2 or parts[0].casefold() not in self.by_name:
            return None
        return self.by_name[parts[0].casefold()], parts[1]


def _read_object(
    entry: object, index: int, shown: str, index_of: _Index
) -> ContractTable:
    if not isinstance(entry, dict):
        raise ContractError(f"{shown}: schema object {index} isn't a mapping")
    name = entry.get("physicalName") or entry.get("name")
    if not isinstance(name, str) or not name:
        raise ContractError(f"{shown}: schema object {index} has no name")
    where = f"{shown}, object {name!r}"
    properties = entry.get("properties")
    if not isinstance(properties, list) or not properties:
        raise ContractError(f"{where} has no properties to make columns from")
    columns = tuple(_read_column(prop, f"{where}", top=True) for prop in properties)
    pairs = [
        (prop, column)
        for prop, column in zip(properties, columns, strict=True)
        if isinstance(prop, dict)
    ]
    keyed = _in_position(pairs, "primaryKey", "primaryKeyPosition")
    references, notes = _references(entry, pairs, name, index_of)
    return ContractTable(
        name=name,
        columns=columns,
        primary_key=PrimaryKey(keyed) if keyed else None,
        comment=_optional_string(entry, "description"),
        tags=_tags(entry, where),
        partitioned_by=_in_position(pairs, "partitioned", "partitionKeyPosition"),
        checks=tuple(
            check for prop, column in pairs for check in _enum_check(prop, column, where)
        ),
        references=references,
        notes=notes,
    )


def _in_position(
    pairs: list[tuple[dict[str, object], Column]], flag: str, position: str
) -> tuple[str, ...]:
    """The columns a boolean marks — the key, the partitioning — in the order
    their position says: where the contract gives one, by it; the rest after,
    as written. Positions start at 1 in ODCS, and -1 means "none"."""
    marked = [(prop, column) for prop, column in pairs if prop.get(flag) is True]

    def order(item: tuple[int, tuple[dict[str, object], Column]]) -> int:
        at = item[1][0].get(position)
        if isinstance(at, int) and not isinstance(at, bool) and at >= 1:
            return at
        return len(marked) + item[0] + 1

    return tuple(column.name for _, (_, column) in sorted(enumerate(marked), key=order))


def _enum_check(prop: dict[str, object], column: Column, where: str) -> tuple[Check, ...]:
    """A property's `enum` as a CHECK: `status IN ('open', 'shipped')`.

    A value is an object with a `value` (ODCS 3.2) or the value itself. A
    column that may be null says so in the expression, so the constraint means
    the same whether a CHECK that evaluates to NULL passes or fails.
    """
    values = prop.get("enum")
    if values is None:
        return ()
    at = f"{where}, property {column.name!r}"
    if not isinstance(values, list) or not values:
        raise ContractError(f"{at}: `enum` must be a list of values")
    literals: list[str] = []
    for entry in values:
        value = entry.get("value") if isinstance(entry, dict) else entry
        if isinstance(value, bool):
            literals.append("TRUE" if value else "FALSE")
        elif isinstance(value, int | float):
            literals.append(repr(value))
        elif isinstance(value, str):
            literals.append(quote_literal(value))
        else:
            raise ContractError(f"{at}: an enum value must be text or a number")
    # Bare where it can be, as someone would write it and as the catalog says
    # it back: the differ compares the two.
    name = maybe_quote_ident(column.name)
    allowed = f"{name} IN ({', '.join(literals)})"
    expression = allowed if not column.nullable else f"{name} IS NULL OR {allowed}"
    return (Check(f"{column.name}_enum", expression),)


def _references(
    entry: dict[str, object],
    pairs: list[tuple[dict[str, object], Column]],
    name: str,
    index_of: _Index,
) -> tuple[tuple[Reference, ...], tuple[str, ...]]:
    """The object's relationships as references, and a note for each one that
    can't be followed. At a property's level `from` is the property itself; at
    the object's level `from` and `to` are one reference each, or a list of the
    same length for a composite key."""
    found: list[Reference] = []
    notes: list[str] = []

    def add(columns: list[str], to: object) -> None:
        targets = to if isinstance(to, list) else [to]
        resolved = [index_of.resolve(target) for target in targets]
        tables = {target[0] for target in resolved if target is not None}
        if None in resolved or len(tables) != 1 or len(resolved) != len(columns):
            notes.append(
                f"the relationship from {', '.join(columns)} to "
                f"{', '.join(str(t) for t in targets)} isn't made a foreign key: "
                "stevin follows `object.property` and `schema/<id>/properties/<id>` "
                "references to one object of the same contract"
            )
            return
        found.append(
            Reference(
                tuple(columns),
                tables.pop(),
                tuple(target[1] for target in resolved if target is not None),
            )
        )

    def relationships(holder: dict[str, object]) -> list[dict[str, object]]:
        listed = holder.get("relationships")
        return (
            [r for r in listed if isinstance(r, dict)] if isinstance(listed, list) else []
        )

    for prop, column in pairs:
        for relationship in relationships(prop):
            add([column.name], relationship.get("to"))
    for relationship in relationships(entry):
        sources = relationship.get("from")
        sources = sources if isinstance(sources, list) else [sources]
        resolved = [index_of.resolve(source) for source in sources]
        if None in resolved or any(r is not None and r[0] != name for r in resolved):
            notes.append(
                f"the relationship from {', '.join(str(s) for s in sources)} isn't "
                f"made a foreign key: it doesn't start at {name}'s own properties"
            )
            continue
        add([r[1] for r in resolved if r is not None], relationship.get("to"))
    return tuple(found), tuple(notes)


def _read_column(prop: object, where: str, *, top: bool) -> Field:
    """A property as a column (`top`) or a struct's field."""
    if not isinstance(prop, dict):
        raise ContractError(f"{where}: a property isn't a mapping")
    name = prop.get("name")
    if not isinstance(name, str) or not name:
        raise ContractError(f"{where}: a property has no name")
    at = f"{where}, property {name!r}"
    required = prop.get("required") is True or prop.get("primaryKey") is True
    return Field(
        name,
        _type_of(prop, at),
        nullable=not required,
        comment=_optional_string(prop, "description"),
        # Unity Catalog tags live on columns, not on a struct's fields.
        tags=_tags(prop, at) if top else (),
    )


def _type_of(prop: dict[str, object], at: str) -> DataType:
    """The column's type: the contract's physical type where stevin can parse
    it, a struct or array where the contract spells one out, else the logical
    type's Databricks counterpart."""
    logical = prop.get("logicalType")
    nested = prop.get("properties")
    if isinstance(nested, list) and nested:
        if logical not in (None, "object"):
            raise ContractError(
                f"{at} has properties, which only `logicalType: object` may"
            )
        return Struct(tuple(_read_column(member, at, top=False) for member in nested))
    if logical == "array":
        items = prop.get("items")
        if not isinstance(items, dict):
            raise ContractError(f"{at} is an array with no `items` to say of what")
        return Array(_type_of(items, f"{at}, items"))
    spelled = prop.get("map")
    if logical == "map" and isinstance(spelled, dict):
        key, value = spelled.get("key"), spelled.get("value")
        if not isinstance(key, dict) or not isinstance(value, dict):
            raise ContractError(f"{at} is a map that needs a `key` and a `value`")
        return Map(_type_of(key, f"{at}, key"), _type_of(value, f"{at}, value"))
    physical = prop.get("physicalType")
    if isinstance(physical, str) and physical.strip():
        try:
            parsed = parse_type(physical.strip())
        except TypeParseError:
            parsed = None  # not a type at all: fall back to the logical one
        # The parser lets an unknown name through, so a live table with a type
        # Databricks added last week still reads; a contract's `nvarchar2` is
        # another platform's word for the logical type, not a column's type.
        if parsed is not None and not (
            isinstance(parsed, Primitive) and not parsed.known
        ):
            return parsed
    if isinstance(logical, str) and logical in LOGICAL_TYPES:
        return Primitive(LOGICAL_TYPES[logical])
    if logical == "vector":
        options = prop.get("logicalTypeOptions")
        element = (
            options.get("elementType", VECTOR_DEFAULT)
            if isinstance(options, dict)
            else VECTOR_DEFAULT
        )
        if element == "binary":
            return Primitive("binary")
        if element not in VECTOR_ELEMENTS:
            raise ContractError(f"{at}: no Databricks type for a vector of {element!r}")
        return Array(Primitive(VECTOR_ELEMENTS[element]))
    shown = f"physicalType {physical!r}" if physical else f"logicalType {logical!r}"
    raise ContractError(
        f"{at}: no Databricks type for {shown}; give a `physicalType` stevin "
        "can read, such as `bigint`, `decimal(18,2)` or `string`"
    )


def _tags(entry: dict[str, object], at: str) -> tuple[tuple[str, str], ...]:
    """`tags: [pii, domain:sales]` → `(pii, ''), (domain, sales)`; a
    `classification` becomes the tag of that name."""
    found: list[tuple[str, str]] = []
    tags = entry.get("tags")
    if tags is not None:
        if not isinstance(tags, list):
            raise ContractError(f"{at}: `tags` must be a list")
        for tag in tags:
            if not isinstance(tag, str) or not tag.strip():
                raise ContractError(f"{at}: a tag must be text, not {tag!r}")
            key, _, value = tag.partition(":")
            found.append((key.strip(), value.strip()))
    classification = entry.get("classification")
    if isinstance(classification, str) and classification.strip():
        found.append(("classification", classification.strip()))
    return tuple(found)


def _optional_string(entry: dict[str, object], key: str) -> str | None:
    value = entry.get(key)
    return value if isinstance(value, str) and value != "" else None

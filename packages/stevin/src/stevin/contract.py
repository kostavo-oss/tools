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
| `required: true`, or `primaryKey: true`  | `nullable: false`                          |
| `primaryKey: true`, `primaryKeyPosition` | the primary key                            |
| `description`                            | the comment                                |
| `tags` (`key:value`, or just `key`)      | tags                                       |
| `classification`                         | the tag `classification`                   |

`unique`, `logicalTypeOptions`, `quality`, `servers` and the rest are the
contract's business, not a table's shape, and are left alone. Only ODCS v3
(3.0 to 3.2) is read, and only the fields above — checked here, by hand, so a
contract from a newer minor version still reads for what it has.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from stevin.errors import StevinError
from stevin.model.table import PrimaryKey
from stevin.model.types import Array, Column, DataType, Field, Primitive, Struct
from stevin.typeparser import TypeParseError, parse_type

#: The `kind` a contract declares, and the standard's major version stevin reads.
KIND = "DataContract"
API_VERSIONS = ("v3.0", "v3.1", "v3.2")

#: What a logical type becomes when the contract names no physical type stevin
#: can parse. `time` has no Databricks type, `map` and `vector` no column shape
#: a contract spells out; those need a `physicalType`.
LOGICAL_TYPES: dict[str, str] = {
    "string": "string",
    "date": "date",
    "timestamp": "timestamp",
    "integer": "bigint",
    "number": "double",
    "boolean": "boolean",
}


class ContractError(StevinError):
    """A data contract that can't be read as a table's shape."""


@dataclass(frozen=True, slots=True)
class ContractTable:
    """One of a contract's schema objects, in a table's terms."""

    #: `physicalName` when the contract gives one, else `name`.
    name: str
    columns: tuple[Column, ...]
    primary_key: PrimaryKey | None = None
    comment: str | None = None
    tags: tuple[tuple[str, str], ...] = ()


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
    tables = tuple(
        _read_object(entry, index, shown) for index, entry in enumerate(objects, 1)
    )
    return Contract(
        path,
        version,
        tables,
        id=_optional_string(document, "id"),
        version=_optional_string(document, "version"),
        shown=shown,
    )


def _read_object(entry: object, index: int, shown: str) -> ContractTable:
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
    keyed = [
        (prop, column)
        for prop, column in zip(properties, columns, strict=True)
        if isinstance(prop, dict) and prop.get("primaryKey") is True
    ]
    primary_key = None
    if keyed:
        # By `primaryKeyPosition` where the contract gives one; the rest after,
        # as written. Positions start at 1 in ODCS.
        ordered = sorted(
            enumerate(keyed),
            key=lambda item: (
                item[1][0].get("primaryKeyPosition")
                if isinstance(item[1][0].get("primaryKeyPosition"), int)
                else len(keyed) + item[0] + 1
            ),
        )
        primary_key = PrimaryKey(tuple(column.name for _, (_, column) in ordered))
    return ContractTable(
        name=name,
        columns=columns,
        primary_key=primary_key,
        comment=_optional_string(entry, "description"),
        tags=_tags(entry, where),
    )


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

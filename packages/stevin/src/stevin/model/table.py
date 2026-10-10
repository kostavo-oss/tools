"""Tables and their constraints.

A `Table` is the desired *or* the live state — the differ takes one of each and
never needs to know which came from where.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from typing import TypeAlias

from stevin.formerly import MANAGED_PROPERTY, SEED_PROPERTY
from stevin.model.types import Array, Column, DataType, Field, GovernedColumn, Map, Struct

#: Delta table features stevin turns on itself, as prerequisites for a change
#: that needs them. A spec doesn't list them, and reporting them as unmanaged
#: would be reporting our own work back at the user.
#: https://docs.databricks.com/aws/en/delta/column-mapping
#: https://docs.databricks.com/aws/en/delta/type-widening
COLUMN_MAPPING_PROPERTY = "delta.columnMapping.mode"
TYPE_WIDENING_PROPERTY = "delta.enableTypeWidening"
#: The table feature column defaults need. A `delta.feature.*` flag, so it is
#: bookkeeping as far as reporting and import are concerned.
DEFAULTS_FEATURE = "delta.feature.allowColumnDefaults"
PREREQUISITE_PROPERTIES = frozenset({COLUMN_MAPPING_PROPERTY, TYPE_WIDENING_PROPERTY})

#: Properties Delta maintains itself. Declaring one in a spec would have stevin
#: fight Delta for it — setting `maxColumnId` back after columns were added
#: corrupts column mapping — so a spec may not, and `import` never writes them.
MAINTAINED_PROPERTIES = frozenset(
    {
        "delta.columnMapping.maxColumnId",
        "delta.minReaderVersion",
        "delta.minWriterVersion",
    }
)

#: Delta keeps each CHECK constraint as a table property under this prefix,
#: named after the constraint. stevin models them as constraints instead.
CHECK_PROPERTY_PREFIX = "delta.constraints."

#: How a `set_cluster_by` change says "automatic liquid clustering".
CLUSTER_AUTO = "auto"

#: `delta.feature.<name>` records that a table feature is supported. Delta sets it
#: when the feature is enabled another way; it isn't anyone's intent to report.
FEATURE_FLAG_PREFIX = "delta.feature."


#: Properties Unity Catalog and Delta set for their own use — table ids, the
#: hidden columns row tracking keeps, internal format markers. Seen on every new
#: table in a live workspace (2026-09-18); never anyone's intent, and replayed
#: onto another table they would be wrong.
INTERNAL_PROPERTY_PREFIXES = ("io.unitycatalog.", "delta.rowTracking.materialized")

#: What a new table gets without asking, on a current workspace (observed
#: 2026-09-18). Not reported as unmanaged and not written by `import` while they
#: hold these values — they are the platform's, not the table's. A table where
#: someone changed one still shows it. A spec may declare them like any other.
PLATFORM_DEFAULTS: dict[str, str] = {
    "delta.enableDeletionVectors": "true",
    "delta.enableRowTracking": "true",
    "delta.checkpointPolicy": "v2",
    "delta.checkpoint.writeStatsAsJson": "false",
    "delta.checkpoint.writeStatsAsStruct": "true",
    "delta.parquet.compression.codec": "zstd",
    "delta.parquet.format.version": "2.12.0",
}


def is_platform_default(key: str, value: str) -> bool:
    return PLATFORM_DEFAULTS.get(key) == value


def is_bookkeeping(key: str) -> bool:
    """Is this property Delta's or stevin's own, rather than anyone's intent?"""
    return (
        key in MAINTAINED_PROPERTIES
        or key.startswith(INTERNAL_PROPERTY_PREFIXES)
        or key.endswith(".internal")
        or key.startswith(FEATURE_FLAG_PREFIX)
        or key in (MANAGED_PROPERTY, SEED_PROPERTY)
        or key in PREREQUISITE_PROPERTIES
        or key.startswith(CHECK_PROPERTY_PREFIX)
    )


@dataclass(frozen=True, slots=True)
class PrimaryKey:
    """An informational primary key.

    Unity Catalog primary keys are declarative (`RELY`/`NORELY`) rather than
    enforced, and their columns must be `NOT NULL`.
    https://docs.databricks.com/aws/en/tables/constraints
    """

    columns: tuple[str, ...]
    name: str | None = None


@dataclass(frozen=True, slots=True)
class Check:
    """An enforced `CHECK` constraint."""

    name: str
    expression: str


@dataclass(frozen=True, slots=True)
class ForeignKey:
    """An informational foreign key onto another table's primary key.

    Like a primary key in Unity Catalog, it is declared rather than enforced.
    https://docs.databricks.com/aws/en/tables/constraints
    """

    columns: tuple[str, ...]
    references: str
    referenced_columns: tuple[str, ...]
    name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "references", self.references.lower())

    def same_as(self, other: ForeignKey) -> bool:
        """The same relationship, whatever it is called."""
        return (
            tuple(c.casefold() for c in self.columns)
            == tuple(c.casefold() for c in other.columns)
            and self.references == other.references
            and tuple(c.casefold() for c in self.referenced_columns)
            == tuple(c.casefold() for c in other.referenced_columns)
        )


Constraint: TypeAlias = PrimaryKey | Check | ForeignKey


@dataclass(frozen=True, slots=True)
class RowFilter:
    """A row filter: a SQL function over some columns that hides rows.

    https://docs.databricks.com/aws/en/tables/row-and-column-filters
    """

    function: str
    columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "function", self.function.lower())


@dataclass(frozen=True, slots=True)
class Seed:
    """The rows a table's spec declares — reference data, kept in the repo.

    A seed is the table's whole content, not an addition to it: applying one
    replaces what is there. That is what makes it comparable at all. Rows are
    held as text and rendered as literals of each column's declared type when
    the statement is built, so a spec can't smuggle SQL in through a value.

    `digest` is what the plan compares — the rows themselves never go near a
    diff, because a plan that printed five hundred of them would tell nobody
    anything.
    """

    columns: tuple[str, ...] = ()
    rows: tuple[tuple[str | None, ...], ...] = ()
    #: Where it came from, for the message when something in it is wrong.
    source: str | None = field(default=None, compare=False)

    @property
    def digest(self) -> str:
        """A short hash of the rows, as they will be loaded.

        Over the values, not the file: reformatting a CSV, or moving the same
        rows into the spec, is not a change to the table.
        """
        canonical = "\n".join(
            "\x1f".join("\x00" if value is None else value for value in row)
            for row in (self.columns, *self.rows)
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def __len__(self) -> int:
        return len(self.rows)


@dataclass(frozen=True, slots=True)
class Grant:
    """What one principal may do with a table.

    A spec that names a principal manages that principal's privileges exactly;
    principals it doesn't name are someone else's business.
    """

    principal: str
    privileges: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "privileges", tuple(sorted(set(self.privileges))))


class Securable:
    """What tables and views share: a three-part name, and what governs them.

    A mixin rather than a base dataclass, so both stay frozen and slotted.
    """

    __slots__ = ()

    name: str
    properties: tuple[tuple[str, str], ...]
    tags: tuple[tuple[str, str], ...]
    grants: tuple[Grant, ...]
    removed_properties: tuple[str, ...]
    removed_tags: tuple[str, ...]
    owner: str | None

    @property
    def parts(self) -> tuple[str, ...]:
        return tuple(self.name.split("."))

    @property
    def short_name(self) -> str:
        return self.parts[-1]

    @property
    def schema(self) -> str:
        """The `catalog.schema` this lives in."""
        return ".".join(self.parts[:-1])

    def properties_map(self) -> dict[str, str]:
        return dict(self.properties)

    def tags_map(self) -> dict[str, str]:
        return dict(self.tags)

    def grants_map(self) -> dict[str, tuple[str, ...]]:
        return {grant.principal: grant.privileges for grant in self.grants}

    @property
    def managed(self) -> bool:
        """True when stevin created this and may therefore drop it."""
        return self.properties_map().get(MANAGED_PROPERTY, "").lower() == "true"


def _governed(column: Column, spec: GovernedColumn | None) -> Column:
    """A live column with what a governance-only spec says about it on top."""
    if spec is None:
        # Not mentioned: tags and a mask the spec doesn't declare are reported
        # as unmanaged, like any other spec's; the comment stays the owner's.
        return replace(column, tags=(), removed_tags=())
    return replace(
        column,
        comment=spec.comment if spec.comment is not None else column.comment,
        tags=spec.tags,
        removed_tags=spec.removed_tags,
        mask=spec.mask,
    )


def sort_governance(obj: Securable) -> None:
    """Normalise what the catalog normalises, so equality means what it says.

    * The name in lower case: Unity Catalog stores catalog, schema, table and
      view names that way, whatever case they were written in. Comparing them any
      other way would make `Orders` in a spec a different table from the live
      `orders` — which, in a strict schema, plans dropping the real one.
      https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-names
    * Unordered maps sorted, so equality ignores the order they came in.
    """
    object.__setattr__(obj, "name", obj.name.lower())
    object.__setattr__(obj, "properties", tuple(sorted(obj.properties)))
    object.__setattr__(obj, "tags", tuple(sorted(obj.tags)))
    object.__setattr__(
        obj, "grants", tuple(sorted(obj.grants, key=lambda g: g.principal))
    )


@dataclass(frozen=True, slots=True)
class Table(Securable):
    """A Delta table in Unity Catalog.

    `properties` and `tags` are unordered maps, so they are stored sorted and
    compare regardless of the order they were written in. `cluster_by` and
    `columns` keep their order, because theirs is meaningful.
    """

    name: str
    columns: tuple[Column, ...]
    comment: str | None = None
    cluster_by: tuple[str, ...] = ()
    #: Automatic liquid clustering: Databricks picks the keys and may change
    #: them, so `cluster_by` is then what it chose — never compared.
    #: https://docs.databricks.com/aws/en/delta/clustering#automatic-liquid-clustering
    cluster_auto: bool = False
    #: Hive-style partition columns. In a spec, None leaves the table's
    #: partitioning as it is and () says it has none; on a live table, None is
    #: unpartitioned. Delta allows partitioning or clustering, not both.
    #: https://docs.databricks.com/aws/en/tables/partitions
    partitioned_by: tuple[str, ...] | None = None
    properties: tuple[tuple[str, str], ...] = ()
    tags: tuple[tuple[str, str], ...] = ()
    constraints: tuple[Constraint, ...] = ()
    grants: tuple[Grant, ...] = ()
    row_filter: RowFilter | None = None
    #: Reference data this table is loaded with. Compared through its digest,
    #: which a loaded table carries as a property — never row by row.
    seed: Seed | None = field(default=None, compare=False)
    #: The table's previous full name, while a rename is still to be applied.
    renamed_from: str | None = field(default=None, compare=False)
    #: What the spec says must not be there: `tags: {pii: null}`. Spec-only —
    #: a live object never has any — so they take no part in comparing.
    removed_properties: tuple[str, ...] = field(default=(), compare=False)
    removed_tags: tuple[str, ...] = field(default=(), compare=False)
    #: Who owns it in Unity Catalog. Only a spec that names an owner has it
    #: enforced; a live object always has one, so it takes no part in comparing.
    owner: str | None = field(default=None, compare=False)
    #: A governance-only spec's columns: a name with a mask, tags or a comment,
    #: and no type. Spec-only — `govern` folds them into the live columns.
    governed_columns: tuple[GovernedColumn, ...] = field(default=(), compare=False)
    #: Where the shape came from, when a spec took it from a data contract: the
    #: contract's path as the spec wrote it, and the object in it. Spec-only,
    #: and not state: the columns are what is compared, wherever they came from.
    from_contract: str | None = field(default=None, compare=False)
    contract_port: str | None = field(default=None, compare=False)
    #: What the contract says that didn't become part of the table — a
    #: relationship into another file — for `validate` to say as a warning.
    contract_notes: tuple[str, ...] = field(default=(), compare=False)

    def __post_init__(self) -> None:
        sort_governance(self)
        if self.renamed_from is not None:
            object.__setattr__(self, "renamed_from", self.renamed_from.lower())

    @property
    def governance_only(self) -> bool:
        """A spec that says who may see the table and nothing about its shape.

        It has no typed columns: the table is another tool's — dlt's, a
        notebook team's — and stevin only puts the tags, grants, masks, row
        filter and owner in place. Never claimed, reshaped or dropped.
        """
        return not self.columns

    def govern(self, live: Table) -> Table:
        """This governance-only spec, laid over the live table it governs.

        The result is an ordinary table — the live shape, with the spec's
        governance on top — so the differ compares it as it compares any
        table and finds only governance to change. What the spec doesn't
        mention is carried over from the live table rather than left blank,
        because a blank would read as "remove it": a comment the owner wrote,
        a mask the spec doesn't name, the properties, the clustering.

        Raises `KeyError` for a governed column the table doesn't have.
        """
        governed = {g.name.casefold(): g for g in self.governed_columns}
        missing = set(governed) - {c.name.casefold() for c in live.columns}
        if missing:
            raise KeyError(sorted(governed[m].name for m in missing)[0])
        columns = tuple(
            _governed(column, governed.get(column.name.casefold()))
            for column in live.columns
        )
        return replace(
            live,
            columns=columns,
            comment=self.comment if self.comment is not None else live.comment,
            tags=self.tags,
            removed_tags=self.removed_tags,
            grants=self.grants,
            row_filter=self.row_filter,
            owner=self.owner,
            governed_columns=(),
            # Spec-only hints a live table never has.
            seed=None,
            renamed_from=None,
            removed_properties=(),
        )

    def governance_spec(self) -> Table:
        """The governance-only spec that would govern this live table as it is:
        what `import` writes for a table another tool makes."""
        return Table(
            name=self.name,
            columns=(),
            tags=self.tags,
            grants=self.grants,
            row_filter=self.row_filter,
            governed_columns=tuple(
                GovernedColumn(column.name, tags=column.tags, mask=column.mask)
                for column in self.columns
                if column.tags or column.mask is not None
            ),
        )

    # -- lookups -----------------------------------------------------------
    def column(self, name: str) -> Column | None:
        """Look a column up the way Delta resolves one: ignoring case.

        Delta keeps the case a column was written in but won't hold two names
        that differ only by it, so a case-insensitive match is never ambiguous.
        """
        wanted = name.casefold()
        for candidate in self.columns:
            if candidate.name.casefold() == wanted:
                return candidate
        return None

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    @property
    def protected(self) -> bool:
        """Does anything here decide what a reader may see?"""
        return self.row_filter is not None or any(c.mask for c in self.columns)

    def primary_key(self) -> PrimaryKey | None:
        for constraint in self.constraints:
            if isinstance(constraint, PrimaryKey):
                return constraint
        return None

    def checks(self) -> tuple[Check, ...]:
        return tuple(c for c in self.constraints if isinstance(c, Check))

    def foreign_keys(self) -> tuple[ForeignKey, ...]:
        return tuple(c for c in self.constraints if isinstance(c, ForeignKey))


def default_foreign_key_name(table: str, key: ForeignKey) -> str:
    """Databricks requires a name; this is ours: `orders_customer_id_fk`."""
    return f"{table.split('.')[-1]}_{'_'.join(key.columns)}_fk"


def default_primary_key_name(table: Table) -> str:
    """Databricks requires every constraint to be named; this is our default."""
    return f"{table.short_name}_pk"


def type_at(table: Table, path: str) -> DataType | None:
    """The type at a nested path, or None if nothing lives there.

    Paths are Databricks' own: `amount`, `address.zip`, `lines.element.sku`,
    `by_code.key` / `by_code.value`.
    """
    parts = path.split(".")
    column = table.column(parts[0])
    if column is None:
        return None
    current: DataType = column.type
    for part in parts[1:]:
        match current:
            case Struct():
                member = current.field(part)
                if member is None:
                    return None
                current = member.type
            case Array(element, _) if part == "element":
                current = element
            case Map(key, _) if part == "key":
                current = key
            case Map(_, value) if part == "value":
                current = value
            case _:
                return None
    return current


def field_at(table: Table, path: str) -> Field | None:
    """The field at a nested path — a column, or a struct member inside one.

    Array elements and map keys/values are types, not fields, so they have no
    name, comment or nullability of their own and return None here.
    """
    parts = path.split(".")
    column = table.column(parts[0])
    if column is None or len(parts) == 1:
        return column
    parent = type_at(table, ".".join(parts[:-1]))
    return parent.field(parts[-1]) if isinstance(parent, Struct) else None

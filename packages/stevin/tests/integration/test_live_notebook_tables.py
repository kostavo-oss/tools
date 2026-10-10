"""A table a notebook writes into — against a real workspace.

The loop `docs/tables-your-notebooks-write.md` describes, end to end: a spec
declares the table, stevin creates it, a notebook writes to it and widens it,
`drift` shows the new column, `adopt` puts it into the spec, and the next plan
is empty. The rows and the ownership marker are still there at the end.

The notebook is simulated through the warehouse. An append with schema evolution
(`mergeSchema`) leaves two things behind: rows, and a new nullable column at the
end of the table. An `INSERT` and an `ALTER TABLE … ADD COLUMN` leave the same.
https://docs.databricks.com/aws/en/delta/update-schema
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from stevin.adopt import adopt
from stevin.executor import Executor
from stevin.history import MemoryHistory
from stevin.introspect import Introspector, WarehouseRunner
from stevin.loader import LoadedSpec, load_spec_text
from stevin.model.plan import Plan
from stevin.planning import plan_tables
from stevin.sql import quote_qualified

pytestmark = pytest.mark.integration

#: A principal to grant to. Every account has `account users`; a workspace that
#: doesn't can name another.
PRINCIPAL = os.environ.get("STEVIN_TEST_PRINCIPAL", "account users")

SPEC = """\
# Sensor readings, appended by the ingest notebook
table: ${catalog}.readings
comment: One row per reading
cluster_by: [taken_at]

grants:
  - principal: ${principal}        # who may read it
    privileges: [SELECT]

columns:
  - name: reading_id               # the key the notebook merges on
    type: bigint
    nullable: false
  - {name: taken_at, type: timestamp}
  - {name: value, type: double}

constraints:
  - primary_key: {columns: [reading_id], name: readings_pk}
"""


def test_a_notebooks_write_is_seen_and_adopted(
    runner: WarehouseRunner, introspector: Introspector, schema: str, tmp_path: Path
) -> None:
    path = tmp_path / "readings.yml"
    path.write_text(SPEC, encoding="utf-8")
    variables = {"catalog": schema, "principal": PRINCIPAL}

    def spec() -> LoadedSpec:
        text = path.read_text(encoding="utf-8")
        return LoadedSpec(path, load_spec_text(text, path, variables))

    def planned() -> Plan:
        return plan_tables(
            [spec().table], introspector, target="integration", tool_version="0"
        )

    def changes(plan: Plan) -> list[tuple[str, str]]:
        return [(str(c.kind), str(c.path)) for d in plan.diffs for c in d.changes]

    # stevin makes the table: the key, the clustering, the grant.
    result = Executor(runner, introspector, MemoryHistory()).apply(planned())
    assert result.ok, result.error
    assert planned().empty, changes(planned())

    # The notebook appends, then appends again with a column the table lacks.
    name = quote_qualified(f"{schema}.readings")
    runner.query(f"INSERT INTO {name} VALUES (1, TIMESTAMP '2026-10-01 08:00:00', 20.5)")
    runner.query(f"ALTER TABLE {name} ADD COLUMNS (sensor STRING)")
    runner.query(
        f"INSERT INTO {name} VALUES (2, TIMESTAMP '2026-10-01 09:00:00', 21.0, 'north')"
    )

    # Drift is the new column, and nothing else: rows are not drift.
    drifted = planned()
    print(f"drift: {changes(drifted)}")
    assert not drifted.empty, "the plan should have seen the notebook's column"
    assert [where for _, where in changes(drifted)] == ["sensor"], changes(drifted)

    # Adopt writes the column into the file, and keeps what only a file says.
    live = introspector.table(f"{schema}.readings")
    assert live is not None
    adoption = adopt(spec(), live.table, variables=variables)
    print("adopt: " + "; ".join(adoption.notes))
    assert adoption.changed
    assert adoption.remaining == ()
    assert adoption.notes == ("+ columns: sensor string",), adoption.notes
    adoption.write()

    after = path.read_text(encoding="utf-8")
    assert "# Sensor readings, appended by the ingest notebook" in after
    assert "# the key the notebook merges on" in after
    assert "# who may read it" in after
    assert "${catalog}" in after
    assert "${principal}" in after
    assert "sensor" in after
    assert planned().empty, changes(planned())

    # Nothing stevin did touched the data, and the table is still its own.
    rows = runner.query(f"SELECT reading_id, sensor FROM {name} ORDER BY reading_id")
    assert [(row["reading_id"], row["sensor"]) for row in rows] == [
        ("1", None),
        ("2", "north"),
    ]
    kept = introspector.table(f"{schema}.readings")
    assert kept is not None
    assert kept.table.managed, "the ownership marker is still on the table"

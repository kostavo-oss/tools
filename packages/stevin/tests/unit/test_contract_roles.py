"""A contract's roles, read into grants.

A data contract says who may use its data: `roles`, each a name and an access
level. A project that says in `stevin.yml` who each role is on a target gets
them as grants on every table read from that contract. A project that doesn't
say reads the contract as it always did.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from helpers import plan_against
from stevin.cli import app
from stevin.differ import diff, unmanaged
from stevin.loader import Project, SpecError, SpecErrors, dump_spec, validate_table
from stevin.model.table import Grant, Table

runner = CliRunner()

SHAPE = """\
apiVersion: v3.1.0
kind: DataContract
id: 2f9e3c1a-5b77-4c1e-9f0e-6d1c7a2b8e44
version: 2.0.0
schema:
  - name: orders
    properties:
      - {name: order_id, logicalType: integer, primaryKey: true}
      - {name: amount, logicalType: number}
"""
ROLES = """\
roles:
  - role: consumer
    access: read
    description: Anyone who reports on orders
    firstLevelApprovers: Sales lead
  - {role: steward, access: Write, id: steward_role}
"""
CONTRACT = SHAPE + ROLES

CONFIG = """\
version: 1
specs: [tables]
targets:
  dev:
    vars: {catalog: dev, analysts: dev-analysts}
  prod:
    vars: {catalog: prod, analysts: analysts}
"""
MAP = """\
contract_roles:
  consumer: ${analysts}
  steward: [data-stewards, "${analysts}"]
"""
SPEC = """\
table: ${catalog}.sales.orders
from_contract: ../contracts/orders.odcs.yaml
"""
CONTRACT_PATH = "../contracts/orders.odcs.yaml"


def project(
    tmp_path: Path,
    config: str = CONFIG + MAP,
    contract: str = CONTRACT,
    spec: str = SPEC,
) -> Project:
    (tmp_path / "contracts").mkdir(exist_ok=True)
    (tmp_path / "contracts" / "orders.odcs.yaml").write_text(contract, encoding="utf-8")
    (tmp_path / "tables").mkdir(exist_ok=True)
    (tmp_path / "tables" / "orders.yml").write_text(
        textwrap.dedent(spec), encoding="utf-8"
    )
    (tmp_path / "stevin.yml").write_text(config, encoding="utf-8")
    return Project.load(tmp_path / "stevin.yml")


def orders(tmp_path: Path, *, target: str = "dev", **files: str) -> Table:
    found = project(tmp_path, **files)
    [loaded] = found.load_specs(found.target(target)).files
    assert isinstance(loaded.table, Table)
    return loaded.table


def refused(tmp_path: Path, **files: str) -> str:
    found = project(tmp_path, **files)
    with pytest.raises(SpecErrors) as caught:
        found.load_specs(found.target("dev"))
    [error] = caught.value.errors
    return str(error)


# ---------------------------------------------------------------------------
# with the map
# ---------------------------------------------------------------------------


def test_a_role_becomes_a_grant_to_the_principals_the_project_names(
    tmp_path: Path,
) -> None:
    # RULES.md: SPEC-4.
    """`read` is SELECT, `write` is SELECT and MODIFY, whatever the case. Who a
    role is comes from `stevin.yml`, with the target's variables in, so dev and
    prod read one contract and grant to their own groups."""
    dev = orders(tmp_path)
    assert dev.grants == (
        Grant("data-stewards", ("MODIFY", "SELECT")),
        Grant("dev-analysts", ("MODIFY", "SELECT")),
    )
    prod = orders(tmp_path, target="prod")
    assert prod.grants_map() == {
        "analysts": ("MODIFY", "SELECT"),
        "data-stewards": ("MODIFY", "SELECT"),
    }
    assert not validate_table(dev, "x"), "nothing to say: the roles were read"

    _, plan = plan_against(dev)
    assert [step.sql for step in plan.steps if "GRANT" in (step.sql or "")] == [
        "GRANT MODIFY, SELECT ON TABLE `dev`.`sales`.`orders` TO `data-stewards`",
        "GRANT MODIFY, SELECT ON TABLE `dev`.`sales`.`orders` TO `dev-analysts`",
    ]


def test_a_roles_grants_join_the_specs_own(tmp_path: Path) -> None:
    """One list: a principal the spec and a role both name gets what the two
    give together, once; the others are as each wrote them."""
    spec = SPEC + (
        "grants:\n"
        "  - {principal: dev-analysts, privileges: [SELECT]}\n"
        "  - {principal: etl, privileges: [MODIFY]}\n"
    )
    config = CONFIG + "contract_roles:\n  consumer: ${analysts}\n  steward: []\n"
    found = orders(tmp_path, config=config, spec=spec)
    assert found.grants == (
        Grant("dev-analysts", ("SELECT",)),
        Grant("etl", ("MODIFY",)),
    )
    steward = CONFIG + "contract_roles:\n  consumer: []\n  steward: ${analysts}\n"
    found = orders(tmp_path, config=steward, spec=spec)
    assert found.grants_map() == {
        "dev-analysts": ("MODIFY", "SELECT"),
        "etl": ("MODIFY",),
    }


def test_a_role_mapped_to_nobody_gives_no_grant(tmp_path: Path) -> None:
    """`[]` is an answer: nobody on this target. It holds for a role whose
    access stevin doesn't know, too, which is how such a role is left out."""
    contract = SHAPE + "roles:\n  - {role: consumer, access: read}\n  - role: owner\n"
    contract += "  - {role: auditor, access: audit}\n"
    config = CONFIG + "contract_roles: {consumer: [], owner: [], auditor: []}\n"
    found = orders(tmp_path, config=config, contract=contract)
    assert found.grants == ()
    assert not validate_table(found, "x")
    _, plan = plan_against(found)
    assert not [step for step in plan.steps if "GRANT" in (step.sql or "")]


def test_a_role_taken_out_of_the_contract_is_a_grant_taken_out_of_a_spec(
    tmp_path: Path,
) -> None:
    # RULES.md: SPEC-4.
    """Its principal is no longer named, so it is left alone and said as
    unmanaged: nothing is revoked. A role whose access goes from write to read
    still names its principal, and that one loses MODIFY."""
    before = orders(tmp_path)
    _, settled = plan_against(before, before)
    assert not settled.steps, "the table as the first contract left it"

    gone = SHAPE + "roles:\n  - {role: consumer, access: read}\n"
    after = orders(tmp_path, contract=gone)
    assert after.grants == (Grant("dev-analysts", ("SELECT",)),)
    changes = diff(after, before)
    assert [(c.kind, c.path, c.before) for c in changes] == [
        ("revoke", "dev-analysts", ("MODIFY",))
    ]
    assert "grants to data-stewards" in unmanaged(after, before)

    by_hand = SPEC + "grants:\n  - {principal: dev-analysts, privileges: [SELECT]}\n"
    same = orders(tmp_path, config=CONFIG, contract=SHAPE, spec=by_hand)
    assert diff(same, before) == changes, "as a spec that stops naming the grant"


# ---------------------------------------------------------------------------
# without the map
# ---------------------------------------------------------------------------


def test_without_the_key_roles_are_not_read_and_validate_says_so_once(
    tmp_path: Path,
) -> None:
    # RULES.md: SPEC-5.
    """The same table and the same plan as a contract with no roles at all, and
    one warning that names the roles and the key."""
    with_roles = orders(tmp_path, config=CONFIG)
    without = orders(tmp_path, config=CONFIG, contract=SHAPE)
    assert with_roles == without
    assert with_roles.grants == ()
    _, plan = plan_against(with_roles)
    _, plain = plan_against(without)
    assert [step.sql for step in plan.steps] == [step.sql for step in plain.steps]

    assert not validate_table(without, "x")
    [note] = validate_table(with_roles, "x")
    assert note.severity == "warning"
    assert note.message == (
        f"{CONTRACT_PATH} names roles (consumer, steward) and stevin makes no grant "
        "from them: it reads a contract's roles only when stevin.yml says who they "
        "are, under `contract_roles:`"
    )


def test_a_contract_stevin_could_not_grant_from_still_reads_without_the_key(
    tmp_path: Path,
) -> None:
    """Roles nobody asked stevin to read are not checked: no access, an access
    it doesn't know, not even a list."""
    for roles in (
        "roles:\n  - role: owner\n  - {role: auditor, access: audit}\n  - nonsense\n",
        "roles: everyone\n",
    ):
        found = orders(tmp_path, config=CONFIG, contract=SHAPE + roles)
        assert found.grants == ()
        assert [d.severity for d in validate_table(found, "x")] == ["warning"]


def test_validate_passes_with_the_note_and_fails_on_an_unmapped_role(
    tmp_path: Path,
) -> None:
    project(tmp_path, config=CONFIG)
    config = str(tmp_path / "stevin.yml")
    result = runner.invoke(app, ["validate", "--config", config, "-t", "dev"])
    assert result.exit_code == 0, result.output
    assert result.output.count("names roles (consumer, steward)") == 1

    project(tmp_path, config=CONFIG + "contract_roles: {consumer: analysts}\n")
    result = runner.invoke(app, ["validate", "--config", config, "-t", "dev"])
    assert result.exit_code == 1
    assert "names the role 'steward'" in " ".join(result.output.split())


# ---------------------------------------------------------------------------
# what is refused, and how it is said
# ---------------------------------------------------------------------------


def test_a_role_the_map_does_not_name_is_refused(tmp_path: Path) -> None:
    # RULES.md: SPEC-5.
    """A grant nobody chose is the unsafe side, and so is a role that quietly
    gets nothing: the error names the role, the contract and the key."""
    message = refused(tmp_path, config=CONFIG + "contract_roles: {consumer: analysts}\n")
    assert message.startswith(f"{(tmp_path / 'tables' / 'orders.yml').as_posix()}:2:")
    assert message.endswith(
        f"{CONTRACT_PATH} names the role 'steward', and `contract_roles:` in "
        "stevin.yml doesn't say who that is. Add `steward:` there with its groups, "
        "or with `[]` for nobody"
    )
    assert "names the role 'consumer'" in refused(
        tmp_path, config=CONFIG + "contract_roles: {}\n"
    ), "an empty map answers for no role"


@pytest.mark.parametrize(
    ("roles", "message"),
    [
        (
            "roles:\n  - role: consumer\n",
            f"{CONTRACT_PATH}: the role 'consumer' has no `access`, so stevin can't "
            "tell what to grant (it knows: read, write). Give it one in the "
            "contract, or map the role to `[]` under `contract_roles:`",
        ),
        (
            "roles:\n  - {role: consumer, access: 3}\n",
            "the role 'consumer' has no `access`",
        ),
        (
            "roles:\n  - {role: consumer, access: Admin}\n",
            f"{CONTRACT_PATH}: the role 'consumer' has access 'Admin', and stevin "
            "knows only: read, write. Map the role to `[]` under `contract_roles:` "
            "and grant it in the spec",
        ),
        (
            "roles:\n  - {access: read}\n",
            f"{CONTRACT_PATH}: `roles` must be a list of roles, each with a `role` name",
        ),
        ("roles: everyone\n", "`roles` must be a list of roles"),
    ],
)
def test_a_role_stevin_cannot_read_into_a_grant_is_refused(
    tmp_path: Path, roles: str, message: str
) -> None:
    # RULES.md: SPEC-5.
    found = refused(
        tmp_path,
        config=CONFIG + "contract_roles: {consumer: analysts}\n",
        contract=SHAPE + roles,
    )
    assert found.endswith(message) or message in found
    assert "tables/orders.yml:2:" in found, "on the from_contract line, as the others"


def test_what_the_map_itself_must_say(tmp_path: Path) -> None:
    """A reference with no value for the target, a principal that comes out
    empty, and a project that hands grants to another tool: each is refused in
    `stevin.yml`, on its own line."""
    message = refused(tmp_path, config=CONFIG + "contract_roles: {consumer: '${nope}'}\n")
    assert "stevin.yml:8:18" in message
    assert (
        "contract_roles, role 'consumer', for target 'dev': undefined variable ${nope}"
        in message
    )

    blank = CONFIG.replace("analysts: dev-analysts", 'analysts: ""') + MAP
    message = refused(tmp_path, config=blank)
    assert message.endswith(
        "contract_roles, role 'consumer': ${analysts} is empty for target 'dev'. "
        "Name a principal, or write `[]` for nobody"
    )

    with pytest.raises(SpecError, match="has an empty principal") as caught:
        project(tmp_path, config=CONFIG + "contract_roles: {consumer: ['']}\n")
    assert "stevin.yml:8" in str(caught.value)

    handed = CONFIG + "manage: {grants: false}\n" + MAP
    with pytest.raises(SpecError, match="Take one of the two out") as caught:
        project(tmp_path, config=handed)
    assert "`manage.grants: false` says grants are set somewhere else" in str(
        caught.value
    )


# ---------------------------------------------------------------------------
# what a role's grant is not
# ---------------------------------------------------------------------------


def test_a_roles_grant_is_never_written_as_the_specs_own(tmp_path: Path) -> None:
    # RULES.md: SPEC-4.
    """`dump_spec` writes what the spec said: a role's grant is read from the
    contract each time, so taking the role out there takes it out here.
    (`adopt` refuses a spec with `from_contract` before it writes anything.)"""
    spec = SPEC + "grants:\n  - {principal: etl, privileges: [MODIFY]}\n"
    found = orders(tmp_path, spec=spec)
    assert set(found.grants_map()) == {"data-stewards", "dev-analysts", "etl"}
    written = yaml.safe_load(dump_spec(found))
    assert written["grants"] == [{"principal": "etl", "privileges": ["MODIFY"]}]

    only_roles = orders(tmp_path)
    assert only_roles.grants
    assert "grants" not in yaml.safe_load(dump_spec(only_roles))


def test_a_spec_without_a_contract_is_as_it_was(tmp_path: Path) -> None:
    """The map is about contracts. A spec that points at none, and a
    governance-only one, get no grant from it."""
    spec = "table: ${catalog}.raw.customers\ngrants:\n"
    spec += "  - {principal: etl, privileges: [SELECT]}\n"
    found = orders(tmp_path, spec=spec)
    assert found.governance_only
    assert found.grants == (Grant("etl", ("SELECT",)),)
    assert found.own_grants is None

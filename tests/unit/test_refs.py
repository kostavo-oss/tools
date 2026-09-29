"""References: where they may stand, and what they answer."""

from typing import Any

import pytest

from sluis.config import Loc
from sluis.model import Secret
from sluis.refs import Position, Ref, RefError, Scope, Unknown, check, parse, resolve

LOC = Loc("sluis.yml", 3, 7)

CONFIG: dict[str, Any] = {
    "bundle": {"name": "shop", "target": "dev"},
    "variables": {"catalog": {"default": "dev", "value": "dev"}},
    "resources": {"jobs": {"nightly": {"name": "[dev jane] nightly"}}},
    "workspace": {"current_user": {"short_name": "jane"}},
}
DEPLOYED: dict[str, Any] = {
    "resources": {
        "jobs": {"nightly": {"id": "662311427418745", "url": "https://x/jobs/1"}}
    }
}


def scope(**kwargs: Any) -> Scope:
    return Scope(CONFIG, **kwargs)


# -- shape --------------------------------------------------------------------


def test_finds_every_reference_in_a_string() -> None:
    refs = parse("${var.catalog}.ml.${steps.model.name}", LOC)
    assert refs == (Ref(("var", "catalog")), Ref(("steps", "model", "name")))


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("${vars.catalog}", "unknown namespace `vars`"),
        ("${var}", "a variable is `${var.<name>}`"),
        ("${var.a.b}", "a variable is `${var.<name>}`"),
        ("${resources.jobs.nightly}", "a resource field is"),
        ("${steps.model}", "a step's output is"),
        ("${var..x}", "is not a reference"),
    ],
)
def test_a_malformed_reference_says_what_is_expected(text: str, message: str) -> None:
    with pytest.raises(RefError, match=message.replace("$", r"\$").replace(".", r"\.")):
        parse(text, LOC)


# -- where it stands ----------------------------------------------------------

PRE = Position("step `model`", "pre", earlier=(), later=("model", "tables"), this="model")
POST = Position(
    "step `tables`",
    "post",
    earlier=("model",),
    later=("tables",),
    fed=frozenset({"v"}),
    this="tables",
)


def test_a_step_may_use_an_earlier_steps_outputs() -> None:
    check(Ref(("steps", "model", "version")), POST, LOC)


def test_a_step_may_not_use_a_later_steps_outputs() -> None:
    later = Position("step `a`", "pre", earlier=(), later=("a", "b"), this="a")
    with pytest.raises(RefError, match="step `b` runs after step `a`"):
        check(Ref(("steps", "b", "x")), later, LOC)


def test_a_step_may_not_use_its_own_outputs() -> None:
    with pytest.raises(RefError, match="its own outputs"):
        check(Ref(("steps", "tables", "x")), POST, LOC)


def test_an_unknown_step_is_an_error() -> None:
    with pytest.raises(RefError, match="there is no step `nope`"):
        check(Ref(("steps", "nope", "x")), POST, LOC)


def test_a_deployed_id_is_for_post_steps_only() -> None:
    check(Ref(("resources", "jobs", "nightly", "id")), POST, LOC)
    with pytest.raises(RefError, match="known only once the bundle has deployed"):
        check(Ref(("resources", "jobs", "nightly", "id")), PRE, LOC)
    check(Ref(("resources", "jobs", "nightly", "name")), PRE, LOC)


def test_a_pre_step_may_not_read_a_variable_sluis_sets() -> None:
    fed = Position("step `a`", "pre", (), ("a",), fed=frozenset({"v"}), this="a")
    with pytest.raises(RefError, match="set by bundle_vars"):
        check(Ref(("var", "v")), fed, LOC)
    check(Ref(("var", "v")), POST, LOC)


# -- answers ------------------------------------------------------------------


def test_a_whole_reference_keeps_its_type() -> None:
    answer = resolve(
        "${steps.model.version}", scope(outputs={"model": {"version": 14}}), LOC
    )
    assert answer == 14


def test_references_in_a_longer_string_are_formatted_in() -> None:
    assert resolve("${var.catalog}.ml.churn", scope(), LOC) == "dev.ml.churn"
    assert (
        resolve("${workspace.current_user.short_name}-${bundle.target}", scope(), LOC)
        == "jane-dev"
    )


def test_a_string_without_references_is_itself() -> None:
    assert resolve("plain", scope(), LOC) == "plain"


def test_a_missing_variable_is_an_error_not_an_empty_string() -> None:
    with pytest.raises(RefError, match="the bundle has no variable `schema`"):
        resolve("${var.schema}", scope(), LOC)


def test_a_resource_field_comes_from_the_resolved_config() -> None:
    assert resolve("${resources.jobs.nightly.name}", scope(), LOC) == "[dev jane] nightly"
    with pytest.raises(RefError, match=r"there is no `resources\.jobs\.weekly`"):
        resolve("${resources.jobs.weekly.name}", scope(), LOC)


def test_a_deployed_id_comes_from_the_summary() -> None:
    answer = resolve("${resources.jobs.nightly.id}", scope(deployed=DEPLOYED), LOC)
    assert answer == "662311427418745"


def test_the_id_of_something_this_deploy_creates_is_unknown() -> None:
    answer = resolve(
        "run ${resources.jobs.nightly.id}",
        scope(deployed=DEPLOYED, created=frozenset({"jobs.nightly"})),
        LOC,
    )
    assert answer == Unknown("resources.jobs.nightly is created by this deploy")


def test_the_id_of_something_never_deployed_is_unknown() -> None:
    answer = resolve("${resources.jobs.weekly.id}", scope(deployed=DEPLOYED), LOC)
    assert answer == Unknown("resources.jobs.weekly hasn't been deployed yet")


def test_a_missing_output_names_the_ones_there_are() -> None:
    with pytest.raises(RefError, match=r"has no output `version` \(its outputs: name\)"):
        resolve("${steps.model.version}", scope(outputs={"model": {"name": "x"}}), LOC)


def test_the_output_of_a_deferred_step_is_unknown() -> None:
    answer = resolve(
        "${steps.model.version}",
        scope(outputs={"model": {}}, deferred={"model": "later"}),
        LOC,
    )
    assert answer == Unknown("step `model` is decided at apply")


def test_a_pending_variable_is_unknown() -> None:
    answer = resolve("${var.catalog}", scope(pending={"catalog": "set at apply"}), LOC)
    assert answer == Unknown("set at apply")


def test_the_environment_is_read_or_left_as_written() -> None:
    env = scope(env={"TOKEN": "s3cret"})
    assert resolve("Bearer ${env.TOKEN}", env, LOC) == "Bearer s3cret"
    assert (
        resolve("Bearer ${env.TOKEN}", env, LOC, redact_env=True) == "Bearer ${env.TOKEN}"
    )
    with pytest.raises(RefError, match="`NOPE` isn't set"):
        resolve("${env.NOPE}", env, LOC)


def test_a_secret_makes_the_whole_string_one() -> None:
    answer = resolve(
        "Bearer ${steps.login.token}",
        scope(outputs={"login": {"token": Secret("t0k")}}),
        LOC,
    )
    assert isinstance(answer, Secret)
    assert answer.reveal() == "Bearer t0k"
    assert str(answer) == "***"

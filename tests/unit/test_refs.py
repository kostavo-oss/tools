"""References: where they may stand, and what they answer."""

import pytest

from lely.config import Loc
from lely.model import Output, Secret
from lely.refs import (
    Above,
    Given,
    Position,
    Ref,
    RefError,
    Scope,
    Unknown,
    check,
    check_step,
    match,
    parse,
    resolve,
)

LOC = Loc("lely.yml", 3, 7)

#: What a bundle step declares, as far as these tests need it.
BUNDLE = (
    Output("target"),
    Output("var.<name>"),
    Output("workspace.<field>"),
    Output("resources.<type>.<key>.<field>"),
    Output("resources.<type>.<key>.id", "exists"),
)
MODEL = (Output("version"),)
SEED = (Output("count", "run"),)


# -- shape --------------------------------------------------------------------


def test_finds_every_reference_in_a_string() -> None:
    refs = parse("${steps.app.var.catalog}.ml.${steps.model.name}", LOC)
    assert refs == (
        Ref(("steps", "app", "var", "catalog")),
        Ref(("steps", "model", "name")),
    )
    assert (refs[0].step, refs[0].output) == ("app", ("var", "catalog"))


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("${vars.catalog}", "unknown namespace `vars`; expected one of steps, env."),
        ("${env}", "an environment variable is `${env.<NAME>}`"),
        ("${env.A.B}", "an environment variable is `${env.<NAME>}`"),
        ("${steps.model}", "a step's output is `${steps.<name>.<output>}`"),
        ("${steps..x}", "is not a reference"),
    ],
)
def test_a_malformed_reference_says_what_is_expected(text: str, message: str) -> None:
    with pytest.raises(RefError, match=message.replace("$", r"\$").replace(".", r"\.")):
        parse(text, LOC)


@pytest.mark.parametrize(
    ("text", "now"),
    [
        ("${var.catalog}", "${steps.app.var.catalog}"),
        ("${resources.jobs.nightly.id}", "${steps.app.resources.jobs.nightly.id}"),
        ("${workspace.host}", "${steps.app.workspace.host}"),
    ],
)
def test_what_a_step_above_gives_is_written_with_its_step(text: str, now: str) -> None:
    """A bundle's own file says `${var.catalog}`; here every reference names the
    step its value comes from, and the error names the step that gives it."""
    above = {"model": Above(MODEL), "app": Above(BUNDLE), "lost": Above(None)}
    with pytest.raises(RefError) as caught:
        parse(text, LOC, above)
    said = str(caught.value)
    assert "unknown namespace" in said
    assert f"Step `app` gives `{text[2:-1]}`" in said
    assert "every reference names the step its value comes from" in said
    assert f"write `{now}`" in said


@pytest.mark.parametrize("above", [None, {"model": Above(MODEL)}])
def test_no_step_is_named_that_isnt_there_to_give_it(
    above: dict[str, Above] | None,
) -> None:
    """`${var.x}` used to answer "write `${steps.<bundle step>.var.x}`" in a
    project with no bundle step at all."""
    with pytest.raises(RefError) as caught:
        parse("${var.catalog}", LOC, above)
    assert str(caught.value) == (
        "lely.yml:3:7: `${var.catalog}`: unknown namespace `var`; expected one of "
        "steps, env. For a literal `${var.catalog}`, write `$${var.catalog}`."
    )


# -- a literal `${…}` ------------------------------------------------------------


def test_a_doubled_dollar_is_a_literal_and_no_reference() -> None:
    """As Terraform and Compose have it. A shell's own `${HOME}` in a command
    could not be written at all: it failed as an unknown namespace, and so did
    `\\${HOME}`."""
    assert parse("echo $${HOME} $${not a name}", LOC) == ()
    assert resolve("echo $${HOME}", scope(), LOC) == "echo ${HOME}"
    assert resolve("$${steps.app.target}", scope(), LOC) == "${steps.app.target}"
    # beside a reference, each is read for what it is
    assert parse("$${A}-${steps.app.target}", LOC) == (Ref(("steps", "app", "target")),)
    assert resolve("$${A}-${steps.app.target}", scope(), LOC) == "${A}-dev"
    # read from the left: a dollar before the two is only a dollar
    assert resolve("$$${HOME}", scope(), LOC) == "$${HOME}"
    assert resolve("costs $$5 and $5", scope(), LOC) == "costs $$5 and $5"


@pytest.mark.parametrize("text", ["${HOME}", "\\${HOME}", "${HOME:-/root}", "${a b}"])
def test_what_is_no_reference_says_how_to_write_it_out(text: str) -> None:
    with pytest.raises(RefError) as caught:
        parse(text, LOC)
    body = text[text.index("${") + 2 : -1]
    assert f"For a literal `${{{body}}}`, write `$${{{body}}}`." in str(caught.value)


# -- which declared output ------------------------------------------------------


def test_a_plain_name_matches_and_the_rest_walks_into_the_value() -> None:
    found = match(MODEL, ("version", "major"))
    assert found is not None
    assert (found.name, found.rest) == ("version", ("major",))


def test_a_shape_stands_for_one_part_each() -> None:
    found = match(BUNDLE, ("resources", "jobs", "nightly", "name"))
    assert found is not None
    assert found.output.name == "resources.<type>.<key>.<field>"
    assert found.name == "resources.jobs.nightly.name"
    assert match(BUNDLE, ("resources", "jobs", "nightly")) is None
    assert match(BUNDLE, ("nope",)) is None


def test_the_most_literal_declaration_wins() -> None:
    found = match(BUNDLE, ("resources", "jobs", "nightly", "id"))
    assert found is not None
    assert found.output.known == "exists"


# -- where it stands ----------------------------------------------------------

ABOVE = {"model": Above(MODEL), "app": Above(BUNDLE), "seed": Above(SEED, ("dev",))}
HERE = Position(this="tables", above=ABOVE, below=("backfill",))


def test_a_step_may_use_the_outputs_of_a_step_above() -> None:
    assert check(Ref(("steps", "model", "version")), HERE, LOC) == MODEL[0]
    assert check(Ref(("env", "TOKEN")), HERE, LOC) is None


def test_a_reference_down_the_list_says_to_move_it() -> None:
    with pytest.raises(RefError) as caught:
        check(Ref(("steps", "backfill", "x")), HERE, LOC)
    assert "step `backfill` is listed below step `tables`" in str(caught.value)
    assert "move `backfill` up, or `tables` down" in str(caught.value)


def test_a_step_may_not_use_its_own_outputs() -> None:
    with pytest.raises(RefError, match="its own outputs"):
        check(Ref(("steps", "tables", "x")), HERE, LOC)


def test_an_unknown_step_is_an_error() -> None:
    with pytest.raises(RefError, match="there is no step `nope`"):
        check(Ref(("steps", "nope", "x")), HERE, LOC)


def test_an_output_the_plugin_doesnt_declare_is_an_error() -> None:
    with pytest.raises(RefError) as caught:
        check(Ref(("steps", "model", "verison")), HERE, LOC)
    assert "step `model` gives no output `verison`; it gives: version" in str(
        caught.value
    )
    with pytest.raises(RefError, match="gives no output `resources.jobs`"):
        check(Ref(("steps", "app", "resources", "jobs")), HERE, LOC)


def test_a_step_whose_plugin_wasnt_found_isnt_checked_twice() -> None:
    position = Position(this="x", above={"broken": Above(None)})
    assert check(Ref(("steps", "broken", "anything")), position, LOC) is None


def test_a_step_for_fewer_targets_cant_feed_one_for_more() -> None:
    with pytest.raises(RefError) as caught:
        check(Ref(("steps", "seed", "count")), HERE, LOC)
    assert "step `seed` runs only for dev" in str(caught.value)
    assert "step `tables` also runs for every other target" in str(caught.value)
    wider = Position(this="tables", above=ABOVE, targets=("dev", "prod"))
    with pytest.raises(RefError, match="also runs for prod"):
        check(Ref(("steps", "seed", "count")), wider, LOC)
    same = Position(this="tables", above=ABOVE, targets=("dev",))
    assert check(Ref(("steps", "seed", "count")), same, LOC) == SEED[0]


def test_a_named_step_follows_the_same_rules() -> None:
    assert check_step("app", HERE, "lely.yml:1:1: `app`") is ABOVE["app"]
    with pytest.raises(RefError, match="is listed below"):
        check_step("backfill", HERE, "lely.yml:1:1: `backfill`")


# -- answers ------------------------------------------------------------------

APP = Given(
    BUNDLE,
    outputs={
        "target": "dev",
        "var.catalog": "dev",
        "workspace.current_user": {"short_name": "jane"},
        "resources.jobs.nightly.name": "[dev jane] nightly",
        "resources.jobs.nightly.id": "662311427418745",
        "resources.jobs.weekly.name": "weekly",
    },
    later=frozenset({"resources.jobs.weekly.id"}),
)


def scope(**steps: Given) -> Scope:
    return Scope({"app": APP, **steps}, env={"TOKEN": "s3cret"})


def test_a_whole_reference_keeps_its_type() -> None:
    answer = resolve(
        "${steps.model.version}", scope(model=Given(MODEL, {"version": 14})), LOC
    )
    assert answer == 14


def test_references_in_a_longer_string_are_formatted_in() -> None:
    assert resolve("${steps.app.var.catalog}.ml.churn", scope(), LOC) == "dev.ml.churn"
    assert (
        resolve(
            "${steps.app.workspace.current_user.short_name}-${steps.app.target}",
            scope(),
            LOC,
        )
        == "jane-dev"
    )


def test_a_string_without_references_is_itself() -> None:
    assert resolve("plain", scope(), LOC) == "plain"


def test_a_value_that_exists_is_answered() -> None:
    answer = resolve("${steps.app.resources.jobs.nightly.id}", scope(), LOC)
    assert answer == "662311427418745"


def test_a_value_still_to_come_is_unknown_and_named() -> None:
    answer = resolve("run ${steps.app.resources.jobs.weekly.id}", scope(), LOC)
    assert answer == Unknown("app.resources.jobs.weekly.id")


def test_a_name_neither_given_nor_promised_is_an_error() -> None:
    with pytest.raises(RefError) as caught:
        resolve("${steps.app.resources.jobs.monthly.id}", scope(), LOC)
    assert "step `app` has no `resources.jobs.monthly.id`" in str(caught.value)
    assert "(it has: resources.jobs.nightly.id, resources.jobs.weekly.id)" in str(
        caught.value
    )
    with pytest.raises(RefError, match="has no `var.schema`"):
        resolve("${steps.app.var.schema}", scope(), LOC)


def test_a_plain_output_that_exists_only_after_apply_is_unknown() -> None:
    made = Given((Output("id", "exists"),))
    assert resolve("${steps.wh.id}", scope(wh=made), LOC) == Unknown("wh.id")


def test_an_output_of_every_run_is_never_known_at_plan() -> None:
    assert resolve("${steps.seed.count}", scope(seed=Given(SEED)), LOC) == Unknown(
        "seed.count"
    )


def test_a_plan_that_withholds_what_it_declared_is_an_error() -> None:
    with pytest.raises(RefError, match="declares `version` as known at plan"):
        resolve("${steps.model.version}", scope(model=Given(MODEL)), LOC)


def test_nothing_a_waiting_step_gives_is_known() -> None:
    waiting = Given(MODEL, planned=False)
    assert resolve("${steps.model.version}", scope(model=waiting), LOC) == Unknown(
        "model.version"
    )


def test_what_is_still_missing_after_the_step_ran_will_not_come() -> None:
    ran = Given(SEED, applied=True)
    with pytest.raises(RefError, match="has run and still gives no `count`"):
        resolve("${steps.seed.count}", scope(seed=ran), LOC)


def test_walking_past_the_value_is_an_error() -> None:
    with pytest.raises(
        RefError, match=r"there is no `steps\.app\.workspace\.current_user\.nope`"
    ):
        resolve("${steps.app.workspace.current_user.nope}", scope(), LOC)


def test_the_environment_is_a_secret() -> None:
    answer = resolve("Bearer ${env.TOKEN}", scope(), LOC)
    assert isinstance(answer, Secret)
    assert answer.reveal() == "Bearer s3cret"
    assert str(answer) == "***"
    with pytest.raises(RefError, match="`NOPE` isn't set"):
        resolve("${env.NOPE}", scope(), LOC)


def test_a_secret_makes_the_whole_string_one() -> None:
    login = Given((Output("token"),), {"token": Secret("t0k")})
    answer = resolve("Bearer ${steps.login.token}", scope(login=login), LOC)
    assert isinstance(answer, Secret)
    assert answer.reveal() == "Bearer t0k"
    with pytest.raises(RefError, match="a secret has no fields"):
        resolve("${steps.login.token.x}", scope(login=login), LOC)

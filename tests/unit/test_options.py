"""A step's `with:` block, read into its `Options` dataclass — strictly."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pytest

from lely.config import Map, Scalar, load_text
from lely.model import Linked, Secret
from lely.options import OptionsError, Unresolved, build, fields_of
from lely.refs import Unknown


@dataclass(frozen=True, slots=True)
class Options:
    model: str
    retries: int = 3
    ratio: float = 0.5
    enabled: bool = True
    mode: Literal["fast", "safe"] = "safe"
    tags: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    note: str | None = None
    token: Secret | None = None
    extra: object = None


def block(yaml: str) -> Map | None:
    config = load_text(f"steps:\n  - uses: x\n    with:\n{yaml}", Path("lely.yml"))
    return config.steps[0].options


def plain(scalar: Scalar) -> Any:
    return scalar.value


def test_reads_every_supported_type() -> None:
    options = build(
        Options,
        block(
            "      model: main.ml.churn\n"
            "      retries: 5\n"
            "      ratio: 1\n"
            "      enabled: false\n"
            "      mode: fast\n"
            "      tags: [a, b]\n"
            "      env: {A: '1'}\n"
            "      note: null\n"
            "      token: t0k\n"
            "      extra: {any: [1, two]}\n"
        ),
        plain,
        "step `x`",
    )
    assert options == Options(
        model="main.ml.churn",
        retries=5,
        ratio=1.0,
        enabled=False,
        mode="fast",
        tags=("a", "b"),
        env={"A": "1"},
        note=None,
        token=Secret("t0k"),
        extra={"any": [1, "two"]},
    )
    assert options.token.reveal() == "t0k"


def test_defaults_fill_what_isnt_given() -> None:
    assert build(Options, block("      model: m\n"), plain, "step `x`") == Options(
        model="m"
    )


def test_a_number_is_accepted_as_a_string() -> None:
    assert build(Options, block("      model: 14\n"), plain, "step `x`") == Options(
        model="14"
    )


def problem(yaml: str) -> str:
    with pytest.raises(OptionsError) as caught:
        build(Options, block(yaml), plain, "step `x` (x)")
    return str(caught.value)


def test_an_unknown_option_names_the_known_ones() -> None:
    assert problem("      model: m\n      modle: m\n").startswith(
        "lely.yml:5:7: unknown option `modle`; known: model, retries,"
    )


def test_a_missing_option_is_an_error() -> None:
    assert (
        problem("      retries: 1\n")
        == "lely.yml:4:7: missing option `model` (step `x` (x))"
    )


def test_a_wrong_type_says_what_it_wanted() -> None:
    assert problem("      model: m\n      retries: many\n") == (
        "lely.yml:5:16: `retries` must be an integer, not 'many' (step `x` (x))"
    )
    assert "must be one of 'fast', 'safe'" in problem(
        "      model: m\n      mode: slow\n"
    )
    assert "`tags` must be a list" in problem("      model: m\n      tags: a\n")
    assert "must be a single value" in problem("      model: [m]\n")


def test_a_value_that_isnt_known_yet_leaves_the_options_unresolved() -> None:
    def resolver(scalar: Scalar) -> Any:
        return (
            Unknown("app.resources.jobs.x.id")
            if "${" in str(scalar.value)
            else scalar.value
        )

    result = build(
        Options,
        block(
            "      model: ${steps.app.resources.jobs.x.id}\n"
            "      tags: ['${steps.app.resources.jobs.x.id}']\n"
        ),
        resolver,
        "s",
    )
    # named once, however often it is taken
    assert result == Unresolved(("app.resources.jobs.x.id",))


@dataclass(frozen=True, slots=True)
class Runs:
    bundle: Linked
    resource: str


def test_an_option_can_name_a_step() -> None:
    app = Linked("app", "bundle", options=object())
    built = build(
        Runs,
        block("      bundle: app\n      resource: jobs.x\n"),
        plain,
        "s",
        link=lambda scalar: app,
    )
    assert built == Runs(bundle=app, resource="jobs.x")
    waiting = build(
        Runs,
        block("      bundle: app\n      resource: jobs.x\n"),
        plain,
        "s",
        link=lambda scalar: Unknown("app"),
    )
    assert waiting == Unresolved(("app",))
    with pytest.raises(OptionsError, match="`bundle` must be the name of a step"):
        build(Runs, block("      bundle: [app]\n      resource: x\n"), plain, "s")
    assert fields_of(Runs)[0].type == "the name of a step"


def test_a_secret_goes_only_where_a_secret_is_expected() -> None:
    def resolver(scalar: Scalar) -> Any:
        return Secret("t0k") if scalar.value == "${steps.login.token}" else scalar.value

    built = build(
        Options,
        block("      model: m\n      token: ${steps.login.token}\n"),
        resolver,
        "s",
    )
    assert built.token.reveal() == "t0k"
    with pytest.raises(OptionsError, match="would hold a secret"):
        build(Options, block("      model: ${steps.login.token}\n"), resolver, "s")


def test_a_secret_option_takes_a_plain_number_too() -> None:
    built = build(Options, block("      model: m\n      token: 8080\n"), plain, "s")
    assert built.token.reveal() == "8080"


def test_fields_describe_the_options() -> None:
    described = {f.name: f for f in fields_of(Options)}
    assert described["model"].required
    assert described["model"].type == "a string"
    assert described["tags"].type == "list of strings"
    assert described["mode"].type == "'fast' | 'safe'"
    assert described["retries"].default == "3"


# -- found in the second review ------------------------------------------------------


def test_a_number_meant_as_text_is_passed_on_as_it_was_written() -> None:
    """`1.10` isn't `1.1`, `0123` isn't octal 83, and `yes` is `yes`: an option
    that wants text gets what was written, not what YAML made of it."""
    for written, expected in (
        ("1.10", "1.10"),
        ("0123", "0123"),
        ("1e3", "1e3"),
        ("yes", "yes"),
        ("true", "true"),
        ("14", "14"),
    ):
        built = build(Options, block(f"      model: {written}\n"), plain, "s")
        assert built.model == expected, written


def test_text_that_came_from_a_reference_is_written_the_way_json_would() -> None:
    def resolver(scalar: Scalar) -> Any:
        return {"${a}": 14, "${b}": True, "${c}": 1.5}.get(
            str(scalar.value), scalar.value
        )

    for reference, expected in (("${a}", "14"), ("${b}", "true"), ("${c}", "1.5")):
        built = build(Options, block(f"      model: '{reference}'\n"), resolver, "s")
        assert built.model == expected


def test_a_value_known_to_be_secret_is_checked_without_being_there() -> None:
    """Offline, a value from the environment isn't looked up — and isn't faked
    either: the plugin's options are not built with a stand-in for it."""
    built_with: list[Any] = []

    @dataclass(frozen=True)
    class Checked:
        token: Secret
        note: str = ""

        def __post_init__(self) -> None:
            built_with.append(self.token)

    def offline(scalar: Scalar) -> Any:
        if "${env." in str(scalar.value):
            return Unknown("offline", secret=True)
        return scalar.value

    fits = build(Checked, block("      token: ${env.TOKEN}\n"), offline, "s")
    assert fits == Unresolved(("offline",))
    assert built_with == []  # `__post_init__` never saw a placeholder
    with pytest.raises(OptionsError, match="`note` would hold a secret"):
        build(
            Checked,
            block("      token: ${env.TOKEN}\n      note: ${env.TOKEN}\n"),
            offline,
            "s",
        )


# -- found in the third review -------------------------------------------------------


def test_an_optional_text_takes_a_null_that_came_by_reference() -> None:
    """`note: str | None` took a written `null` and refused the same null
    arriving from another step's output."""

    def resolver(scalar: Scalar) -> Any:
        return None if scalar.value == "${steps.x.note}" else scalar.value

    built = build(
        Options, block("      model: m\n      note: ${steps.x.note}\n"), resolver, "s"
    )
    assert built.note is None
    with pytest.raises(OptionsError, match="`model` must be a string, not None"):
        build(Options, block("      model: ${steps.x.note}\n"), resolver, "s")


def test_a_field_the_class_fills_in_itself_is_not_an_option() -> None:
    @dataclass(frozen=True)
    class Filled:
        size: int = 1
        made: str = field(default="by the class", init=False)

    assert [f.name for f in fields_of(Filled)] == ["size"]
    assert build(Filled, block("      size: 2\n"), plain, "s") == Filled(size=2)
    with pytest.raises(OptionsError, match="unknown option `made`; known: size"):
        build(Filled, block("      made: by hand\n"), plain, "s")


def test_a_literal_is_one_of_its_members_and_of_its_kind() -> None:
    """`true` equals `1` in Python; it is not the `1` of `Literal[1, 2]`."""

    @dataclass(frozen=True)
    class Level:
        level: Literal[1, 2] = 1

    assert build(Level, block("      level: 2\n"), plain, "s") == Level(2)
    with pytest.raises(OptionsError, match="`level` must be one of 1, 2, not True"):
        build(Level, block("      level: true\n"), plain, "s")


# -- found in the fourth review ------------------------------------------------------


def test_a_number_too_large_to_hold_is_said() -> None:
    @dataclass(frozen=True)
    class Options:
        ratio: float = 0.5

    with pytest.raises(OptionsError, match="`ratio` is a number too large to hold"):
        build(Options, block("      ratio: 1" + "0" * 400 + "\n"), plain, "step `x`")


def test_a_default_that_cant_be_made_is_said_and_what_it_prints_is_not_lelys(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from lely.options import fields_of

    def loud() -> list[str]:
        print("making a default")
        return ["a"]

    def broken() -> list[str]:
        raise RuntimeError("no default today")

    @dataclass(frozen=True)
    class Loud:
        names: list[str] = field(default_factory=loud)

    @dataclass(frozen=True)
    class Broken:
        names: list[str] = field(default_factory=broken)

    assert fields_of(Loud)[0].default == "['a']"
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "making a default\n")
    with pytest.raises(OptionsError) as caught:
        fields_of(Broken)
    assert "the default of its option `names` can't be made: RuntimeError" in str(
        caught.value
    )

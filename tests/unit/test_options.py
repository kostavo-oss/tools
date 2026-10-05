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

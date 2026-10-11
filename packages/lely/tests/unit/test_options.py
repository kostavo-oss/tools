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
    """PLG-3."""
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
    """PLG-3."""
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
    """REF-4."""
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
    """CFG-10. `1.10` isn't `1.1`, `0123` isn't octal 83, and `yes` is `yes`: an option
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


def test_a_list_or_a_mapping_can_be_given_whole_by_reference() -> None:
    """`tags: ${steps.model.tags}` was "`tags` must be a list" before the
    reference was looked at — so one that named no step was never reported,
    and a null by reference was no null for an option that may be left out."""

    @dataclass(frozen=True)
    class Options:
        tags: tuple[str, ...] = ()
        env: Mapping[str, str] = field(default_factory=dict)
        to: tuple[str, ...] | None = None
        rows: tuple[object, ...] = ()

    answers: dict[str, Any] = {
        "${tags}": ["a", "b"],
        "${env}": {"A": "1"},
        "${nothing}": None,
        "${numbers}": [1, 2],
        "${later}": Unknown("model.tags"),
    }

    def resolve(scalar: Scalar) -> Any:
        return answers[str(scalar.value)]

    def built(yaml: str) -> Any:
        return build(Options, block(yaml), resolve, "step `x`")

    assert built("      tags: ${tags}\n      env: ${env}\n      to: ${nothing}\n") == (
        Options(tags=("a", "b"), env={"A": "1"}, to=None)
    )
    assert built("      rows: ${numbers}\n").rows == (1, 2)
    assert built("      tags: ${later}\n") == Unresolved(("model.tags",))
    for yaml, message in (
        (
            "      tags: ${numbers}\n",
            r"`tags` must be a list of text; \$\{numbers\} gives",
        ),
        ("      tags: ${env}\n", "`tags` must be a list of text"),
        ("      env: ${tags}\n", "`env` must be a mapping of text"),
        ("      tags: ${nothing}\n", "`tags` must be a list of text"),
        ("      tags: plain\n", "`tags` must be a list"),
    ):
        with pytest.raises(OptionsError, match=message):
            built(yaml)


def test_a_list_or_a_mapping_given_whole_is_converted_by_element() -> None:
    """CFG-11: what came whole by one reference is handed to the plugin as the
    option declares its elements, as if each had been written out."""

    @dataclass(frozen=True)
    class Options:
        tokens: tuple[Secret, ...] = ()
        keys: Mapping[str, Secret] = field(default_factory=dict)
        sizes: tuple[int, ...] = ()
        ratios: Mapping[str, float] = field(default_factory=dict)
        maybe: tuple[int | None, ...] = ()
        modes: tuple[Literal["fast", "safe"], ...] = ()
        names: tuple[str, ...] = ()
        notes: Mapping[str, str | None] = field(default_factory=dict)
        rows: tuple[object, ...] = ()
        grid: tuple[tuple[int, ...], ...] = ()

    answers: dict[str, Any] = {
        "${texts}": ["t0k-one", "t0k-two"],
        "${mapping}": {"a": "t0k-one"},
        "${numbers}": [1, 2],
        "${wholes}": {"a": 1, "b": 2.5},
        "${gaps}": [1, None],
        "${modes}": ["fast", "safe"],
        "${words}": ["a", "b"],
        "${secrets}": [Secret("t0k-one")],
        "${nested}": [{"deep": [Secret("t0k-one")]}],
        "${lists}": [[1, 2], [3]],
        "${flags}": [True],
    }

    def resolve(scalar: Scalar) -> Any:
        return answers[str(scalar.value)]

    def built(yaml: str) -> Any:
        return build(Options, block(yaml), resolve, "step `x`")

    made = built(
        "      tokens: ${texts}\n      keys: ${mapping}\n      sizes: ${numbers}\n"
        "      ratios: ${wholes}\n      maybe: ${gaps}\n      modes: ${modes}\n"
        "      grid: ${lists}\n"
    )
    assert all(isinstance(token, Secret) for token in made.tokens)
    assert [token.reveal() for token in made.tokens] == ["t0k-one", "t0k-two"]
    assert isinstance(made.keys["a"], Secret) and made.keys["a"].reveal() == "t0k-one"
    assert "t0k-one" not in repr(made)
    assert made.sizes == (1, 2)
    assert made.ratios == {"a": 1.0, "b": 2.5}
    assert [type(ratio) for ratio in made.ratios.values()] == [float, float]
    assert made.maybe == (1, None)
    assert made.modes == ("fast", "safe")
    assert made.grid == ((1, 2), (3,))
    # as the bundle's `vars` take them: a number is its text, a null stays one
    answers["${some}"] = {"a": "x", "b": None, "n": 5, "yes": True}
    assert built("      notes: ${some}\n").notes == {
        "a": "x",
        "b": None,
        "n": "5",
        "yes": "true",
    }
    assert built("      tokens: ${secrets}\n").tokens[0].reveal() == "t0k-one"
    for yaml, message in (
        ("      sizes: ${words}\n", "`sizes` must be an integer, not 'a'"),
        ("      sizes: ${flags}\n", "`sizes` must be an integer, not True"),
        ("      modes: ${words}\n", "`modes` must be one of 'fast', 'safe', not 'a'"),
        ("      grid: ${numbers}\n", "`grid` must hold lists, not 1"),
        ("      sizes: ${secrets}\n", "`sizes` would hold a secret"),
        ("      rows: ${secrets}\n", "`rows` would hold a secret"),
        ("      rows: ${nested}\n", "`rows` would hold a secret"),
        ("      names: ${secrets}\n", "`names` must be a list of text"),
    ):
        with pytest.raises(OptionsError, match=message) as caught:
            built(yaml)
        assert "t0k-one" not in str(caught.value)


# -- what a step is made from ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Kinds:
    text: str = ""
    ratio: float = 0.0
    loud: bool = False
    count: int = 0
    names: tuple[str, ...] = ()
    labels: Mapping[str, str | None] = field(default_factory=dict)
    anything: object = None
    level: Literal[1, 2] = 1
    token: Secret | None = None
    keys: Mapping[str, Secret] = field(default_factory=dict)
    tokens: tuple[Secret, ...] = ()
    either: Secret | tuple[Secret, ...] = ()
    pair: tuple[str, Secret] = ("", Secret(""))


def handed_of(source: str, name: str = "lely.yml") -> object:
    from lely.options import handed

    return handed(Kinds, load_text(source, Path(name)).steps[0].options)


def in_yaml(block: str) -> object:
    return handed_of(f"steps:\n  - uses: bundle\n    with: {block}\n")


def in_toml(block: str) -> object:
    return handed_of(
        f'[[tool.lely.steps]]\nuses = "bundle"\nwith = {block}\n', "pyproject.toml"
    )


def test_what_a_step_is_made_from_is_what_its_plugin_is_handed() -> None:
    """PLAN-4: options as the plugin is handed them. `1.10` edited to `1.1`
    hands a text option another text, so it is another step; for a number it
    is the same number, and the same step."""
    assert in_yaml("{text: 1.10}") == {"text": "1.10"}
    assert in_yaml("{text: 1.10}") != in_yaml("{text: 1.1}")
    assert in_yaml("{text: 0123}") != in_yaml("{text: 83}")
    assert in_yaml("{text: yes}") != in_yaml("{text: true}")
    assert in_yaml("{names: [1.10], labels: {a: 0123}}") == {
        "names": ["1.10"],
        "labels": {"a": "0123"},
    }
    assert in_yaml("{ratio: 1.10}") == in_yaml("{ratio: 1.1}") == {"ratio": 1.1}
    assert in_yaml("{loud: yes}") == in_yaml("{loud: true}") == {"loud": True}
    assert in_yaml("{anything: [1.10, yes]}") == {"anything": [1.1, True]}
    # a reference stays as it was written, and so does what fits no option
    assert in_yaml("{text: '${env.X}', other: 1.10}") == {
        "text": "${env.X}",
        "other": 1.1,
    }


def test_a_secret_written_out_is_not_in_what_a_step_is_made_from() -> None:
    """SEC-4: a `Secret` option counts by where it comes from, never by its
    text. What a step is made from is hashed into the plan file."""
    assert in_yaml("{token: t0p-s3cret}") == in_yaml("{token: another}") == {"token": ""}
    assert in_yaml("{token: 1234}") == in_toml("{ token = 1234 }") == {"token": ""}
    assert in_yaml("{token: 'pa$${ss}'}") == {"token": ""}
    # that one is given counts, and so does where it comes from
    assert in_yaml("{token: t0p-s3cret}") != in_yaml("{}") != in_yaml("{token: null}")
    assert in_yaml("{token: '${env.TOKEN}'}") == {"token": "${env.TOKEN}"}
    assert in_yaml("{token: '${env.TOKEN}'}") != in_yaml("{token: '${env.OTHER}'}")
    assert in_yaml("{token: 'Bearer ${env.TOKEN}'}") == {"token": "${env.TOKEN}"}
    assert in_yaml("{token: '${steps.a.user}:${env.PASS}'}") == {
        "token": "${steps.a.user}${env.PASS}"
    }
    # a secret in a list or a mapping: its place and its key count, its text never
    assert in_yaml("{keys: {a: one, b: '${env.B}'}, tokens: [x, y]}") == {
        "keys": {"a": "", "b": "${env.B}"},
        "tokens": ["", ""],
    }
    # also where what is written has not the shape the option wants: a text
    # before a reference to a whole list, a list where one secret goes
    assert in_yaml("{tokens: 't0p-s3cret${steps.up.list}'}") == {
        "tokens": "${steps.up.list}"
    }
    assert in_yaml("{keys: 't0p-s3cret${steps.up.map}'}") == {"keys": "${steps.up.map}"}
    assert in_yaml("{token: [t0p-s3cret, {deep: t0p-s3cret}]}") == {
        "token": ["", {"deep": ""}]
    }
    assert in_yaml("{pair: [name, t0p-s3cret]}") == {"pair": ["", ""]}
    assert in_yaml("{either: t0p-s3cret}") == {"either": ""}
    assert in_yaml("{either: [t0p-s3cret]}") == {"either": [""]}
    assert "t0p" not in repr(in_yaml("{either: t0p-s3cret, keys: [t0p-s3cret]}"))
    # the same words in an option that is no secret count as they did
    assert in_yaml("{text: t0p-s3cret}") == {"text": "t0p-s3cret"}


def test_a_mapping_counts_in_the_order_written() -> None:
    """PLAN-12: a plugin is handed a mapping in the order written, so that
    order is part of what the step is made from. The order of the options
    themselves is not: a plugin is handed those by name."""
    import hashlib
    import json

    from lely import planning

    def made_from(block: str, name: str = "lely.yml") -> str:
        source = f"steps:\n  - uses: bundle\n    with: {block}\n"
        if name == "pyproject.toml":
            source = f'[[tool.lely.steps]]\nuses = "bundle"\nwith = {block}\n'
        return planning.made_from(load_text(source, Path(name)).steps[0], Kinds)

    assert made_from("{labels: {a: x, b: y}}") != made_from("{labels: {b: y, a: x}}")
    assert made_from("{anything: {deep: {a: 1, b: 2}}}") != made_from(
        "{anything: {deep: {b: 2, a: 1}}}"
    )
    assert made_from("{text: t, count: 2}") == made_from("{count: 2, text: t}")
    # and the same order in the other file is still the same step
    assert made_from("{labels: {b: y, a: x}}") == made_from(
        '{ labels = { b = "y", a = "x" } }', "pyproject.toml"
    )
    # a mapping written in the order of its keys counts as it did before the
    # order counted, so a plan saved for one is not refused
    before = json.dumps(
        {"uses": "bundle", "targets": None, "with": {"labels": {"a": "x", "b": "y"}}},
        sort_keys=True,
        default=str,
    )
    assert (
        made_from("{labels: {a: x, b: y}}")
        == (hashlib.sha256(before.encode("utf-8")).hexdigest()[:16])
    )


def test_a_value_counts_the_same_in_yaml_and_in_toml() -> None:
    """CFG-4: `1.10` and `yes` in a `lely.yml` are the values a `pyproject.toml`
    writes as `1.10` and `true`; where the option wants text, as `"1.10"` and
    `"yes"`."""
    assert in_yaml("{ratio: 1.10, loud: yes, count: 5, level: 2}") == in_toml(
        "{ ratio = 1.10, loud = true, count = 5, level = 2 }"
    )
    assert in_yaml("{text: 1.10}") == in_toml('{ text = "1.10" }')
    assert in_yaml("{text: yes}") == in_toml('{ text = "yes" }')
    assert in_yaml("{text: 5, ratio: 5}") == in_toml("{ text = 5, ratio = 5.0 }")
    assert in_yaml("{names: [1.10], labels: {a: yes}}") == in_toml(
        '{ names = ["1.10"], labels = { a = "yes" } }'
    )
    assert in_yaml("{anything: {a: [1.10, yes]}}") == in_toml(
        "{ anything = { a = [1.10, true] } }"
    )
    # a number in TOML has no spelling to keep: for text it is its value
    assert in_toml("{ text = 1.10 }") == {"text": "1.1"} != in_yaml("{text: 1.10}")

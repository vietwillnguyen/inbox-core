"""The per-client configuration: typed, validated, loadable from TOML or YAML."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

from inbox_core.config import (
    CategoryRule,
    ClientConfig,
    ConfigError,
    Organisation,
    TriagePolicy,
    load_config,
)

FIXTURES = Path(__file__).parent / "fixtures"
ORIGIN = FIXTURES / "origin_table.toml"


def minimal_policy(**overrides: Any) -> TriagePolicy:
    values: dict[str, Any] = {
        "categories": (
            CategoryRule("faq", "a general question", auto_answer=True),
            CategoryRule("refund", "asks for money back", escalates_to="needs_executive"),
            CategoryRule("other", "anything else"),
            CategoryRule("automated", "not written by a person", escalates_to="skip"),
        ),
        "languages": {"en": "English"},
        "confidence_threshold": 0.6,
        "fallback_category": "other",
    }
    values.update(overrides)
    return TriagePolicy(**values)


def problems_of(build: Any) -> str:
    with pytest.raises(ConfigError) as caught:
        build()
    return str(caught.value)


class TestConstructingInPython:
    def test_a_valid_policy_builds(self) -> None:
        policy = minimal_policy()
        assert policy.category("faq") == CategoryRule("faq", "a general question", True)
        assert policy.category("nope") is None
        assert policy.default_language == "en"
        assert policy.executive_categories == frozenset({"refund"})
        assert policy.skip_categories == frozenset({"automated"})
        assert policy.auto_answer_categories == frozenset({"faq"})

    def test_category_defaults_are_the_safe_ones(self) -> None:
        rule = CategoryRule("other", "anything")
        assert rule.auto_answer is False
        assert rule.escalates_to == "needs_admin"

    def test_languages_are_read_only(self) -> None:
        policy = minimal_policy()
        with pytest.raises(TypeError):
            policy.languages["fr"] = "French"  # type: ignore[index]

    def test_with_threshold_revalidates(self) -> None:
        assert minimal_policy().with_threshold(0.8).confidence_threshold == 0.8
        assert "confidence_threshold" in problems_of(lambda: minimal_policy().with_threshold(0))

    def test_seriousness_order_puts_executive_first_then_admin_then_auto(self) -> None:
        order = minimal_policy().seriousness_order()
        assert order == ("refund", "other", "faq")


class TestValidationRejects:
    def test_auto_answer_without_a_confidence_threshold(self) -> None:
        message = problems_of(lambda: minimal_policy(confidence_threshold=None))
        assert "confidence_threshold" in message
        assert "faq" in message

    def test_a_policy_with_no_auto_answer_may_omit_the_threshold(self) -> None:
        policy = minimal_policy(
            categories=(CategoryRule("other", "anything"),), confidence_threshold=None
        )
        assert policy.confidence_threshold is None

    @pytest.mark.parametrize("threshold", [0.0, -0.1, 1.5, float("nan"), float("inf")])
    def test_a_threshold_outside_zero_to_one(self, threshold: float) -> None:
        assert "confidence_threshold" in problems_of(
            lambda: minimal_policy(confidence_threshold=threshold)
        )

    def test_a_boolean_threshold(self) -> None:
        assert "confidence_threshold" in problems_of(
            lambda: minimal_policy(confidence_threshold=True)
        )

    def test_an_unknown_tier(self) -> None:
        message = problems_of(
            lambda: minimal_policy(
                categories=(
                    CategoryRule("faq", "q", auto_answer=True),
                    CategoryRule("other", "x", escalates_to="needs_ceo"),  # type: ignore[arg-type]
                )
            )
        )
        assert "unknown tier" in message
        assert "needs_ceo" in message

    def test_escalating_to_auto_answer(self) -> None:
        message = problems_of(
            lambda: minimal_policy(
                categories=(
                    CategoryRule("faq", "q", escalates_to="auto_answer"),  # type: ignore[arg-type]
                    CategoryRule("other", "x"),
                )
            )
        )
        assert "auto_answer = true" in message

    @pytest.mark.parametrize("tier", ["needs_executive", "skip"])
    def test_an_auto_answer_category_that_escalates_elsewhere(self, tier: str) -> None:
        message = problems_of(
            lambda: minimal_policy(
                categories=(
                    CategoryRule("faq", "q", auto_answer=True, escalates_to=tier),  # type: ignore[arg-type]
                    CategoryRule("other", "x"),
                )
            )
        )
        assert "faq" in message
        assert tier in message

    def test_duplicate_categories(self) -> None:
        message = problems_of(
            lambda: minimal_policy(
                categories=(
                    CategoryRule("faq", "q", auto_answer=True),
                    CategoryRule("faq", "again"),
                    CategoryRule("other", "x"),
                )
            )
        )
        assert "duplicate category 'faq'" in message

    def test_no_categories(self) -> None:
        assert "at least one category" in problems_of(lambda: minimal_policy(categories=()))

    @pytest.mark.parametrize("name", ["", "Faq", "has space", "9lives", "x" * 65])
    def test_a_bad_category_name(self, name: str) -> None:
        assert "category name" in problems_of(
            lambda: minimal_policy(categories=(CategoryRule(name, "d"), CategoryRule("other", "x")))
        )

    def test_an_empty_description(self) -> None:
        assert "description" in problems_of(
            lambda: minimal_policy(categories=(CategoryRule("other", " "),))
        )

    def test_no_languages(self) -> None:
        assert "language" in problems_of(lambda: minimal_policy(languages={}))

    @pytest.mark.parametrize("code", ["other", "EN", "english", "e"])
    def test_a_bad_or_reserved_language_code(self, code: str) -> None:
        assert code in problems_of(lambda: minimal_policy(languages={code: "Name"}))

    def test_a_fallback_category_that_does_not_exist(self) -> None:
        assert "fallback_category" in problems_of(
            lambda: minimal_policy(fallback_category="missing")
        )

    @pytest.mark.parametrize("fallback", ["faq", "automated"])
    def test_a_fallback_category_that_would_not_reach_a_person(self, fallback: str) -> None:
        assert "fallback_category" in problems_of(
            lambda: minimal_policy(fallback_category=fallback)
        )

    def test_every_problem_is_reported_at_once(self) -> None:
        message = problems_of(
            lambda: minimal_policy(
                categories=(
                    CategoryRule("faq", "q", auto_answer=True),
                    CategoryRule("faq", "q"),
                    CategoryRule("x", "d", escalates_to="nope"),  # type: ignore[arg-type]
                ),
                confidence_threshold=None,
                fallback_category="missing",
            )
        )
        for fragment in ("duplicate", "unknown tier", "confidence_threshold", "fallback"):
            assert fragment in message


class TestLoadingFromFiles:
    def test_toml_loads_into_the_typed_object(self) -> None:
        config = load_config(ORIGIN)
        assert isinstance(config, ClientConfig)
        assert config.organisation == Organisation(
            name="Origin Equivalent",
            summary=(
                "a volunteer-run organisation used to prove the configurable "
                "policy matches the original"
            ),
        )
        assert [rule.name for rule in config.triage.categories][:2] == ["signup", "faq"]
        assert dict(config.triage.languages) == {"en": "English", "vi": "Vietnamese"}

    def test_yaml_loads_to_the_same_object_as_toml(self, tmp_path: Path) -> None:
        import yaml

        data = tomllib.loads(ORIGIN.read_text(encoding="utf-8"))
        path = tmp_path / "client.yaml"
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        assert load_config(path) == load_config(ORIGIN)

    def test_from_mapping_equals_load(self) -> None:
        data = tomllib.loads(ORIGIN.read_text(encoding="utf-8"))
        assert ClientConfig.from_mapping(data) == load_config(ORIGIN)

    def test_an_unknown_key_is_an_error_not_ignored(self) -> None:
        data = tomllib.loads(ORIGIN.read_text(encoding="utf-8"))
        data["triage"]["categories"][0]["auto_anwser"] = True
        assert "auto_anwser" in problems_of(lambda: ClientConfig.from_mapping(data))

    def test_a_string_where_a_boolean_belongs_is_an_error(self) -> None:
        data = tomllib.loads(ORIGIN.read_text(encoding="utf-8"))
        data["triage"]["categories"][0]["auto_answer"] = "yes"
        assert "auto_answer" in problems_of(lambda: ClientConfig.from_mapping(data))

    def test_a_missing_section_is_an_error(self) -> None:
        assert "organisation" in problems_of(lambda: ClientConfig.from_mapping({"triage": {}}))

    def test_wrong_shapes_are_errors(self) -> None:
        assert "triage" in problems_of(
            lambda: ClientConfig.from_mapping({"organisation": {"name": "a", "summary": "b"}})
        )
        assert "categories" in problems_of(
            lambda: ClientConfig.from_mapping(
                {
                    "organisation": {"name": "a", "summary": "b"},
                    "triage": {"categories": "faq", "languages": {"en": "English"}},
                }
            )
        )

    def test_an_unsupported_suffix(self, tmp_path: Path) -> None:
        path = tmp_path / "client.ini"
        path.write_text("[x]", encoding="utf-8")
        assert ".ini" in problems_of(lambda: load_config(path))

    def test_a_missing_file(self, tmp_path: Path) -> None:
        assert "no configuration file" in problems_of(lambda: load_config(tmp_path / "none.toml"))

    def test_malformed_toml_names_the_file(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.toml"
        path.write_text("[triage\n", encoding="utf-8")
        assert "broken.toml" in problems_of(lambda: load_config(path))

    def test_yaml_without_pyyaml_explains_the_extra(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import builtins

        real_import = builtins.__import__

        def no_yaml(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "yaml":
                raise ImportError("no yaml")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_yaml)
        path = tmp_path / "client.yml"
        path.write_text("organisation: {}", encoding="utf-8")
        assert "inbox-core[yaml]" in problems_of(lambda: load_config(path))

    def test_organisation_fields_are_required(self) -> None:
        data = tomllib.loads(ORIGIN.read_text(encoding="utf-8"))
        data["organisation"]["name"] = ""
        assert "organisation.name" in problems_of(lambda: ClientConfig.from_mapping(data))


class TestRemainingShapes:
    def test_a_language_without_a_name(self) -> None:
        assert "needs a name" in problems_of(lambda: minimal_policy(languages={"en": ""}))

    def test_a_non_boolean_auto_answer_from_python(self) -> None:
        assert "auto_answer must be true or false" in problems_of(
            lambda: minimal_policy(
                categories=(CategoryRule("other", "x", auto_answer="yes"),)  # type: ignore[arg-type]
            )
        )

    def test_malformed_yaml_names_the_file(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.yaml"
        path.write_text("organisation: [unclosed\n", encoding="utf-8")
        assert "not valid YAML" in problems_of(lambda: load_config(path))

    def test_yaml_that_is_not_a_mapping(self, tmp_path: Path) -> None:
        path = tmp_path / "list.yaml"
        path.write_text("- a\n- b\n", encoding="utf-8")
        assert "mapping at the top level" in problems_of(lambda: load_config(path))

    def test_a_non_table_root(self) -> None:
        assert "must be a table" in problems_of(
            lambda: ClientConfig.from_mapping(["not", "a", "table"])  # type: ignore[arg-type]
        )

    def test_languages_that_are_not_a_table(self) -> None:
        data = tomllib.loads(ORIGIN.read_text(encoding="utf-8"))
        data["triage"]["languages"] = ["en"]
        assert "triage.languages" in problems_of(lambda: ClientConfig.from_mapping(data))

    def test_a_category_that_is_not_a_table(self) -> None:
        data = tomllib.loads(ORIGIN.read_text(encoding="utf-8"))
        data["triage"]["categories"].append("faq")
        assert "triage.categories[11] must be a table" in problems_of(
            lambda: ClientConfig.from_mapping(data)
        )


class TestTemplates:
    def with_templates(self, templates: Any) -> dict[str, Any]:
        data = tomllib.loads(ORIGIN.read_text(encoding="utf-8"))
        data["templates"] = templates
        return data

    def test_templates_load_and_are_read_only(self) -> None:
        config = ClientConfig.from_mapping(
            self.with_templates({"join": {"en": "Join here.", "vi": "Tham gia."}})
        )
        assert config.templates["join"]["vi"] == "Tham gia."
        with pytest.raises(TypeError):
            config.templates["join"]["en"] = "x"  # type: ignore[index]

    @pytest.mark.parametrize(
        ("templates", "problem"),
        [
            ({"join": {"fr": "Bonjour"}}, "unconfigured language 'fr'"),
            ({"join": {"en": " "}}, "empty text"),
            ({"join": {}}, "at least one"),
            ({"Join Now": {"en": "x"}}, "lower-case identifier"),
            ("join", "templates must be a table"),
        ],
    )
    def test_bad_templates_are_refused(self, templates: Any, problem: str) -> None:
        assert problem in problems_of(
            lambda: ClientConfig.from_mapping(self.with_templates(templates))
        )

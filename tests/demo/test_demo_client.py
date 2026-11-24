"""The public demo's made-up shop, and the stand-in model the bundle runs on without a key.

The stand-in is exercised through the real adapters: the LiteLLM classifier and
generator, given a ``completion`` that answers from the stand-in, the way the
LiteLLM gateway's custom provider does in the bundle.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from inbox_core.adapters.litellm import LiteLLMClassifier, LiteLLMGenerator
from inbox_core.chatwoot.app import default_handlers
from inbox_core.config import ClientConfig, load_config
from inbox_core.evals.golden import GoldenCase, as_incoming, load_golden_set
from inbox_core.handlers import HandlerRequest
from inbox_core.knowledge import InMemoryRetriever, load_markdown_knowledge
from inbox_core.prompts import REFUSAL_SENTINEL
from inbox_core.testing.standin_model import StandInError, StandInModel
from inbox_core.triage import decide

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "deploy" / "demo" / "client"


def config() -> ClientConfig:
    return load_config(CLIENT / "client.toml")


def golden() -> tuple[GoldenCase, ...]:
    return load_golden_set(CLIENT / "golden.toml", config())


def model() -> StandInModel:
    return StandInModel.from_file(CLIENT / "standin.toml")


def completion_from(standin: StandInModel, calls: list[dict[str, Any]] | None = None) -> Any:
    def completion(**kwargs: Any) -> dict[str, Any]:
        if calls is not None:
            calls.append(kwargs)
        return {"choices": [{"message": {"content": standin.complete(kwargs["messages"])}}]}

    return completion


class TestTheShop:
    def test_the_config_loads_with_an_approval_category(self) -> None:
        loaded = config()
        assert loaded.organisation.name == "Quillmoor Cycle Works"
        assert loaded.delivery.mode.value == "auto"
        assert loaded.delivery.approval_categories == frozenset({"repair_advice"})

    def test_thirty_knowledge_entries(self) -> None:
        assert len(load_markdown_knowledge(CLIENT / "knowledge.md")) == 30

    def test_the_golden_set_is_valid_and_covers_every_category(self) -> None:
        cases = golden()
        assert len(cases) >= 30
        assert {case.expected_category for case in cases} == {
            rule.name for rule in config().triage.categories
        }

    def test_the_holding_message_says_it_is_a_demo(self) -> None:
        assert "demo" in (config().holding_text("en") or "")

    @pytest.mark.parametrize("name", ["client.toml", "knowledge.md", "golden.toml", "standin.toml"])
    def test_the_data_holds_no_real_looking_address(self, name: str) -> None:
        text = (CLIENT / name).read_text(encoding="utf-8")
        assert re.findall(r"[\w.-]+\.(?:com|org|net|io|uk|dev|co)\b", text) == []
        assert re.findall(r"[\w.+-]+@[\w.-]+", text) == []
        assert re.findall(r"https?://", text) == []


class TestTheStandInClassifies:
    @pytest.mark.parametrize("case", golden(), ids=lambda case: case.id)
    def test_every_golden_case_gets_its_category_and_tier(self, case: GoldenCase) -> None:
        classifier = LiteLLMClassifier(config(), completion=completion_from(model()))
        found = classifier.classify(as_incoming(case))
        decision = decide(found, config().triage)
        assert (found.category, decision.tier) == (case.expected_category, case.expected_tier)
        assert found.language == case.language

    def test_it_answers_the_schema_the_classifier_asks_for(self) -> None:
        calls: list[dict[str, Any]] = []
        classifier = LiteLLMClassifier(config(), completion=completion_from(model(), calls))
        classifier.classify(as_incoming(golden()[0]))
        content = model().complete(calls[0]["messages"])
        schema = calls[0]["response_format"]["json_schema"]["schema"]
        assert set(json.loads(content)) == set(schema["required"])

    def test_a_message_matching_no_rule_is_unsure_and_falls_back(self) -> None:
        reply = json.loads(
            model().complete(
                [
                    {"role": "system", "content": "You classify messages."},
                    {"role": "user", "content": json.dumps({"subject": "", "body": "zzz"})},
                ]
            )
        )
        assert reply["category"] == "other"
        assert reply["confidence"] < config().triage.confidence_threshold

    def test_a_user_message_that_is_not_json_is_read_as_text(self) -> None:
        reply = json.loads(
            model().complete(
                [
                    {"role": "system", "content": "You classify messages."},
                    {"role": "user", "content": "I want my money back"},
                ]
            )
        )
        assert reply["category"] == "refund"
        assert reply["mentions_money_or_commitment"] is True


class TestTheStandInAnswers:
    def handlers(self) -> Any:
        entries = load_markdown_knowledge(CLIENT / "knowledge.md")
        generator = LiteLLMGenerator(completion=completion_from(model()))
        return default_handlers(config(), InMemoryRetriever(entries), generator)

    @pytest.mark.parametrize(
        "case", [c for c in golden() if c.is_answerable], ids=lambda case: case.id
    )
    def test_every_answerable_case_is_answered_from_the_right_entry(self, case: GoldenCase) -> None:
        decision = decide(case.expected_signals(), config().triage)
        handler = self.handlers().for_category(case.expected_category)
        result = handler.handle(HandlerRequest(as_incoming(case), decision, config()))
        assert result.outcome == "reply", result.reason
        for phrase in case.must_mention:
            assert phrase.lower() in result.text.lower(), (case.id, phrase)

    def test_a_question_the_knowledge_does_not_cover_is_refused(self) -> None:
        case = next(c for c in golden() if c.id == "faq-hours")
        off_topic = GoldenCase(
            id="x",
            language="en",
            subject="",
            text="What is the capital of France?",
            expected_category="faq",
            expected_tier="auto_answer",
        )
        decision = decide(case.expected_signals(), config().triage)
        handler = self.handlers().for_category("faq")
        result = handler.handle(HandlerRequest(as_incoming(off_topic), decision, config()))
        assert result.outcome == "hand_off"

    def test_no_context_is_the_refusal_sentinel(self) -> None:
        reply = model().complete(
            [
                {"role": "system", "content": "Rules.\n\nContext:\n"},
                {"role": "user", "content": "Anything?"},
            ]
        )
        assert reply == REFUSAL_SENTINEL

    def test_it_returns_the_first_passage_only(self) -> None:
        reply = model().complete(
            [
                {
                    "role": "system",
                    "content": "Rules.\n\nContext:\n[A-1] First\nLine one.\nLine two.\n\n"
                    "[A-2] Second\nOther text.",
                },
                {"role": "user", "content": "Question"},
            ]
        )
        assert reply == "Line one.\nLine two."


class TestTheRulesFile:
    def test_a_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(StandInError, match="no stand-in rules"):
            StandInModel.from_file(tmp_path / "missing.toml")

    @pytest.mark.parametrize(
        ("text", "problem"),
        [
            ("fallback_category = 'other'\n", "at least one rule"),
            ("[[rules]]\ncategory = 'faq'\npatterns = ['(']\n", "not a valid pattern"),
            ("[[rules]]\ncategory = ''\npatterns = ['x']\n", "needs a category"),
            ("[[rules]]\ncategory = 'faq'\npatterns = []\n", "needs patterns"),
            ("colour = 'blue'\n[[rules]]\ncategory = 'faq'\npatterns = ['x']\n", "colour"),
            ("not toml = = =", "not valid TOML"),
        ],
    )
    def test_bad_rules_are_refused(self, tmp_path: Path, text: str, problem: str) -> None:
        path = tmp_path / "rules.toml"
        path.write_text(text)
        with pytest.raises(StandInError, match=problem):
            StandInModel.from_file(path)

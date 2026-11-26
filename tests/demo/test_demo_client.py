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

    def test_thirty_two_knowledge_entries(self) -> None:
        assert len(load_markdown_knowledge(CLIENT / "knowledge.md")) == 32

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
        # The only URLs are the shop's made-up public pages, on the reserved .example domain.
        urls = re.findall(r"\w+://\S+", text)
        assert all(url.startswith("https://quillmoor-cycles.example/") for url in urls), urls

    def test_answers_link_to_public_pages_and_some_entries_name_one(self) -> None:
        assert config().delivery.show_sources is True
        entries = load_markdown_knowledge(CLIENT / "knowledge.md")
        linked = {entry.id: entry.url for entry in entries if entry.url}
        assert linked == {
            "QCW-01": "https://quillmoor-cycles.example/visit",
            "QCW-02": "https://quillmoor-cycles.example/visit",
            "QCW-12": "https://quillmoor-cycles.example/rentals",
            "QCW-22": "https://quillmoor-cycles.example/classes",
            "QCW-25": "https://quillmoor-cycles.example/guides/gears",
            "QCW-31": "https://quillmoor-cycles.example/prices",
            "QCW-32": "https://quillmoor-cycles.example/prices",
        }


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
        # Not asked the fifth question, so it does not answer it.
        assert "asks_listed_price" not in reply

    def test_it_answers_the_price_question_only_when_asked(self) -> None:
        def ask(body: str) -> Any:
            system = "You classify messages.\nasks_listed_price: Is every mention..."
            return json.loads(
                model().complete(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps({"subject": "", "body": body})},
                    ]
                )
            )["asks_listed_price"]

        assert ask("How much is a puncture repair?") is True
        assert ask("Can I have a discount on a puncture repair?") is False


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


class TestTheVisitorSeesLinksNotSources:
    def run(self, question: str) -> tuple[Any, Any]:
        from inbox_core.pipeline import InMemoryAuditSink, Pipeline
        from inbox_core.store.memory import InMemoryConversationStore
        from inbox_core.testing.fakes import (
            FakeClassifier,
            RecordingNotifier,
            RecordingSink,
            signals,
        )
        from tests.helpers import message

        sink = RecordingSink()
        audit = InMemoryAuditSink()
        Pipeline(
            config=config(),
            classifier=FakeClassifier(default=signals("faq")),
            handlers=TestTheStandInAnswers().handlers(),
            sink=sink,
            store=InMemoryConversationStore(),
            notifier=RecordingNotifier(),
            audit=audit,
        ).process(message(question))
        return sink, audit.records[-1]

    def test_an_answer_ends_with_its_public_page_and_names_no_entry(self) -> None:
        sink, record = self.run("What are your opening hours?")
        (sent,) = sink.sent
        assert sent.text.startswith("The shop is open Tuesday to Friday")
        assert sent.text.endswith("\n\nMore: https://quillmoor-cycles.example/visit")
        assert "QCW-" not in sent.text
        assert "Opening hours" not in sent.text
        assert record.sources[0] == "QCW-01"


class TestTheShopAnswersListedPrices:
    """The demo's ``triage.prices = "published_prices_only"``, end to end on the stand-in."""

    def run(self, question: str, *, answer: str | None = None) -> tuple[Any, Any]:
        from inbox_core.pipeline import InMemoryAuditSink, Pipeline
        from inbox_core.store.memory import InMemoryConversationStore
        from inbox_core.testing.fakes import RecordingNotifier, RecordingSink
        from tests.helpers import message

        standin = model()

        def completion(**kwargs: Any) -> dict[str, Any]:
            content = standin.complete(kwargs["messages"])
            if answer is not None and "response_format" not in kwargs:
                content = answer  # a model that writes its own figure
            return {"choices": [{"message": {"content": content}}]}

        entries = load_markdown_knowledge(CLIENT / "knowledge.md")
        sink, audit = RecordingSink(), InMemoryAuditSink()
        Pipeline(
            config=config(),
            classifier=LiteLLMClassifier(config(), completion=completion),
            handlers=default_handlers(
                config(), InMemoryRetriever(entries), LiteLLMGenerator(completion=completion)
            ),
            sink=sink,
            store=InMemoryConversationStore(),
            notifier=RecordingNotifier(),
            audit=audit,
        ).process(message(question))
        return sink, audit.records[-1]

    def test_the_shop_answers_prices(self) -> None:
        assert config().triage.prices == "published_prices_only"

    def test_a_listed_price_is_answered_with_its_page(self) -> None:
        sink, record = self.run("How much does a basic service cost?")
        assert record.decision == "answered"
        assert record.sources[0] == "QCW-31"
        (sent,) = sink.sent
        assert "A basic service costs £45" in sent.text
        assert sent.text.endswith("More: https://quillmoor-cycles.example/prices")

    def test_an_invented_price_goes_to_a_person(self) -> None:
        sink, record = self.run(
            "How much does a basic service cost?", answer="A basic service is £39."
        )
        assert (record.decision, record.tier) == ("handed_off", "needs_executive")
        assert [reply.kind for reply in sink.sent] == ["holding"]

    @pytest.mark.parametrize(
        "question",
        [
            "Is there a discount on a full service if I bring two bikes?",
            "Would you do a basic service for £30 instead?",
            "My rental deposit still has not come back to my card.",
        ],
    )
    def test_everything_else_about_money_goes_to_a_person(self, question: str) -> None:
        sink, record = self.run(question)
        assert (record.decision, record.tier) == ("handed_off", "needs_executive")
        assert [reply.kind for reply in sink.sent] == ["holding"]

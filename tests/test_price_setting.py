"""The per-client price setting: always hand off (the default), published prices only, or drafts.

The decision is made in code: :func:`derive_tier` lets a plain price question
through only when the client says so, and the pipeline checks every price the
reply states against the passages it cites before anything is delivered.
"""

from __future__ import annotations

import dataclasses
import json
import secrets
from typing import Any

import pytest

from inbox_core.adapters.jev import build_questions
from inbox_core.adapters.litellm import LiteLLMClassifier
from inbox_core.config import ClientConfig, ConfigError, DeliveryPolicy, PricePolicy
from inbox_core.crypto import FieldCipher
from inbox_core.delivery import DeliveryMode
from inbox_core.handlers import (
    GenerationRequest,
    GroundedAnswer,
    HandlerRegistry,
    HandlerRequest,
    HandlerResult,
)
from inbox_core.knowledge import InMemoryRetriever, KnowledgeEntry
from inbox_core.pipeline import UNSTATED_PRICE, InMemoryAuditSink, Pipeline
from inbox_core.prompts import render_answer_instructions, render_triage_prompts
from inbox_core.store.memory import InMemoryConversationStore
from inbox_core.testing.fakes import FakeClassifier, RecordingNotifier, RecordingSink, signals
from inbox_core.triage import (
    TriageSignals,
    TriageUnavailable,
    decide,
    derive_tier,
    escalation_reason,
    signals_from_payload,
)
from tests.helpers import bike_config, message

ENTRIES = (
    KnowledgeEntry(
        "KB-10",
        "Service prices",
        "A basic service costs £45 and a full service costs £120.",
        keywords=("price", "cost", "how much", "service"),
    ),
    KnowledgeEntry("KB-01", "Opening hours", "We are open Tuesday to Saturday, 9am to 6pm."),
)
HOLDING = "Thanks for writing. A person from the workshop will reply here."
PRICE_QUESTION = "How much does a basic service cost?"


def client(prices: PricePolicy = "always_hand_off", **delivery: Any) -> ClientConfig:
    base = bike_config(prices=prices)
    values: dict[str, Any] = {
        "mode": DeliveryMode.AUTO,
        "auto_languages": frozenset({"en"}),
        "holding": {"en": HOLDING},
    }
    values.update(delivery)
    return dataclasses.replace(base, delivery=DeliveryPolicy(**values))


def price_signals(*, listed: bool = True, category: str = "faq") -> TriageSignals:
    return dataclasses.replace(signals(category, money=True), asks_listed_price=listed)


class SaysThis:
    """A generator that ignores the passages and says what it was told: a model that invents."""

    def __init__(self, text: str) -> None:
        self.name = "says-this"
        self.text = text
        self.calls = 0

    def generate(self, request: GenerationRequest) -> str:
        self.calls += 1
        return self.text


def run(
    prices: PricePolicy,
    text: str,
    *,
    triage: TriageSignals | None = None,
    **delivery: Any,
) -> tuple[Any, RecordingSink, SaysThis]:
    generator = SaysThis(text)
    handlers = HandlerRegistry(
        {"faq": GroundedAnswer(InMemoryRetriever(ENTRIES), generator, min_score=0.1, limit=1)}
    )
    sink = RecordingSink()
    pipeline = Pipeline(
        config=client(prices, **delivery),
        classifier=FakeClassifier(default=triage or price_signals()),
        handlers=handlers,
        sink=sink,
        store=InMemoryConversationStore(cipher=FieldCipher({"k1": secrets.token_bytes(32)}, "k1")),
        notifier=RecordingNotifier(),
        audit=InMemoryAuditSink(),
        sleep=lambda _: None,
    )
    return pipeline.process(message(PRICE_QUESTION)), sink, generator


class TestTheSetting:
    def test_the_default_is_always_hand_off(self) -> None:
        assert bike_config().triage.prices == "always_hand_off"
        assert not bike_config().triage.answers_prices

    @pytest.mark.parametrize("value", ["published_prices_only", "draft_for_approval"])
    def test_a_file_can_choose_a_level(self, value: str) -> None:
        loaded = ClientConfig.from_mapping(
            {
                "organisation": {"name": "Shop", "summary": "a made-up shop"},
                "triage": {
                    "prices": value,
                    "confidence_threshold": 0.6,
                    "fallback_category": "other",
                    "languages": {"en": "English"},
                    "categories": [
                        {"name": "faq", "description": "a question", "auto_answer": True},
                        {"name": "other", "description": "anything else"},
                    ],
                },
            }
        )
        assert loaded.triage.prices == value
        assert loaded.triage.answers_prices

    def test_an_unknown_level_is_refused(self) -> None:
        with pytest.raises(ConfigError, match=r"triage\.prices must be one of"):
            bike_config(prices="sometimes")


class TestTiering:
    def test_by_default_a_price_question_is_still_executive(self) -> None:
        # Even if a classifier claims it is a plain price question.
        assert derive_tier(price_signals(), bike_config().triage) == "needs_executive"

    @pytest.mark.parametrize("value", ["published_prices_only", "draft_for_approval"])
    def test_a_plain_price_question_is_triaged_like_any_other(self, value: str) -> None:
        policy = bike_config(prices=value).triage
        assert derive_tier(price_signals(), policy) == "auto_answer"
        assert derive_tier(price_signals(category="booking"), policy) == "needs_admin"

    @pytest.mark.parametrize("value", ["published_prices_only", "draft_for_approval"])
    def test_any_other_mention_of_money_is_still_executive(self, value: str) -> None:
        # Refunds, discounts, disputes, negotiation and custom quotes are not
        # plain price questions: the classifier answers no, and money escalates.
        policy = bike_config(prices=value).triage
        assert derive_tier(price_signals(listed=False), policy) == "needs_executive"
        assert escalation_reason(price_signals(listed=False), policy) == (
            "mentions money or a commitment"
        )

    def test_an_executive_category_stays_executive(self) -> None:
        policy = bike_config(prices="published_prices_only").triage
        assert derive_tier(price_signals(category="refund"), policy) == "needs_executive"

    def test_the_other_rules_still_apply(self) -> None:
        policy = bike_config(prices="published_prices_only").triage
        unsure = dataclasses.replace(price_signals(), confidence=0.2)
        person = dataclasses.replace(price_signals(), asks_for_human=True)
        assert derive_tier(unsure, policy) == "needs_admin"
        assert derive_tier(person, policy) == "needs_admin"


class TestTheClassifierIsAskedOnlyWhenItMatters:
    def payload(self, **extra: object) -> dict[str, object]:
        return {
            "category": "faq",
            "language": "en",
            "confidence": 0.9,
            "asks_for_human": False,
            "mentions_money_or_commitment": True,
            **extra,
        }

    def test_by_default_the_flag_is_never_read(self) -> None:
        found = signals_from_payload(
            self.payload(asks_listed_price=True),
            bike_config().triage,
            classifier="c",
            message_id="m",
        )
        assert found.asks_listed_price is False

    def test_when_prices_are_answered_the_flag_is_required(self) -> None:
        policy = bike_config(prices="published_prices_only").triage
        with pytest.raises(TriageUnavailable, match="non-boolean asks_listed_price for m"):
            signals_from_payload(self.payload(), policy, classifier="c", message_id="m")
        found = signals_from_payload(
            self.payload(asks_listed_price=True), policy, classifier="c", message_id="m"
        )
        assert found.asks_listed_price is True

    def test_the_default_prompt_and_schema_are_unchanged(self) -> None:
        config = bike_config()
        prompts = render_triage_prompts(config)
        assert prompts.listed_price == ""
        assert "asks_listed_price" not in prompts.system
        assert "copy it exactly" not in render_answer_instructions(config, "en")
        assert "asks_listed_price" not in build_questions(config)
        calls: list[dict[str, Any]] = []

        def completion(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {"choices": [{"message": {"content": json.dumps(self.payload())}}]}

        LiteLLMClassifier(config, completion=completion).classify(message())
        schema = calls[0]["response_format"]["json_schema"]["schema"]
        assert "asks_listed_price" not in schema["properties"]

    def test_a_client_answering_prices_asks_the_fifth_question(self) -> None:
        config = bike_config(prices="published_prices_only")
        prompts = render_triage_prompts(config)
        assert "refund" in prompts.listed_price
        assert "discount" in prompts.listed_price
        assert "asks_listed_price:" in prompts.system
        assert "copy it exactly" in render_answer_instructions(config, "en")
        assert build_questions(config)["asks_listed_price"]["type"] == "noul"
        calls: list[dict[str, Any]] = []

        def completion(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            content = json.dumps(self.payload(asks_listed_price=True))
            return {"choices": [{"message": {"content": content}}]}

        found = LiteLLMClassifier(config, completion=completion).classify(message())
        assert found.asks_listed_price is True
        schema = calls[0]["response_format"]["json_schema"]["schema"]
        assert "asks_listed_price" in schema["required"]
        assert decide(found, config.triage).tier == "auto_answer"


class TestAlwaysHandOff:
    def test_a_price_question_is_handed_to_an_executive_without_a_reply(self) -> None:
        record, sink, generator = run("always_hand_off", "A basic service costs £45.")
        assert (record.decision, record.tier) == ("handed_off", "needs_executive")
        assert record.reason == "mentions money or a commitment"
        assert generator.calls == 0
        assert [reply.kind for reply in sink.sent] == ["holding"]


class TestPublishedPricesOnly:
    def test_a_price_stated_in_the_cited_entry_is_answered(self) -> None:
        record, sink, _ = run("published_prices_only", "A basic service costs £45.")
        assert record.decision == "answered"
        assert record.sources == ("KB-10",)
        assert "price:stated" in record.tags
        assert sink.sent[0].text == "A basic service costs £45."

    def test_a_model_that_invents_a_price_is_handed_to_an_executive(self) -> None:
        record, sink, generator = run("published_prices_only", "A basic service costs £40.")
        assert generator.calls == 1
        assert (record.decision, record.tier) == ("handed_off", "needs_executive")
        assert record.reason == UNSTATED_PRICE
        assert "price:unstated" in record.tags
        assert [reply.kind for reply in sink.sent] == ["holding"]
        assert all("£40" not in reply.text for reply in sink.sent)

    def test_a_price_written_in_words_is_handed_off(self) -> None:
        record, sink, _ = run("published_prices_only", "It is forty-five pounds.")
        assert record.reason == UNSTATED_PRICE
        assert [reply.kind for reply in sink.sent] == ["holding"]

    def test_a_bare_invented_figure_in_an_answer_to_a_price_question_is_handed_off(self) -> None:
        record, _, _ = run("published_prices_only", "A basic service is 40.")
        assert record.reason == UNSTATED_PRICE

    def test_an_invented_price_in_reply_to_any_question_is_handed_off(self) -> None:
        # Not a price question, but the model put a price in the answer anyway.
        record, _, _ = run(
            "published_prices_only", "We open at 9am. Parking is $5.", triage=signals("faq")
        )
        assert (record.decision, record.tier) == ("handed_off", "needs_executive")

    def test_a_reply_without_any_price_is_answered(self) -> None:
        record, sink, _ = run("published_prices_only", "Please ask at the counter.")
        assert record.decision == "answered"
        assert sink.sent[0].text == "Please ask at the counter."

    def test_a_refund_is_still_handed_off_before_any_model_writes(self) -> None:
        record, _, generator = run(
            "published_prices_only", "Refunded £45.", triage=price_signals(listed=False)
        )
        assert (record.tier, generator.calls) == ("needs_executive", 0)

    def test_a_template_with_a_price_cites_nothing_so_it_is_handed_off(self) -> None:
        class FixedPrice:
            name = "fixed"

            def handle(self, request: HandlerRequest) -> HandlerResult:
                return HandlerResult.reply(self.name, "A basic service costs £45.")

        pipeline = Pipeline(
            config=client("published_prices_only"),
            classifier=FakeClassifier(default=price_signals()),
            handlers=HandlerRegistry({"faq": FixedPrice()}),
            sink=RecordingSink(),
            store=InMemoryConversationStore(),
            notifier=RecordingNotifier(),
            audit=InMemoryAuditSink(),
        )
        assert pipeline.process(message(PRICE_QUESTION)).reason == UNSTATED_PRICE


class TestDraftForApproval:
    def test_a_price_answer_is_held_for_a_person(self) -> None:
        record, sink, _ = run("draft_for_approval", "A basic service costs £45.")
        assert (record.decision, record.delivery) == ("answer_held", "held")
        assert record.held_because == "a price needs approval"
        assert sink.sent == []
        assert sink.held[0].text == "A basic service costs £45."

    def test_an_invented_price_is_held_and_says_so(self) -> None:
        record, sink, _ = run("draft_for_approval", "A basic service costs £40.")
        assert record.decision == "answer_held"
        assert record.held_because == "a price no cited entry states needs approval"
        assert sink.sent == []

    def test_a_price_question_answered_without_a_price_is_still_held(self) -> None:
        record, _, _ = run("draft_for_approval", "Please ask at the counter.")
        assert record.held_because == "a price needs approval"

    def test_an_ordinary_answer_without_a_price_is_sent(self) -> None:
        record, _, _ = run("draft_for_approval", "We open at 9am.", triage=signals("faq"))
        assert record.decision == "answered"

    def test_a_category_that_needs_approval_keeps_its_reason(self) -> None:
        record, _, _ = run(
            "draft_for_approval",
            "A basic service costs £45.",
            approval_categories=frozenset({"faq"}),
        )
        assert record.held_because == "category faq needs approval"

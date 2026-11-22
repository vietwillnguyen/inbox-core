"""The tier rules over a configured category table."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from inbox_core.config import CategoryRule, TriagePolicy, load_config
from inbox_core.triage import (
    TIERS,
    TriageDecision,
    TriageSignals,
    decide,
    derive_tier,
    escalation_reason,
)

POLICY = TriagePolicy(
    categories=(
        CategoryRule("faq", "q", auto_answer=True),
        CategoryRule("booking", "reserve"),
        CategoryRule("refund", "money back", escalates_to="needs_executive"),
        CategoryRule("other", "anything"),
        CategoryRule("automated", "machines", escalates_to="skip"),
    ),
    languages={"en": "English", "es": "Spanish"},
    confidence_threshold=0.6,
    fallback_category="other",
)


def signals(
    category: str = "faq",
    language: str = "en",
    confidence: float = 0.9,
    human: bool = False,
    money: bool = False,
) -> TriageSignals:
    return TriageSignals(category, language, confidence, human, money, "test")


class TestTheFourRules:
    def test_rule_1_executive_category_wins_over_everything(self) -> None:
        assert derive_tier(signals("refund", confidence=0.0, language="xx"), POLICY) == (
            "needs_executive"
        )

    def test_rule_1_money_or_commitment_escalates_even_an_faq(self) -> None:
        assert derive_tier(signals(money=True), POLICY) == "needs_executive"
        assert derive_tier(signals("automated", money=True), POLICY) == "needs_executive"

    def test_rule_2_skip_wins_over_an_ask_for_a_person(self) -> None:
        assert derive_tier(signals("automated", human=True, confidence=0.1), POLICY) == "skip"

    @pytest.mark.parametrize(
        "kwargs",
        [{"language": "fr"}, {"language": "other"}, {"human": True}, {"confidence": 0.59}],
    )
    def test_rule_3_fails_closed_to_a_person(self, kwargs: dict[str, object]) -> None:
        assert derive_tier(signals(**kwargs), POLICY) == "needs_admin"  # type: ignore[arg-type]

    def test_rule_3_threshold_is_inclusive(self) -> None:
        assert derive_tier(signals(confidence=0.6), POLICY) == "auto_answer"

    def test_rule_4_the_category_decides(self) -> None:
        assert derive_tier(signals("faq"), POLICY) == "auto_answer"
        assert derive_tier(signals("booking"), POLICY) == "needs_admin"

    def test_an_unlisted_category_goes_to_a_person(self) -> None:
        assert derive_tier(signals("made_up"), POLICY) == "needs_admin"

    @pytest.mark.parametrize("confidence", [float("nan"), float("inf"), float("-inf")])
    def test_a_non_finite_confidence_is_never_confident(self, confidence: float) -> None:
        assert derive_tier(signals(confidence=confidence), POLICY) == "needs_admin"

    def test_the_result_is_always_a_known_tier(self) -> None:
        for category in ("faq", "booking", "refund", "other", "automated", "zzz"):
            assert derive_tier(signals(category), POLICY) in TIERS


class TestDecide:
    def test_decide_carries_the_signals_and_the_tier(self) -> None:
        decision = decide(signals(), POLICY)
        assert isinstance(decision, TriageDecision)
        assert decision.tier == "auto_answer"
        assert decision.signals() == signals()
        assert decision.with_tier("needs_admin").tier == "needs_admin"

    def test_decisions_are_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            decide(signals(), POLICY).tier = "skip"  # type: ignore[misc]

    def test_as_record_is_ids_and_numbers_only(self) -> None:
        record = signals(confidence=0.123456).as_record()
        assert record == {
            "category": "faq",
            "language": "en",
            "confidence": 0.1235,
            "asks_for_human": False,
            "mentions_money_or_commitment": False,
            "classifier": "test",
        }


class TestEscalationReason:
    @pytest.mark.parametrize(
        ("given", "reason"),
        [
            (signals("refund"), "executive category refund"),
            (signals(money=True), "mentions money or a commitment"),
            (signals(human=True), "the sender asked for a person"),
            (signals(language="fr"), "unsupported language fr"),
            (signals(confidence=0.3), "confidence 0.30 below threshold 0.60"),
            (signals(confidence=float("nan")), "confidence nan below threshold 0.60"),
            (signals("booking"), "category booking is handled by a person"),
        ],
    )
    def test_reasons_name_categories_and_numbers_only(
        self, given: TriageSignals, reason: str
    ) -> None:
        assert escalation_reason(given, POLICY) == reason

    def test_an_unlisted_category_is_not_echoed(self) -> None:
        reason = escalation_reason(signals("whatever the model typed"), POLICY)
        assert reason == "an unlisted category is handled by a person"

    def test_an_unbounded_language_code_is_not_echoed(self) -> None:
        reason = escalation_reason(signals(language="x" * 40), POLICY)
        assert "x" * 40 not in reason


def test_policy_from_the_example_file_gives_the_documented_tiers() -> None:
    config = load_config(Path(__file__).parent / "fixtures" / "origin_table.toml")
    assert derive_tier(signals("signup", "vi"), config.triage) == "auto_answer"
    assert derive_tier(signals("press"), config.triage) == "needs_executive"

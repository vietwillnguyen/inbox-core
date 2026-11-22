"""Evaluation: golden-set validation and metric arithmetic run in CI; real model calls never do."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from inbox_core.evals.golden import (
    GoldenCase,
    GoldenSetInvalid,
    answerable_cases,
    as_incoming,
    executive_cases,
    load_golden_set,
)
from inbox_core.evals.judge import Verdict, judge_prompt, parse_verdict, strip_fences
from inbox_core.evals.metrics import ClassCounts, GroundednessMetrics, TriageMetrics, format_table
from inbox_core.evals.runners import (
    classify_once,
    evaluate_groundedness,
    evaluate_triage,
    groundedness_summary,
    sweep_answer_threshold,
    sweep_triage_threshold,
    triage_summary,
)
from inbox_core.handlers import ExtractiveGenerator, GroundedAnswer
from inbox_core.knowledge import InMemoryRetriever, KnowledgeEntry
from inbox_core.messages import IncomingMessage
from inbox_core.testing.fakes import FakeClassifier, signals
from inbox_core.triage import TriageSignals, TriageUnavailable
from tests.helpers import bike_config

CONFIG = bike_config()

GOLDEN = """
[[cases]]
id = "faq-en"
language = "en"
text = "When do you open on Saturday?"
expected_category = "faq"
expected_tier = "auto_answer"
must_mention = ["opens at 9am"]

[[cases]]
id = "faq-es"
language = "es"
subject = "Horario"
text = "A que hora abren el sabado?"
expected_category = "faq"
expected_tier = "auto_answer"
must_mention = ["abre a las 9"]

[[cases]]
id = "refund-en"
language = "en"
text = "I want my money back"
expected_category = "refund"
expected_tier = "needs_executive"
expected_mentions_money = true
must_not_answer = ["a refund amount", "a promise of a refund"]

[[cases]]
id = "booking-es"
language = "es"
text = "Quiero reservar una reparacion"
expected_category = "booking"
expected_tier = "needs_admin"

[[cases]]
id = "other-en"
language = "en"
text = "Can I speak to the owner please"
expected_category = "other"
expected_tier = "needs_admin"
expected_asks_for_human = true

[[cases]]
id = "auto-en"
language = "en"
text = "Your invoice is attached"
expected_category = "automated"
expected_tier = "needs_executive"
expected_mentions_money = true

[[cases]]
id = "faq-fr"
language = "other"
text = "Quand ouvrez-vous?"
expected_category = "faq"
expected_tier = "needs_admin"
"""


def write(tmp_path: Path, body: str = GOLDEN, name: str = "golden.toml") -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


class TestGoldenSet:
    def test_a_valid_set_loads(self, tmp_path: Path) -> None:
        cases = load_golden_set(write(tmp_path), CONFIG)
        assert [case.id for case in cases][:2] == ["faq-en", "faq-es"]
        assert {case.id for case in executive_cases(cases)} == {"refund-en", "auto-en"}
        assert {case.id for case in answerable_cases(cases)} == {"faq-en", "faq-es"}

    def test_the_expected_tier_is_checked_against_derive_tier(self, tmp_path: Path) -> None:
        wrong = GOLDEN.replace(
            'expected_category = "booking"\nexpected_tier = "needs_admin"',
            'expected_category = "booking"\nexpected_tier = "auto_answer"',
        )
        with pytest.raises(GoldenSetInvalid, match="derive_tier gives 'needs_admin'"):
            load_golden_set(write(tmp_path, wrong), CONFIG)

    @pytest.mark.parametrize(
        ("old", "new", "problem"),
        [
            ('id = "faq-es"', 'id = "faq-en"', "duplicate id 'faq-en'"),
            ('expected_category = "booking"', 'expected_category = "cake"', "unknown category"),
            ('language = "es"\ntext = "Quiero', 'language = "de"\ntext = "Quiero', "language"),
            ('must_mention = ["opens at 9am"]', "", "must_mention"),
            ('text = "I want my money back"', 'text = ""', "missing text"),
            (
                "expected_mentions_money = true\nmust_not",
                'expected_mentions_money = "yes"\nmust_not',
                "expected_mentions_money",
            ),
            ('id = "booking-es"', 'id = "booking-es"\ncolour = "red"', "unknown key 'colour'"),
            (
                'must_mention = ["opens at 9am"]',
                'must_mention = "opens at 9am"',
                "must_mention must be a list",
            ),
        ],
    )
    def test_problems_are_reported(self, tmp_path: Path, old: str, new: str, problem: str) -> None:
        assert old in GOLDEN
        with pytest.raises(GoldenSetInvalid, match=problem):
            load_golden_set(write(tmp_path, GOLDEN.replace(old, new, 1)), CONFIG)

    def test_every_category_must_have_a_case(self, tmp_path: Path) -> None:
        start = GOLDEN.index('[[cases]]\nid = "booking-es"')
        end = GOLDEN.index('[[cases]]\nid = "other-en"')
        with pytest.raises(GoldenSetInvalid, match="category 'booking' has no cases"):
            load_golden_set(write(tmp_path, GOLDEN[:start] + GOLDEN[end:]), CONFIG)

    def test_every_language_can_be_required(self, tmp_path: Path) -> None:
        with pytest.raises(GoldenSetInvalid, match="category 'refund' has no es case"):
            load_golden_set(write(tmp_path), CONFIG, require_every_language=True)

    def test_yaml_golden_sets(self, tmp_path: Path) -> None:
        import tomllib

        import yaml

        data = tomllib.loads(GOLDEN)
        path = write(tmp_path, yaml.safe_dump(data), "golden.yaml")
        assert len(load_golden_set(path, CONFIG)) == 7

    def test_files_that_are_not_golden_sets(self, tmp_path: Path) -> None:
        with pytest.raises(GoldenSetInvalid, match="no golden set"):
            load_golden_set(tmp_path / "missing.toml", CONFIG)
        with pytest.raises(GoldenSetInvalid, match="no list of cases"):
            load_golden_set(write(tmp_path, 'title = "x"'), CONFIG)
        with pytest.raises(GoldenSetInvalid, match="must be a table"):
            load_golden_set(write(tmp_path, "cases = [1]"), CONFIG)
        with pytest.raises(GoldenSetInvalid, match=r"\.txt"):
            load_golden_set(write(tmp_path, "x", "golden.txt"), CONFIG)

    def test_as_incoming_hides_nothing_the_classifier_needs_and_no_real_sender(
        self, tmp_path: Path
    ) -> None:
        case = load_golden_set(write(tmp_path), CONFIG)[1]
        message = as_incoming(case)
        assert isinstance(message, IncomingMessage)
        assert (message.subject, message.text) == ("Horario", "A que hora abren el sabado?")
        assert message.sender_address.endswith("@example.com")
        assert message.provider_message_id == "golden-faq-es"
        assert case.expected_signals() == TriageSignals("faq", "es", 1.0, False, False, "golden")


class TestMetrics:
    def test_class_counts(self) -> None:
        counts = ClassCounts(true_positive=3, false_positive=1, false_negative=2)
        assert counts.support == 5
        assert counts.precision == 0.75
        assert counts.recall == 0.6
        assert ClassCounts().precision == 1.0
        assert ClassCounts().recall == 1.0

    def test_triage_metrics_and_the_executive_gate(self) -> None:
        metrics = TriageMetrics()
        metrics.record("a", "faq", "faq", "auto_answer", "auto_answer", "en", "en")
        metrics.record("b", "refund", "refund", "needs_executive", "needs_executive", "en", "en")
        assert metrics.passes_executive_gate()
        metrics.record("c", "refund", "faq", "needs_executive", "auto_answer", "es", "en")
        assert metrics.missed_executive == [
            "c: expected needs_executive, got auto_answer (category refund -> faq)"
        ]
        assert not metrics.passes_executive_gate()
        assert metrics.executive_recall == 0.5
        assert metrics.category_accuracy == pytest.approx(2 / 3)
        assert metrics.language_accuracy == pytest.approx(2 / 3)
        assert metrics.confusion[("refund", "faq")] == 1

    def test_an_error_fails_the_gate_even_with_perfect_recall(self) -> None:
        metrics = TriageMetrics()
        metrics.record_error("x", "classifier unavailable")
        assert metrics.executive_recall == 1.0
        assert not metrics.passes_executive_gate()

    def test_empty_metrics(self) -> None:
        metrics = TriageMetrics()
        assert metrics.category_accuracy == 1.0
        assert metrics.language_accuracy == 1.0

    def test_groundedness_counts_refusals_in_the_denominator(self) -> None:
        metrics = GroundednessMetrics()
        metrics.record("a", True, similarity=2.0)
        metrics.record("b", False, "ungrounded", similarity=1.0)
        metrics.record_refusal("c", "no knowledge entry")
        assert metrics.total == 3
        assert metrics.correctness == pytest.approx(1 / 3)
        assert metrics.ungrounded == ["b: ungrounded"]
        assert metrics.answers == [("a", 2.0, True), ("b", 1.0, False)]
        assert not metrics.passes_gate(0.9)
        assert GroundednessMetrics().correctness == 1.0

    def test_format_table(self) -> None:
        table = format_table([("faq", "3")], ("category", "n"))
        assert table.splitlines() == ["category  n", "--------  -", "faq       3"]


class TestJudge:
    def test_parses_a_fenced_verdict(self) -> None:
        raw = (
            '```json\n{"mentions": {"opens at 9am": true}, "grounded": true, '
            '"violations": [], "reasoning": "ok"}\n```'
        )
        verdict = parse_verdict(raw, ("opens at 9am",))
        assert verdict == Verdict(True, {"opens at 9am": True}, (), "ok")
        assert verdict.passes
        assert verdict.why_not() == ""

    def test_reasons_when_it_fails(self) -> None:
        verdict = Verdict(False, {"a": False, "b": True}, ("a price",), "")
        assert not verdict.passes
        assert verdict.why_not() == "ungrounded; missing a; states a price"

    @pytest.mark.parametrize(
        "raw",
        [
            "not json",
            "[]",
            '{"mentions": [1], "grounded": true}',
            '{"mentions": {"x": "yes"}, "grounded": true}',
            '{"mentions": {}, "grounded": true}',
            '{"mentions": {"x": true}, "grounded": "yes"}',
            '{"mentions": {"x": true}, "grounded": true, "violations": "none"}',
        ],
    )
    def test_an_unreadable_verdict_raises_rather_than_passing(self, raw: str) -> None:
        with pytest.raises(ValueError, match=r"."):
            parse_verdict(raw, ("x",))

    def test_strip_fences(self) -> None:
        assert strip_fences("```\n{}\n```") == "{}"

    def test_the_prompt_names_the_organisation_and_the_facts(self) -> None:
        prompt = judge_prompt(
            CONFIG,
            question="q",
            answer="a",
            context="c",
            must_mention=("opens at 9am",),
            must_not_answer=("a price",),
        )
        assert "Example Bike Workshop" in prompt
        assert "- opens at 9am" in prompt
        assert "- a price" in prompt


ENTRIES = (
    KnowledgeEntry("KB-01", "Opening hours", "We open at 9am on Saturdays.", ("abren", "sabado")),
)


@dataclass
class FakeJudge:
    passes: bool = True
    fail: bool = False

    def __call__(self, **kwargs: Any) -> Verdict:
        if self.fail:
            raise ValueError("unreadable")
        facts = dict.fromkeys(kwargs["must_mention"], self.passes)
        return Verdict(self.passes, facts, (), "")


class TestRunners:
    def cases(self, tmp_path: Path) -> tuple[GoldenCase, ...]:
        return load_golden_set(write(tmp_path), CONFIG)

    def perfect(self, cases: tuple[GoldenCase, ...]) -> FakeClassifier:
        return FakeClassifier(
            by_message={
                f"golden-{c.id}": signals(
                    c.expected_category,
                    language=c.language,
                    asks_for_human=c.expected_asks_for_human,
                    money=c.expected_mentions_money,
                )
                for c in cases
            }
        )

    def test_a_perfect_classifier_passes_the_gate(self, tmp_path: Path) -> None:
        cases = self.cases(tmp_path)
        metrics = evaluate_triage(self.perfect(cases), cases, CONFIG.triage)
        assert metrics.passes_executive_gate()
        assert metrics.category_accuracy == 1.0

    def test_a_classifier_failure_on_an_executive_case_fails_the_gate(self, tmp_path: Path) -> None:
        cases = self.cases(tmp_path)
        fake = self.perfect(cases)
        broken = dict(fake.by_message)
        del broken["golden-refund-en"]
        metrics = evaluate_triage(FakeClassifier(by_message=broken), cases, CONFIG.triage)
        assert not metrics.passes_executive_gate()
        assert any("refund-en" in line for line in metrics.missed_executive)

    def test_threshold_sweep_reuses_one_pass_of_calls(self, tmp_path: Path) -> None:
        cases = self.cases(tmp_path)
        fake = self.perfect(cases)
        answered, errors = classify_once(fake, cases)
        assert fake.calls == len(cases)
        assert errors == []
        rows = sweep_triage_threshold(answered, CONFIG.triage, thresholds=(0.5, 0.95))
        assert [row["threshold"] for row in rows] == [0.5, 0.95]
        assert rows[0]["executive_recall"] == 1.0
        assert rows[1]["answered_share"] == pytest.approx(0.0)
        assert fake.calls == len(cases)

    def test_classify_once_records_errors(self, tmp_path: Path) -> None:
        cases = self.cases(tmp_path)
        answered, errors = classify_once(FakeClassifier(fail_with=TriageUnavailable("x")), cases)
        assert answered == []
        assert len(errors) == len(cases)

    def test_groundedness_with_a_grounded_answer_handler(self, tmp_path: Path) -> None:
        cases = self.cases(tmp_path)
        handler = GroundedAnswer(InMemoryRetriever(ENTRIES), ExtractiveGenerator(), min_score=0.1)
        knowledge = {entry.id: entry for entry in ENTRIES}
        metrics = evaluate_groundedness(handler, FakeJudge(), cases, CONFIG, knowledge)
        assert metrics.total == 2
        assert metrics.grounded == 2
        refused = evaluate_groundedness(
            GroundedAnswer(InMemoryRetriever(ENTRIES), ExtractiveGenerator(), min_score=99),
            FakeJudge(),
            cases,
            CONFIG,
            knowledge,
        )
        assert refused.refused == 2
        assert refused.correctness == 0.0

    def test_a_judge_failure_is_never_a_pass(self, tmp_path: Path) -> None:
        cases = self.cases(tmp_path)
        handler = GroundedAnswer(InMemoryRetriever(ENTRIES), ExtractiveGenerator(), min_score=0.1)
        metrics = evaluate_groundedness(
            handler, FakeJudge(fail=True), cases, CONFIG, {e.id: e for e in ENTRIES}
        )
        assert metrics.grounded == 0
        assert metrics.ungrounded == [
            "faq-en: judge failed (ValueError)",
            "faq-es: judge failed (ValueError)",
        ]

    def test_answer_threshold_sweep(self) -> None:
        rows = sweep_answer_threshold([("a", 2.0, True), ("b", 1.0, False)], thresholds=(0.5, 1.5))
        assert rows == [
            {
                "threshold": 0.5,
                "answered": 2,
                "answered_share": 1.0,
                "precision": 0.5,
                "wrong_answers": 1,
            },
            {
                "threshold": 1.5,
                "answered": 1,
                "answered_share": 0.5,
                "precision": 1.0,
                "wrong_answers": 0,
            },
        ]

    def test_summaries_hold_numbers_and_ids_only(self, tmp_path: Path) -> None:
        cases = self.cases(tmp_path)
        metrics = evaluate_triage(self.perfect(cases), cases, CONFIG.triage)
        summary = triage_summary(metrics, classifier="fake", threshold=0.6, cases=len(cases))
        dumped = json.dumps(summary)
        for case in cases:
            assert case.text not in dumped
        assert summary["executive_gate_passed"] is True
        assert summary["cases"] == len(cases)
        per_category = summary["per_category"]
        assert isinstance(per_category, dict)
        assert per_category["faq"] == {"support": 3, "precision": 1.0, "recall": 1.0}
        grounded = groundedness_summary(GroundednessMetrics(), generator="g", judge="j", cases=0)
        assert grounded["correctness"] == 1.0


@pytest.mark.parametrize(
    ("verdict", "why"),
    [
        (Verdict(True, {"a": False}, (), ""), "missing a"),
        (Verdict(True, {}, ("a price",), ""), "states a price"),
        (Verdict(False, {}, (), ""), "ungrounded"),
    ],
)
def test_each_reason_a_verdict_fails(verdict: Verdict, why: str) -> None:
    assert verdict.why_not() == why


@pytest.mark.parametrize("api_base", [None, "http://gateway.example"])
def test_the_litellm_judge(api_base: str | None) -> None:
    from inbox_core.evals.judge import LiteLLMJudge

    calls: list[dict[str, Any]] = []

    def completion(**kwargs: Any) -> Any:
        calls.append(kwargs)
        content = '{"mentions": {"opens": true}, "grounded": true, "violations": []}'
        return {"choices": [{"message": {"content": content}}]}

    judge = LiteLLMJudge(CONFIG, model="gemini/judge", completion=completion, api_base=api_base)
    verdict = judge(
        question="q", answer="a", context="c", must_mention=("opens",), must_not_answer=()
    )
    assert verdict.passes
    assert calls[0]["model"] == "gemini/judge"
    assert calls[0].get("api_base") == api_base


def test_a_judged_answer_without_a_score() -> None:
    metrics = GroundednessMetrics()
    metrics.record("a", True)
    assert metrics.answers == []
    assert metrics.grounded == 1

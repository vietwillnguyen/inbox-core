"""The evaluation runners. Each takes its model-backed parts as arguments.

Nothing here constructs a model client, so every runner is tested in CI with
fakes; :mod:`inbox_core.evals.cli` builds the real ones on demand.

- :func:`evaluate_triage`: may this classifier decide? The gate is 100 percent
  recall on ``needs_executive`` with no case left unclassified.
- :func:`evaluate_groundedness`: are the answers good enough to send unread?
- :func:`sweep_triage_threshold` and :func:`sweep_answer_threshold`: what each
  threshold would have done, from one pass of calls.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from inbox_core.config import ClientConfig, TriagePolicy
from inbox_core.evals.golden import GoldenCase, answerable_cases, as_incoming
from inbox_core.evals.judge import Judge
from inbox_core.evals.metrics import GroundednessMetrics, TriageMetrics
from inbox_core.handlers import Handler, HandlerRequest
from inbox_core.knowledge import KnowledgeEntry
from inbox_core.triage import (
    TriageClassifier,
    TriageDecision,
    TriageSignals,
    TriageUnavailable,
    decide,
)

__all__ = [
    "DEFAULT_ANSWER_SWEEP",
    "DEFAULT_TRIAGE_SWEEP",
    "classify_once",
    "evaluate_groundedness",
    "evaluate_triage",
    "groundedness_summary",
    "sweep_answer_threshold",
    "sweep_triage_threshold",
    "triage_summary",
]

DEFAULT_TRIAGE_SWEEP = (0.3, 0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.8, 0.9, 0.95)
DEFAULT_ANSWER_SWEEP = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0)

Answered = list[tuple[GoldenCase, TriageSignals]]


def classify_once(
    classifier: TriageClassifier, cases: Sequence[GoldenCase]
) -> tuple[Answered, list[str]]:
    """One classifier call per case, kept for reuse at every threshold."""
    answered: Answered = []
    errors: list[str] = []
    for case in cases:
        try:
            answered.append((case, classifier.classify(as_incoming(case))))
        except TriageUnavailable as exc:
            errors.append(f"{case.id}: {exc}")
    return answered, errors


def _score(metrics: TriageMetrics, case: GoldenCase, decision: TriageDecision) -> None:
    metrics.record(
        case_id=case.id,
        expected_category=case.expected_category,
        actual_category=decision.category,
        expected_tier=case.expected_tier,
        actual_tier=decision.tier,
        expected_language=case.language,
        actual_language=decision.language,
    )


def evaluate_triage(
    classifier: TriageClassifier, cases: Sequence[GoldenCase], policy: TriagePolicy
) -> TriageMetrics:
    """Classify every case and score it against its expected category and tier.

    An unavailable classifier on an executive case counts as a missed
    escalation: recall that could not be measured has not been shown.
    """
    metrics = TriageMetrics()
    answered, errors = classify_once(classifier, cases)
    for line in errors:
        metrics.record_error(line.split(":", 1)[0], "classifier unavailable")
    failed = {line.split(":", 1)[0] for line in errors}
    for case in cases:
        if case.id in failed and case.is_executive:
            metrics.missed_executive.append(f"{case.id}: classifier unavailable, recall unproven")
    for case, found in answered:
        _score(metrics, case, decide(found, policy))
    return metrics


def sweep_triage_threshold(
    answered: Answered,
    policy: TriagePolicy,
    thresholds: Sequence[float] = DEFAULT_TRIAGE_SWEEP,
) -> list[dict[str, float]]:
    """What each confidence threshold would have done to the same answers."""
    rows: list[dict[str, float]] = []
    for threshold in thresholds:
        at = policy.with_threshold(threshold)
        metrics = TriageMetrics()
        auto = 0
        for case, found in answered:
            decision = decide(found, at)
            _score(metrics, case, decision)
            auto += decision.tier == "auto_answer"
        rows.append(
            {
                "threshold": threshold,
                "executive_recall": metrics.executive_recall,
                "category_accuracy": metrics.category_accuracy,
                "answered_share": auto / (len(answered) or 1),
                "missed_executive": float(len(metrics.missed_executive)),
            }
        )
    return rows


def evaluate_groundedness(
    handler: Handler,
    judge: Judge,
    cases: Sequence[GoldenCase],
    config: ClientConfig,
    knowledge: Mapping[str, KnowledgeEntry],
) -> GroundednessMetrics:
    """Answer every answerable case with ``handler`` and have ``judge`` grade it.

    A refusal counts against correctness, and a judge that fails is never a pass.
    """
    metrics = GroundednessMetrics()
    for case in answerable_cases(cases):
        decision = TriageDecision(**vars(case.expected_signals()), tier="auto_answer")
        result = handler.handle(HandlerRequest(as_incoming(case), decision, config))
        if result.outcome == "hand_off":
            metrics.record_refusal(case.id, result.reason)
            continue
        context = "\n\n".join(
            f"[{source.id}] {knowledge[source.id].text}"
            for source in result.sources
            if source.id in knowledge
        )
        top = max((source.score for source in result.sources), default=None)
        try:
            verdict = judge(
                question=case.text,
                answer=result.text,
                context=context,
                must_mention=case.must_mention,
                must_not_answer=case.must_not_answer,
            )
        except Exception as exc:
            metrics.record(case.id, False, f"judge failed ({type(exc).__name__})", top)
            continue
        metrics.record(case.id, verdict.passes, verdict.why_not(), top)
    return metrics


def sweep_answer_threshold(
    answers: Sequence[tuple[str, float, bool]],
    thresholds: Sequence[float] = DEFAULT_ANSWER_SWEEP,
) -> list[dict[str, float]]:
    """What each retrieval-score gate would have let through, judged by the judge."""
    rows: list[dict[str, float]] = []
    for threshold in thresholds:
        passed = [item for item in answers if item[1] >= threshold]
        correct = [item for item in passed if item[2]]
        rows.append(
            {
                "threshold": threshold,
                "answered": len(passed),
                "answered_share": len(passed) / (len(answers) or 1),
                "precision": len(correct) / (len(passed) or 1),
                "wrong_answers": len(passed) - len(correct),
            }
        )
    return rows


def triage_summary(
    metrics: TriageMetrics, *, classifier: str, threshold: float | None, cases: int
) -> dict[str, object]:
    """A JSON-ready summary: numbers, category names and case ids only."""
    return {
        "classifier": classifier,
        "confidence_threshold": threshold,
        "cases": cases,
        "errors": len(metrics.errors),
        "category_accuracy": round(metrics.category_accuracy, 4),
        "language_accuracy": round(metrics.language_accuracy, 4),
        "executive_recall": round(metrics.executive_recall, 4),
        "executive_gate_passed": metrics.passes_executive_gate(),
        "missed_executive_case_ids": sorted(
            {line.split(":", 1)[0] for line in metrics.missed_executive}
        ),
        "per_category": {
            name: {
                "support": counts.support,
                "precision": round(counts.precision, 4),
                "recall": round(counts.recall, 4),
            }
            for name, counts in sorted(metrics.per_category.items())
        },
        "per_tier_recall": {
            name: round(counts.recall, 4) for name, counts in sorted(metrics.per_tier.items())
        },
        "confusion": [
            {"expected": expected, "actual": actual, "count": count}
            for (expected, actual), count in sorted(metrics.confusion.items())
            if expected != actual
        ],
    }


def groundedness_summary(
    metrics: GroundednessMetrics, *, generator: str, judge: str, cases: int
) -> dict[str, object]:
    """A JSON-ready summary: numbers and case ids only."""
    return {
        "generator": generator,
        "judge": judge,
        "answerable_cases": cases,
        "judged": metrics.judged,
        "grounded": metrics.grounded,
        "refused": metrics.refused,
        "correctness": round(metrics.correctness, 4),
        "not_passed_case_ids": sorted(
            {line.split(":", 1)[0] for line in [*metrics.ungrounded, *metrics.failures]}
        ),
    }

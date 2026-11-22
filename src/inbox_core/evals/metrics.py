"""Metric arithmetic, kept apart from the runners that make model calls.

Split out so it can be tested in CI. A runner that computed its percentages
inline would only ever be exercised by a run that costs money, which is how a
confidently wrong recall number gets believed.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

__all__ = ["ClassCounts", "GroundednessMetrics", "TriageMetrics", "format_table", "percentage"]


@dataclass
class ClassCounts:
    """True positives, false positives and false negatives for one class."""

    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0

    @property
    def support(self) -> int:
        """How many cases genuinely belong to this class."""
        return self.true_positive + self.false_negative

    @property
    def precision(self) -> float:
        """Of what was called this class, how much was. 1.0 when nothing was."""
        predicted = self.true_positive + self.false_positive
        return 1.0 if predicted == 0 else self.true_positive / predicted

    @property
    def recall(self) -> float:
        """Of what genuinely was this class, how much was caught."""
        return 1.0 if self.support == 0 else self.true_positive / self.support


@dataclass
class TriageMetrics:
    """Per-category and per-tier counts, plus the two gate numbers."""

    per_category: dict[str, ClassCounts] = field(default_factory=dict)
    per_tier: dict[str, ClassCounts] = field(default_factory=dict)
    language_correct: int = 0
    language_total: int = 0
    confusion: Counter[tuple[str, str]] = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)
    missed_executive: list[str] = field(default_factory=list)

    def record(
        self,
        case_id: str,
        expected_category: str,
        actual_category: str,
        expected_tier: str,
        actual_tier: str,
        expected_language: str,
        actual_language: str,
    ) -> None:
        """Count one classified case."""
        self._count(self.per_category, expected_category, actual_category)
        self._count(self.per_tier, expected_tier, actual_tier)
        self.language_total += 1
        self.language_correct += expected_language == actual_language
        self.confusion[(expected_category, actual_category)] += 1
        if expected_tier == "needs_executive" and actual_tier != "needs_executive":
            self.missed_executive.append(
                f"{case_id}: expected needs_executive, got {actual_tier} "
                f"(category {expected_category} -> {actual_category})"
            )

    def record_error(self, case_id: str, reason: str) -> None:
        """A case the classifier could not answer at all. Fails the gate."""
        self.errors.append(f"{case_id}: {reason}")

    @staticmethod
    def _count(table: dict[str, ClassCounts], expected: str, actual: str) -> None:
        table.setdefault(expected, ClassCounts())
        table.setdefault(actual, ClassCounts())
        if expected == actual:
            table[expected].true_positive += 1
        else:
            table[expected].false_negative += 1
            table[actual].false_positive += 1

    @property
    def executive_recall(self) -> float:
        """Of the messages that had to reach a senior person, how many did."""
        counts = self.per_tier.get("needs_executive")
        return 1.0 if counts is None else counts.recall

    @property
    def language_accuracy(self) -> float:
        """Share of cases whose language was read correctly."""
        return 1.0 if self.language_total == 0 else self.language_correct / self.language_total

    @property
    def category_accuracy(self) -> float:
        """Share of cases given their expected category."""
        total = sum(counts.support for counts in self.per_category.values())
        correct = sum(counts.true_positive for counts in self.per_category.values())
        return 1.0 if total == 0 else correct / total

    def passes_executive_gate(self) -> bool:
        """100 percent recall on ``needs_executive`` and no case left unclassified."""
        return self.executive_recall == 1.0 and not self.missed_executive and not self.errors


@dataclass
class GroundednessMetrics:
    """How often an answerable case was answered, and answered from the facts."""

    judged: int = 0
    grounded: int = 0
    refused: int = 0
    failures: list[str] = field(default_factory=list)
    ungrounded: list[str] = field(default_factory=list)
    answers: list[tuple[str, float, bool]] = field(default_factory=list)

    def record(
        self, case_id: str, is_grounded: bool, reason: str = "", similarity: float | None = None
    ) -> None:
        """Count one judged answer, with its top retrieval score if known."""
        self.judged += 1
        if similarity is not None:
            self.answers.append((case_id, similarity, is_grounded))
        if is_grounded:
            self.grounded += 1
        else:
            self.ungrounded.append(f"{case_id}: {reason}" if reason else case_id)

    def record_refusal(self, case_id: str, reason: str) -> None:
        """The handler declined an answerable case: safe, and still a miss."""
        self.refused += 1
        self.failures.append(f"{case_id}: {reason}")

    @property
    def total(self) -> int:
        """Every answerable case, judged or refused."""
        return self.judged + self.refused

    @property
    def correctness(self) -> float:
        """Grounded answers over every answerable case, refusals included."""
        return 1.0 if self.total == 0 else self.grounded / self.total

    def passes_gate(self, threshold: float = 0.9) -> bool:
        """Whether correctness reaches ``threshold``."""
        return self.correctness >= threshold


def percentage(value: float) -> str:
    """``0.5`` as ``"50.0%"``."""
    return f"{value * 100:.1f}%"


def format_table(rows: Sequence[Sequence[str]], headers: Sequence[str]) -> str:
    """A plain-text table for a terminal."""
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))

    def line(cells: Sequence[str]) -> str:
        return "  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(cells)).rstrip()

    separator = "  ".join("-" * width for width in widths)
    return "\n".join([line(headers), separator, *(line(row) for row in rows)])

"""The triage contract: typed signals in, a tier out, decided in code.

A classifier is asked only what a classifier can be trusted with: what the
message is about, what language it is in, whether the writer asked for a
person, and whether money or a commitment is mentioned. It is never asked what
to do. :func:`derive_tier` decides that, from the client's category table,
because the consequence of a wrong tier on a sensitive message is not a quality
problem.

The four rules, in this order, and the order is the design:

1. An executive category, or any mention of money or a commitment, is
   ``needs_executive``. First, so nothing below can talk it down.
2. Otherwise a skipped category (``automated``) is ``skip``, whatever the
   confidence and even if the text "asks for a person": an auto-responder
   saying "contact my colleague" must not start a loop.
3. Otherwise an unsupported language, an explicit ask for a person, or a
   confidence below the threshold (or not a finite number) is ``needs_admin``.
   This is the fail-closed rule.
4. Otherwise ``auto_answer`` if the category may be auto-answered, and
   ``needs_admin`` for everything else, including a category the table does
   not list.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Literal, Protocol, runtime_checkable

from inbox_core.config import TriagePolicy
from inbox_core.messages import IncomingMessage

__all__ = [
    "ESCALATING_TIERS",
    "TIERS",
    "Tier",
    "TriageClassifier",
    "TriageDecision",
    "TriageSignals",
    "TriageUnavailable",
    "decide",
    "derive_tier",
    "escalation_reason",
    "is_confident",
]

Tier = Literal["auto_answer", "needs_admin", "needs_executive", "skip"]
"""Who handles a message: the assistant, a person, a senior person, or nobody."""

TIERS: tuple[Tier, ...] = ("auto_answer", "needs_admin", "needs_executive", "skip")

ESCALATING_TIERS: frozenset[Tier] = frozenset({"needs_admin", "needs_executive"})
"""Tiers that hand a message to a person."""

_SAFE_CODE = re.compile(r"^[a-z]{2,3}(-[a-z0-9]{2,8})?$")


class TriageUnavailable(RuntimeError):  # noqa: N818 - the established name clients catch
    """The classifier could not produce a usable answer.

    Raised rather than guessed, for a transport failure and for a malformed
    response alike. The pipeline retries a bounded number of times and then
    treats the message as ``needs_admin``: an unavailable classifier must never
    silently become "probably an FAQ". The message carries ids only.
    """


@dataclass(frozen=True)
class TriageSignals:
    """What a classifier reports. No tier, deliberately."""

    category: str
    language: str
    confidence: float
    asks_for_human: bool
    mentions_money_or_commitment: bool
    classifier: str

    def as_record(self) -> dict[str, object]:
        """A JSON-ready form holding categories, codes and numbers only."""
        return {
            "category": self.category,
            "language": self.language,
            "confidence": round(float(self.confidence), 4),
            "asks_for_human": bool(self.asks_for_human),
            "mentions_money_or_commitment": bool(self.mentions_money_or_commitment),
            "classifier": self.classifier,
        }


@dataclass(frozen=True)
class TriageDecision(TriageSignals):
    """Signals plus the tier the policy derived from them."""

    tier: Tier = "needs_admin"

    def signals(self) -> TriageSignals:
        """The classifier's signals without the tier."""
        return TriageSignals(
            category=self.category,
            language=self.language,
            confidence=self.confidence,
            asks_for_human=self.asks_for_human,
            mentions_money_or_commitment=self.mentions_money_or_commitment,
            classifier=self.classifier,
        )

    def with_tier(self, tier: Tier) -> TriageDecision:
        """A copy with another tier, for an escalation decided after triage."""
        return replace(self, tier=tier)


@runtime_checkable
class TriageClassifier(Protocol):
    """One call, four answers. Raises :class:`TriageUnavailable` rather than guessing."""

    name: str

    def classify(self, message: IncomingMessage) -> TriageSignals:
        """The signals for ``message``."""
        ...


def is_confident(confidence: float, policy: TriagePolicy) -> bool:
    """Whether ``confidence`` clears the policy's threshold. Never true for NaN."""
    threshold = policy.confidence_threshold
    return threshold is not None and math.isfinite(confidence) and confidence >= threshold


def derive_tier(signals: TriageSignals, policy: TriagePolicy) -> Tier:
    """Which tier handles this message. Pure, deterministic, never chosen by a model."""
    rule = policy.category(signals.category)
    if (rule is not None and rule.escalates_to == "needs_executive") or (
        signals.mentions_money_or_commitment
    ):
        return "needs_executive"

    if rule is not None and rule.escalates_to == "skip":
        return "skip"

    if (
        signals.language not in policy.languages
        or signals.asks_for_human
        or not is_confident(signals.confidence, policy)
    ):
        return "needs_admin"

    if rule is not None and rule.auto_answer:
        return "auto_answer"
    return "needs_admin"


def decide(signals: TriageSignals, policy: TriagePolicy) -> TriageDecision:
    """``signals`` plus its derived tier, as one immutable record."""
    return TriageDecision(
        category=signals.category,
        language=signals.language,
        confidence=signals.confidence,
        asks_for_human=signals.asks_for_human,
        mentions_money_or_commitment=signals.mentions_money_or_commitment,
        classifier=signals.classifier,
        tier=derive_tier(signals, policy),
    )


def escalation_reason(signals: TriageSignals, policy: TriagePolicy) -> str:
    """One short phrase saying why a message escalated.

    Categories, codes and numbers only: this string reaches the audit record
    and the notifier, so it must not be able to carry any of the message.
    """
    if signals.category in policy.executive_categories:
        return f"executive category {signals.category}"
    if signals.mentions_money_or_commitment:
        return "mentions money or a commitment"
    if signals.asks_for_human:
        return "the sender asked for a person"
    if signals.language not in policy.languages:
        shown = signals.language if _SAFE_CODE.match(signals.language) else "code"
        return f"unsupported language {shown}"
    if not is_confident(signals.confidence, policy):
        threshold = policy.confidence_threshold or 0.0
        return f"confidence {signals.confidence:.2f} below threshold {threshold:.2f}"
    if policy.category(signals.category) is None:
        return "an unlisted category is handled by a person"
    return f"category {signals.category} is handled by a person"

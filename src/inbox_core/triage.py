"""The triage contract: typed signals in, a tier out, decided in code.

A classifier is asked only what a classifier can be trusted with: what the
message is about, what language it is in, whether the writer asked for a
person, and whether money or a commitment is mentioned (and, for a client that
answers prices, whether that mention is only a question about a usual price).
It is never asked what to do. :func:`derive_tier` decides that, from the client's category table,
because the consequence of a wrong tier on a sensitive message is not a quality
problem.

The four rules, in this order, and the order is the design:

1. An executive category, or any mention of money or a commitment, is
   ``needs_executive``. First, so nothing below can talk it down. The one
   exception is a client's own choice: with ``triage.prices`` set to anything
   but ``always_hand_off``, a message whose only money is a question about a
   usual price (:func:`is_price_question`) is not escalated by this rule; it
   is triaged by the rules below like any other, and the pipeline checks the
   reply's prices in code before anything is delivered.
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
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal, Protocol, runtime_checkable

from inbox_core.config import TriagePolicy
from inbox_core.messages import IncomingMessage

__all__ = [
    "ESCALATING_TIERS",
    "TIERS",
    "RetryingClassifier",
    "Tier",
    "TriageClassifier",
    "TriageDecision",
    "TriageSignals",
    "TriageUnavailable",
    "decide",
    "derive_tier",
    "escalation_reason",
    "is_confident",
    "is_price_question",
    "signals_from_payload",
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
    """What a classifier reports. No tier, deliberately.

    ``asks_listed_price`` is asked only of a client whose ``triage.prices``
    answers prices: every mention of money in the message is a question about
    what something usually costs, with no refund, discount, dispute,
    negotiation or custom quote. It is false for everyone else.
    """

    category: str
    language: str
    confidence: float
    asks_for_human: bool
    mentions_money_or_commitment: bool
    classifier: str
    asks_listed_price: bool = False

    def as_record(self) -> dict[str, object]:
        """A JSON-ready form holding categories, codes and numbers only."""
        record: dict[str, object] = {
            "category": self.category,
            "language": self.language,
            "confidence": round(float(self.confidence), 4),
            "asks_for_human": bool(self.asks_for_human),
            "mentions_money_or_commitment": bool(self.mentions_money_or_commitment),
            "classifier": self.classifier,
        }
        if self.asks_listed_price:
            record["asks_listed_price"] = True
        return record


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
            asks_listed_price=self.asks_listed_price,
        )

    def with_tier(self, tier: Tier) -> TriageDecision:
        """A copy with another tier, for an escalation decided after triage."""
        return replace(self, tier=tier)


@runtime_checkable
class TriageClassifier(Protocol):
    """One call, four answers. Raises :class:`TriageUnavailable` rather than guessing."""

    @property
    def name(self) -> str:
        """A short identifier for audit records and logs."""
        ...

    def classify(self, message: IncomingMessage) -> TriageSignals:
        """The signals for ``message``."""
        ...


def is_confident(confidence: float, policy: TriagePolicy) -> bool:
    """Whether ``confidence`` clears the policy's threshold. Never true for NaN."""
    threshold = policy.confidence_threshold
    return threshold is not None and math.isfinite(confidence) and confidence >= threshold


def is_price_question(signals: TriageSignals, policy: TriagePolicy) -> bool:
    """Whether the money this message mentions is only a usual-price question the client answers.

    Never true under ``triage.prices = "always_hand_off"``, so for such a
    client every mention of money stays ``needs_executive``.
    """
    return (
        policy.answers_prices
        and bool(signals.mentions_money_or_commitment)
        and signals.asks_listed_price is True
    )


def derive_tier(signals: TriageSignals, policy: TriagePolicy) -> Tier:
    """Which tier handles this message. Pure, deterministic, never chosen by a model."""
    rule = policy.category(signals.category)
    money = signals.mentions_money_or_commitment and not is_price_question(signals, policy)
    if (rule is not None and rule.escalates_to == "needs_executive") or money:
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
        asks_listed_price=signals.asks_listed_price,
        tier=derive_tier(signals, policy),
    )


def escalation_reason(signals: TriageSignals, policy: TriagePolicy) -> str:
    """One short phrase saying why a message escalated.

    Categories, codes and numbers only: this string reaches the audit record
    and the notifier, so it must not be able to carry any of the message.
    """
    if signals.category in policy.executive_categories:
        return f"executive category {signals.category}"
    if signals.mentions_money_or_commitment and not is_price_question(signals, policy):
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


_SIGNAL_FLAGS = ("asks_for_human", "mentions_money_or_commitment")
_PRICE_FLAG = "asks_listed_price"


def signals_from_payload(
    payload: object, policy: TriagePolicy, *, classifier: str, message_id: str
) -> TriageSignals:
    """Validate a classifier's raw answer against the client's table, or raise.

    Shared by every adapter so they refuse the same things. ``asks_listed_price``
    is required, and read, only when the client's ``triage.prices`` answers
    prices. A category outside
    the table is a malformed answer, not a new category: mapping it to a
    default would let a model typo choose a tier. Exception messages carry the
    message id and the field name, never the offending value, because a model
    can echo the message into any field.
    """
    if not isinstance(payload, dict):
        raise TriageUnavailable(
            f"{classifier} returned a {type(payload).__name__} for message {message_id}"
        )
    category = payload.get("category")
    if not isinstance(category, str) or policy.category(category) is None:
        raise TriageUnavailable(f"{classifier} returned an unknown category for {message_id}")
    language = payload.get("language")
    if not isinstance(language, str) or (language not in policy.languages and language != "other"):
        raise TriageUnavailable(f"{classifier} returned an unknown language for {message_id}")

    raw_confidence = payload.get("confidence")
    if isinstance(raw_confidence, bool) or not isinstance(raw_confidence, int | float | str):
        raise TriageUnavailable(f"{classifier} returned no numeric confidence for {message_id}")
    try:
        confidence = float(raw_confidence)
    except ValueError:
        raise TriageUnavailable(
            f"{classifier} returned an unreadable confidence for {message_id}"
        ) from None
    if not math.isfinite(confidence):
        raise TriageUnavailable(f"{classifier} returned a non-finite confidence for {message_id}")

    flags = (*_SIGNAL_FLAGS, _PRICE_FLAG) if policy.answers_prices else _SIGNAL_FLAGS
    for name in flags:
        if not isinstance(payload.get(name), bool):
            raise TriageUnavailable(f"{classifier} returned a non-boolean {name} for {message_id}")

    return TriageSignals(
        category=category,
        language=language,
        confidence=max(0.0, min(1.0, confidence)),
        asks_for_human=payload["asks_for_human"],
        mentions_money_or_commitment=payload["mentions_money_or_commitment"],
        classifier=classifier,
        # Read only when the client answers prices; otherwise never asked, never trusted.
        asks_listed_price=bool(payload.get(_PRICE_FLAG)) if policy.answers_prices else False,
    )


class RetryingClassifier:
    """A classifier that retries a bounded number of times, then fails closed.

    Any exception from the inner classifier counts as unavailable, not only
    :class:`TriageUnavailable`: a bug in an adapter must lead to a person, not
    to a crash that leaves the message unhandled. Only the exception's type
    name is kept, because a provider error can echo the prompt. ``sleep`` is
    injectable so tests never wait.
    """

    def __init__(
        self,
        inner: TriageClassifier,
        *,
        attempts: int = 3,
        backoff: tuple[float, ...] = (0.5, 2.0),
        sleep: Callable[[float], object] = time.sleep,
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        self._inner = inner
        self._attempts = attempts
        self._backoff = backoff
        self._sleep = sleep

    @property
    def name(self) -> str:
        """The inner classifier's name, so audit records name the real model."""
        return self._inner.name

    def classify(self, message: IncomingMessage) -> TriageSignals:
        """The inner classifier's signals, or :class:`TriageUnavailable` after the bound."""
        last = "TriageUnavailable"
        for attempt in range(self._attempts):
            if attempt:
                step = min(attempt - 1, len(self._backoff) - 1)
                if step >= 0:
                    self._sleep(self._backoff[step])
            try:
                return self._inner.classify(message)
            except TriageUnavailable:
                last = "TriageUnavailable"
            except Exception as exc:
                last = type(exc).__name__
        raise TriageUnavailable(
            f"classifier {self.name} unavailable after {self._attempts} attempts for "
            f"{message.provider_message_id} (last error: {last})"
        )

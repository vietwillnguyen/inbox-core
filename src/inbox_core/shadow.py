"""Shadow mode: run the decider, then a second classifier, and record both.

The decider's answer is what comes back, always. The shadow's answer is kept
out of band (``last_shadow``) and never influences anything, which is what
makes a disagreement report an honest measurement.

A shadow failure is swallowed on purpose: the shadow exists to be measured,
and its model being over quota must not cost a triaged message. A decider
failure propagates, because the pipeline must fail closed on it.
"""

from __future__ import annotations

import logging

from inbox_core.messages import IncomingMessage
from inbox_core.triage import TriageClassifier, TriageSignals

__all__ = ["ShadowingClassifier", "agreement"]

logger = logging.getLogger("inbox_core.shadow")


class ShadowingClassifier:
    """Decorates a decider with a non-authoritative second opinion."""

    def __init__(self, decider: TriageClassifier, shadow: TriageClassifier | None = None) -> None:
        self._decider = decider
        self._shadow = shadow
        self.last_shadow: TriageSignals | None = None

    @property
    def name(self) -> str:
        """The decider's name: it is the one whose answer counts."""
        return self._decider.name

    def classify(self, message: IncomingMessage) -> TriageSignals:
        """The decider's signals. ``last_shadow`` holds the shadow's, if any."""
        self.last_shadow = None
        decided = self._decider.classify(message)
        self.last_shadow = self._run_shadow(message)
        return decided

    def _run_shadow(self, message: IncomingMessage) -> TriageSignals | None:
        if self._shadow is None:
            return None
        try:
            return self._shadow.classify(message)
        except Exception as exc:
            logger.warning(
                "shadow classifier failed for %s: %s",
                message.provider_message_id,
                type(exc).__name__,
            )
            return None


def agreement(decided: TriageSignals, shadow: TriageSignals | None) -> dict[str, bool]:
    """Field-by-field agreement, because "they disagreed" alone is not actionable.

    Confidence is not compared: a calibrated probability and a model's
    self-report are different scales, and comparing them manufactures noise.
    """
    if shadow is None:
        return {}
    return {
        "category": decided.category == shadow.category,
        "language": decided.language == shadow.language,
        "asks_for_human": decided.asks_for_human == shadow.asks_for_human,
        "mentions_money_or_commitment": (
            decided.mentions_money_or_commitment == shadow.mentions_money_or_commitment
        ),
    }

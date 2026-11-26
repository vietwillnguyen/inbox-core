"""Classification through Jev, the TypeSafe system-one classifier.

Jev answers the four questions in one ``system_one`` call: category and
language as ``choice`` questions, the two booleans as ``noul`` questions. Its
category confidence is a per-option probability rather than a model's opinion
of itself, which is why it is worth having as a decider.

Optional: ``typesafe_sdk`` is imported only by :meth:`JevClassifier.from_api_key`.
Install it with ``pip install 'inbox-core[jev]'``. Any client object with a
compatible ``system_one`` method can be passed instead.
"""

from __future__ import annotations

import importlib
from typing import Any

from inbox_core.config import ClientConfig
from inbox_core.messages import IncomingMessage
from inbox_core.prompts import classifier_input, render_triage_prompts
from inbox_core.triage import TriageSignals, TriageUnavailable, signals_from_payload

__all__ = ["DEFAULT_MODEL", "NOUL_TRUE_AT", "JevClassifier", "build_questions"]

DEFAULT_MODEL = "jev-latest"
"""The Jev model used unless another is named."""

NOUL_TRUE_AT = 0.5
"""A ``noul`` answer is a probability of yes; both are used to escalate, so 0.5 is the cut."""

Q_CATEGORY = "category"
Q_LANGUAGE = "language"
Q_ASKS_FOR_HUMAN = "asks_for_human"
Q_MONEY = "mentions_money_or_commitment"
Q_LISTED_PRICE = "asks_listed_price"


def build_questions(config: ClientConfig) -> dict[str, Any]:
    """The questions as plain dictionaries, rendered from the client config.

    Four, and a fifth (``asks_listed_price``) for a client that answers prices.
    """
    prompts = render_triage_prompts(config)
    policy = config.triage
    questions: dict[str, Any] = {
        Q_CATEGORY: {
            "type": "choice",
            "instructions": prompts.category,
            "criteria": dict.fromkeys(rule.name for rule in policy.categories),
        },
        Q_LANGUAGE: {
            "type": "choice",
            "instructions": prompts.language,
            "criteria": dict.fromkeys([*policy.languages, "other"]),
        },
        Q_ASKS_FOR_HUMAN: {"type": "noul", "instructions": prompts.asks_for_human},
        Q_MONEY: {"type": "noul", "instructions": prompts.money},
    }
    if policy.answers_prices:
        questions[Q_LISTED_PRICE] = {"type": "noul", "instructions": prompts.listed_price}
    return questions


class JevClassifier:
    """A :class:`inbox_core.triage.TriageClassifier` over a Jev client."""

    def __init__(self, config: ClientConfig, client: Any, *, model: str = DEFAULT_MODEL) -> None:
        self._policy = config.triage
        self._questions = build_questions(config)
        self._client = client
        self._model = model

    @classmethod
    def from_api_key(
        cls, config: ClientConfig, api_key: str, *, model: str = DEFAULT_MODEL
    ) -> JevClassifier:
        """Build the vendor client. Imports ``typesafe_sdk`` here and only here."""
        try:
            sdk = importlib.import_module("typesafe_sdk")
        except ImportError:
            raise ImportError("the Jev adapter needs: pip install 'inbox-core[jev]'") from None
        return cls(config, sdk.TypeSafeClient(api_key=api_key, model=model), model=model)

    @property
    def name(self) -> str:
        """Includes the model, so a mid-window model change is visible in reports."""
        return f"jev:{self._model}"

    def classify(self, message: IncomingMessage) -> TriageSignals:
        """One ``system_one`` call, validated against the client's table."""
        message_id = message.provider_message_id
        try:
            response = self._client.system_one(
                state=classifier_input(message), questions=self._questions, model=self._model
            )
        except Exception as exc:
            raise TriageUnavailable(
                f"Jev classification failed for {message_id}: {type(exc).__name__}"
            ) from None

        try:
            choices = response.choices
            nouls = response.nouls
            payload = {
                "category": choices[Q_CATEGORY].choice,
                "language": choices[Q_LANGUAGE].choice,
                "confidence": choices[Q_CATEGORY].confidence,
                "asks_for_human": float(nouls[Q_ASKS_FOR_HUMAN].noul) >= NOUL_TRUE_AT,
                "mentions_money_or_commitment": float(nouls[Q_MONEY].noul) >= NOUL_TRUE_AT,
            }
            if Q_LISTED_PRICE in self._questions:
                payload[Q_LISTED_PRICE] = float(nouls[Q_LISTED_PRICE].noul) >= NOUL_TRUE_AT
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise TriageUnavailable(
                f"Jev returned an unreadable answer set for {message_id}: {type(exc).__name__}"
            ) from None
        return signals_from_payload(
            payload, self._policy, classifier=self.name, message_id=message_id
        )

    def close(self) -> None:
        """Close the vendor client if it has a ``close`` method."""
        close = getattr(self._client, "close", None)
        if callable(close):
            close()

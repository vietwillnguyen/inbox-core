"""Classification through LiteLLM, over one JSON-schema structured call.

LiteLLM is the seam rather than a vendor SDK because the model is a setting:
the same class reaches Gemini directly, or any model behind a LiteLLM gateway
(pass ``api_base``), with no code change.

``litellm`` is imported only when a call is made and no ``completion`` function
was injected, so the core installs and imports without it. Install it with
``pip install 'inbox-core[litellm]'``.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from typing import Any

from inbox_core.config import ClientConfig
from inbox_core.handlers import GenerationRequest
from inbox_core.messages import IncomingMessage
from inbox_core.prompts import REFUSAL_SENTINEL, classifier_input, render_triage_prompts
from inbox_core.triage import TriageSignals, TriageUnavailable, signals_from_payload

__all__ = [
    "DEFAULT_MODEL",
    "LiteLLMClassifier",
    "LiteLLMGenerator",
    "first_content",
    "load_completion",
]

DEFAULT_MODEL = "gemini/gemini-3.5-flash-lite"
"""Gemini Flash-Lite, the default classifier model. Override with ``model``."""

Completion = Callable[..., Any]


def load_completion() -> Completion:
    """``litellm.completion``, or an ImportError that names the extra to install."""
    try:
        module = importlib.import_module("litellm")
    except ImportError:
        raise ImportError("the LiteLLM adapter needs: pip install 'inbox-core[litellm]'") from None
    completion: Completion = module.completion
    return completion


def first_content(response: Any) -> str:
    """The text of the first choice, whether the response is an object or a dict."""
    if isinstance(response, dict):
        choices = response.get("choices") or []
        if not choices:
            raise TriageUnavailable("LiteLLM returned no choices")
        message = choices[0].get("message") or {}
        return str(message.get("content") or "")
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise TriageUnavailable("LiteLLM returned no choices")
    return str(getattr(getattr(choices[0], "message", None), "content", "") or "")


class LiteLLMClassifier:
    """A :class:`inbox_core.triage.TriageClassifier` over ``litellm.completion``.

    Its confidence is the model's own report and is uncalibrated; calibrate
    the threshold against a golden set before trusting it (see
    :mod:`inbox_core.evals`).
    """

    def __init__(
        self,
        config: ClientConfig,
        *,
        model: str = DEFAULT_MODEL,
        completion: Completion | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._policy = config.triage
        self._system = render_triage_prompts(config).system
        self._schema = _schema(config)
        self._model = model
        self._completion = completion if completion is not None else load_completion()
        self._api_key = api_key
        self._api_base = api_base
        self._timeout = timeout

    @property
    def name(self) -> str:
        """Includes the model, because the model is the setting that varies."""
        return f"litellm:{self._model}"

    def classify(self, message: IncomingMessage) -> TriageSignals:
        """One structured call, validated against the client's table."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._system},
                {
                    "role": "user",
                    "content": json.dumps(classifier_input(message), ensure_ascii=False),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "triage", "schema": self._schema, "strict": True},
            },
            "temperature": 0,
            "timeout": self._timeout,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._api_base:
            kwargs["api_base"] = self._api_base

        try:
            content = first_content(self._completion(**kwargs))
        except TriageUnavailable:
            raise
        except Exception as exc:
            # ``from None``: a provider exception can echo the prompt, and the
            # chain is what an error tracker would render.
            raise TriageUnavailable(
                f"LiteLLM classification failed for {message.provider_message_id}: "
                f"{type(exc).__name__}"
            ) from None

        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            raise TriageUnavailable(
                f"LiteLLM returned non-JSON for {message.provider_message_id}"
            ) from None
        return signals_from_payload(
            payload, self._policy, classifier=self.name, message_id=message.provider_message_id
        )


def _schema(config: ClientConfig) -> dict[str, Any]:
    policy = config.triage
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": [rule.name for rule in policy.categories]},
            "language": {"type": "string", "enum": [*policy.languages, "other"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "asks_for_human": {"type": "boolean"},
            "mentions_money_or_commitment": {"type": "boolean"},
        },
        "required": [
            "category",
            "language",
            "confidence",
            "asks_for_human",
            "mentions_money_or_commitment",
        ],
        "additionalProperties": False,
    }


class LiteLLMGenerator:
    """A :class:`inbox_core.handlers.Generator` over ``litellm.completion``.

    The system message is the answer instructions followed by the passages,
    each labelled with its id; the user message is the sender's subject and
    text. Errors propagate: :class:`inbox_core.handlers.GroundedAnswer` turns
    them into a hand-off.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        completion: Completion | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._model = model
        self._completion = completion if completion is not None else load_completion()
        self._api_key = api_key
        self._api_base = api_base
        self._timeout = timeout

    @property
    def name(self) -> str:
        """Includes the model."""
        return f"litellm:{self._model}"

    def generate(self, request: GenerationRequest) -> str:
        """The model's answer, or the refusal sentinel when it returns nothing."""
        context = "\n\n".join(
            f"[{p.entry.id}] {p.entry.title}\n{p.entry.text}" for p in request.passages
        )
        question = request.question
        if request.subject:
            question = f"Subject: {request.subject}\n\n{question}"
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": f"{request.instructions}\n\nContext:\n{context}"},
                {"role": "user", "content": question},
            ],
            "temperature": 0,
            "timeout": self._timeout,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._api_base:
            kwargs["api_base"] = self._api_base
        return first_content(self._completion(**kwargs)).strip() or REFUSAL_SENTINEL

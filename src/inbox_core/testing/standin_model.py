"""A deterministic stand-in for a chat model, so a whole deployment runs with no key.

It is not a model and it is not accurate. It answers the two calls the core's
LiteLLM adapters make, in the shape they expect:

- **Classification** (:class:`inbox_core.adapters.litellm.LiteLLMClassifier`):
  the user message is the JSON of :func:`inbox_core.prompts.classifier_input`.
  The reply is the JSON object the triage schema asks for, chosen by ordered
  keyword rules read from a TOML file. A message no rule matches is reported
  as the fallback category with a confidence below any sensible threshold, so
  it reaches a person, as an unsure model's answer would.
- **Grounded answers** (:class:`inbox_core.adapters.litellm.LiteLLMGenerator`):
  the system message ends with ``Context:`` and the retrieved passages. The
  reply is the first passage's text, verbatim, or the refusal sentinel when
  there is none.

A call is told apart by that ``Context:`` section, which only the generator
sends. The module uses the standard library only, so a LiteLLM gateway can load
it as a custom provider without installing the core (``deploy/demo/litellm``).
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["REFUSAL", "StandInError", "StandInModel"]

REFUSAL = "INSUFFICIENT_CONTEXT"
"""The refusal sentinel; the same text as :data:`inbox_core.prompts.REFUSAL_SENTINEL`."""

_CONTEXT = "\n\nContext:\n"
_PASSAGE = re.compile(r"^\[[^\]\n]+\] [^\n]*\n", re.MULTILINE)
_KEYS = {
    "fallback_category",
    "language",
    "confidence",
    "unsure_confidence",
    "other_language",
    "asks_for_human",
    "mentions_money",
    "rules",
}


class StandInError(ValueError):
    """The stand-in's rules file is missing or malformed."""


def _patterns(values: object, where: str) -> tuple[re.Pattern[str], ...]:
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise StandInError(f"{where} must be a list of patterns")
    compiled = []
    for value in values:
        try:
            compiled.append(re.compile(value, re.IGNORECASE))
        except re.error:
            raise StandInError(f"{where}: {value!r} is not a valid pattern") from None
    return tuple(compiled)


def _any(patterns: Sequence[re.Pattern[str]], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


@dataclass(frozen=True)
class StandInModel:
    """Ordered category rules, and the patterns for the other triage signals."""

    rules: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...]
    fallback_category: str = "other"
    language: str = "en"
    confidence: float = 0.9
    unsure_confidence: float = 0.3
    other_language: tuple[re.Pattern[str], ...] = ()
    asks_for_human: tuple[re.Pattern[str], ...] = ()
    mentions_money: tuple[re.Pattern[str], ...] = ()

    @classmethod
    def from_file(cls, path: str | Path) -> StandInModel:
        """Read the rules from a TOML file. Raises :class:`StandInError`."""
        source = Path(path)
        if not source.is_file():
            raise StandInError(f"no stand-in rules at {source.name}")
        try:
            data = tomllib.loads(source.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise StandInError(f"not valid TOML: {exc}") from None
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> StandInModel:
        """Build from parsed TOML. Raises :class:`StandInError`."""
        unknown = sorted(set(data) - _KEYS)
        if unknown:
            raise StandInError(f"unknown key {unknown[0]!r}")
        raw_rules = data.get("rules", [])
        if not isinstance(raw_rules, list) or not raw_rules:
            raise StandInError("the stand-in needs at least one rule")
        rules = []
        for index, rule in enumerate(raw_rules):
            where = f"rules[{index}]"
            if not isinstance(rule, Mapping):
                raise StandInError(f"{where} must be a table")
            category = rule.get("category")
            if not isinstance(category, str) or not category.strip():
                raise StandInError(f"{where} needs a category")
            patterns = _patterns(rule.get("patterns"), f"{where}.patterns")
            if not patterns:
                raise StandInError(f"{where} needs patterns")
            rules.append((category, patterns))
        return cls(
            rules=tuple(rules),
            fallback_category=str(data.get("fallback_category", "other")),
            language=str(data.get("language", "en")),
            confidence=float(data.get("confidence", 0.9)),
            unsure_confidence=float(data.get("unsure_confidence", 0.3)),
            other_language=_patterns(data.get("other_language", []), "other_language"),
            asks_for_human=_patterns(data.get("asks_for_human", []), "asks_for_human"),
            mentions_money=_patterns(data.get("mentions_money", []), "mentions_money"),
        )

    def complete(self, messages: Sequence[Mapping[str, Any]]) -> str:
        """The reply text for one chat call: a triage JSON object, or an answer."""
        system = "\n".join(
            str(m.get("content") or "") for m in messages if m.get("role") == "system"
        )
        user = next(
            (str(m.get("content") or "") for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        if _CONTEXT in system:
            return self.answer(system.split(_CONTEXT, 1)[1])
        return json.dumps(self.classify(user))

    def classify(self, user_content: str) -> dict[str, object]:
        """The triage signals for one classifier input."""
        try:
            shown = json.loads(user_content)
        except json.JSONDecodeError:
            shown = None
        if isinstance(shown, Mapping):
            text = f"{shown.get('subject') or ''}\n{shown.get('body') or ''}"
        else:
            text = user_content
        category, confidence = self.fallback_category, self.unsure_confidence
        for name, patterns in self.rules:
            if _any(patterns, text):
                category, confidence = name, self.confidence
                break
        return {
            "category": category,
            "language": "other" if _any(self.other_language, text) else self.language,
            "confidence": confidence,
            "asks_for_human": _any(self.asks_for_human, text),
            "mentions_money_or_commitment": _any(self.mentions_money, text),
        }

    @staticmethod
    def answer(context: str) -> str:
        """The first passage's text, or :data:`REFUSAL` when the context has none."""
        found = _PASSAGE.search(context)
        if found is None:
            return REFUSAL
        rest = context[found.end() :]
        following = _PASSAGE.search(rest)
        text = (rest[: following.start()] if following else rest).strip()
        return text or REFUSAL

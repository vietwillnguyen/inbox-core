"""Handlers: the pluggable step that decides what to say to a message.

The pipeline calls a handler only for a message whose tier is ``auto_answer``,
choosing it by category from a :class:`HandlerRegistry`. A handler returns a
:class:`HandlerResult`: a reply to deliver, or a hand-off to a person. It never
sends anything itself and never chooses a tier; delivery and escalation stay in
the pipeline, so every handler inherits the same modes, gates and caps.

Three built-ins:

- :class:`GroundedAnswer` answers from retrieved knowledge entries and returns
  the sources it used, refusing when nothing scores above its threshold. The
  sources travel beside the text, never in it: the pipeline keeps them for
  staff, and when the client opts in (``delivery.show_sources``) adds a line
  linking to the public pages of the ones that have one, never an id or title.
- :class:`Template` returns fixed text the client wrote, chosen by language.
- :class:`HandOff` always hands off.

How later handler kinds fit without changing this protocol is described in
``docs/design.md`` ("Handlers").
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Protocol, runtime_checkable

from inbox_core.config import ClientConfig, ConfigError
from inbox_core.knowledge import Passage, Retriever
from inbox_core.messages import IncomingMessage
from inbox_core.prompts import REFUSAL_SENTINEL, render_answer_instructions
from inbox_core.triage import TriageDecision

__all__ = [
    "ExtractiveGenerator",
    "GenerationRequest",
    "Generator",
    "GroundedAnswer",
    "HandOff",
    "Handler",
    "HandlerRegistry",
    "HandlerRequest",
    "HandlerResult",
    "Outcome",
    "Source",
    "Template",
]

logger = logging.getLogger("inbox_core.handlers")

Outcome = Literal["reply", "hand_off"]
"""What a handler decided: deliver this text, or give the message to a person."""

MAX_REASON = 120
_TAG = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,63}$")


@dataclass(frozen=True)
class Source:
    """A knowledge entry a reply was grounded in, recorded by id and title.

    ``url`` is the entry's public page, when it has one. The id and title are
    for staff; the url is the only part the public may be shown, and only
    when the client sets ``delivery.show_sources``.

    ``passage`` is the title and text the reply was written from. The
    pipeline's published-price check (:mod:`inbox_core.prices`) reads it; it
    is never stored, audited or shown. A handler that leaves it empty cites
    no price, so any price in its reply is unstated.
    """

    id: str
    title: str
    score: float
    url: str | None = None
    passage: str = field(default="", repr=False, compare=False)


@dataclass(frozen=True)
class HandlerRequest:
    """Everything a handler is given about one message.

    One object rather than positional arguments so that the core can add
    context later (the conversation so far, a tool budget) as new fields with
    defaults, and existing handlers keep working unchanged.
    """

    message: IncomingMessage
    decision: TriageDecision
    config: ClientConfig


@dataclass(frozen=True)
class HandlerResult:
    """What a handler decided.

    ``kind`` names the handler, for the audit record and per-path metrics.
    ``reason`` says why a hand-off happened, as a short fixed phrase.
    ``requires_approval`` makes delivery hold the reply for a person whatever
    the mode, which is how a handler that proposes an action asks for sign-off.
    ``tags`` are identifiers for the audit record, such as ``tool:order_lookup``;
    the pattern they must match cannot carry free text.
    """

    outcome: Outcome
    kind: str
    text: str = field(default="", repr=False)
    sources: tuple[Source, ...] = ()
    reason: str = ""
    requires_approval: bool = False
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.outcome not in ("reply", "hand_off"):
            raise ValueError("outcome must be 'reply' or 'hand_off'")
        if self.outcome == "reply" and not self.text.strip():
            raise ValueError("a reply needs non-empty text")
        if self.outcome == "hand_off" and not self.reason:
            raise ValueError("a hand-off needs a reason")
        if len(self.reason) > MAX_REASON:
            raise ValueError(f"reason must be at most {MAX_REASON} characters")
        for tag in self.tags:
            if not _TAG.match(tag):
                raise ValueError(f"tag {tag!r} must be a lower-case identifier")

    @classmethod
    def reply(
        cls,
        kind: str,
        text: str,
        *,
        sources: tuple[Source, ...] = (),
        requires_approval: bool = False,
        tags: tuple[str, ...] = (),
    ) -> HandlerResult:
        """A reply to deliver."""
        return cls(
            "reply",
            kind,
            text=text,
            sources=sources,
            requires_approval=requires_approval,
            tags=tags,
        )

    @classmethod
    def hand_off(cls, kind: str, reason: str, *, tags: tuple[str, ...] = ()) -> HandlerResult:
        """Give the message to a person, for ``reason``."""
        return cls("hand_off", kind, reason=reason, tags=tags)


@runtime_checkable
class Handler(Protocol):
    """Decides what to say to one auto-answerable message."""

    @property
    def name(self) -> str:
        """A short identifier for audit records and logs."""
        ...

    def handle(self, request: HandlerRequest) -> HandlerResult:
        """A reply or a hand-off. May raise; the pipeline treats that as a hand-off."""
        ...


class HandOff:
    """Always hands off. The default for any category without a handler."""

    def __init__(self, *, reason: str = "no handler answers this category", name: str = "hand_off"):
        self.name = name
        self.reason = reason

    def handle(self, request: HandlerRequest) -> HandlerResult:
        """A hand-off with this handler's reason."""
        return HandlerResult.hand_off(self.name, self.reason)


class Template:
    """Fixed text the client wrote, by language code.

    A message in a language the template has no text for is handed off rather
    than answered in the wrong language.
    """

    def __init__(self, texts: Mapping[str, str], *, name: str = "template") -> None:
        if not texts or any(not isinstance(t, str) or not t.strip() for t in texts.values()):
            raise ValueError("a template needs at least one non-empty text")
        self.name = name
        self.texts = MappingProxyType(dict(texts))

    @classmethod
    def from_config(cls, config: ClientConfig, template: str) -> Template:
        """The template named ``template`` in the client's configuration."""
        texts = config.templates.get(template)
        if texts is None:
            raise ConfigError([f"no template named {template!r} in the configuration"])
        return cls(texts, name=template)

    def validate(self, config: ClientConfig) -> None:
        """Raise :class:`ConfigError` if any text is for an unconfigured language."""
        unknown = sorted(set(self.texts) - set(config.triage.languages))
        if unknown:
            raise ConfigError(
                [
                    f"template {self.name!r} has text for unconfigured language {code!r}"
                    for code in unknown
                ]
            )

    def handle(self, request: HandlerRequest) -> HandlerResult:
        """The text for the message's language, or a hand-off."""
        language = request.decision.language
        text = self.texts.get(language)
        if text is None:
            return HandlerResult.hand_off(self.name, f"no template text for language {language}")
        return HandlerResult.reply(self.name, text)


@dataclass(frozen=True)
class GenerationRequest:
    """What a generator is given: the question, the passages and the rules."""

    question: str = field(repr=False)
    subject: str = field(repr=False)
    passages: tuple[Passage, ...]
    language: str
    language_name: str
    instructions: str = field(repr=False)


@runtime_checkable
class Generator(Protocol):
    """Writes an answer from passages, or returns the refusal sentinel."""

    @property
    def name(self) -> str:
        """A short identifier for audit records and logs."""
        ...

    def generate(self, request: GenerationRequest) -> str:
        """The answer text, or :data:`inbox_core.prompts.REFUSAL_SENTINEL`."""
        ...


class ExtractiveGenerator:
    """Returns the best passage's text verbatim. Deterministic; for tests and demos."""

    name = "extractive"

    def generate(self, request: GenerationRequest) -> str:
        """The top passage's text, or the refusal sentinel when there is none."""
        if not request.passages:
            return REFUSAL_SENTINEL
        return request.passages[0].entry.text


class GroundedAnswer:
    """Answers from the client's knowledge, and says which entries it used.

    Refuses (hands off) when no passage scores at least ``min_score``, when
    the generator returns the refusal sentinel or nothing, and when retrieval
    or generation fails. Only passages above the threshold are given to the
    generator, and those are the sources returned, so ``limit`` should match
    what the generator actually uses (1 for :class:`ExtractiveGenerator`).
    The reply text is the generator's alone; it never names its sources.
    """

    def __init__(
        self,
        retriever: Retriever,
        generator: Generator,
        *,
        min_score: float,
        limit: int = 3,
        name: str = "grounded_answer",
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if min_score < 0:
            raise ValueError("min_score must not be negative")
        self.name = name
        self._retriever = retriever
        self._generator = generator
        self._min_score = min_score
        self._limit = limit

    def handle(self, request: HandlerRequest) -> HandlerResult:
        """A grounded reply with its sources, or a hand-off saying why not."""
        message = request.message
        query = f"{message.subject}\n{message.text}".strip()
        try:
            found: Sequence[Passage] = self._retriever.search(query, limit=self._limit)
        except Exception as exc:
            logger.warning(
                "retrieval failed for %s: %s", message.provider_message_id, type(exc).__name__
            )
            return HandlerResult.hand_off(self.name, f"retrieval failed ({type(exc).__name__})")

        passages = tuple(p for p in found if p.score >= self._min_score)
        if not passages:
            return HandlerResult.hand_off(
                self.name, f"no knowledge entry scored at least {self._min_score:.2f}"
            )

        language = request.decision.language
        policy = request.config.triage
        generation = GenerationRequest(
            question=message.text,
            subject=message.subject,
            passages=passages,
            language=language,
            language_name=policy.languages.get(language, policy.languages[policy.default_language]),
            instructions=render_answer_instructions(request.config, language),
        )
        try:
            text = self._generator.generate(generation).strip()
        except Exception as exc:
            logger.warning(
                "generator failed for %s: %s", message.provider_message_id, type(exc).__name__
            )
            return HandlerResult.hand_off(
                self.name, f"generator {self._generator.name} failed ({type(exc).__name__})"
            )
        if not text or REFUSAL_SENTINEL in text:
            return HandlerResult.hand_off(self.name, "the generator found the context insufficient")

        sources = tuple(
            Source(
                p.entry.id, p.entry.title, p.score, p.entry.url, f"{p.entry.title}\n{p.entry.text}"
            )
            for p in passages
        )
        return HandlerResult.reply(self.name, text, sources=sources)


class HandlerRegistry:
    """Which handler answers which category. Anything unlisted gets ``default``."""

    def __init__(self, handlers: Mapping[str, Handler], *, default: Handler | None = None) -> None:
        self._handlers = MappingProxyType(dict(handlers))
        self.default: Handler = default if default is not None else HandOff()

    def for_category(self, category: str) -> Handler:
        """The handler for ``category``."""
        return self._handlers.get(category, self.default)

    def validate(self, config: ClientConfig) -> None:
        """Raise :class:`ConfigError` for a handler that could never run.

        That is one registered for a category the table does not list, or for
        one that can never be auto-answered.
        """
        problems = []
        for category in self._handlers:
            rule = config.triage.category(category)
            if rule is None:
                problems.append(f"handler registered for unknown category {category!r}")
            elif not rule.auto_answer:
                problems.append(
                    f"handler registered for {category!r}, which can never be auto-answered"
                )
        if problems:
            raise ConfigError(problems)

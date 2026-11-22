"""Run one message through the example pipeline and print what the core decided.

    python -m inbox_core.examples.demo "What are your opening hours?"
    python -m inbox_core.examples.demo --mode auto "¿Dónde está la biblioteca?"
    python -m inbox_core.examples.demo --model gemini/gemini-3.5-flash-lite "Can I borrow a ladder?"

Without ``--model`` it uses :class:`KeywordClassifier`, a deterministic
stand-in that is not a model and is not accurate, and an extractive generator
that returns the best knowledge entry verbatim. With ``--model`` it uses
LiteLLM for both (needs ``inbox-core[litellm]`` and a provider key in the
environment).

Everything is in memory and nothing is sent anywhere: the "sink" prints.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from inbox_core.config import ClientConfig, load_config
from inbox_core.delivery import DeliveryMode
from inbox_core.handlers import (
    ExtractiveGenerator,
    Generator,
    GroundedAnswer,
    HandlerRegistry,
    Template,
)
from inbox_core.knowledge import (
    DEFAULT_STOPWORDS,
    InMemoryRetriever,
    KnowledgeEntry,
    load_markdown_knowledge,
)
from inbox_core.messages import IncomingMessage, OutboundReply, make_sender_key
from inbox_core.pipeline import AuditSink, Escalation, InMemoryAuditSink, Notifier, Pipeline
from inbox_core.store.memory import InMemoryConversationStore
from inbox_core.triage import TriageClassifier, TriageSignals

__all__ = [
    "EXAMPLE_DIR",
    "MIN_SCORE",
    "KeywordClassifier",
    "build_pipeline",
    "example_config",
    "example_knowledge",
    "example_retriever",
    "main",
]

EXAMPLE_DIR = Path(__file__).parent / "tool_library"
"""Where the example's configuration, knowledge and golden set live."""

MIN_SCORE = 2.0
"""The BM25 score below which the example's grounded answer refuses."""


def example_config() -> ClientConfig:
    """The Brambleford Tool Library's configuration."""
    return load_config(EXAMPLE_DIR / "client.toml")


def example_knowledge() -> tuple[KnowledgeEntry, ...]:
    """The Brambleford Tool Library's knowledge entries."""
    return load_markdown_knowledge(EXAMPLE_DIR / "knowledge.md")


EXAMPLE_STOPWORDS = DEFAULT_STOPWORDS | {
    "library",
    "biblioteca",
    "tool",
    "tools",
    "herramienta",
    "herramientas",
    "brambleford",
}
"""Words every message to this library contains, so they carry no signal for retrieval."""


def example_retriever() -> InMemoryRetriever:
    """BM25 over the example's knowledge, with its domain stop words."""
    return InMemoryRetriever(example_knowledge(), stopwords=EXAMPLE_STOPWORDS)


def _rx(*words: str) -> re.Pattern[str]:
    return re.compile("|".join(words), re.IGNORECASE)


_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "automated",
        _rx(
            r"out of the office",
            r"automatic reply",
            r"delivery status",
            r"could not be delivered",
            r"unsubscribe",
            r"darse de baja",
            r"bolet[ií]n",
        ),
    ),
    (
        "damage_report",
        _rx(
            r"stopped working",
            r"burning",
            r"broke",
            r"broken",
            r"slipped",
            r"\bhurt",
            r"injur",
            r"stolen",
            r"\blost\b",
            r"robaron",
            r"\broto\b",
            r"se ha roto",
            r"se me cay",
            r"herid",
        ),
    ),
    ("complaint", _rx(r"\brude\b", r"complain", r"quej", r"\btrato\b")),
    (
        "press",
        _rx(
            r"journalist",
            r"interview",
            r"news site",
            r"\bwrite for\b",
            r"student",
            r"research",
            r"\bradio\b",
            r"reportaje",
            r"periodista",
        ),
    ),
    (
        "donation",
        _rx(
            r"donat",
            r"give (it|them|you)",
            r"would you take",
            r"clearing out",
            r"spare .* i could",
            r"la quieren",
            r"donativo",
            r"\bdonar",
        ),
    ),
    ("reservation", _rx(r"reserv", r"put .* aside", r"cancel my", r"cambiarla")),
    ("membership", _rx(r"member", r"sign up", r"\bjoin", r"\bsoci[oa]\b", r"inscrib", r"hacerme")),
    (
        "other",
        _rx(
            r"speak to",
            r"talk to",
            r"hablar (por tel[eé]fono )?con",
            r"responsable",
            r"\bfound\b",
            r"cartel",
            r"fiesta",
        ),
    ),
)
_HUMAN = _rx(r"speak to", r"talk to", r"hablar (por tel[eé]fono )?con", r"persona responsable")
_MONEY = _rx(
    r"\bpay\b",
    r"\bpaid\b",
    r"\bfine\b",
    r"\bfee",
    r"\bcost",
    r"\bprice",
    r"money",
    r"[£€$]",
    r"\bdinero",
    r"econ[oó]mic",
    r"\bpagar",
    r"\bmulta",
    r"\bprecio",
)
_OTHER_LANGUAGE = _rx(
    r"\bbonjour\b", r"\bquels\b", r"\bvos\b", r"\bwie\b", r"\bviele\b", r"\bdarf\b", r"\bich\b"
)
_SPANISH = _rx(
    r"[¿¡ñáéíóú]",
    r"\bhola\b",
    r"\bqu[eé]\b",
    r"\btengo\b",
    r"\bquiero\b",
    r"\bpuedo\b",
    r"\blos\b",
    r"\blas\b",
    r"\bdel\b",
    r"\buna\b",
    r"\bpara\b",
    r"\bme\b",
    r"\bse\b",
    r"\bmi\b",
)
_QUESTION = _rx(r"\?", r"^(what|when|where|how|can|do|does|is|are)\b")


@dataclass
class KeywordClassifier:
    """A deterministic keyword stand-in for a classifier. Not a model, and not accurate.

    It exists so the example and its tests run with no network. Its rules are
    ordered most serious first, like the multi-topic rule in the real prompt.
    """

    name: str = "keywords:example"
    calls: int = field(default=0, compare=False)

    def classify(self, message: IncomingMessage) -> TriageSignals:
        """Signals from keyword rules over the subject and the text."""
        self.calls += 1
        text = f"{message.subject}\n{message.text}"
        category, confidence = "other", 0.5
        for name, pattern in _RULES:
            if pattern.search(text):
                category, confidence = name, 0.9
                break
        else:
            if _QUESTION.search(message.text.strip()):
                category, confidence = "faq", 0.75
        if _OTHER_LANGUAGE.search(text):
            language = "other"
        elif _SPANISH.search(text):
            language = "es"
        else:
            language = "en"
        return TriageSignals(
            category=category,
            language=language,
            confidence=confidence,
            asks_for_human=bool(_HUMAN.search(text)),
            mentions_money_or_commitment=bool(_MONEY.search(text)),
            classifier=self.name,
        )


def build_pipeline(
    *,
    classifier: TriageClassifier,
    sink: object,
    notifier: Notifier,
    audit: AuditSink,
    generator: Generator | None = None,
    mode_override: DeliveryMode | None = None,
    config: ClientConfig | None = None,
) -> Pipeline:
    """The example's pipeline: grounded answers for ``faq``, the template for ``membership``."""
    client = config or example_config()
    # The extractive stand-in uses only the best passage, so it is given only
    # that one: the sources a reply cites must be the ones it was written from.
    handlers = HandlerRegistry(
        {
            "faq": GroundedAnswer(
                example_retriever(),
                generator or ExtractiveGenerator(),
                min_score=MIN_SCORE,
                limit=3 if generator is not None else 1,
                cite=True,
            ),
            "membership": Template.from_config(client, "membership"),
        }
    )
    return Pipeline(
        config=client,
        classifier=classifier,
        handlers=handlers,
        sink=sink,  # type: ignore[arg-type]
        store=InMemoryConversationStore(),
        notifier=notifier,
        audit=audit,
        mode_override=mode_override,
    )


@dataclass
class _PrintingSink:
    lines: list[str] = field(default_factory=list)

    def send_to_public(self, reply: OutboundReply) -> str | None:
        self.lines.append(f"reply sent ({reply.kind}):\n{reply.text}")
        return "demo-sent"

    def hold_for_review(self, reply: OutboundReply) -> str | None:
        self.lines.append(f"reply held for review ({reply.kind}):\n{reply.text}")
        return "demo-held"


@dataclass
class _PrintingNotifier:
    lines: list[str] = field(default_factory=list)

    def notify(self, escalation: Escalation) -> None:
        self.lines.append(f"escalation: {json.dumps(dataclasses.asdict(escalation))}")


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    """Run one message through the example and print the outcome and its audit record."""
    out = stdout or sys.stdout
    parser = argparse.ArgumentParser(prog="python -m inbox_core.examples.demo")
    parser.add_argument("text", help="the message, as a visitor would write it")
    parser.add_argument("--subject", default="")
    parser.add_argument("--mode", choices=[mode.value for mode in DeliveryMode], default=None)
    parser.add_argument("--model", default=None, help="a LiteLLM model; omit for the stand-in")
    parser.add_argument("--api-base", default=None, help="a LiteLLM gateway URL")
    args = parser.parse_args(argv)

    classifier: TriageClassifier
    generator: Generator | None = None
    if args.model:
        try:
            from inbox_core.adapters.litellm import LiteLLMClassifier, LiteLLMGenerator

            classifier = LiteLLMClassifier(
                example_config(), model=args.model, api_base=args.api_base
            )
            generator = LiteLLMGenerator(model=args.model, api_base=args.api_base)
        except ImportError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    else:
        classifier = KeywordClassifier()

    sink, notifier, audit = _PrintingSink(), _PrintingNotifier(), InMemoryAuditSink()
    pipeline = build_pipeline(
        classifier=classifier,
        sink=sink,
        notifier=notifier,
        audit=audit,
        generator=generator,
        mode_override=DeliveryMode(args.mode) if args.mode else None,
    )
    address = "visitor@mail.example"
    record = pipeline.process(
        IncomingMessage(
            channel="web",
            thread_key="demo-conversation",
            provider_message_id="demo-message",
            sender_key=make_sender_key(address),
            sender_address=address,
            subject=args.subject,
            text=args.text,
        )
    )
    for line in (*sink.lines, *notifier.lines):
        print(line, file=out)
    print("audit record:", file=out)
    print(json.dumps(record.to_dict(), indent=2, ensure_ascii=False), file=out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

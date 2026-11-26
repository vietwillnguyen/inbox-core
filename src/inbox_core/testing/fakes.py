"""Fakes for testing a client's wiring of the core without any network.

They implement the core protocols and record what they were given, so a test
can drive a :class:`inbox_core.pipeline.Pipeline` end to end.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from inbox_core.handoff import HandOffRequest
from inbox_core.messages import IncomingMessage, OutboundReply
from inbox_core.pipeline import Escalation
from inbox_core.triage import TriageSignals, TriageUnavailable

__all__ = [
    "FakeClassifier",
    "RecordingHandOff",
    "RecordingNotifier",
    "RecordingSink",
    "signals",
]


def signals(
    category: str = "faq",
    *,
    language: str = "en",
    confidence: float = 0.9,
    asks_for_human: bool = False,
    money: bool = False,
    classifier: str = "fake",
) -> TriageSignals:
    """Classifier signals with convenient defaults."""
    return TriageSignals(category, language, confidence, asks_for_human, money, classifier)


@dataclass
class FakeClassifier:
    """Answers from a table keyed by provider message id, then ``default``.

    With ``fail_with`` set it raises that on every call, which is how a test
    proves the fail-closed path. With neither a match nor a default it raises
    :class:`TriageUnavailable`.
    """

    by_message: Mapping[str, TriageSignals] = field(default_factory=dict)
    default: TriageSignals | None = None
    fail_with: BaseException | None = None
    name: str = "fake"
    calls: int = 0

    def classify(self, message: IncomingMessage) -> TriageSignals:
        """The configured signals for ``message``."""
        self.calls += 1
        if self.fail_with is not None:
            raise self.fail_with
        found = self.by_message.get(message.provider_message_id, self.default)
        if found is None:
            raise TriageUnavailable(f"no fake signals for {message.provider_message_id}")
        return found


@dataclass
class RecordingSink:
    """A :class:`inbox_core.delivery.ReplySink` that records instead of delivering."""

    sent: list[OutboundReply] = field(default_factory=list)
    held: list[OutboundReply] = field(default_factory=list)

    def send_to_public(self, reply: OutboundReply) -> str | None:
        """Record a send."""
        self.sent.append(reply)
        return f"sent-{len(self.sent)}"

    def hold_for_review(self, reply: OutboundReply) -> str | None:
        """Record a hold."""
        self.held.append(reply)
        return f"held-{len(self.held)}"


@dataclass
class RecordingNotifier:
    """A :class:`inbox_core.pipeline.Notifier` that records escalations, or fails on demand."""

    escalations: list[Escalation] = field(default_factory=list)
    fail: bool = False

    def notify(self, escalation: Escalation) -> None:
        """Record ``escalation``, or raise ``ConnectionError`` when ``fail`` is set."""
        if self.fail:
            raise ConnectionError("notifier unavailable")
        self.escalations.append(escalation)


@dataclass
class RecordingHandOff:
    """A :class:`inbox_core.handoff.HandOffActions` that records each step and its request."""

    calls: list[tuple[str, HandOffRequest]] = field(default_factory=list)

    def _step(self, name: str, request: HandOffRequest) -> None:
        self.calls.append((name, request))

    def add_internal_note(self, request: HandOffRequest) -> None:
        """Record the note."""
        self._step("add_internal_note", request)

    def add_labels(self, request: HandOffRequest) -> None:
        """Record the labels."""
        self._step("add_labels", request)

    def assign(self, request: HandOffRequest) -> None:
        """Record the assignment."""
        self._step("assign", request)

    def open_for_person(self, request: HandOffRequest) -> None:
        """Record the opening."""
        self._step("open_for_person", request)

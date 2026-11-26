"""A person replied in a conversation: the bot stays silent there until it is resumed."""

from __future__ import annotations

from dataclasses import dataclass

from inbox_core.messages import IncomingMessage, make_sender_key
from inbox_core.testing.fakes import FakeClassifier, signals
from inbox_core.triage import TriageSignals
from tests.helpers import ADDRESS, message
from tests.test_pipeline import QUESTION, harness

SENDER = make_sender_key(ADDRESS)


def test_a_person_replying_silences_the_bot_in_that_conversation() -> None:
    h = harness()
    record = h.pipeline.person_replied("web", "conv-1", SENDER, message_id="agent-7")
    assert record.decision == "person_replied"
    assert record.reason == "a person replied in this conversation"
    assert record.message_id == "agent-7"
    assert record.thread_key == "conv-1"
    assert record.conversation_id == 1
    assert h.audit.records == [record]

    later = h.pipeline.process(message(QUESTION, message_id="visitor-2"))
    assert later.decision == "left_for_person"
    assert h.sink.sent == []
    assert h.sink.held == []
    assert h.notifier.escalations == []
    assert h.classifier.calls == 0


def test_other_conversations_are_unaffected() -> None:
    h = harness()
    h.pipeline.person_replied("web", "conv-1", SENDER, message_id="agent-7")
    other = h.pipeline.process(message(QUESTION, message_id="x", thread="conv-2"))
    assert other.decision == "answered"


def test_it_works_after_a_hand_off_and_survives_a_later_hand_off() -> None:
    h = harness(classifier=FakeClassifier(default=signals("refund")))
    assert h.pipeline.process(message("money back please")).decision == "handed_off"
    h.pipeline.person_replied("web", "conv-1", SENDER, message_id="agent-1")
    conversation = h.store.get_conversation(1)
    assert conversation is not None
    assert conversation.status == "paused_manual"


def test_only_resuming_gives_the_conversation_back() -> None:
    h = harness(client=None)
    h.pipeline.person_replied("web", "conv-1", SENDER, message_id="agent-7")
    assert h.pipeline.resume("web", "conv-1") is True
    assert h.pipeline.process(message(QUESTION, message_id="v-3")).decision == "answered"


def test_resuming_an_unknown_conversation_says_so() -> None:
    assert harness().pipeline.resume("web", "never-seen") is False


def test_a_reply_during_processing_stops_the_bot_before_it_delivers() -> None:
    # The person's reply lands while the classifier is still thinking: the
    # pipeline re-reads the conversation right before delivering, and stays
    # silent rather than answer over the person.
    @dataclass
    class ReplyWhileClassifying:
        name: str = "fake"
        calls: int = 0

        def classify(self, incoming: IncomingMessage) -> TriageSignals:
            self.calls += 1
            h.pipeline.person_replied("web", "conv-1", SENDER, message_id="agent-9")
            return signals("faq")

    h = harness(classifier=ReplyWhileClassifying())
    record = h.pipeline.process(message(QUESTION))
    assert record.decision == "left_for_person"
    assert record.reason == "a person replied while this message was processed"
    assert h.sink.sent == []
    assert h.store.is_handled("web", "msg-1")
    assert h.store.outbound_for(1) == ()


def test_a_reply_during_a_hand_off_skips_the_holding_message_and_the_notifier() -> None:
    @dataclass
    class ReplyWhileClassifying:
        name: str = "fake"

        def classify(self, incoming: IncomingMessage) -> TriageSignals:
            h.pipeline.person_replied("web", "conv-1", SENDER, message_id="agent-9")
            return signals("refund")

    h = harness(classifier=ReplyWhileClassifying())
    record = h.pipeline.process(message("money back please"))
    assert record.decision == "left_for_person"
    assert h.sink.sent == []
    assert h.notifier.escalations == []


def test_the_record_carries_no_content() -> None:
    h = harness()
    record = h.pipeline.person_replied("web", "conv-1", SENDER, message_id="agent-7")
    assert ADDRESS not in str(record.to_dict())


def test_a_store_failure_is_incomplete_and_still_audited() -> None:
    h = harness()

    def broken(conversation_id: int) -> None:
        raise ConnectionError("database unavailable")

    h.store.pause_manual = broken  # type: ignore[method-assign]
    record = h.pipeline.person_replied("web", "conv-1", SENDER, message_id="agent-7")
    assert record.decision == "incomplete"
    assert record.reason == "internal error (ConnectionError)"
    assert h.audit.records == [record]


def test_a_failing_audit_sink_does_not_raise() -> None:
    h = harness()

    def broken(record: object) -> None:
        raise OSError("disk full")

    h.audit.emit = broken  # type: ignore[method-assign]
    record = h.pipeline.person_replied("web", "conv-1", SENDER, message_id="agent-7")
    assert record.decision == "person_replied"

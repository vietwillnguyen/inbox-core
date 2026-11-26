"""Hand-off side effects: what a channel does in its own inbox when a person must act."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from inbox_core.handlers import HandlerRegistry, HandlerRequest, HandlerResult
from inbox_core.handoff import (
    HandOffActions,
    HandOffRequest,
    NoHandOffActions,
    handoff_labels,
    handoff_note,
)
from inbox_core.testing.fakes import FakeClassifier, RecordingHandOff, signals
from tests.helpers import message
from tests.test_pipeline import QUESTION, harness


@dataclass
class FailingHandOff(RecordingHandOff):
    fail_on: frozenset[str] = field(default_factory=frozenset)

    def _step(self, name: str, request: HandOffRequest) -> None:
        if name in self.fail_on:
            raise ConnectionError(f"{name} unavailable")
        super()._step(name, request)


class TestTheProtocol:
    def test_the_fakes_satisfy_it(self) -> None:
        assert isinstance(RecordingHandOff(), HandOffActions)
        assert isinstance(NoHandOffActions(), HandOffActions)

    def test_the_no_op_does_nothing(self) -> None:
        request = HandOffRequest(
            purpose="hand_off",
            channel="web",
            thread_key="t",
            message_id="m",
            conversation_id=1,
            category="refund",
            tier="needs_executive",
            reason="executive category refund",
            labels=("handoff",),
            note="n",
        )
        actions = NoHandOffActions()
        actions.add_internal_note(request)
        actions.add_labels(request)
        actions.assign(request)
        actions.open_for_person(request)


class TestLabelsAndNotes:
    def test_hand_off_labels(self) -> None:
        assert handoff_labels("hand_off", "refund", classifier_unavailable=False) == (
            "handoff",
            "refund",
        )
        assert handoff_labels("hand_off", "other", classifier_unavailable=True) == (
            "handoff",
            "other",
            "classifier-unavailable",
        )
        assert handoff_labels("review", "faq", classifier_unavailable=False) == (
            "draft-pending",
            "faq",
        )

    def test_the_note_carries_only_fixed_phrases_and_identifiers(self) -> None:
        note = handoff_note(
            "hand_off",
            category="refund",
            tier="needs_executive",
            reason="executive category refund",
            sources=(),
        )
        assert note == (
            "inbox-core handed this conversation to a person.\n"
            "Category: refund. Tier: needs_executive.\n"
            "Reason: executive category refund."
        )
        review = handoff_note(
            "review",
            category="faq",
            tier="auto_answer",
            reason="draft mode",
            sources=("KB-01", "KB-02"),
            titles={"KB-01": "Opening hours"},
        )
        assert review.startswith("inbox-core drafted a reply and is holding it for review")
        assert "Sources: KB-01 Opening hours; KB-02." in review

    def test_a_request_rejects_free_text_labels(self) -> None:
        with pytest.raises(ValueError, match="label"):
            HandOffRequest(
                purpose="hand_off",
                channel="web",
                thread_key="t",
                message_id="m",
                conversation_id=1,
                category="refund",
                tier="needs_executive",
                reason="r",
                labels=("My name is Sam",),
                note="n",
            )

    def test_a_request_hides_its_note_from_repr(self) -> None:
        request = HandOffRequest(
            purpose="review",
            channel="web",
            thread_key="t",
            message_id="m",
            conversation_id=1,
            category="faq",
            tier="auto_answer",
            reason="draft mode",
            labels=("draft-pending",),
            note="secret-looking note",
        )
        assert "secret-looking" not in repr(request)


class TestThePipelineCallsThem:
    def test_a_hand_off_posts_a_note_labels_opens_and_assigns_in_that_order(self) -> None:
        actions = RecordingHandOff()
        h = harness(classifier=FakeClassifier(default=signals("refund")), handoff_actions=actions)
        record = h.pipeline.process(message("I want my money back"))
        assert record.decision == "handed_off"
        assert [step for step, _ in actions.calls] == [
            "add_internal_note",
            "add_labels",
            "open_for_person",
            "assign",
        ]
        request = actions.calls[0][1]
        assert request.purpose == "hand_off"
        assert request.thread_key == "conv-1"
        assert request.labels == ("handoff", "refund")
        assert request.category == "refund"
        assert request.tier == "needs_executive"
        assert "Reason: executive category refund." in request.note
        assert record.handoff_failures == ()

    def test_the_holding_message_goes_before_the_actions_and_the_notifier_after(
        self,
    ) -> None:
        order: list[str] = []

        class Sink:
            def send_to_public(self, reply: object) -> str:
                order.append("holding")
                return "s1"

            def hold_for_review(self, reply: object) -> str:
                raise AssertionError

        class Notifier:
            def notify(self, escalation: object) -> None:
                order.append("notify")

        @dataclass
        class Ordered(RecordingHandOff):
            def _step(self, name: str, request: HandOffRequest) -> None:
                order.append(name)

        h = harness(
            classifier=FakeClassifier(default=signals("refund")),
            sink=Sink(),  # type: ignore[arg-type]
            notifier=Notifier(),  # type: ignore[arg-type]
            handoff_actions=Ordered(),
        )
        h.pipeline.process(message("I want my money back"))
        assert order == [
            "holding",
            "add_internal_note",
            "add_labels",
            "open_for_person",
            "assign",
            "notify",
        ]

    def test_an_unavailable_classifier_adds_its_label(self) -> None:
        actions = RecordingHandOff()
        h = harness(
            classifier=FakeClassifier(fail_with=ConnectionError("down")), handoff_actions=actions
        )
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "handed_off"
        assert actions.calls[1][1].labels == ("handoff", "other", "classifier-unavailable")

    def test_a_held_draft_is_opened_for_review(self) -> None:
        actions = RecordingHandOff()
        h = harness(mode="draft", handoff_actions=actions)
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "answer_held"
        assert [step for step, _ in actions.calls] == [
            "add_internal_note",
            "add_labels",
            "open_for_person",
            "assign",
        ]
        request = actions.calls[0][1]
        assert request.purpose == "review"
        assert request.labels == ("draft-pending", "faq")
        assert "Sources: KB-01 Opening hours." in request.note
        assert "Held because: draft mode." in request.note
        # Holding a draft is not a hand-off: the conversation stays the bot's.
        conversation = h.store.get_conversation(1)
        assert conversation is not None
        assert conversation.status == "bot"
        assert h.notifier.escalations == []

    def test_a_sent_answer_only_gets_a_staff_note_of_its_sources(self) -> None:
        order: list[str] = []

        class Sink:
            def send_to_public(self, reply: object) -> str:
                order.append("answer")
                return "s1"

            def hold_for_review(self, reply: object) -> str:
                raise AssertionError

        @dataclass
        class Ordered(RecordingHandOff):
            def _step(self, name: str, request: HandOffRequest) -> None:
                order.append(name)
                super()._step(name, request)

        actions = Ordered()
        h = harness(handoff_actions=actions, sink=Sink())  # type: ignore[arg-type]
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "answered"
        assert record.sources == ("KB-01",)
        # The note follows the answer; nothing labels, assigns or opens it.
        assert order == ["answer", "add_internal_note"]
        ((_, request),) = actions.calls
        assert request.purpose == "answered"
        assert request.labels == ()
        assert request.note == (
            "inbox-core answered this message automatically.\n"
            "Category: faq. Tier: auto_answer.\n"
            "Sources: KB-01 Opening hours."
        )
        conversation = h.store.get_conversation(1)
        assert conversation is not None
        assert conversation.status == "bot"

    def test_an_answer_without_sources_gets_no_note(self) -> None:
        class Fixed:
            name = "fixed"

            def handle(self, request: HandlerRequest) -> HandlerResult:
                return HandlerResult.reply(self.name, "We open at 9am.")

        actions = RecordingHandOff()
        h = harness(handoff_actions=actions, handlers=HandlerRegistry({"faq": Fixed()}))
        assert h.pipeline.process(message(QUESTION)).decision == "answered"
        assert actions.calls == []

    def test_a_failed_source_note_is_recorded_and_the_answer_stands(self) -> None:
        actions = FailingHandOff(fail_on=frozenset({"add_internal_note"}))
        h = harness(handoff_actions=actions)
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "answered"
        assert record.delivery == "sent"
        assert record.handoff_failures == ("source_note",)
        assert len(h.sink.sent) == 1

    @pytest.mark.parametrize("step", ["add_internal_note", "add_labels", "assign"])
    def test_a_failed_secondary_step_is_recorded_and_does_not_stop_the_hand_off(
        self, step: str
    ) -> None:
        actions = FailingHandOff(fail_on=frozenset({step}))
        h = harness(classifier=FakeClassifier(default=signals("refund")), handoff_actions=actions)
        record = h.pipeline.process(message("I want my money back"))
        assert record.decision == "handed_off"
        assert record.handoff_failures == (step,)
        assert "open_for_person" in [name for name, _ in actions.calls]
        assert len(h.notifier.escalations) == 1

    def test_failing_to_open_the_conversation_leaves_the_message_for_a_retry(self) -> None:
        actions = FailingHandOff(fail_on=frozenset({"open_for_person"}))
        h = harness(classifier=FakeClassifier(default=signals("refund")), handoff_actions=actions)
        record = h.pipeline.process(message("I want my money back"))
        assert record.decision == "incomplete"
        assert record.reason == "could not open the conversation for a person (ConnectionError)"
        assert not h.store.is_handled("web", "msg-1")
        conversation = h.store.get_conversation(1)
        assert conversation is not None
        assert conversation.status == "bot"
        assert h.notifier.escalations == []
        # Nothing is assigned to a conversation nobody could be shown.
        assert "assign" not in [name for name, _ in actions.calls]

        # The retry does not send a second holding message, and finishes.
        actions.fail_on = frozenset()
        again = h.pipeline.process(message("I want my money back"))
        assert again.decision == "handed_off"
        assert len(h.sink.sent) == 1

    def test_failing_to_open_a_held_draft_leaves_it_for_a_retry_without_a_second_draft(
        self,
    ) -> None:
        actions = FailingHandOff(fail_on=frozenset({"open_for_person"}))
        h = harness(mode="draft", handoff_actions=actions)
        assert h.pipeline.process(message(QUESTION)).decision == "incomplete"
        actions.fail_on = frozenset()
        assert h.pipeline.process(message(QUESTION)).decision == "answer_held"
        assert len(h.sink.held) == 1

    def test_handoff_failures_reach_the_audit_dictionary(self) -> None:
        actions = FailingHandOff(fail_on=frozenset({"assign"}))
        h = harness(classifier=FakeClassifier(default=signals("refund")), handoff_actions=actions)
        record = h.pipeline.process(message("I want my money back"))
        assert record.to_dict()["handoff_failures"] == ["assign"]


def test_a_request_needs_a_known_purpose() -> None:
    with pytest.raises(ValueError, match="purpose"):
        HandOffRequest(
            purpose="escalate",  # type: ignore[arg-type]
            channel="web",
            thread_key="t",
            message_id="m",
            conversation_id=1,
            category="refund",
            tier="needs_executive",
            reason="r",
            labels=(),
            note="n",
        )


def test_a_category_that_is_not_a_label_is_left_out() -> None:
    assert handoff_labels("hand_off", "", classifier_unavailable=False) == ("handoff",)

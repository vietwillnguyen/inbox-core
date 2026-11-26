"""The pipeline: small, explicit, fail-closed, one audit record per message."""

from __future__ import annotations

import dataclasses
import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from inbox_core.config import ClientConfig, ConfigError, DeliveryPolicy
from inbox_core.crypto import FieldCipher
from inbox_core.delivery import CapDecision, DeliveryMode
from inbox_core.handlers import (
    ExtractiveGenerator,
    GroundedAnswer,
    HandlerRegistry,
    HandlerRequest,
    HandlerResult,
    Source,
    Template,
)
from inbox_core.knowledge import InMemoryRetriever, KnowledgeEntry
from inbox_core.messages import IncomingMessage
from inbox_core.pipeline import (
    AuditRecord,
    Escalation,
    InMemoryAuditSink,
    JsonlAuditSink,
    LoggingAuditSink,
    Pipeline,
)
from inbox_core.shadow import ShadowingClassifier
from inbox_core.store.memory import InMemoryConversationStore
from inbox_core.testing.fakes import FakeClassifier, RecordingNotifier, RecordingSink, signals
from inbox_core.testing.logs import attached_caplog
from inbox_core.triage import TriageSignals, TriageUnavailable
from tests.helpers import bike_config, message

ENTRIES = (
    KnowledgeEntry("KB-01", "Opening hours", "We are open Tuesday to Saturday, 9am to 6pm."),
    KnowledgeEntry("KB-02", "Location", "The workshop is next to the ferry terminal."),
)
HOLDING = "Thanks for writing. A person from the workshop will reply here."


def config(mode: str = "auto", **delivery: Any) -> ClientConfig:
    base = bike_config()
    values: dict[str, Any] = {
        "mode": DeliveryMode(mode),
        "auto_languages": frozenset({"en"}),
        "holding": {"en": HOLDING},
    }
    values.update(delivery)
    return dataclasses.replace(base, delivery=DeliveryPolicy(**values))


def registry() -> HandlerRegistry:
    return HandlerRegistry(
        {"faq": GroundedAnswer(InMemoryRetriever(ENTRIES), ExtractiveGenerator(), min_score=0.5)}
    )


@dataclass
class Harness:
    pipeline: Pipeline
    classifier: FakeClassifier
    sink: RecordingSink
    notifier: RecordingNotifier
    audit: InMemoryAuditSink
    store: InMemoryConversationStore
    slept: list[float] = field(default_factory=list)


def harness(
    *,
    mode: str = "auto",
    classifier: Any = None,
    handlers: HandlerRegistry | None = None,
    sink: RecordingSink | None = None,
    notifier: RecordingNotifier | None = None,
    store: InMemoryConversationStore | None = None,
    client: ClientConfig | None = None,
    **kwargs: Any,
) -> Harness:
    fake = classifier if classifier is not None else FakeClassifier(default=signals("faq"))
    slept: list[float] = []
    sleep = kwargs.pop("sleep", slept.append)
    parts = Harness(
        pipeline=None,  # type: ignore[arg-type]
        classifier=fake,
        sink=sink or RecordingSink(),
        notifier=notifier or RecordingNotifier(),
        audit=InMemoryAuditSink(),
        store=store
        or InMemoryConversationStore(cipher=FieldCipher({"k1": secrets.token_bytes(32)}, "k1")),
        slept=slept,
    )
    parts.pipeline = Pipeline(
        config=client or config(mode),
        classifier=fake,
        handlers=handlers or registry(),
        sink=parts.sink,
        store=parts.store,
        notifier=parts.notifier,
        audit=parts.audit,
        sleep=sleep,
        **kwargs,
    )
    return parts


QUESTION = "What are your opening hours on Saturday?"


def h_decision(client: ClientConfig) -> str:
    return harness(client=client).pipeline.process(message(QUESTION)).decision


HOURS_URL = "https://bikes.example/hours"
LINKED = (
    dataclasses.replace(ENTRIES[0], url=HOURS_URL),
    ENTRIES[1],
)


def linked_registry() -> HandlerRegistry:
    return HandlerRegistry(
        {"faq": GroundedAnswer(InMemoryRetriever(LINKED), ExtractiveGenerator(), min_score=0.5)}
    )


class Cites:
    """A handler that answers with fixed text and the sources it is given."""

    name = "cites"

    def __init__(self, *sources: Source) -> None:
        self.sources = sources

    def handle(self, request: HandlerRequest) -> HandlerResult:
        return HandlerResult.reply("grounded_answer", "Here is the answer.", sources=self.sources)


def everything_sent_or_held(h: Harness) -> list[str]:
    return [r.text for r in (*h.sink.sent, *h.sink.held)]


class TestPublicLinks:
    """``delivery.show_sources``: links to public pages, never ids or titles."""

    def test_off_by_default_nothing_is_added_even_when_an_entry_has_a_url(self) -> None:
        for mode in ("auto", "draft"):
            h = harness(mode=mode, handlers=linked_registry())
            h.pipeline.process(message(QUESTION))
            assert everything_sent_or_held(h) == [ENTRIES[0].text]

    def test_on_a_sent_answer_ends_with_its_public_link_only(self) -> None:
        h = harness(client=config(show_sources=True), handlers=linked_registry())
        record = h.pipeline.process(message(QUESTION))
        (sent,) = h.sink.sent
        assert sent.text == f"{ENTRIES[0].text}\n\nMore: {HOURS_URL}"
        assert "KB-01" not in sent.text
        assert "Opening hours" not in sent.text
        assert "Source" not in sent.text
        # Staff tracking is unchanged: the audit keeps the id.
        assert record.sources == ("KB-01",)

    def test_on_without_a_url_nothing_is_added(self) -> None:
        h = harness(client=config(show_sources=True))
        h.pipeline.process(message(QUESTION))
        assert [r.text for r in h.sink.sent] == [ENTRIES[0].text]

    def test_only_sources_with_a_url_are_linked_once_each_in_order(self) -> None:
        handler = Cites(
            Source("KB-01", "Opening hours", 2.0, HOURS_URL),
            Source("KB-02", "Location", 1.5),
            Source("KB-03", "Holiday hours", 1.2, HOURS_URL),
            Source("KB-04", "Finding us", 1.0, "https://bikes.example/find-us"),
        )
        h = harness(client=config(show_sources=True), handlers=HandlerRegistry({"faq": handler}))
        h.pipeline.process(message(QUESTION))
        (sent,) = h.sink.sent
        assert sent.text == (
            f"Here is the answer.\n\nMore: {HOURS_URL}, https://bikes.example/find-us"
        )
        for hidden in ("KB-0", "Opening hours", "Location", "Holiday hours", "Finding us"):
            assert hidden not in sent.text

    def test_a_reply_without_sources_gets_no_line(self) -> None:
        h = harness(
            client=config(show_sources=True),
            classifier=FakeClassifier(default=signals("refund")),
        )
        h.pipeline.process(message("I want my money back"))
        assert [r.text for r in h.sink.sent] == [HOLDING]

    def test_the_label_follows_the_reply_language(self) -> None:
        h = harness(
            client=config(show_sources=True, links_label={"es": "Más información:"}),
            handlers=linked_registry(),
            classifier=FakeClassifier(default=signals("faq", language="es")),
        )
        h.pipeline.process(message("Cual es el horario de apertura? opening hours"))
        (held,) = h.sink.held
        assert held.text.endswith(f"\n\nMás información: {HOURS_URL}")

    def test_a_held_draft_shows_the_reviewer_the_line_and_approval_sends_what_they_saw(
        self,
    ) -> None:
        h = harness(
            mode="draft", client=config("draft", show_sources=True), handlers=linked_registry()
        )
        h.pipeline.process(message(QUESTION))
        (draft,) = h.pipeline.drafts.pending(1)
        expected = f"{ENTRIES[0].text}\n\nMore: {HOURS_URL}"
        assert draft.text == expected
        assert [r.text for r in h.sink.held] == [expected]
        h.pipeline.drafts.send(draft.id, reviewer="chatwoot-user:5")
        assert [r.text for r in h.sink.sent] == [expected]

    def test_an_approved_draft_with_the_option_off_has_no_line(self) -> None:
        h = harness(mode="draft", handlers=linked_registry())
        h.pipeline.process(message(QUESTION))
        (draft,) = h.pipeline.drafts.pending(1)
        assert draft.text == ENTRIES[0].text
        h.pipeline.drafts.send(draft.id, reviewer="chatwoot-user:5")
        assert [r.text for r in h.sink.sent] == [ENTRIES[0].text]


class TestAnswering:
    def test_auto_mode_sends_a_grounded_answer_with_its_sources(self) -> None:
        h = harness()
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "answered"
        assert record.delivery == "sent"
        assert record.handler == "grounded_answer"
        assert record.sources == ("KB-01",)
        assert record.tier == "auto_answer"
        assert record.mode == "auto"
        assert [r.text for r in h.sink.sent] == [ENTRIES[0].text]
        assert h.sink.sent[0].sources == ("KB-01",)
        assert h.notifier.escalations == []
        assert h.store.is_handled("web", "msg-1")
        assert h.audit.records == [record]

    def test_no_reply_names_its_sources_sent_held_or_approved(self) -> None:
        sent = harness()
        sent.pipeline.process(message(QUESTION))
        held = harness(mode="draft")
        held.pipeline.process(message(QUESTION))
        (draft,) = held.pipeline.drafts.pending(1)
        held.pipeline.drafts.send(draft.id, reviewer="chatwoot-user:5")
        for reply in (*sent.sink.sent, *held.sink.held, *held.sink.sent):
            assert reply.text == ENTRIES[0].text
            assert reply.sources == ("KB-01",)
        assert [r.sources for r in (*sent.audit.records, *held.audit.records)] == [
            ("KB-01",),
            ("KB-01",),
        ]

    def test_draft_mode_holds_and_never_sends(self) -> None:
        h = harness(mode="draft")
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "answer_held"
        assert record.held_because == "draft mode"
        assert h.sink.sent == []
        assert len(h.sink.held) == 1

    def test_a_language_not_signed_off_is_held(self) -> None:
        h = harness(classifier=FakeClassifier(default=signals("faq", language="es")))
        record = h.pipeline.process(message("Cual es el horario de apertura? opening hours"))
        assert record.decision == "answer_held"
        assert "language es" in record.held_because

    def test_a_reached_cap_holds(self) -> None:
        class Full:
            def allows(self, sender_key: str, thread_key: str) -> CapDecision:
                return CapDecision.refuse("daily", "30 of 30 sent today")

            def record_send(self, sender_key: str, thread_key: str) -> None:
                raise AssertionError("must not record a send that did not happen")

        h = harness(caps=Full())
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "answer_held"
        assert record.held_because == "daily cap reached"

    def test_a_handler_asking_for_approval_is_held_even_in_auto(self) -> None:
        class Proposer:
            name = "proposer"

            def handle(self, request: HandlerRequest) -> HandlerResult:
                return HandlerResult.reply(
                    self.name,
                    "Proposed refund of a tune-up.",
                    requires_approval=True,
                    tags=("tool:refund_proposal",),
                )

        h = harness(handlers=HandlerRegistry({"faq": Proposer()}))
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "answer_held"
        assert record.held_because == "the handler asked for approval"
        assert record.tags == ("tool:refund_proposal",)
        assert h.sink.sent == []

    def test_a_category_configured_for_approval_is_held_even_in_auto(self) -> None:
        h = harness(client=config(approval_categories=frozenset({"faq"})))
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "answer_held"
        assert record.held_because == "category faq needs approval"
        assert record.sources == ("KB-01",)
        assert h.sink.sent == []
        assert [r.text for r in h.sink.held] == [ENTRIES[0].text]

    def test_a_held_approval_category_reply_is_sent_once_a_person_approves(self) -> None:
        h = harness(client=config(approval_categories=frozenset({"faq"})))
        record = h.pipeline.process(message(QUESTION))
        assert record.conversation_id is not None
        [draft] = h.pipeline.drafts.pending(record.conversation_id)
        h.pipeline.drafts.send(draft.id, reviewer="staff:1")
        assert [r.text for r in h.sink.sent] == [ENTRIES[0].text]

    def test_categories_not_listed_for_approval_still_send(self) -> None:
        base = config()
        rules = tuple(
            dataclasses.replace(rule, auto_answer=True) if rule.name == "booking" else rule
            for rule in base.triage.categories
        )
        client = dataclasses.replace(
            base,
            triage=dataclasses.replace(base.triage, categories=rules),
            delivery=dataclasses.replace(base.delivery, approval_categories=frozenset({"booking"})),
        )
        assert h_decision(client) == "answered"

    def test_the_mode_can_be_overridden_at_runtime(self) -> None:
        h = harness(mode="auto", mode_override=DeliveryMode.DRAFT)
        assert h.pipeline.process(message(QUESTION)).decision == "answer_held"


class TestHandingOff:
    def test_an_executive_category_hands_off_with_a_holding_message(self) -> None:
        h = harness(classifier=FakeClassifier(default=signals("refund")))
        record = h.pipeline.process(message("I want my money back for the tune-up"))
        assert record.decision == "handed_off"
        assert record.tier == "needs_executive"
        assert record.reason == "executive category refund"
        assert record.delivery == "sent"
        assert [r.text for r in h.sink.sent] == [HOLDING]
        assert h.sink.sent[0].kind == "holding"
        assert h.notifier.escalations == [
            Escalation(
                channel="web",
                thread_key="conv-1",
                message_id="msg-1",
                conversation_id=1,
                category="refund",
                tier="needs_executive",
                reason="executive category refund",
            )
        ]
        conversation = h.store.get_conversation(1)
        assert conversation is not None
        assert conversation.status == "paused_handoff"

    def test_off_mode_hands_off_an_answerable_message_and_delivers_nothing(self) -> None:
        h = harness(mode="off")
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "handed_off"
        assert record.reason == "delivery is off"
        assert record.delivery == "none"
        assert h.sink.sent == []
        assert h.sink.held == []
        assert len(h.notifier.escalations) == 1

    def test_low_confidence_hands_off(self) -> None:
        h = harness(classifier=FakeClassifier(default=signals("faq", confidence=0.2)))
        record = h.pipeline.process(message(QUESTION))
        assert record.reason == "confidence 0.20 below threshold 0.60"

    def test_a_handler_hand_off_is_escalated_with_its_reason(self) -> None:
        h = harness()
        record = h.pipeline.process(message("Do you sell pianos?"))
        assert record.decision == "handed_off"
        assert record.handler == "grounded_answer"
        assert record.reason == "no knowledge entry scored at least 0.50"

    def test_a_crashing_handler_hands_off(self) -> None:
        class Broken:
            name = "broken"

            def handle(self, request: HandlerRequest) -> HandlerResult:
                raise RuntimeError(request.message.text)

        h = harness(handlers=HandlerRegistry({"faq": Broken()}))
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "handed_off"
        assert record.reason == "handler broken failed (RuntimeError)"

    def test_the_reply_cap_hands_off_the_next_message(self) -> None:
        h = harness()
        assert h.pipeline.process(message(QUESTION, message_id="m1")).decision == "answered"
        second = h.pipeline.process(message(QUESTION, message_id="m2"))
        assert second.decision == "handed_off"
        assert second.reason == "bot reply cap reached (1 per conversation)"

    def test_a_category_without_a_handler_hands_off(self) -> None:
        h = harness(handlers=HandlerRegistry({}))
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "handed_off"
        assert record.handler == "hand_off"

    def test_no_holding_message_when_none_is_configured(self) -> None:
        h = harness(
            classifier=FakeClassifier(default=signals("refund")),
            client=config(holding={}),
        )
        record = h.pipeline.process(message("money back"))
        assert record.decision == "handed_off"
        assert record.delivery == "none"
        assert h.sink.sent == []

    def test_a_failed_holding_message_does_not_stop_the_hand_off(self) -> None:
        class Broken(RecordingSink):
            def send_to_public(self, reply: Any) -> str | None:
                raise ConnectionError("down")

        h = harness(classifier=FakeClassifier(default=signals("refund")), sink=Broken())
        record = h.pipeline.process(message("money back"))
        assert record.decision == "handed_off"
        assert record.delivery == "failed"
        assert len(h.notifier.escalations) == 1

    def test_a_failed_answer_delivery_hands_off(self) -> None:
        class Broken(RecordingSink):
            def send_to_public(self, reply: Any) -> str | None:
                raise ConnectionError("down")

        h = harness(sink=Broken())
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "handed_off"
        assert record.reason == "delivery failed (ConnectionError)"
        assert len(h.notifier.escalations) == 1


class TestClassifierFailure:
    def test_an_unavailable_classifier_is_retried_then_hands_off(self) -> None:
        down = FakeClassifier(fail_with=TriageUnavailable("down"))
        h = harness(classifier=down, classifier_attempts=3, backoff=(0.5, 2.0))
        record = h.pipeline.process(message(QUESTION))
        assert down.calls == 3
        assert h.slept == [0.5, 2.0]
        assert record.decision == "handed_off"
        assert record.classifier == "unavailable"
        assert record.category == "other"
        assert record.tier == "needs_admin"
        assert record.reason == "classifier unavailable"
        assert h.sink.sent[0].text == HOLDING

    def test_a_buggy_classifier_fails_closed_too(self) -> None:
        h = harness(classifier=FakeClassifier(fail_with=KeyError("category")))
        assert h.pipeline.process(message(QUESTION)).classifier == "unavailable"

    def test_the_shadow_is_recorded_but_never_decides(self) -> None:
        decider = FakeClassifier(default=signals("faq"))
        shadow = FakeClassifier(default=signals("refund"), name="shadow")
        h = harness(classifier=ShadowingClassifier(decider, shadow))
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "answered"
        row = h.store.messages_in(1)[0]
        assert row.shadow is not None
        assert row.shadow["category"] == "refund"


class TestSkippingAndGuards:
    def test_automated_mail_is_skipped_silently(self) -> None:
        h = harness(classifier=FakeClassifier(default=signals("automated")))
        record = h.pipeline.process(message("Your weekly newsletter"))
        assert record.decision == "skipped"
        assert h.sink.sent == []
        assert h.notifier.escalations == []
        assert h.store.is_handled("web", "msg-1")

    def test_an_empty_message_is_dropped_before_any_model(self) -> None:
        h = harness()
        record = h.pipeline.process(message("   "))
        assert record.decision == "dropped"
        assert record.guard == "empty_message"
        assert h.classifier.calls == 0
        assert h.store.is_handled("web", "msg-1")

    def test_an_oversize_message_goes_to_a_person_unclassified(self) -> None:
        h = harness()
        record = h.pipeline.process(message("x" * 9000))
        assert record.decision == "handed_off"
        assert record.guard == "oversize"
        assert record.reason == "message longer than 8000 characters"
        assert record.category == "other"
        assert h.classifier.calls == 0
        assert len(h.notifier.escalations) == 1

    def test_custom_guards_replace_the_defaults(self) -> None:
        h = harness(guards=())
        assert h.pipeline.process(message("   ")).decision != "dropped"


class TestDedupeAndOwnership:
    def test_a_handled_message_is_a_duplicate_with_no_side_effects(self) -> None:
        h = harness()
        h.pipeline.process(message(QUESTION))
        again = h.pipeline.process(message(QUESTION))
        assert again.decision == "duplicate"
        assert len(h.sink.sent) == 1
        assert h.classifier.calls == 1
        assert len(h.audit.records) == 2

    def test_a_conversation_a_person_owns_is_left_alone(self) -> None:
        h = harness()
        conversation = h.store.conversation_for("web", "conv-1", message().sender_key)
        h.store.pause_manual(conversation.id)
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "left_for_person"
        assert h.sink.sent == []
        assert h.classifier.calls == 0
        assert h.store.is_handled("web", "msg-1")

    def test_a_notifier_failure_leaves_the_message_for_retry(self) -> None:
        notifier = RecordingNotifier(fail=True)
        store = InMemoryConversationStore()
        first = harness(
            classifier=FakeClassifier(default=signals("refund")), notifier=notifier, store=store
        )
        record = first.pipeline.process(message("money back"))
        assert record.decision == "incomplete"
        assert record.reason == "could not notify a person (ConnectionError)"
        assert not store.is_handled("web", "msg-1")
        conversation = store.get_conversation(1)
        assert conversation is not None
        assert conversation.status == "bot", "not paused until a person has been told"

        notifier.fail = False
        retry = harness(
            classifier=FakeClassifier(default=signals("refund")),
            notifier=notifier,
            store=store,
            sink=first.sink,
        )
        again = retry.pipeline.process(message("money back"))
        assert again.decision == "handed_off"
        assert store.is_handled("web", "msg-1")
        assert len(first.sink.sent) == 1, "the holding message is not sent twice"
        assert len(notifier.escalations) == 1

    def test_an_unfinished_earlier_delivery_is_never_repeated(self) -> None:
        store = InMemoryConversationStore()
        msg = message(QUESTION)
        conversation = store.conversation_for(msg.channel, msg.thread_key, msg.sender_key)
        row = store.record_inbound(conversation.id, msg)
        store.begin_outbound(
            conversation.id, reply_to_id=row.id, kind="grounded_answer", language="en", text="x"
        )  # a crash happened here on the earlier run
        h = harness(store=store)
        record = h.pipeline.process(msg)
        assert record.decision == "handed_off"
        assert record.reason == "an earlier delivery attempt did not finish"
        assert [r.text for r in h.sink.sent] == [HOLDING], "the answer is not sent again"

    def test_an_unfinished_earlier_holding_message_is_not_repeated(self) -> None:
        store = InMemoryConversationStore()
        msg = message("money back")
        conversation = store.conversation_for(msg.channel, msg.thread_key, msg.sender_key)
        row = store.record_inbound(conversation.id, msg)
        store.begin_outbound(
            conversation.id, reply_to_id=row.id, kind="holding", language="en", text="x"
        )
        h = harness(classifier=FakeClassifier(default=signals("refund")), store=store)
        record = h.pipeline.process(msg)
        assert record.decision == "handed_off"
        assert record.delivery == "none"
        assert h.sink.sent == []
        assert len(h.notifier.escalations) == 1

    @pytest.mark.parametrize(("earlier", "reported"), [("held", "held"), ("none", "none")])
    def test_a_finished_earlier_holding_attempt_is_reported_not_repeated(
        self, earlier: str, reported: str
    ) -> None:
        store = InMemoryConversationStore()
        msg = message(QUESTION)
        conversation = store.conversation_for(msg.channel, msg.thread_key, msg.sender_key)
        row = store.record_inbound(conversation.id, msg)
        out = store.begin_outbound(
            conversation.id, reply_to_id=row.id, kind="holding", language="en", text="x"
        )
        store.finish_outbound(out.id, action=earlier, provider_ref="d-1")
        h = harness(classifier=FakeClassifier(default=signals("refund")), store=store)
        record = h.pipeline.process(msg)
        assert record.decision == "handed_off"
        assert record.delivery == reported
        assert h.sink.held == []
        assert h.sink.sent == []

    def test_an_unexpected_failure_is_reported_and_left_for_retry(self) -> None:
        class BrokenStore(InMemoryConversationStore):
            def record_triage(self, *args: Any, **kwargs: Any) -> None:
                raise OSError("disk full")

        h = harness(store=BrokenStore())
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "incomplete"
        assert record.reason == "internal error (OSError)"
        assert len(h.notifier.escalations) == 1
        assert h.notifier.escalations[0].reason == "internal error (OSError)"
        assert not h.store.is_handled("web", "msg-1")

    def test_even_a_failing_notifier_after_an_internal_error_returns_a_record(self) -> None:
        class BrokenStore(InMemoryConversationStore):
            def record_triage(self, *args: Any, **kwargs: Any) -> None:
                raise OSError("disk full")

        h = harness(store=BrokenStore(), notifier=RecordingNotifier(fail=True))
        assert h.pipeline.process(message(QUESTION)).decision == "incomplete"
        assert len(h.audit.records) == 1


class TestConstruction:
    def test_the_registry_is_validated_against_the_config(self) -> None:
        with pytest.raises(ConfigError):
            harness(handlers=HandlerRegistry({"refund": Template({"en": "x"})}))

    def test_store_backed_caps_are_the_default(self) -> None:
        h = harness(client=config(daily_send_cap=1, max_bot_replies_per_conversation=5))
        h.pipeline.process(message(QUESTION, message_id="a", thread="t1"))
        record = h.pipeline.process(message(QUESTION, message_id="b", thread="t2"))
        assert record.held_because == "daily cap reached"


class TestAuditRecord:
    def test_one_record_per_message_on_every_path(self) -> None:
        h = harness()
        texts = [QUESTION, "   ", "Do you sell pianos?", QUESTION]
        for n, text in enumerate(texts):
            h.pipeline.process(message(text, message_id=f"m{n}", thread=f"t{n}"))
        h.pipeline.process(message(QUESTION, message_id="m0", thread="t0"))
        assert len(h.audit.records) == 5

    def test_the_record_holds_ids_and_decisions_only(self) -> None:
        record = harness().pipeline.process(message(QUESTION))
        as_dict = record.to_dict()
        assert set(as_dict) == {
            "at",
            "channel",
            "thread_key",
            "message_id",
            "conversation_id",
            "category",
            "tier",
            "confidence",
            "classifier",
            "decision",
            "reason",
            "handler",
            "mode",
            "delivery",
            "held_because",
            "sources",
            "guard",
            "tags",
            "handoff_failures",
        }
        dumped = json.dumps(as_dict)
        assert "opening hours" not in dumped.lower()
        assert "@" not in dumped

    def test_jsonl_and_logging_sinks(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        record = harness().pipeline.process(message(QUESTION))
        path = tmp_path / "audit" / "audit.jsonl"
        sink = JsonlAuditSink(path)
        sink.emit(record)
        sink.emit(record)
        lines = path.read_text(encoding="utf-8").splitlines()
        assert [json.loads(line)["decision"] for line in lines] == ["answered", "answered"]
        with attached_caplog(caplog, "inbox_core.audit"):
            LoggingAuditSink().emit(record)
        assert '"decision": "answered"' in caplog.text

    def test_an_audit_sink_failure_never_loses_the_decision(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class Broken(InMemoryAuditSink):
            def emit(self, record: AuditRecord) -> None:
                raise OSError("read-only file system")

        h = harness()
        h.pipeline._audit = Broken()
        with attached_caplog(caplog):
            record = h.pipeline.process(message(QUESTION))
        assert record.decision == "answered"
        assert "audit sink failed" in caplog.text


def test_signals_helper_and_fakes() -> None:
    fake = FakeClassifier(by_message={"m-9": signals("booking")}, default=signals("faq"))
    assert fake.classify(message(message_id="m-9")).category == "booking"
    assert fake.classify(message()).category == "faq"
    with pytest.raises(TriageUnavailable):
        FakeClassifier().classify(message())
    assert isinstance(signals(), TriageSignals)
    built = IncomingMessage(
        channel="web",
        thread_key="t",
        provider_message_id="x",
        sender_key="k",
        sender_address="",
        text="hi",
    )
    assert fake.classify(built).classifier == "fake"

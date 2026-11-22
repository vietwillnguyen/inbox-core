"""Held drafts: a person sends, edits or discards them, and what happened is counted."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from inbox_core.crypto import FieldCipher
from inbox_core.delivery import DeliveryMode, ReleaseRefusedError
from inbox_core.review import (
    DraftContentUnavailableError,
    DraftNotFoundError,
    DraftNotPendingError,
    DraftOutcomes,
    DraftReview,
    DraftSendFailedError,
)
from inbox_core.store.memory import InMemoryConversationStore
from inbox_core.testing.fakes import FakeClassifier, RecordingSink, signals
from tests.helpers import ADDRESS, message, track
from tests.test_pipeline import ENTRIES, HOLDING, QUESTION, harness

NOW = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def cipher() -> FieldCipher:
    return FieldCipher({"k1": secrets.token_bytes(32)}, "k1")


@pytest.fixture(params=["memory", "sqlalchemy"])
def store_kind(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def make_store(kind: str, tmp_path: Path, clock: Clock, *, with_cipher: bool = True) -> Any:
    key = cipher() if with_cipher else None
    if kind == "memory":
        return InMemoryConversationStore(cipher=key, clock=clock)
    from sqlalchemy import create_engine

    from inbox_core.store.sqlalchemy import SqlAlchemyConversationStore, create_schema

    engine = create_engine(f"sqlite:///{tmp_path / 'review.db'}")
    create_schema(engine)
    return track(SqlAlchemyConversationStore(engine, cipher=key, clock=clock))


def drafted(store_kind: str, tmp_path: Path, **kwargs: Any) -> tuple[Any, Clock]:
    clock = Clock()
    store = make_store(store_kind, tmp_path, clock)
    h = harness(mode="draft", store=store, clock=clock, **kwargs)
    record = h.pipeline.process(message(QUESTION))
    assert record.decision == "answer_held"
    return h, clock


class TestPending:
    def test_a_held_draft_is_listed_with_its_sources_and_decision(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        h, _ = drafted(store_kind, tmp_path)
        (draft,) = h.pipeline.drafts.pending(1)
        assert draft.text == ENTRIES[0].text
        assert draft.kind == "grounded_answer"
        assert draft.sources == ("KB-01",)
        assert draft.held_because == "draft mode"
        assert draft.category == "faq"
        assert draft.tier == "auto_answer"
        assert draft.confidence == pytest.approx(0.9)
        assert draft.classifier == "fake"
        assert draft.thread_key == "conv-1"
        assert draft.inbound_message_id == "msg-1"
        assert draft.created_at == NOW.replace(tzinfo=None)
        assert ENTRIES[0].text not in repr(draft)

    def test_a_held_holding_message_is_reviewable_too(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        clock = Clock()
        h = harness(
            mode="draft",
            store=make_store(store_kind, tmp_path, clock),
            classifier=FakeClassifier(default=signals("refund")),
        )
        assert h.pipeline.process(message("money back")).decision == "handed_off"
        (draft,) = h.pipeline.drafts.pending(1)
        assert draft.kind == "holding"
        assert draft.text == HOLDING
        assert draft.tier == "needs_executive"

    def test_nothing_pending_for_an_answered_conversation(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        clock = Clock()
        h = harness(store=make_store(store_kind, tmp_path, clock))
        h.pipeline.process(message(QUESTION))
        assert h.pipeline.drafts.pending(1) == ()


class TestSending:
    def test_sending_as_written(self, store_kind: str, tmp_path: Path) -> None:
        h, clock = drafted(store_kind, tmp_path)
        (draft,) = h.pipeline.drafts.pending(1)
        clock.now = NOW + timedelta(minutes=5)
        result = h.pipeline.drafts.send(draft.id, reviewer="chatwoot-user:5")
        assert result.outcome == "sent_as_written"
        assert result.reviewer == "chatwoot-user:5"
        assert result.provider_ref == "sent-1"
        (sent,) = h.sink.sent
        assert sent.text == ENTRIES[0].text
        assert sent.thread_key == "conv-1"
        assert sent.in_reply_to == "msg-1"
        assert sent.to_address == ADDRESS
        assert sent.sources == ("KB-01",)
        assert sent.kind == "grounded_answer"
        assert h.pipeline.drafts.pending(1) == ()
        row = h.store.get_message(draft.id)
        assert row.action == "sent"
        assert row.review_outcome == "sent_as_written"
        assert row.reviewed_by == "chatwoot-user:5"
        assert row.reviewed_at == (NOW + timedelta(minutes=5)).replace(tzinfo=None)

    def test_sending_edited_text_stores_what_was_sent(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        h, _ = drafted(store_kind, tmp_path)
        (draft,) = h.pipeline.drafts.pending(1)
        edited = "We open at 9 on Saturdays, see you then."
        result = h.pipeline.drafts.send(draft.id, reviewer="chatwoot-user:5", text=f"  {edited} ")
        assert result.outcome == "sent_edited"
        assert [r.text for r in h.sink.sent] == [edited]
        assert h.store.read_content(draft.id) == {"text": edited}

    def test_whitespace_only_changes_count_as_written(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        h, _ = drafted(store_kind, tmp_path)
        (draft,) = h.pipeline.drafts.pending(1)
        result = h.pipeline.drafts.send(
            draft.id, reviewer="chatwoot-user:5", text=f"\n{ENTRIES[0].text}  "
        )
        assert result.outcome == "sent_as_written"

    def test_empty_text_is_refused_and_the_draft_stays(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        h, _ = drafted(store_kind, tmp_path)
        (draft,) = h.pipeline.drafts.pending(1)
        with pytest.raises(ValueError, match="empty"):
            h.pipeline.drafts.send(draft.id, reviewer="chatwoot-user:5", text="   ")
        assert len(h.pipeline.drafts.pending(1)) == 1

    def test_a_draft_is_sent_at_most_once(self, store_kind: str, tmp_path: Path) -> None:
        h, _ = drafted(store_kind, tmp_path)
        (draft,) = h.pipeline.drafts.pending(1)
        h.pipeline.drafts.send(draft.id, reviewer="chatwoot-user:5")
        with pytest.raises(DraftNotPendingError):
            h.pipeline.drafts.send(draft.id, reviewer="chatwoot-user:6")
        with pytest.raises(DraftNotPendingError):
            h.pipeline.drafts.discard(draft.id, reviewer="chatwoot-user:6")
        assert len(h.sink.sent) == 1

    def test_a_failed_send_is_not_retried_and_is_marked_failed(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        class Failing(RecordingSink):
            def send_to_public(self, reply: Any) -> str | None:
                raise ConnectionError("channel down")

        h, _ = drafted(store_kind, tmp_path, sink=Failing())
        (draft,) = h.pipeline.drafts.pending(1)
        with pytest.raises(DraftSendFailedError, match="ConnectionError"):
            h.pipeline.drafts.send(draft.id, reviewer="chatwoot-user:5")
        assert h.store.get_message(draft.id).action == "failed"
        assert h.pipeline.drafts.pending(1) == ()
        with pytest.raises(DraftNotPendingError):
            h.pipeline.drafts.send(draft.id, reviewer="chatwoot-user:5")

    def test_delivery_off_refuses_and_keeps_the_draft(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        h, clock = drafted(store_kind, tmp_path)
        (draft,) = h.pipeline.drafts.pending(1)
        off = harness(mode="off", store=h.store, sink=h.sink, clock=clock)
        with pytest.raises(ReleaseRefusedError):
            off.pipeline.drafts.send(draft.id, reviewer="chatwoot-user:5")
        assert len(h.pipeline.drafts.pending(1)) == 1
        assert h.sink.sent == []

    def test_an_approved_send_bypasses_the_caps_but_is_counted(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        h, _ = drafted(store_kind, tmp_path, client=None)
        (draft,) = h.pipeline.drafts.pending(1)
        h.pipeline.drafts.send(draft.id, reviewer="chatwoot-user:5")
        start = NOW.replace(tzinfo=None) - timedelta(days=1)
        assert len(h.store.replies_sent_between(start, start + timedelta(days=2))) == 1

    def test_without_stored_content_a_draft_cannot_be_sent(self, tmp_path: Path) -> None:
        clock = Clock()
        h = harness(mode="draft", store=make_store("memory", tmp_path, clock, with_cipher=False))
        h.pipeline.process(message(QUESTION))
        (draft,) = h.store.held_for_review(1)
        with pytest.raises(DraftContentUnavailableError):
            h.pipeline.drafts.pending(1)
        with pytest.raises(DraftContentUnavailableError):
            h.pipeline.drafts.send(draft.id, reviewer="chatwoot-user:5")
        assert len(h.store.held_for_review(1)) == 1


class TestDiscardAndExpiry:
    def test_discard(self, store_kind: str, tmp_path: Path) -> None:
        h, _ = drafted(store_kind, tmp_path)
        (draft,) = h.pipeline.drafts.pending(1)
        result = h.pipeline.drafts.discard(draft.id, reviewer="chatwoot-user:5")
        assert result.outcome == "discarded"
        assert h.sink.sent == []
        assert h.pipeline.drafts.pending(1) == ()
        row = h.store.get_message(draft.id)
        assert (row.action, row.reviewed_by) == ("discarded", "chatwoot-user:5")

    def test_expiry_takes_only_drafts_older_than_the_cutoff(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        h, clock = drafted(store_kind, tmp_path)
        clock.now = NOW + timedelta(hours=3)
        h.pipeline.process(message(QUESTION, message_id="m2", thread="conv-2"))
        cutoff = NOW + timedelta(hours=1)
        assert h.pipeline.drafts.expire_before(cutoff) == 1
        assert h.pipeline.drafts.pending(1) == ()
        assert len(h.pipeline.drafts.pending(2)) == 1
        assert h.store.get_message(h.store.held_for_review(2)[0].id).action == "held"
        assert h.pipeline.drafts.expire_before(cutoff) == 0

    def test_unknown_and_non_draft_ids(self, store_kind: str, tmp_path: Path) -> None:
        h, _ = drafted(store_kind, tmp_path)
        with pytest.raises(DraftNotFoundError):
            h.pipeline.drafts.send(999, reviewer="chatwoot-user:5")
        with pytest.raises(DraftNotFoundError):
            h.pipeline.drafts.get(1)  # the inbound row, not a draft
        with pytest.raises(DraftNotFoundError):
            h.pipeline.drafts.discard(999, reviewer="chatwoot-user:5")

    def test_a_reviewer_is_an_identifier_not_a_name(self, store_kind: str, tmp_path: Path) -> None:
        h, _ = drafted(store_kind, tmp_path)
        (draft,) = h.pipeline.drafts.pending(1)
        with pytest.raises(ValueError, match="reviewer"):
            h.pipeline.drafts.discard(draft.id, reviewer="Sam Example <sam@example.com>")


class TestAcceptanceRate:
    def test_outcomes_are_counted_over_a_window(self, store_kind: str, tmp_path: Path) -> None:
        clock = Clock()
        store = make_store(store_kind, tmp_path, clock)
        h = harness(mode="draft", store=store, clock=clock, client=None)
        for n in range(5):
            h.pipeline.process(message(QUESTION, message_id=f"m{n}", thread=f"t{n}"))
        ids = [h.pipeline.drafts.pending(n + 1)[0].id for n in range(5)]
        review = h.pipeline.drafts
        review.send(ids[0], reviewer="chatwoot-user:1")
        review.send(ids[1], reviewer="chatwoot-user:1")
        review.send(ids[2], reviewer="chatwoot-user:1", text="Edited reply text.")
        review.discard(ids[3], reviewer="chatwoot-user:2")
        clock.now = NOW + timedelta(days=2)
        review.expire_before(NOW + timedelta(days=1))
        start = NOW - timedelta(days=1)
        outcomes = review.outcomes(start, NOW + timedelta(days=3))
        assert outcomes == DraftOutcomes(sent_as_written=2, sent_edited=1, discarded=1, expired=1)
        assert outcomes.resolved == 5
        assert outcomes.acceptance_rate == pytest.approx(0.4)
        assert outcomes.sent_rate == pytest.approx(0.6)
        # The window is on when the draft was resolved.
        assert review.outcomes(start, NOW + timedelta(days=1)).expired == 0

    def test_no_resolved_drafts_has_no_rate(self) -> None:
        empty = DraftOutcomes()
        assert empty.resolved == 0
        assert empty.acceptance_rate is None
        assert empty.sent_rate is None


def test_a_review_is_built_over_a_store_and_a_delivery() -> None:
    h = harness(mode="draft")
    assert isinstance(h.pipeline.drafts, DraftReview)
    assert h.pipeline.drafts.mode is DeliveryMode.DRAFT


def test_draft_review_send_reaches_the_public_only_through_release_approved() -> None:
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(DraftReview.send).lstrip())
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "release_approved" in called
    assert "send_to_public" not in called


class TestRacesAndDamage:
    def test_losing_the_claim_race_is_not_pending(self, store_kind: str, tmp_path: Path) -> None:
        h, _ = drafted(store_kind, tmp_path)
        (draft,) = h.pipeline.drafts.pending(1)
        # Another worker claims it between our read and our claim.
        real_get = h.store.get_message

        def get_then_lose(message_id: int) -> Any:
            row = real_get(message_id)
            if message_id == draft.id and row.action == "held":
                h.store.claim_held(draft.id)
            return row

        h.store.get_message = get_then_lose
        with pytest.raises(DraftNotPendingError):
            h.pipeline.drafts.send(draft.id, reviewer="chatwoot-user:5")
        h.store.get_message = real_get
        with pytest.raises(DraftNotPendingError):
            h.pipeline.drafts.discard(draft.id, reviewer="chatwoot-user:5")
        assert h.sink.sent == []

    def test_a_draft_whose_address_was_erased_cannot_be_sent(self) -> None:
        h = harness(mode="draft")
        h.pipeline.process(message(QUESTION))
        (draft,) = h.pipeline.drafts.pending(1)
        real = h.store.read_content
        h.store.read_content = lambda message_id: None if message_id == 1 else real(message_id)  # type: ignore[method-assign]
        with pytest.raises(DraftContentUnavailableError):
            h.pipeline.drafts.send(draft.id, reviewer="chatwoot-user:5")
        assert len(h.store.held_for_review(1)) == 1

    def test_a_draft_with_no_conversation_is_not_found(self) -> None:
        h = harness(mode="draft")
        h.pipeline.process(message(QUESTION))
        h.store.get_conversation = lambda conversation_id: None  # type: ignore[method-assign]
        with pytest.raises(DraftNotFoundError):
            h.pipeline.drafts.pending(1)


class TestStoreReviewContract:
    def test_resolving_a_draft_that_is_not_being_reviewed_raises(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        h, _ = drafted(store_kind, tmp_path)
        (draft,) = h.store.held_for_review(1)
        with pytest.raises(ValueError, match="not being reviewed"):
            h.store.resolve_review(draft.id, outcome="discarded", reviewer="x")

    def test_failing_a_draft_that_is_not_being_reviewed_changes_nothing(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        h, _ = drafted(store_kind, tmp_path)
        (draft,) = h.store.held_for_review(1)
        h.store.fail_review(draft.id)
        assert h.store.get_message(draft.id).action == "held"

    def test_claiming_twice_wins_once_and_an_inbound_row_cannot_be_claimed(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        h, _ = drafted(store_kind, tmp_path)
        (draft,) = h.store.held_for_review(1)
        assert h.store.claim_held(draft.id) is True
        assert h.store.claim_held(draft.id) is False
        assert h.store.claim_held(1) is False
        assert h.store.claim_held(999) is False
        assert h.store.get_message(999) is None

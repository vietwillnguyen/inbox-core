"""The conversation store contract, run against every implementation."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from inbox_core.crypto import FieldCipher
from inbox_core.store import (
    ConversationStore,
    StoreSendCaps,
    as_naive_utc,
)
from inbox_core.store.memory import InMemoryConversationStore
from inbox_core.triage import TriageDecision, TriageSignals
from tests.helpers import ADDRESS, message

BODY = "My daughter was upset after the Tuesday class"
SUBJECT = "About Tuesday"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def cipher() -> FieldCipher:
    return FieldCipher({"k1": secrets.token_bytes(32)}, "k1")


def build(kind: str, tmp_path: Path, clock: Clock, with_cipher: bool = True) -> Any:
    key = cipher() if with_cipher else None
    if kind == "memory":
        return InMemoryConversationStore(cipher=key, clock=clock)
    from sqlalchemy import create_engine

    from inbox_core.store.sqlalchemy import SqlAlchemyConversationStore, create_schema

    engine = create_engine(f"sqlite:///{tmp_path / 'store.db'}")
    create_schema(engine)
    return SqlAlchemyConversationStore(engine, cipher=key, clock=clock)


@pytest.fixture(params=["memory", "sqlalchemy"])
def kind(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(kind: str, tmp_path: Path, clock: Clock) -> Iterator[Any]:
    built = build(kind, tmp_path, clock)
    yield built
    close = getattr(built, "close", None)
    if close:
        close()


def decision(tier: str = "needs_admin") -> TriageDecision:
    return TriageDecision("faq", "en", 0.8, False, False, "test", tier=tier)  # type: ignore[arg-type]


def inbound(store: Any, **kwargs: Any) -> Any:
    msg = message(BODY, subject=SUBJECT, **kwargs)
    conversation = store.conversation_for(msg.channel, msg.thread_key, msg.sender_key)
    return conversation, store.record_inbound(conversation.id, msg)


class TestConversations:
    def test_satisfies_the_protocol(self, store: Any) -> None:
        assert isinstance(store, ConversationStore)

    def test_get_or_create_is_stable(self, store: Any) -> None:
        first = store.conversation_for("web", "t1", "k")
        again = store.conversation_for("web", "t1", "k")
        other = store.conversation_for("email", "t1", "k")
        assert first.id == again.id
        assert other.id != first.id
        assert first.status == "bot"
        assert first.bot_reply_count == 0
        assert store.get_conversation(first.id) == first
        assert store.get_conversation(9999) is None

    def test_pause_resume_and_manual_pause_is_the_stronger_state(self, store: Any) -> None:
        conversation = store.conversation_for("web", "t1", "k")
        store.pause(conversation.id, "needs_admin: asked for a person")
        assert store.get_conversation(conversation.id).status == "paused_handoff"
        store.pause_manual(conversation.id)
        store.pause(conversation.id, "later escalation")
        paused = store.get_conversation(conversation.id)
        assert paused.status == "paused_manual"
        assert paused.pause_reason == "a person replied in this conversation"
        store.resume(conversation.id)
        resumed = store.get_conversation(conversation.id)
        assert resumed.status == "bot"
        assert resumed.pause_reason is None


class TestHandledNotSeen:
    def test_a_recorded_message_is_not_handled_until_marked(self, store: Any) -> None:
        _, row = inbound(store)
        assert not store.is_handled("web", "msg-1")
        store.mark_handled(row.id, "answered")
        assert store.is_handled("web", "msg-1")
        assert store.messages_in(row.conversation_id)[0].action == "answered"

    def test_recording_twice_returns_the_same_row(self, store: Any) -> None:
        _, first = inbound(store)
        _, again = inbound(store)
        assert first.id == again.id
        assert len(store.messages_in(first.conversation_id)) == 1

    def test_dedupe_is_per_channel(self, store: Any) -> None:
        _, row = inbound(store)
        store.mark_handled(row.id, "answered")
        assert not store.is_handled("email", "msg-1")

    def test_triage_is_recorded_on_the_row(self, store: Any) -> None:
        _, row = inbound(store)
        shadow = TriageSignals("booking", "en", 0.4, False, False, "shadow")
        store.record_triage(row.id, decision("auto_answer"), shadow)
        stored = store.messages_in(row.conversation_id)[0]
        assert (stored.category, stored.tier, stored.classifier) == ("faq", "auto_answer", "test")
        assert stored.confidence == 0.8
        assert stored.shadow == shadow.as_record()


class TestOutbound:
    def test_an_outbound_attempt_is_recorded_before_it_finishes(self, store: Any) -> None:
        conversation, row = inbound(store)
        out = store.begin_outbound(
            conversation.id,
            reply_to_id=row.id,
            kind="faq",
            language="en",
            text="We open at 9.",
            sources=("KB-01",),
        )
        assert [m.action for m in store.outbound_for(row.id)] == ["pending"]
        store.finish_outbound(out.id, action="sent", provider_ref="out-1")
        finished = store.outbound_for(row.id)[0]
        assert finished.action == "sent"
        assert finished.provider_ref == "out-1"
        assert finished.sources == ("KB-01",)
        assert store.get_conversation(conversation.id).bot_reply_count == 1

    def test_held_counts_toward_the_reply_count_and_none_does_not(self, store: Any) -> None:
        conversation, row = inbound(store)
        for action in ("held", "none", "failed"):
            out = store.begin_outbound(
                conversation.id, reply_to_id=row.id, kind="faq", language="en", text="x"
            )
            store.finish_outbound(out.id, action=action, provider_ref=None)
        assert store.get_conversation(conversation.id).bot_reply_count == 1

    def test_replies_sent_between_lists_sent_replies_in_the_window(
        self, store: Any, clock: Clock
    ) -> None:
        conversation, row = inbound(store)
        out = store.begin_outbound(
            conversation.id, reply_to_id=row.id, kind="faq", language="en", text="x"
        )
        store.finish_outbound(out.id, action="sent", provider_ref=None)
        start = as_naive_utc(clock.now - timedelta(hours=1))
        end = as_naive_utc(clock.now + timedelta(hours=1))
        assert store.replies_sent_between(start, end) == [(conversation.sender_key, "conv-1")]
        later = as_naive_utc(clock.now + timedelta(days=1))
        assert store.replies_sent_between(end, later) == []


class TestContent:
    def test_inbound_content_is_stored_encrypted_and_readable(self, store: Any) -> None:
        _, row = inbound(store)
        assert row.has_content
        assert store.read_content(row.id) == {
            "subject": SUBJECT,
            "text": BODY,
            "sender_address": ADDRESS,
        }

    def test_outbound_text_is_readable(self, store: Any) -> None:
        conversation, row = inbound(store)
        out = store.begin_outbound(
            conversation.id, reply_to_id=row.id, kind="faq", language="en", text="We open at 9."
        )
        assert store.read_content(out.id) == {"text": "We open at 9."}

    def test_no_plaintext_reaches_the_rows(self, store: Any, kind: str, tmp_path: Path) -> None:
        conversation, row = inbound(store)
        store.begin_outbound(
            conversation.id, reply_to_id=row.id, kind="faq", language="en", text="Reply words here"
        )
        if kind == "memory":
            # The raw fields, not repr: the rows hide content from repr, so a
            # repr-based check would pass even if the text were stored in clear.
            fields = [
                str(getattr(row, name))
                for row in vars(store)["_rows"].values()
                for name in ("subject", "body", "sender_address")
            ]
            assert any(value.startswith("icenc:v1:") for value in fields)
            raw = "\n".join(fields).encode()
        else:
            raw = (tmp_path / "store.db").read_bytes()
        for secret in (BODY, SUBJECT, ADDRESS, "Reply words here"):
            assert secret.encode() not in raw, secret

    def test_delete_content_keeps_the_skeleton(self, store: Any) -> None:
        conversation, row = inbound(store)
        store.record_triage(row.id, decision(), None)
        store.mark_handled(row.id, "handed_off")
        out = store.begin_outbound(
            conversation.id, reply_to_id=row.id, kind="holding", language="en", text="Soon."
        )
        assert store.erase_conversation(conversation.id) == 2
        assert store.read_content(row.id) is None
        assert store.read_content(out.id) is None
        rows = store.messages_in(conversation.id)
        assert len(rows) == 2
        assert all(not m.has_content and m.content_erased_at is not None for m in rows)
        assert rows[0].category == "faq"
        assert store.is_handled("web", "msg-1"), "dedupe must survive erasure"

    def test_delete_by_sender(self, store: Any) -> None:
        conversation, row = inbound(store, thread="a")
        inbound(store, thread="b", message_id="msg-2")
        inbound(store, thread="c", message_id="msg-3", address="someone.else@example.com")
        assert store.erase_sender(conversation.sender_key) == 2
        assert store.read_content(row.id) is None
        assert store.erase_sender(conversation.sender_key) == 0

    def test_without_a_cipher_no_content_is_kept(
        self, kind: str, tmp_path: Path, clock: Clock
    ) -> None:
        plain = build(kind, tmp_path, clock, with_cipher=False)
        msg = message(BODY)
        conversation = plain.conversation_for(msg.channel, msg.thread_key, msg.sender_key)
        row = plain.record_inbound(conversation.id, msg)
        out = plain.begin_outbound(
            conversation.id, reply_to_id=row.id, kind="faq", language="en", text="x"
        )
        assert not row.has_content
        assert plain.read_content(row.id) is None
        assert plain.read_content(out.id) is None
        if kind == "sqlalchemy":
            plain.close()


class TestTimestamps:
    def test_stored_timestamps_are_naive_utc(self, store: Any, clock: Clock) -> None:
        clock.now = datetime(2026, 5, 1, 16, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
        _, row = inbound(store)
        store.mark_handled(row.id, "answered")
        stored = store.messages_in(row.conversation_id)[0]
        assert stored.created_at == datetime(2026, 5, 1, 9, 30)  # noqa: DTZ001
        assert stored.created_at.tzinfo is None
        assert stored.handled_at is not None
        assert stored.handled_at.tzinfo is None

    def test_as_naive_utc(self) -> None:
        aware = datetime(2026, 1, 1, 7, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
        assert as_naive_utc(aware) == datetime(2026, 1, 1, 0, 0)  # noqa: DTZ001
        naive = datetime(2026, 1, 1, 0, 0)  # noqa: DTZ001
        assert as_naive_utc(naive) is naive


def test_unknown_ids_raise(store: Any) -> None:
    with pytest.raises(KeyError):
        store.mark_handled(424242, "answered")
    with pytest.raises(KeyError):
        store.pause(424242, "x")
    with pytest.raises(KeyError):
        store.record_inbound(424242, message())
    assert store.read_content(424242) is None


def test_the_inbound_row_is_committed_before_any_side_effect(tmp_path: Path, clock: Clock) -> None:
    # A second connection sees the row as soon as record_inbound returns,
    # which is what makes "record, then act" safe across a crash.
    from sqlalchemy import create_engine, text

    store = build("sqlalchemy", tmp_path, clock)
    inbound(store)
    other = create_engine(f"sqlite:///{tmp_path / 'store.db'}")
    with other.connect() as connection:
        count = connection.execute(
            text("select count(*) from inbox_messages where handled_at is null")
        ).scalar_one()
    assert count == 1
    other.dispose()
    store.close()


class TestStoreSendCaps:
    def send(self, store: Any, thread: str, address: str = ADDRESS) -> None:
        msg = message(thread=thread, message_id=f"m-{thread}-{address}", address=address)
        conversation = store.conversation_for(msg.channel, msg.thread_key, msg.sender_key)
        row = store.record_inbound(conversation.id, msg)
        out = store.begin_outbound(
            conversation.id, reply_to_id=row.id, kind="faq", language="en", text="x"
        )
        store.finish_outbound(out.id, action="sent", provider_ref=None)

    def test_counts_from_the_store_so_caps_survive_a_restart(
        self, store: Any, clock: Clock
    ) -> None:
        self.send(store, "t1")
        self.send(store, "t2")
        key = message().sender_key
        caps = StoreSendCaps(store, daily_cap=10, per_sender_cap=2, clock=clock)
        assert caps.allows(key, "t1").allowed
        assert caps.allows(key, "t3").cap == "per_sender"
        caps.record_send(key, "t3")  # counted by the store, not in memory
        assert caps.allows("someone-else", "t9").allowed

    def test_daily_cap_and_the_local_day(self, store: Any, clock: Clock) -> None:
        zone = ZoneInfo("Asia/Ho_Chi_Minh")
        clock.now = datetime(2026, 5, 1, 16, 30, tzinfo=UTC)  # 23:30 local
        self.send(store, "t1", "a@example.com")
        caps = StoreSendCaps(store, daily_cap=1, per_sender_cap=5, timezone=zone, clock=clock)
        assert caps.allows("x", "t2").cap == "daily"
        clock.now += timedelta(hours=1)
        assert caps.allows("x", "t2").allowed

    def test_bounds_must_be_positive(self, store: Any) -> None:
        with pytest.raises(ValueError, match="positive"):
            StoreSendCaps(store, daily_cap=0, per_sender_cap=1)


def test_naive_utc_now_is_naive_and_current() -> None:
    from inbox_core.store import naive_utc_now

    now = naive_utc_now()
    assert now.tzinfo is None
    assert abs(now - as_naive_utc(datetime.now(UTC))) < timedelta(seconds=5)


def test_a_conversation_created_concurrently_is_read_not_duplicated(
    tmp_path: Path, clock: Clock
) -> None:
    from sqlalchemy import create_engine, event, insert

    from inbox_core.store.sqlalchemy import conversations

    store = build("sqlalchemy", tmp_path, clock)
    rival = create_engine(f"sqlite:///{tmp_path / 'store.db'}")
    engine = vars(store)["_engine"]
    fired: list[bool] = []

    def another_worker_wins(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        if statement.startswith("INSERT INTO inbox_conversations") and not fired:
            fired.append(True)
            with rival.begin() as other:
                other.execute(
                    insert(conversations).values(
                        channel="web",
                        thread_key="t1",
                        sender_key="k",
                        status="bot",
                        pause_reason=None,
                        bot_reply_count=0,
                        created_at=as_naive_utc(clock.now),
                        updated_at=as_naive_utc(clock.now),
                    )
                )

    event.listen(engine, "before_cursor_execute", another_worker_wins)
    conversation = store.conversation_for("web", "t1", "k")
    assert fired
    assert conversation.thread_key == "t1"
    assert store.conversation_for("web", "t1", "k").id == conversation.id
    rival.dispose()
    store.close()

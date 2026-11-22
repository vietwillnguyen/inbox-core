"""A SQLAlchemy :class:`inbox_core.store.ConversationStore`. Needs ``inbox-core[sqlalchemy]``.

Two tables, ``inbox_conversations`` and ``inbox_messages``, created with
:func:`create_schema` or by your own migrations from :data:`metadata`. Every
method runs in its own transaction and commits before it returns, which is
what makes "record the inbound row, then act" safe across a crash.

Timestamps are plain ``DateTime`` columns holding naive UTC (see
:mod:`inbox_core.store`). Content columns hold
:class:`inbox_core.crypto.FieldCipher` tokens only; there is no plaintext
text column.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Engine,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Connection, RowMapping
from sqlalchemy.exc import IntegrityError

from inbox_core.crypto import FieldCipher
from inbox_core.messages import IncomingMessage
from inbox_core.store import (
    BODY_CONTEXT,
    BOT_REPLY_ACTIONS,
    REVIEW_ACTIONS,
    SENDER_CONTEXT,
    SUBJECT_CONTEXT,
    Conversation,
    ReviewOutcome,
    StoredMessage,
    as_naive_utc,
)
from inbox_core.triage import TriageDecision, TriageSignals

__all__ = ["SqlAlchemyConversationStore", "create_schema", "metadata"]

metadata = MetaData()
"""The schema, for ``create_all`` or for generating migrations."""

conversations = Table(
    "inbox_conversations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("channel", String(64), nullable=False),
    Column("thread_key", String(512), nullable=False),
    Column("sender_key", String(64), nullable=False, index=True),
    Column("status", String(32), nullable=False),
    Column("pause_reason", String(256), nullable=True),
    Column("bot_reply_count", Integer, nullable=False, default=0),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    UniqueConstraint("channel", "thread_key", name="uq_inbox_conversations_thread"),
)

messages = Table(
    "inbox_messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("conversation_id", Integer, ForeignKey("inbox_conversations.id"), nullable=False),
    Column("channel", String(64), nullable=False),
    Column("direction", String(16), nullable=False),
    Column("provider_message_id", String(512), nullable=True),
    Column("reply_to_id", Integer, ForeignKey("inbox_messages.id"), nullable=True, index=True),
    Column("action", String(64), nullable=False),
    Column("kind", String(64), nullable=True),
    Column("category", String(64), nullable=True),
    Column("tier", String(32), nullable=True),
    Column("language", String(16), nullable=True),
    Column("confidence", Float, nullable=True),
    Column("classifier", String(128), nullable=True),
    Column("shadow", JSON, nullable=True),
    Column("sources", JSON, nullable=False, default=list),
    Column("provider_ref", String(512), nullable=True),
    Column("created_at", DateTime, nullable=False, index=True),
    Column("handled_at", DateTime, nullable=True),
    Column("content_erased_at", DateTime, nullable=True),
    Column("held_because", String(128), nullable=True),
    Column("review_outcome", String(32), nullable=True),
    Column("reviewed_by", String(64), nullable=True),
    Column("reviewed_at", DateTime, nullable=True, index=True),
    Column("subject_encrypted", Text, nullable=True),
    Column("body_encrypted", Text, nullable=True),
    Column("sender_address_encrypted", Text, nullable=True),
    UniqueConstraint("channel", "provider_message_id", name="uq_inbox_messages_provider"),
)


def create_schema(engine: Engine) -> None:
    """Create the two tables if they do not exist."""
    metadata.create_all(engine)


def _conversation(row: RowMapping) -> Conversation:
    return Conversation(
        id=row["id"],
        channel=row["channel"],
        thread_key=row["thread_key"],
        sender_key=row["sender_key"],
        status=row["status"],
        pause_reason=row["pause_reason"],
        bot_reply_count=row["bot_reply_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _message(row: RowMapping) -> StoredMessage:
    return StoredMessage(
        id=row["id"],
        conversation_id=row["conversation_id"],
        channel=row["channel"],
        direction=row["direction"],
        provider_message_id=row["provider_message_id"],
        reply_to_id=row["reply_to_id"],
        action=row["action"],
        kind=row["kind"],
        category=row["category"],
        tier=row["tier"],
        language=row["language"],
        confidence=row["confidence"],
        classifier=row["classifier"],
        shadow=row["shadow"],
        sources=tuple(row["sources"] or ()),
        provider_ref=row["provider_ref"],
        created_at=row["created_at"],
        handled_at=row["handled_at"],
        content_erased_at=row["content_erased_at"],
        has_content=row["body_encrypted"] is not None,
        held_because=row["held_because"],
        review_outcome=row["review_outcome"],
        reviewed_by=row["reviewed_by"],
        reviewed_at=row["reviewed_at"],
    )


class SqlAlchemyConversationStore:
    """Conversations and messages in a SQL database through SQLAlchemy Core."""

    def __init__(
        self,
        engine: Engine,
        *,
        cipher: FieldCipher | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._engine = engine
        self._cipher = cipher
        self._clock = clock

    def close(self) -> None:
        """Dispose of the engine's connection pool. Only when this store owns the engine."""
        self._engine.dispose()

    def _now(self) -> datetime:
        return as_naive_utc(self._clock())

    def _seal(self, value: str | None, context: str) -> str | None:
        if self._cipher is None or value is None:
            return None
        return self._cipher.encrypt(value, context)

    @staticmethod
    def _one(connection: Connection, table: Table, row_id: int) -> RowMapping:
        row = connection.execute(select(table).where(table.c.id == row_id)).mappings().first()
        if row is None:
            raise KeyError(f"no {table.name} row id={row_id}")
        return row

    def conversation_for(self, channel: str, thread_key: str, sender_key: str) -> Conversation:
        """The conversation for this thread, created if new."""
        query = select(conversations).where(
            conversations.c.channel == channel, conversations.c.thread_key == thread_key
        )
        with self._engine.begin() as connection:
            row = connection.execute(query).mappings().first()
            if row is not None:
                return _conversation(row)
        now = self._now()
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    insert(conversations).values(
                        channel=channel,
                        thread_key=thread_key,
                        sender_key=sender_key,
                        status="bot",
                        pause_reason=None,
                        bot_reply_count=0,
                        created_at=now,
                        updated_at=now,
                    )
                )
        except IntegrityError:
            pass  # another worker created it first; read theirs
        with self._engine.begin() as connection:
            return _conversation(connection.execute(query).mappings().one())

    def get_conversation(self, conversation_id: int) -> Conversation | None:
        """The conversation with this id, if any."""
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    select(conversations).where(conversations.c.id == conversation_id)
                )
                .mappings()
                .first()
            )
        return None if row is None else _conversation(row)

    def find_conversation(self, channel: str, thread_key: str) -> Conversation | None:
        """The conversation for this thread, if it exists."""
        query = select(conversations).where(
            conversations.c.channel == channel, conversations.c.thread_key == thread_key
        )
        with self._engine.begin() as connection:
            row = connection.execute(query).mappings().first()
        return None if row is None else _conversation(row)

    def _inbound_query(self, channel: str, provider_message_id: str) -> Any:
        return select(messages).where(
            messages.c.channel == channel,
            messages.c.provider_message_id == provider_message_id,
            messages.c.direction == "inbound",
        )

    def is_handled(self, channel: str, provider_message_id: str) -> bool:
        """True only when the inbound row has ``handled_at``."""
        with self._engine.begin() as connection:
            row = connection.execute(self._inbound_query(channel, provider_message_id))
            found = row.mappings().first()
        return found is not None and found["handled_at"] is not None

    def record_inbound(self, conversation_id: int, message: IncomingMessage) -> StoredMessage:
        """The inbound row, committed now; the existing one when it was recorded before."""
        query = self._inbound_query(message.channel, message.provider_message_id)
        with self._engine.begin() as connection:
            self._one(connection, conversations, conversation_id)
            existing = connection.execute(query).mappings().first()
            if existing is not None:
                return _message(existing)
            result = connection.execute(
                insert(messages).values(
                    conversation_id=conversation_id,
                    channel=message.channel,
                    direction="inbound",
                    provider_message_id=message.provider_message_id,
                    action="received",
                    sources=[],
                    created_at=self._now(),
                    subject_encrypted=self._seal(message.subject, SUBJECT_CONTEXT),
                    body_encrypted=self._seal(message.text, BODY_CONTEXT),
                    sender_address_encrypted=self._seal(message.sender_address, SENDER_CONTEXT),
                )
            )
            new_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
            return _message(self._one(connection, messages, int(new_id or 0)))

    def _update_message(self, message_id: int, **values: object) -> None:
        with self._engine.begin() as connection:
            self._one(connection, messages, message_id)
            connection.execute(update(messages).where(messages.c.id == message_id).values(**values))

    def record_triage(
        self, message_id: int, decision: TriageDecision, shadow: TriageSignals | None
    ) -> None:
        """Attach the decision and any shadow signals to the inbound row."""
        self._update_message(
            message_id,
            category=decision.category,
            tier=decision.tier,
            language=decision.language,
            confidence=float(decision.confidence),
            classifier=decision.classifier,
            shadow=shadow.as_record() if shadow else None,
        )

    def mark_handled(self, message_id: int, action: str) -> None:
        """Set the terminal action and ``handled_at``."""
        self._update_message(message_id, action=action, handled_at=self._now())

    def begin_outbound(
        self,
        conversation_id: int,
        *,
        reply_to_id: int,
        kind: str,
        language: str,
        text: str,
        sources: tuple[str, ...] = (),
    ) -> StoredMessage:
        """A ``pending`` outbound row, committed before delivery."""
        with self._engine.begin() as connection:
            conversation = self._one(connection, conversations, conversation_id)
            result = connection.execute(
                insert(messages).values(
                    conversation_id=conversation_id,
                    channel=conversation["channel"],
                    direction="outbound",
                    reply_to_id=reply_to_id,
                    action="pending",
                    kind=kind,
                    language=language,
                    sources=list(sources),
                    created_at=self._now(),
                    body_encrypted=self._seal(text, BODY_CONTEXT),
                )
            )
            new_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
            return _message(self._one(connection, messages, int(new_id or 0)))

    def finish_outbound(
        self, message_id: int, *, action: str, provider_ref: str | None, held_because: str = ""
    ) -> None:
        """Record the delivery outcome; ``held`` and ``sent`` count as a bot reply."""
        with self._engine.begin() as connection:
            row = self._one(connection, messages, message_id)
            connection.execute(
                update(messages)
                .where(messages.c.id == message_id)
                .values(action=action, provider_ref=provider_ref, held_because=held_because or None)
            )
            if action in BOT_REPLY_ACTIONS:
                connection.execute(
                    update(conversations)
                    .where(conversations.c.id == row["conversation_id"])
                    .values(bot_reply_count=conversations.c.bot_reply_count + 1)
                )

    def get_message(self, message_id: int) -> StoredMessage | None:
        """The message with this id, if any."""
        with self._engine.begin() as connection:
            row = (
                connection.execute(select(messages).where(messages.c.id == message_id))
                .mappings()
                .first()
            )
        return None if row is None else _message(row)

    def held_for_review(self, conversation_id: int) -> tuple[StoredMessage, ...]:
        """Held outbound replies in the conversation, oldest first."""
        query = (
            select(messages)
            .where(
                messages.c.conversation_id == conversation_id,
                messages.c.direction == "outbound",
                messages.c.action == "held",
            )
            .order_by(messages.c.id)
        )
        with self._engine.begin() as connection:
            return tuple(_message(row) for row in connection.execute(query).mappings())

    def claim_held(self, message_id: int) -> bool:
        """``held`` to ``reviewing`` in one conditional UPDATE; one caller wins."""
        with self._engine.begin() as connection:
            result = connection.execute(
                update(messages)
                .where(
                    messages.c.id == message_id,
                    messages.c.direction == "outbound",
                    messages.c.action == "held",
                )
                .values(action="reviewing")
            )
            return int(result.rowcount or 0) == 1

    def resolve_review(
        self,
        message_id: int,
        *,
        outcome: ReviewOutcome,
        reviewer: str,
        provider_ref: str | None = None,
        text: str | None = None,
    ) -> None:
        """Finish a ``reviewing`` draft."""
        values: dict[str, object] = {
            "action": REVIEW_ACTIONS[outcome],
            "review_outcome": outcome,
            "reviewed_by": reviewer,
            "reviewed_at": self._now(),
        }
        if provider_ref is not None:
            values["provider_ref"] = provider_ref
        with self._engine.begin() as connection:
            row = self._one(connection, messages, message_id)
            if row["action"] != "reviewing":
                raise ValueError(f"message id={message_id} is not being reviewed")
            if text is not None and row["body_encrypted"] is not None:
                values["body_encrypted"] = self._seal(text, BODY_CONTEXT)
            connection.execute(
                update(messages)
                .where(messages.c.id == message_id, messages.c.action == "reviewing")
                .values(**values)
            )

    def fail_review(self, message_id: int) -> None:
        """``reviewing`` to ``failed``."""
        with self._engine.begin() as connection:
            self._one(connection, messages, message_id)
            connection.execute(
                update(messages)
                .where(messages.c.id == message_id, messages.c.action == "reviewing")
                .values(action="failed")
            )

    def expire_held(self, before: datetime, *, reviewer: str) -> int:
        """Expire held replies created before ``before``."""
        with self._engine.begin() as connection:
            result = connection.execute(
                update(messages)
                .where(
                    messages.c.direction == "outbound",
                    messages.c.action == "held",
                    messages.c.created_at < as_naive_utc(before),
                )
                .values(
                    action="expired",
                    review_outcome="expired",
                    reviewed_by=reviewer,
                    reviewed_at=self._now(),
                )
            )
            return int(result.rowcount or 0)

    def review_outcomes_between(self, start: datetime, end: datetime) -> dict[str, int]:
        """Outcome counts over ``[start, end)`` of ``reviewed_at``."""
        query = (
            select(messages.c.review_outcome, func.count())
            .where(
                messages.c.review_outcome.is_not(None),
                messages.c.reviewed_at >= as_naive_utc(start),
                messages.c.reviewed_at < as_naive_utc(end),
            )
            .group_by(messages.c.review_outcome)
        )
        with self._engine.begin() as connection:
            return {str(row[0]): int(row[1]) for row in connection.execute(query)}

    def outbound_for(self, reply_to_id: int) -> tuple[StoredMessage, ...]:
        """Outbound rows answering this inbound row, oldest first."""
        query = (
            select(messages).where(messages.c.reply_to_id == reply_to_id).order_by(messages.c.id)
        )
        with self._engine.begin() as connection:
            return tuple(_message(row) for row in connection.execute(query).mappings())

    def messages_in(self, conversation_id: int) -> tuple[StoredMessage, ...]:
        """Every message in the conversation, oldest first."""
        query = (
            select(messages)
            .where(messages.c.conversation_id == conversation_id)
            .order_by(messages.c.id)
        )
        with self._engine.begin() as connection:
            return tuple(_message(row) for row in connection.execute(query).mappings())

    def _set_status(
        self, conversation_id: int, status: str, reason: str | None, *, unless_manual: bool
    ) -> None:
        with self._engine.begin() as connection:
            current = self._one(connection, conversations, conversation_id)
            if unless_manual and current["status"] == "paused_manual":
                return
            connection.execute(
                update(conversations)
                .where(conversations.c.id == conversation_id)
                .values(status=status, pause_reason=reason, updated_at=self._now())
            )

    def pause(self, conversation_id: int, reason: str) -> None:
        """Pause after a hand-off, unless a person already owns the conversation."""
        self._set_status(conversation_id, "paused_handoff", reason, unless_manual=True)

    def pause_manual(self, conversation_id: int) -> None:
        """A person replied; only :meth:`resume` undoes this."""
        self._set_status(
            conversation_id,
            "paused_manual",
            "a person replied in this conversation",
            unless_manual=False,
        )

    def resume(self, conversation_id: int) -> None:
        """Give the conversation back to the assistant. The reply count is kept."""
        self._set_status(conversation_id, "bot", None, unless_manual=False)

    def replies_sent_between(self, start: datetime, end: datetime) -> list[tuple[str, str]]:
        """``(sender_key, thread_key)`` for each reply sent in ``[start, end)``."""
        query = (
            select(conversations.c.sender_key, conversations.c.thread_key)
            .join(messages, messages.c.conversation_id == conversations.c.id)
            .where(
                messages.c.action == "sent",
                messages.c.created_at >= as_naive_utc(start),
                messages.c.created_at < as_naive_utc(end),
            )
            .order_by(messages.c.id)
        )
        with self._engine.begin() as connection:
            return [(row[0], row[1]) for row in connection.execute(query)]

    def read_content(self, message_id: int) -> dict[str, str] | None:
        """Decrypted content, or None when none is held."""
        with self._engine.begin() as connection:
            row = (
                connection.execute(select(messages).where(messages.c.id == message_id))
                .mappings()
                .first()
            )
        if row is None or self._cipher is None or row["body_encrypted"] is None:
            return None
        ids = f"message id={message_id}"
        cipher = self._cipher
        text = cipher.decrypt(row["body_encrypted"], BODY_CONTEXT, ids=ids)
        if row["direction"] == "outbound":
            return {"text": text}
        return {
            "subject": cipher.decrypt_optional(row["subject_encrypted"], SUBJECT_CONTEXT, ids=ids)
            or "",
            "text": text,
            "sender_address": cipher.decrypt_optional(
                row["sender_address_encrypted"], SENDER_CONTEXT, ids=ids
            )
            or "",
        }

    def _erase(self, connection: Connection, condition: Any) -> int:
        result = connection.execute(
            update(messages)
            .where(condition, messages.c.body_encrypted.is_not(None))
            .values(
                subject_encrypted=None,
                body_encrypted=None,
                sender_address_encrypted=None,
                content_erased_at=self._now(),
            )
        )
        return int(result.rowcount or 0)

    def erase_conversation(self, conversation_id: int) -> int:
        """Delete content from every message in the conversation; keep the rows."""
        with self._engine.begin() as connection:
            self._one(connection, conversations, conversation_id)
            return self._erase(connection, messages.c.conversation_id == conversation_id)

    def erase_content_before(self, cutoff: datetime) -> int:
        """Delete content from every message created before ``cutoff``; keep the rows."""
        with self._engine.begin() as connection:
            return self._erase(connection, messages.c.created_at < as_naive_utc(cutoff))

    def erase_sender(self, sender_key: str) -> int:
        """Delete content from every message in this sender's conversations."""
        owned = select(conversations.c.id).where(conversations.c.sender_key == sender_key)
        with self._engine.begin() as connection:
            return self._erase(connection, messages.c.conversation_id.in_(owned))

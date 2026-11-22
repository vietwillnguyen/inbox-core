"""An in-memory :class:`inbox_core.store.ConversationStore`, for tests, demos and one process.

Everything is lost when the process ends. Thread-safe within one process.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from inbox_core.crypto import FieldCipher
from inbox_core.messages import IncomingMessage
from inbox_core.store import (
    BODY_CONTEXT,
    BOT_REPLY_ACTIONS,
    SENDER_CONTEXT,
    SUBJECT_CONTEXT,
    Conversation,
    StoredMessage,
    as_naive_utc,
)
from inbox_core.triage import TriageDecision, TriageSignals

__all__ = ["InMemoryConversationStore"]


@dataclass
class _Row:
    message: StoredMessage
    subject: str | None = field(default=None, repr=False)
    body: str | None = field(default=None, repr=False)
    sender_address: str | None = field(default=None, repr=False)


class InMemoryConversationStore:
    """Conversations and messages in dictionaries. Content is encrypted when a cipher is given."""

    def __init__(
        self,
        *,
        cipher: FieldCipher | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._cipher = cipher
        self._clock = clock
        self._lock = threading.RLock()
        self._conversations: dict[int, Conversation] = {}
        self._threads: dict[tuple[str, str], int] = {}
        self._rows: dict[int, _Row] = {}
        self._inbound: dict[tuple[str, str], int] = {}

    def _now(self) -> datetime:
        return as_naive_utc(self._clock())

    def _conversation(self, conversation_id: int) -> Conversation:
        try:
            return self._conversations[conversation_id]
        except KeyError:
            raise KeyError(f"no conversation id={conversation_id}") from None

    def _row(self, message_id: int) -> _Row:
        try:
            return self._rows[message_id]
        except KeyError:
            raise KeyError(f"no message id={message_id}") from None

    def _seal(self, value: str | None, context: str) -> str | None:
        if self._cipher is None or value is None:
            return None
        return self._cipher.encrypt(value, context)

    def conversation_for(self, channel: str, thread_key: str, sender_key: str) -> Conversation:
        """The conversation for this thread, created if new."""
        with self._lock:
            existing = self._threads.get((channel, thread_key))
            if existing is not None:
                return self._conversations[existing]
            now = self._now()
            conversation = Conversation(
                id=len(self._conversations) + 1,
                channel=channel,
                thread_key=thread_key,
                sender_key=sender_key,
                status="bot",
                pause_reason=None,
                bot_reply_count=0,
                created_at=now,
                updated_at=now,
            )
            self._conversations[conversation.id] = conversation
            self._threads[(channel, thread_key)] = conversation.id
            return conversation

    def get_conversation(self, conversation_id: int) -> Conversation | None:
        """The conversation with this id, if any."""
        return self._conversations.get(conversation_id)

    def is_handled(self, channel: str, provider_message_id: str) -> bool:
        """True only when the inbound row has ``handled_at``."""
        with self._lock:
            row_id = self._inbound.get((channel, provider_message_id))
            return row_id is not None and self._rows[row_id].message.handled_at is not None

    def record_inbound(self, conversation_id: int, message: IncomingMessage) -> StoredMessage:
        """The inbound row, written now; the existing one when it was recorded before."""
        with self._lock:
            conversation = self._conversation(conversation_id)
            existing = self._inbound.get((message.channel, message.provider_message_id))
            if existing is not None:
                return self._rows[existing].message
            stored = StoredMessage(
                id=len(self._rows) + 1,
                conversation_id=conversation.id,
                channel=message.channel,
                direction="inbound",
                provider_message_id=message.provider_message_id,
                reply_to_id=None,
                action="received",
                kind=None,
                category=None,
                tier=None,
                language=None,
                confidence=None,
                classifier=None,
                shadow=None,
                sources=(),
                provider_ref=None,
                created_at=self._now(),
                handled_at=None,
                content_erased_at=None,
                has_content=self._cipher is not None,
            )
            self._rows[stored.id] = _Row(
                stored,
                subject=self._seal(message.subject, SUBJECT_CONTEXT),
                body=self._seal(message.text, BODY_CONTEXT),
                sender_address=self._seal(message.sender_address, SENDER_CONTEXT),
            )
            self._inbound[(message.channel, message.provider_message_id)] = stored.id
            return stored

    def _update(self, message_id: int, **changes: object) -> None:
        with self._lock:
            row = self._row(message_id)
            row.message = replace(row.message, **changes)  # type: ignore[arg-type]

    def record_triage(
        self, message_id: int, decision: TriageDecision, shadow: TriageSignals | None
    ) -> None:
        """Attach the decision and any shadow signals to the inbound row."""
        self._update(
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
        self._update(message_id, action=action, handled_at=self._now())

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
        """A ``pending`` outbound row, written before delivery."""
        with self._lock:
            conversation = self._conversation(conversation_id)
            stored = StoredMessage(
                id=len(self._rows) + 1,
                conversation_id=conversation.id,
                channel=conversation.channel,
                direction="outbound",
                provider_message_id=None,
                reply_to_id=reply_to_id,
                action="pending",
                kind=kind,
                category=None,
                tier=None,
                language=language,
                confidence=None,
                classifier=None,
                shadow=None,
                sources=tuple(sources),
                provider_ref=None,
                created_at=self._now(),
                handled_at=None,
                content_erased_at=None,
                has_content=self._cipher is not None,
            )
            self._rows[stored.id] = _Row(stored, body=self._seal(text, BODY_CONTEXT))
            return stored

    def finish_outbound(self, message_id: int, *, action: str, provider_ref: str | None) -> None:
        """Record the delivery outcome; ``held`` and ``sent`` count as a bot reply."""
        with self._lock:
            row = self._row(message_id)
            row.message = replace(row.message, action=action, provider_ref=provider_ref)
            if action in BOT_REPLY_ACTIONS:
                conversation = self._conversations[row.message.conversation_id]
                self._conversations[conversation.id] = replace(
                    conversation, bot_reply_count=conversation.bot_reply_count + 1
                )

    def outbound_for(self, reply_to_id: int) -> tuple[StoredMessage, ...]:
        """Outbound rows answering this inbound row, oldest first."""
        with self._lock:
            return tuple(
                row.message for row in self._rows.values() if row.message.reply_to_id == reply_to_id
            )

    def messages_in(self, conversation_id: int) -> tuple[StoredMessage, ...]:
        """Every message in the conversation, oldest first."""
        with self._lock:
            return tuple(
                row.message
                for row in self._rows.values()
                if row.message.conversation_id == conversation_id
            )

    def _set_status(self, conversation_id: int, status: str, reason: str | None) -> None:
        with self._lock:
            conversation = self._conversation(conversation_id)
            self._conversations[conversation_id] = replace(
                conversation,
                status=status,  # type: ignore[arg-type]
                pause_reason=reason,
                updated_at=self._now(),
            )

    def pause(self, conversation_id: int, reason: str) -> None:
        """Pause after a hand-off, unless a person already owns the conversation."""
        with self._lock:
            if self._conversation(conversation_id).status == "paused_manual":
                return
            self._set_status(conversation_id, "paused_handoff", reason)

    def pause_manual(self, conversation_id: int) -> None:
        """A person replied; only :meth:`resume` undoes this."""
        self._set_status(conversation_id, "paused_manual", "a person replied in this conversation")

    def resume(self, conversation_id: int) -> None:
        """Give the conversation back to the assistant. The reply count is kept."""
        self._set_status(conversation_id, "bot", None)

    def replies_sent_between(self, start: datetime, end: datetime) -> list[tuple[str, str]]:
        """``(sender_key, thread_key)`` for each reply sent in ``[start, end)``."""
        with self._lock:
            found = []
            for row in self._rows.values():
                message = row.message
                if message.action == "sent" and start <= message.created_at < end:
                    conversation = self._conversations[message.conversation_id]
                    found.append((conversation.sender_key, conversation.thread_key))
            return found

    def read_content(self, message_id: int) -> dict[str, str] | None:
        """Decrypted content, or None when none is held."""
        with self._lock:
            row = self._rows.get(message_id)
            if row is None or self._cipher is None or not row.message.has_content:
                return None
            ids = f"message id={message_id}"
            text = self._cipher.decrypt_optional(row.body, BODY_CONTEXT, ids=ids) or ""
            if row.message.direction == "outbound":
                return {"text": text}
            return {
                "subject": self._cipher.decrypt_optional(row.subject, SUBJECT_CONTEXT, ids=ids)
                or "",
                "text": text,
                "sender_address": self._cipher.decrypt_optional(
                    row.sender_address, SENDER_CONTEXT, ids=ids
                )
                or "",
            }

    def _erase(self, rows: Mapping[int, _Row]) -> int:
        now = self._now()
        erased = 0
        for row in rows.values():
            if not row.message.has_content:
                continue
            row.subject = row.body = row.sender_address = None
            row.message = replace(row.message, has_content=False, content_erased_at=now)
            erased += 1
        return erased

    def erase_conversation(self, conversation_id: int) -> int:
        """Delete content from every message in the conversation; keep the rows."""
        with self._lock:
            self._conversation(conversation_id)
            rows = {
                key: row
                for key, row in self._rows.items()
                if row.message.conversation_id == conversation_id
            }
            return self._erase(rows)

    def erase_sender(self, sender_key: str) -> int:
        """Delete content from every message in this sender's conversations."""
        with self._lock:
            ids = {c.id for c in self._conversations.values() if c.sender_key == sender_key}
            rows = {k: r for k, r in self._rows.items() if r.message.conversation_id in ids}
            return self._erase(rows)

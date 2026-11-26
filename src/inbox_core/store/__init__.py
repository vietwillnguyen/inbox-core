"""The conversation record, behind one interface.

:class:`ConversationStore` is what the pipeline reads and writes. Two
implementations: :class:`inbox_core.store.memory.InMemoryConversationStore` in
the core, and :class:`inbox_core.store.sqlalchemy.SqlAlchemyConversationStore`
with the ``sqlalchemy`` extra.

Three properties every implementation keeps:

- **Handled, not seen.** The inbound row is written (committed) before any side
  effect, so a crash cannot produce a second reply. But a row existing and a
  message being finished with are different facts: :meth:`ConversationStore.is_handled`
  reads ``handled_at``, which is set only at a terminal state. A row without it
  is a message that was seen and not completed, and it is retried rather than
  written off. Never skip a message because its row exists.
- **Naive UTC.** Timestamps are stored and returned as naive datetimes in UTC.
  Any bound compared against them must be converted with :func:`as_naive_utc`
  first; an aware bound compares as though it carried an offset and silently
  matches nothing. Decide windows in the organisation's timezone, then convert.
- **No plaintext.** Message text, subjects, sender addresses and reply text are
  stored only encrypted, through a :class:`inbox_core.crypto.FieldCipher`.
  Without a cipher, no content is stored at all. Erasing content keeps the
  rest of the row, because dedupe, the caps and the metrics read it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Literal, Protocol, runtime_checkable

from inbox_core.delivery import CapDecision
from inbox_core.messages import IncomingMessage
from inbox_core.triage import TriageDecision, TriageSignals

__all__ = [
    "BOT_REPLY_ACTIONS",
    "REVIEW_OUTCOMES",
    "Conversation",
    "ConversationStatus",
    "ConversationStore",
    "Direction",
    "ReviewOutcome",
    "StoreSendCaps",
    "StoredMessage",
    "as_naive_utc",
    "naive_utc_now",
]

ConversationStatus = Literal["bot", "paused_handoff", "paused_manual"]
"""Who owns a conversation: the assistant, a person after a hand-off, or a person who replied."""

Direction = Literal["inbound", "outbound"]

BOT_REPLY_ACTIONS = frozenset({"held", "sent"})
"""Outbound actions that count toward a conversation's bot reply count."""

ReviewOutcome = Literal["sent_as_written", "sent_edited", "discarded", "expired"]
"""What happened to a held draft once a person (or expiry) dealt with it."""

REVIEW_OUTCOMES: tuple[ReviewOutcome, ...] = (
    "sent_as_written",
    "sent_edited",
    "discarded",
    "expired",
)

REVIEW_ACTIONS: dict[str, str] = {
    "sent_as_written": "sent",
    "sent_edited": "sent",
    "discarded": "discarded",
    "expired": "expired",
}
"""The outbound action a resolved draft ends in."""

SUBJECT_CONTEXT = "inbox_messages.subject"
BODY_CONTEXT = "inbox_messages.body"
SENDER_CONTEXT = "inbox_messages.sender_address"


def as_naive_utc(moment: datetime) -> datetime:
    """``moment`` in the frame timestamps are stored in. Naive input is assumed to be UTC."""
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(UTC).replace(tzinfo=None)


def naive_utc_now() -> datetime:
    """The current time as naive UTC."""
    return as_naive_utc(datetime.now(UTC))


@dataclass(frozen=True)
class Conversation:
    """One conversation (a thread, a chat) on one channel. Holds no content."""

    id: int
    channel: str
    thread_key: str
    sender_key: str
    status: ConversationStatus
    pause_reason: str | None
    bot_reply_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredMessage:
    """The skeleton of one stored message: ids, triage, action and times. No content.

    ``reply_to_id`` links an outbound row to the inbound row it answers.
    ``has_content`` says whether encrypted content is held for it.
    ``held_because`` is why delivery held an outbound reply. A held reply is
    a draft: ``review_outcome``, ``reviewed_by`` (an identifier, never a name)
    and ``reviewed_at`` say what became of it. A held draft's ``action`` moves
    from ``held`` to ``reviewing`` while a person sends it, and ends as
    ``sent``, ``discarded``, ``expired`` or, if sending failed, ``failed``.
    """

    id: int
    conversation_id: int
    channel: str
    direction: Direction
    provider_message_id: str | None
    reply_to_id: int | None
    action: str
    kind: str | None
    category: str | None
    tier: str | None
    language: str | None
    confidence: float | None
    classifier: str | None
    shadow: Mapping[str, object] | None
    sources: tuple[str, ...]
    provider_ref: str | None
    created_at: datetime
    handled_at: datetime | None
    content_erased_at: datetime | None
    has_content: bool
    held_because: str | None = None
    review_outcome: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


@runtime_checkable
class ConversationStore(Protocol):
    """Every read and write of conversations and messages the core makes.

    Each write is durable when the method returns.
    """

    def conversation_for(self, channel: str, thread_key: str, sender_key: str) -> Conversation:
        """The conversation for this thread, created if new."""
        ...

    def get_conversation(self, conversation_id: int) -> Conversation | None:
        """The conversation with this id, if any."""
        ...

    def find_conversation(self, channel: str, thread_key: str) -> Conversation | None:
        """The conversation for this thread, if it exists. Never creates one."""
        ...

    def is_handled(self, channel: str, provider_message_id: str) -> bool:
        """True only when this inbound message reached a terminal state."""
        ...

    def record_inbound(self, conversation_id: int, message: IncomingMessage) -> StoredMessage:
        """The inbound row for ``message``, written now; the existing row on a retry."""
        ...

    def record_triage(
        self, message_id: int, decision: TriageDecision, shadow: TriageSignals | None
    ) -> None:
        """Attach the triage decision (and any shadow signals) to an inbound row."""
        ...

    def mark_handled(self, message_id: int, action: str) -> None:
        """Record that an inbound message is finished with, and how."""
        ...

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
        """An outbound row with action ``pending``, written before delivery is attempted."""
        ...

    def finish_outbound(
        self, message_id: int, *, action: str, provider_ref: str | None, held_because: str = ""
    ) -> None:
        """Record what delivery did. ``held`` and ``sent`` count as a bot reply."""
        ...

    def get_message(self, message_id: int) -> StoredMessage | None:
        """The message with this id, if any."""
        ...

    def held_for_review(self, conversation_id: int) -> tuple[StoredMessage, ...]:
        """Outbound replies in this conversation still ``held`` for a person, oldest first."""
        ...

    def claim_held(self, message_id: int) -> bool:
        """Atomically move a ``held`` reply to ``reviewing``. False if it was not ``held``.

        This is the compare-and-set that makes a draft sendable at most once,
        across threads and, for a shared database, across processes.
        """
        ...

    def resolve_review(
        self,
        message_id: int,
        *,
        outcome: ReviewOutcome,
        reviewer: str,
        provider_ref: str | None = None,
        text: str | None = None,
    ) -> None:
        """Finish a ``reviewing`` draft with ``outcome``; ``text`` replaces what is stored."""
        ...

    def fail_review(self, message_id: int) -> None:
        """A ``reviewing`` draft's send failed: mark it ``failed``, never to be retried."""
        ...

    def expire_held(self, before: datetime, *, reviewer: str) -> int:
        """Expire every ``held`` reply created before ``before`` (naive UTC). Returns the count."""
        ...

    def review_outcomes_between(self, start: datetime, end: datetime) -> dict[str, int]:
        """How many drafts ended in each outcome with ``reviewed_at`` in ``[start, end)``."""
        ...

    def outbound_for(self, reply_to_id: int) -> tuple[StoredMessage, ...]:
        """Every outbound row answering this inbound row, oldest first."""
        ...

    def messages_in(self, conversation_id: int) -> tuple[StoredMessage, ...]:
        """Every message in a conversation, oldest first."""
        ...

    def pause(self, conversation_id: int, reason: str) -> None:
        """Hand the conversation to a person. Does not override a manual pause."""
        ...

    def pause_manual(self, conversation_id: int) -> None:
        """A person replied. Only :meth:`resume` undoes this."""
        ...

    def resume(self, conversation_id: int) -> None:
        """Give the conversation back to the assistant. A person's action, never automatic."""
        ...

    def replies_sent_between(self, start: datetime, end: datetime) -> list[tuple[str, str]]:
        """``(sender_key, thread_key)`` for every reply sent in ``[start, end)``, naive UTC."""
        ...

    def read_content(self, message_id: int) -> dict[str, str] | None:
        """The decrypted content of one message, or None if none is held."""
        ...

    def erase_conversation(self, conversation_id: int) -> int:
        """Delete the content of every message in a conversation; keep the rows."""
        ...

    def erase_sender(self, sender_key: str) -> int:
        """Delete the content of every message in this sender's conversations."""
        ...

    def acquire_lease(self, conversation_id: int, owner: str, *, ttl: timedelta) -> bool:
        """Take the conversation's processing lease for ``ttl``. False if someone else holds it.

        A lease that has expired can be taken. Taking it again as its owner
        renews it. With a shared database this is atomic across processes.
        """
        ...

    def renew_lease(self, conversation_id: int, owner: str, *, ttl: timedelta) -> bool:
        """Extend the lease if ``owner`` still holds it. False if it expired and was taken."""
        ...

    def release_lease(self, conversation_id: int, owner: str) -> None:
        """Give the lease up, if ``owner`` holds it."""
        ...

    def erase_content_before(self, cutoff: datetime) -> int:
        """Delete the content of every message created before ``cutoff``; keep the rows.

        ``cutoff`` may be aware or naive UTC. Returns how many messages lost content.
        """
        ...

    def held_before(self, before: datetime) -> tuple[StoredMessage, ...]:
        """Every reply still ``held`` for a person, created before ``before``, oldest first.

        ``before`` may be aware or naive UTC.
        """
        ...

    def paused_before(self, before: datetime) -> tuple[Conversation, ...]:
        """Every conversation still paused after a hand-off since before ``before``, oldest first.

        A conversation a person replied in (``paused_manual``) is not listed:
        someone already has it. ``before`` may be aware or naive UTC.
        """
        ...

    def claim_reminder(self, key: str) -> bool:
        """Record that a reminder for ``key`` is being sent. False if one already was.

        Atomic, across processes for a shared database, so two reminder runs
        never both send the same one. ``key`` is at most 160 characters.
        """
        ...

    def release_reminder(self, key: str) -> None:
        """Forget a claimed reminder whose send failed, so the next run tries again."""
        ...


class StoreSendCaps:
    """Send caps counted from the store, so they survive restarts and hold across processes.

    Counts are read from the store on every check, so a send is counted once
    the pipeline has recorded it; :meth:`record_send` therefore does nothing.
    With concurrent workers the counts are as current as the store.
    """

    def __init__(
        self,
        store: ConversationStore,
        *,
        daily_cap: int,
        per_sender_cap: int,
        timezone: tzinfo = UTC,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if daily_cap < 1 or per_sender_cap < 1:
            raise ValueError("caps must be positive")
        self._store = store
        self.daily_cap = daily_cap
        self.per_sender_cap = per_sender_cap
        self._zone = timezone
        self._clock = clock

    def _window(self) -> tuple[datetime, datetime]:
        local = self._clock().astimezone(self._zone)
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        return as_naive_utc(start), as_naive_utc(start + timedelta(days=1))

    def allows(self, sender_key: str, thread_key: str) -> CapDecision:
        """Within the daily cap and the per-sender conversation cap for the local day."""
        sends = self._store.replies_sent_between(*self._window())
        if len(sends) >= self.daily_cap:
            return CapDecision.refuse("daily", f"{len(sends)} of {self.daily_cap} sent today")
        threads = {thread for sender, thread in sends if sender == sender_key}
        if thread_key not in threads and len(threads) >= self.per_sender_cap:
            return CapDecision.refuse(
                "per_sender",
                f"{len(threads)} of {self.per_sender_cap} conversations for this sender today",
            )
        return CapDecision.allow()

    def record_send(self, sender_key: str, thread_key: str) -> None:
        """Nothing to do: the store already holds the send once it is recorded."""

"""Held drafts: what a person does with them, and how often the assistant was right.

A reply that delivery held (draft mode, a language not signed off, a reached
cap, a handler asking for approval) is a draft waiting for a person. Its text
is in the store, encrypted, on the outbound row. :class:`DraftReview` is what
a review screen calls:

- :meth:`DraftReview.pending` lists a conversation's drafts with the decision
  that produced them (category, tier, confidence, classifier, sources and why
  it was held).
- :meth:`DraftReview.send` sends one as written or edited, through
  :meth:`inbox_core.delivery.Delivery.release_approved`, so the one path to
  the public is still the delivery module. A draft is claimed with an atomic
  compare-and-set before it is sent, so two clicks, two tabs or two processes
  send it at most once. A send that fails is marked ``failed`` and never
  retried, because it may or may not have reached the public.
- :meth:`DraftReview.discard` and :meth:`DraftReview.expire_before` close a
  draft without sending it.
- :meth:`DraftReview.outcomes` counts what happened over a window, which is
  the acceptance rate to watch before switching a category to ``auto``.

Reviewers are recorded by identifier (``chatwoot-user:5``), never by name or
address, because the store's skeleton outlives its content.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

from inbox_core.delivery import Delivery, DeliveryMode, ReleaseRefusedError
from inbox_core.messages import OutboundReply
from inbox_core.store import ConversationStore, ReviewOutcome, StoredMessage

__all__ = [
    "DraftContentUnavailableError",
    "DraftNotFoundError",
    "DraftNotPendingError",
    "DraftOutcomes",
    "DraftReview",
    "DraftSendFailedError",
    "HeldDraft",
    "ReviewResult",
]

logger = logging.getLogger("inbox_core.review")

_REVIEWER = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,63}$")


class DraftNotFoundError(LookupError):
    """No held draft has this id."""


class DraftNotPendingError(RuntimeError):
    """The draft was already sent, discarded, expired, failed or is being sent."""


class DraftSendFailedError(RuntimeError):
    """Sending the draft failed. It is marked ``failed`` and will not be retried."""


class DraftContentUnavailableError(RuntimeError):
    """The store holds no text for this draft (no cipher, or its content was erased)."""


@dataclass(frozen=True)
class HeldDraft:
    """One draft waiting for a person, with the decision that produced it."""

    id: int
    conversation_id: int
    channel: str
    thread_key: str
    inbound_id: int
    inbound_message_id: str
    kind: str
    language: str
    text: str = field(repr=False)
    sources: tuple[str, ...]
    held_because: str
    created_at: datetime
    category: str
    tier: str
    confidence: float | None
    classifier: str


@dataclass(frozen=True)
class ReviewResult:
    """What a review did with one draft."""

    draft_id: int
    outcome: ReviewOutcome
    reviewer: str
    provider_ref: str | None = None


@dataclass(frozen=True)
class DraftOutcomes:
    """Counts of what became of drafts over a window."""

    sent_as_written: int = 0
    sent_edited: int = 0
    discarded: int = 0
    expired: int = 0

    @property
    def resolved(self) -> int:
        """Every draft that reached an outcome."""
        return self.sent_as_written + self.sent_edited + self.discarded + self.expired

    @property
    def acceptance_rate(self) -> float | None:
        """Drafts sent exactly as written, over all resolved drafts. None when there are none."""
        return self.sent_as_written / self.resolved if self.resolved else None

    @property
    def sent_rate(self) -> float | None:
        """Drafts sent at all, edited or not, over all resolved drafts."""
        return (self.sent_as_written + self.sent_edited) / self.resolved if self.resolved else None


def _check_reviewer(reviewer: str) -> None:
    if not _REVIEWER.match(reviewer):
        raise ValueError("reviewer must be a lower-case identifier such as 'chatwoot-user:5'")


class DraftReview:
    """Lists, sends, discards and expires held drafts over a store and a delivery."""

    def __init__(self, store: ConversationStore, delivery: Delivery) -> None:
        self._store = store
        self._delivery = delivery

    @property
    def mode(self) -> DeliveryMode:
        """The delivery mode a send is released under."""
        return self._delivery.mode

    def _held(self, draft_id: int) -> StoredMessage:
        row = self._store.get_message(draft_id)
        if row is None or row.direction != "outbound" or row.reply_to_id is None:
            raise DraftNotFoundError(f"no draft id={draft_id}")
        return row

    def _describe(self, row: StoredMessage) -> HeldDraft:
        content = self._store.read_content(row.id)
        if content is None:
            raise DraftContentUnavailableError(f"no stored text for draft id={row.id}")
        inbound = self._store.get_message(row.reply_to_id or 0)
        conversation = self._store.get_conversation(row.conversation_id)
        if inbound is None or conversation is None:
            raise DraftNotFoundError(f"draft id={row.id} has lost its conversation")
        return HeldDraft(
            id=row.id,
            conversation_id=row.conversation_id,
            channel=row.channel,
            thread_key=conversation.thread_key,
            inbound_id=inbound.id,
            inbound_message_id=inbound.provider_message_id or "",
            kind=row.kind or "",
            language=row.language or "",
            text=content["text"],
            sources=row.sources,
            held_because=row.held_because or "",
            created_at=row.created_at,
            category=inbound.category or "",
            tier=inbound.tier or "",
            confidence=inbound.confidence,
            classifier=inbound.classifier or "",
        )

    def pending(self, conversation_id: int) -> tuple[HeldDraft, ...]:
        """The conversation's drafts still waiting for a person, oldest first."""
        return tuple(self._describe(row) for row in self._store.held_for_review(conversation_id))

    def get(self, draft_id: int) -> HeldDraft:
        """One draft still waiting for a person."""
        row = self._held(draft_id)
        if row.action != "held":
            raise DraftNotPendingError(f"draft id={draft_id} is {row.action}")
        return self._describe(row)

    def send(self, draft_id: int, *, reviewer: str, text: str | None = None) -> ReviewResult:
        """Send a draft as written, or with ``text`` instead. At most once."""
        _check_reviewer(reviewer)
        draft = self.get(draft_id)
        final = draft.text if text is None else text.strip()
        if not final.strip():
            raise ValueError("a draft cannot be sent empty")
        if self._delivery.mode is DeliveryMode.OFF:
            raise ReleaseRefusedError("delivery is off")
        inbound_content = self._store.read_content(draft.inbound_id)
        if inbound_content is None:
            raise DraftContentUnavailableError(f"no stored address for draft id={draft_id}")
        conversation = self._store.get_conversation(draft.conversation_id)
        sender_key = conversation.sender_key if conversation else ""
        if not self._store.claim_held(draft_id):
            raise DraftNotPendingError(f"draft id={draft_id} is no longer held")
        edited = final.strip() != draft.text.strip()
        reply = OutboundReply(
            thread_key=draft.thread_key,
            in_reply_to=draft.inbound_message_id,
            to_address=inbound_content["sender_address"],
            text=final,
            language=draft.language,
            kind=draft.kind,
            sources=draft.sources,
        )
        try:
            delivered = self._delivery.release_approved(reply, sender_key=sender_key)
        except Exception as exc:
            self._store.fail_review(draft_id)
            logger.warning("draft %s: send failed %s", draft_id, type(exc).__name__)
            raise DraftSendFailedError(
                f"sending draft id={draft_id} failed ({type(exc).__name__})"
            ) from None
        outcome: ReviewOutcome = "sent_edited" if edited else "sent_as_written"
        self._store.resolve_review(
            draft_id,
            outcome=outcome,
            reviewer=reviewer,
            provider_ref=delivered.provider_ref,
            text=final if edited else None,
        )
        logger.info("draft %s: %s by %s", draft_id, outcome, reviewer)
        return ReviewResult(draft_id, outcome, reviewer, delivered.provider_ref)

    def discard(self, draft_id: int, *, reviewer: str) -> ReviewResult:
        """Close a draft without sending it."""
        _check_reviewer(reviewer)
        self._held(draft_id)
        if not self._store.claim_held(draft_id):
            raise DraftNotPendingError(f"draft id={draft_id} is no longer held")
        self._store.resolve_review(draft_id, outcome="discarded", reviewer=reviewer)
        logger.info("draft %s: discarded by %s", draft_id, reviewer)
        return ReviewResult(draft_id, "discarded", reviewer)

    def expire_before(self, cutoff: datetime, *, reviewer: str = "expiry") -> int:
        """Expire every draft held since before ``cutoff``. Returns how many."""
        _check_reviewer(reviewer)
        return self._store.expire_held(cutoff, reviewer=reviewer)

    def outcomes(self, start: datetime, end: datetime) -> DraftOutcomes:
        """What became of drafts resolved in ``[start, end)``."""
        counts = self._store.review_outcomes_between(start, end)
        return DraftOutcomes(
            sent_as_written=counts.get("sent_as_written", 0),
            sent_edited=counts.get("sent_edited", 0),
            discarded=counts.get("discarded", 0),
            expired=counts.get("expired", 0),
        )

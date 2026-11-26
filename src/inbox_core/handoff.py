"""Hand-off side effects: what a channel does in its own inbox when a person must act.

When the pipeline hands a message to a person, or holds a drafted reply for a
person to review, a shared inbox such as Chatwoot has four things it can do
about it: post an internal note that only staff see, label the conversation,
open it so it shows up in a person's queue, and assign it to someone.
:class:`HandOffActions` is that protocol, and the pipeline calls it in that
order (note, labels, open, assign), after any holding message and before the
notifier:

1. ``add_internal_note`` and ``add_labels`` are best effort. A failure is
   logged by exception type, recorded in the audit record's
   ``handoff_failures``, and does not stop the hand-off.
2. ``open_for_person`` is the step that puts the conversation in front of a
   person, so a failure there fails closed: the message is left unhandled
   (``incomplete``) and retried, and the retry does not repeat a holding
   message or a draft that was already delivered.
3. ``assign`` comes after the opening and is best effort like the first two.
   It is last because a shared inbox may not tell anyone about an assignment
   made before the conversation is open: Chatwoot does not notify one made
   while a conversation is still pending, so assigning first was silent.

Everything a :class:`HandOffRequest` carries is built by the core from fixed
phrases, category and tier names, knowledge entry ids and the titles the
client gave those entries, and numbers. It holds no message content, so a
channel may post the note where staff can see it without the note becoming a
second copy of what the visitor wrote.

After an answer is sent automatically, the pipeline also posts one
``add_internal_note`` (purpose ``answered``) naming the knowledge entries the
answer was written from, so a person reading the conversation later sees what
it was based on; the public never sees the note, and the reply itself does not
name its sources. Nothing labels, assigns or opens an answered conversation. A
failed note is recorded as ``source_note`` in ``handoff_failures`` and does not
undo the answer.

A channel without a shared inbox (a mailbox read by one person) passes nothing
and gets :class:`NoHandOffActions`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

__all__ = [
    "HANDOFF_LABEL",
    "HANDOFF_STEPS",
    "REVIEW_LABEL",
    "UNAVAILABLE_LABEL",
    "HandOffActions",
    "HandOffPurpose",
    "HandOffRequest",
    "NoHandOffActions",
    "handoff_labels",
    "handoff_note",
]

HandOffPurpose = Literal["hand_off", "review", "answered"]
"""Why the inbox is told: the message is a person's, a draft awaits review, or
an answer was sent (``answered`` posts only the staff note of its sources)."""

HANDOFF_STEPS = ("add_internal_note", "add_labels", "open_for_person", "assign")
"""The order the pipeline calls the steps in."""

HANDOFF_LABEL = "handoff"
REVIEW_LABEL = "draft-pending"
UNAVAILABLE_LABEL = "classifier-unavailable"

_LABEL = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class HandOffRequest:
    """One hand-off, review or sent answer, as the channel's inbox needs to act on it.

    ``thread_key`` is the channel's conversation reference, ``conversation_id``
    the core store's. ``labels`` are lower-case identifiers. ``note`` is the
    staff-only text the core composed from fixed phrases; it is hidden from
    ``repr`` all the same, so a log line built from a request stays short.
    """

    purpose: HandOffPurpose
    channel: str
    thread_key: str
    message_id: str
    conversation_id: int | None
    category: str
    tier: str
    reason: str
    labels: tuple[str, ...]
    note: str = field(repr=False)

    def __post_init__(self) -> None:
        if self.purpose not in ("hand_off", "review", "answered"):
            raise ValueError("purpose must be 'hand_off', 'review' or 'answered'")
        for label in self.labels:
            if not _LABEL.match(label):
                raise ValueError("every label must be a lower-case identifier")


@runtime_checkable
class HandOffActions(Protocol):
    """A channel's shared-inbox actions for a hand-off or a draft awaiting review.

    Each method raises if it could not do its part. The pipeline decides what
    a failure means (see the module docstring); an implementation should not
    swallow its own errors.
    """

    def add_internal_note(self, request: HandOffRequest) -> None:
        """Post ``request.note`` where staff, and never the public, can read it."""
        ...

    def add_labels(self, request: HandOffRequest) -> None:
        """Attach ``request.labels`` to the conversation."""
        ...

    def assign(self, request: HandOffRequest) -> None:
        """Assign the conversation to whoever handles this inbox."""
        ...

    def open_for_person(self, request: HandOffRequest) -> None:
        """Put the conversation in a person's queue."""
        ...


class NoHandOffActions:
    """Does nothing: for channels without a shared inbox to act in."""

    def add_internal_note(self, request: HandOffRequest) -> None:
        """Nothing to post."""

    def add_labels(self, request: HandOffRequest) -> None:
        """Nothing to label."""

    def assign(self, request: HandOffRequest) -> None:
        """Nobody to assign."""

    def open_for_person(self, request: HandOffRequest) -> None:
        """Nothing to open."""


def handoff_labels(
    purpose: HandOffPurpose, category: str, *, classifier_unavailable: bool
) -> tuple[str, ...]:
    """The labels for a hand-off or review: what happened, the category, and any failure."""
    labels = [REVIEW_LABEL if purpose == "review" else HANDOFF_LABEL]
    if category and _LABEL.match(category):
        labels.append(category)
    if classifier_unavailable:
        labels.append(UNAVAILABLE_LABEL)
    return tuple(labels)


def handoff_note(
    purpose: HandOffPurpose,
    *,
    category: str,
    tier: str,
    reason: str,
    sources: tuple[str, ...],
    titles: Mapping[str, str] | None = None,
) -> str:
    """The staff-only note, built from fixed phrases, identifiers and entry titles.

    ``reason`` is the pipeline's own reason (a fixed phrase, category names and
    numbers, never message text), so the note can be posted as it is.
    ``titles`` maps a source id to its knowledge entry's title, for the
    "Sources:" line of a review or an answer.
    """
    named = "; ".join(f"{source} {(titles or {}).get(source, '')}".strip() for source in sources)
    if purpose == "answered":
        lines = [
            "inbox-core answered this message automatically.",
            f"Category: {category}. Tier: {tier}.",
        ]
        if named:
            lines.append(f"Sources: {named}.")
        return "\n".join(lines)
    if purpose == "review":
        lines = [
            "inbox-core drafted a reply and is holding it for review in the draft tab.",
            f"Category: {category}. Tier: {tier}.",
            f"Held because: {reason}.",
        ]
        if named:
            lines.append(f"Sources: {named}.")
        return "\n".join(lines)
    return "\n".join(
        [
            "inbox-core handed this conversation to a person.",
            f"Category: {category}. Tier: {tier}.",
            f"Reason: {reason}.",
        ]
    )

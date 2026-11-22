"""Channel-neutral message shapes, and the seam a channel plugs into.

Everything above a channel - guards, triage, handlers, delivery, the store and
the audit record - sees only :class:`IncomingMessage` and
:class:`OutboundReply`. A channel adapter fills them from its own payload.

Both are frozen: a pipeline that could rewrite the message it is triaging would
make the audit record a guess about what was actually classified.

What is core and what is channel-specific is decided by one question: does
anything in the core read it? The core reads the ids (dedupe and grouping), the
sender key (caps and flood guards), the text and subject (the classifier and the
privacy sweep) and the reply address (delivery). Email's RFC 5322 ids, its
``References`` chain, its headers and Gmail's label ids are read only by email
code, so they live in :mod:`inbox_core.channels.email` as an extension.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, TypeVar, runtime_checkable

__all__ = [
    "ChannelAdapter",
    "ChannelExtension",
    "IncomingMessage",
    "Labeller",
    "OutboundReply",
    "PollingChannel",
    "make_sender_key",
]


@dataclass(frozen=True)
class ChannelExtension:
    """Base class for the channel-specific part of a message or reply.

    Subclass it with a frozen dataclass holding whatever only that channel's
    code reads. Mark any field that can carry content or identity with
    ``field(repr=False)`` so it never reaches a log line by way of ``repr``.
    """


ExtensionT = TypeVar("ExtensionT", bound=ChannelExtension)


def _require(values: dict[str, str]) -> None:
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError(f"required field(s) empty: {', '.join(missing)}")


@dataclass(frozen=True)
class IncomingMessage:
    """One inbound message, normalised.

    ``sender_address`` is whatever the channel needs to address a reply (an
    email address, a phone number, a contact id). It must never be logged and
    is stored only encrypted. ``sender_key`` is its durable, non-identifying
    form (see :func:`make_sender_key`), which caps and guards count by.

    ``text``, ``subject`` and ``sender_address`` are hidden from ``repr`` so
    that logging or raising with a message object cannot leak what it says.
    """

    channel: str
    thread_key: str
    provider_message_id: str
    sender_key: str
    sender_address: str = field(repr=False)
    text: str = field(repr=False)
    subject: str = field(default="", repr=False)
    received_at: datetime | None = None
    extension: ChannelExtension | None = None

    def __post_init__(self) -> None:
        _require(
            {
                "channel": self.channel,
                "thread_key": self.thread_key,
                "provider_message_id": self.provider_message_id,
                "sender_key": self.sender_key,
            }
        )
        if self.received_at is not None and self.received_at.tzinfo is None:
            raise ValueError("received_at must be timezone-aware")

    def extension_as(self, kind: type[ExtensionT]) -> ExtensionT | None:
        """The channel extension if it is a ``kind``, else None."""
        return self.extension if isinstance(self.extension, kind) else None


@dataclass(frozen=True)
class OutboundReply:
    """One reply the core wants delivered, before delivery decides how.

    ``kind`` names the handler that produced the text (``grounded_answer``,
    ``template``, ``holding``), which is what draft-acceptance metrics group
    by. It is not a routing decision. ``sources`` are the ids of the knowledge
    entries the text was grounded in, empty when there were none.
    """

    thread_key: str
    in_reply_to: str
    to_address: str = field(repr=False)
    text: str = field(repr=False)
    language: str
    kind: str
    sources: tuple[str, ...] = ()
    extension: ChannelExtension | None = None

    def extension_as(self, kind: type[ExtensionT]) -> ExtensionT | None:
        """The channel extension if it is a ``kind``, else None."""
        return self.extension if isinstance(self.extension, kind) else None


def make_sender_key(identity: str) -> str:
    """The durable, non-identifying form of a sender identity.

    SHA-256 of the identity with surrounding space removed and lower-cased.
    Enough to count messages per sender; not enough to recover who wrote in.
    A channel whose identities need richer normalisation (parsing a ``From``
    header, formatting a phone number) normalises first and then calls this.
    """
    normalised = identity.strip().lower()
    if not normalised:
        raise ValueError("a sender identity is required to derive a sender key")
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


@runtime_checkable
class ChannelAdapter(Protocol):
    """What every channel provides: its name and a parser into the core shape.

    Deliberately narrow. Push channels (webhooks) only parse; polling and
    labelling are separate capabilities below, and sending goes through
    :class:`inbox_core.delivery.ReplySink`, never through the adapter.
    """

    channel: str

    def parse(self, raw: object) -> IncomingMessage:
        """Turn one raw channel payload into an :class:`IncomingMessage`."""
        ...


@runtime_checkable
class PollingChannel(ChannelAdapter, Protocol):
    """A channel the core asks for new messages, such as a mailbox."""

    def list_new(self, *, limit: int) -> list[object]:
        """Up to ``limit`` raw payloads not yet seen by this channel."""
        ...


@runtime_checkable
class Labeller(Protocol):
    """A channel that can tag a conversation, such as Gmail labels."""

    def label(self, message: IncomingMessage, names: list[str]) -> None:
        """Attach ``names`` to the conversation ``message`` belongs to."""
        ...

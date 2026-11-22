"""The email-specific part of a message and of a reply.

Kept out of the core shape because nothing in the core reads it: RFC 5322
threading ids, the headers the email guards inspect and Gmail's label ids
matter only to email code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from inbox_core.messages import ChannelExtension

__all__ = ["EmailDetails", "EmailReplyDetails"]


@dataclass(frozen=True)
class EmailDetails(ChannelExtension):
    """Email facts about one inbound message.

    ``headers`` are hidden from ``repr`` because ``From`` and ``Subject`` are
    among them.
    """

    rfc_message_id: str
    references: tuple[str, ...] = ()
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)
    label_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EmailReplyDetails(ChannelExtension):
    """Email facts a reply needs to thread correctly."""

    subject: str = field(default="", repr=False)
    references: tuple[str, ...] = ()

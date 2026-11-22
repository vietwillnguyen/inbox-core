"""Chatwoot's side of delivery and hand-off.

:class:`ChatwootReplySink` is the core's :class:`inbox_core.delivery.ReplySink`
for Chatwoot. ``send_to_public`` posts a reply in the conversation (the
``thread_key`` is Chatwoot's conversation display id) with the bot's token.
``hold_for_review`` sends nothing: the held reply is already in the core's
store, encrypted, and the draft tab reads it from there; the pipeline's
review hand-off (a staff note, the ``draft-pending`` label, opening the
conversation) is what tells a person it is waiting.

:class:`ChatwootHandOff` is the core's
:class:`inbox_core.handoff.HandOffActions`: a private note, labels (added to
the conversation's existing ones), an optional assignee, and opening the
conversation.
"""

from __future__ import annotations

from inbox_core.chatwoot.api import ChatwootApi
from inbox_core.handoff import HandOffRequest
from inbox_core.messages import OutboundReply

__all__ = ["ChatwootHandOff", "ChatwootReplySink", "conversation_id_of"]


def conversation_id_of(thread_key: str) -> int:
    """Chatwoot's conversation display id, from the core's thread key."""
    if not thread_key.isdigit():
        raise ValueError("a Chatwoot thread key is a conversation display id")
    return int(thread_key)


class ChatwootReplySink:
    """Posts replies into Chatwoot conversations; holds by leaving them in the store."""

    def __init__(self, api: ChatwootApi) -> None:
        self._api = api

    def send_to_public(self, reply: OutboundReply) -> str | None:
        """Post ``reply`` in its conversation, where the visitor sees it."""
        return self._api.send_message(conversation_id_of(reply.thread_key), reply.text)

    def hold_for_review(self, reply: OutboundReply) -> str | None:
        """Nothing to do: the core's store is the review queue the draft tab reads."""
        conversation_id_of(reply.thread_key)
        return None


class ChatwootHandOff:
    """Notes, labels, assignment and opening, through the bot's token."""

    def __init__(self, api: ChatwootApi, *, assignee_id: int | None = None) -> None:
        self._api = api
        self._assignee = assignee_id

    def add_internal_note(self, request: HandOffRequest) -> None:
        """A private note with the core's fixed-phrase summary."""
        self._api.add_private_note(conversation_id_of(request.thread_key), request.note)

    def add_labels(self, request: HandOffRequest) -> None:
        """Add the request's labels to the conversation."""
        if request.labels:
            self._api.add_labels(conversation_id_of(request.thread_key), request.labels)

    def assign(self, request: HandOffRequest) -> None:
        """Assign to the configured agent, if one is configured."""
        if self._assignee is not None:
            self._api.assign(conversation_id_of(request.thread_key), self._assignee)

    def open_for_person(self, request: HandOffRequest) -> None:
        """Set the conversation to ``open``."""
        self._api.open_conversation(conversation_id_of(request.thread_key))

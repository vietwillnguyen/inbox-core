"""Chatwoot agent-bot webhooks: is it really from Chatwoot, and what kind of event is it.

**Authenticity.** Chatwoot v4.19.1 signs every agent-bot webhook
(``lib/webhooks/trigger.rb``, ``app/listeners/agent_bot_listener.rb``)::

    X-Chatwoot-Timestamp: <unix seconds>
    X-Chatwoot-Signature: sha256=<hex HMAC-SHA256(bot secret, "<timestamp>.<raw body>")>
    X-Chatwoot-Delivery:  <random UUID per job; a retry of the job reuses it>

The secret is the agent bot's ``secret`` column. :func:`check_webhook` checks,
in order and in constant time where it matters: an unguessable path token
(so a scanner that finds the service cannot even reach the signature check),
the signature over the exact raw bytes, a timestamp within five minutes, and
that the delivery id has not been seen. It returns a rejection reason, or
None. The service then re-fetches the message from Chatwoot's API with the
bot's token and acts on what the API says, never on the webhook body, so even
a leaked secret cannot make the service act on a message that does not exist.

**Events.** The bot receives every event in its inbox. Only two matter:

- ``visitor_message``: ``message_created``, ``incoming``, not private. The core
  processes it.
- ``agent_reply``: ``message_created``, ``outgoing``, not private, sent by a
  ``user`` (a person, not the bot itself). The core treats it as "a person
  replied" and the bot stays silent there.

Everything else is ``ignored``: the bot's own messages (sender ``agent_bot``),
private notes, activity and template messages, ``message_updated``, status
changes and ``webwidget_triggered``. The webhook body's types are only a first
sort; the re-fetched message decides.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "MAX_SKEW_SECONDS",
    "DeliveryLog",
    "EventKind",
    "WebhookEvent",
    "check_webhook",
    "classify_event",
    "signature_for",
]

MAX_SKEW_SECONDS = 300
"""How far a webhook's timestamp may be from now, either way."""

EventKind = Literal["visitor_message", "agent_reply", "ignored"]


def signature_for(secret: str, timestamp: str, raw_body: bytes) -> str:
    """The ``X-Chatwoot-Signature`` value Chatwoot sends for this body and timestamp."""
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + raw_body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


class DeliveryLog:
    """Delivery ids seen recently, so a replayed signed request is refused.

    Bounded and in memory: it covers the five-minute timestamp window in one
    process. A replay to another process inside that window is still caught
    by the core, which skips a message it already handled.
    """

    def __init__(self, *, capacity: int = 10_000, ttl: float = 2 * MAX_SKEW_SECONDS) -> None:
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._capacity = capacity
        self._ttl = ttl
        self._lock = threading.Lock()

    def first_time(self, delivery_id: str, now: float) -> bool:
        """Record ``delivery_id``; False if it was seen within the window."""
        with self._lock:
            while self._seen:
                oldest, at = next(iter(self._seen.items()))
                if now - at <= self._ttl and len(self._seen) < self._capacity:
                    break
                del self._seen[oldest]
            if delivery_id in self._seen:
                return False
            self._seen[delivery_id] = now
            return True


def check_webhook(
    *,
    path_token: str,
    expected_path_token: str,
    secret: str,
    raw_body: bytes,
    timestamp: str | None,
    signature: str | None,
    delivery_id: str | None,
    deliveries: DeliveryLog,
    now: Callable[[], float] = time.time,
) -> str | None:
    """Why this request is not a genuine, fresh Chatwoot webhook, or None if it is."""
    if not expected_path_token or not hmac.compare_digest(
        path_token.encode(), expected_path_token.encode()
    ):
        return "bad_path"
    if not secret or not signature or not timestamp:
        return "unsigned"
    if not timestamp.isdigit():
        return "bad_timestamp"
    if not hmac.compare_digest(
        signature.encode(), signature_for(secret, timestamp, raw_body).encode()
    ):
        return "bad_signature"
    current = now()
    if abs(current - int(timestamp)) > MAX_SKEW_SECONDS:
        return "stale"
    if not delivery_id:
        return "no_delivery_id"
    if not deliveries.first_time(delivery_id, current):
        return "replayed"
    return None


@dataclass(frozen=True)
class WebhookEvent:
    """The ids of a verified event, and what kind it is. Holds no content."""

    kind: EventKind
    event: str
    account_id: int | None
    conversation_id: int | None
    message_id: int | None
    why_ignored: str = ""


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def classify_event(payload: Mapping[str, object]) -> WebhookEvent:
    """Sort a verified payload into the two kinds that matter, or ``ignored`` and why."""
    event = str(payload.get("event", ""))
    conversation = _mapping(payload.get("conversation"))
    # A message payload's "conversation" is Chatwoot's webhook form, whose
    # "id" is the display id the API and the dashboard use.
    conversation_id = _int(conversation.get("id"))
    account_id = _int(_mapping(payload.get("account")).get("id"))
    message_id = _int(payload.get("id")) if event == "message_created" else None

    def made(kind: EventKind, why: str = "") -> WebhookEvent:
        return WebhookEvent(kind, event, account_id, conversation_id, message_id, why)

    if event != "message_created":
        return made("ignored", "not a new message")
    if conversation_id is None or message_id is None:
        return made("ignored", "no ids")
    if payload.get("private") is True:
        return made("ignored", "private note")
    message_type = payload.get("message_type")
    sender_type = str(_mapping(payload.get("sender")).get("type", ""))
    if message_type == "incoming":
        return made("visitor_message")
    if message_type == "outgoing" and sender_type == "user":
        return made("agent_reply")
    if message_type == "outgoing" and sender_type == "agent_bot":
        return made("ignored", "the bot's own message")
    if message_type == "outgoing":
        return made("ignored", "outgoing message not from a person")
    return made("ignored", "activity or template message")

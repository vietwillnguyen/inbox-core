"""Delivery: the mode gate, the language gate, send caps, and the one path to the public.

Three modes and one question: given the mode, the reply's language and the
caps, where may this reply go?

- ``off``: nowhere. Nothing is sent and nothing is drafted. The pipeline still
  records and still escalates, because knowing about a sensitive message is not
  something a delivery switch should be able to turn off.
- ``draft``: held for a person to review. Never sent.
- ``auto``: sent, but only in a language the client has signed off for
  automatic sending, only within the caps, and only if the handler did not ask
  for approval. Every reason not to send holds the reply for review rather than
  dropping it.

:class:`ReplySink` is what a channel implements. Its ``send_to_public`` is
called from exactly one place in this package, ``Delivery._send``, which is
reached from two methods only: :meth:`Delivery.deliver`, after the route has
been decided as ``send``, and :meth:`Delivery.release_approved`, when a person
approved a held draft and delivery is not ``off``. A test walks the package
source to keep it that way.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, tzinfo
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from inbox_core.messages import OutboundReply

if TYPE_CHECKING:
    from inbox_core.config import DeliveryPolicy

__all__ = [
    "HANDLER_APPROVAL",
    "CapDecision",
    "Delivery",
    "DeliveryAction",
    "DeliveryMode",
    "DeliveryResult",
    "InMemorySendCaps",
    "ReleaseRefusedError",
    "ReplySink",
    "Route",
    "SendCaps",
    "choose_route",
    "parse_mode",
]

logger = logging.getLogger("inbox_core.delivery")


class DeliveryMode(StrEnum):
    """How replies are delivered: not at all, as drafts, or automatically."""

    OFF = "off"
    DRAFT = "draft"
    AUTO = "auto"


def parse_mode(value: str | None) -> DeliveryMode:
    """Read a mode from a setting. Anything unrecognised reads as ``off``.

    Fail-closed parsing rather than a raise: a typo in a runtime setting must
    stop the assistant, not crash it, and certainly not fall through to a mode
    that sends. (A configuration file is stricter: an unknown mode there is a
    :class:`inbox_core.config.ConfigError`.)
    """
    candidate = (value or "").strip().lower()
    try:
        return DeliveryMode(candidate)
    except ValueError:
        if candidate:
            logger.warning("unknown delivery mode; treating it as off")
        return DeliveryMode.OFF


class Route(StrEnum):
    """Where a reply goes: nowhere, to a person for review, or to the public."""

    NONE = "none"
    HOLD = "hold"
    SEND = "send"


DeliveryAction = Literal["none", "held", "sent"]
"""What delivery did, for the audit record."""


@dataclass(frozen=True)
class DeliveryResult:
    """What delivery did with one reply.

    ``provider_ref`` is whatever id the channel returned (a draft id, a
    message id). ``held_because`` says why a reply was not sent, as a short
    fixed phrase.
    """

    route: Route
    action: DeliveryAction
    provider_ref: str | None = None
    held_because: str = ""


@dataclass(frozen=True)
class CapDecision:
    """Whether a send is within the caps, and if not, which cap stopped it."""

    allowed: bool
    cap: str = ""
    reason: str = ""

    @classmethod
    def allow(cls) -> CapDecision:
        """Within every cap."""
        return cls(allowed=True)

    @classmethod
    def refuse(cls, cap: str, reason: str) -> CapDecision:
        """Stopped by ``cap``, with a reason made of numbers only."""
        return cls(allowed=False, cap=cap, reason=reason)


@runtime_checkable
class SendCaps(Protocol):
    """The bounds on how much one day and one sender can receive."""

    def allows(self, sender_key: str, thread_key: str) -> CapDecision:
        """Whether one more send to this sender, in this conversation, is allowed."""
        ...

    def record_send(self, sender_key: str, thread_key: str) -> None:
        """Count a send that just happened."""
        ...


class InMemorySendCaps:
    """Daily and per-sender caps counted in memory, per process.

    The per-sender cap counts conversations, not messages, so two replies in
    one conversation count once. "Today" is the organisation's local day, in
    ``timezone``: a server clock in UTC would otherwise roll the cap over in
    the middle of the organisation's morning. A deployment with more than one
    process, or that restarts, should count from its store instead (see
    :class:`inbox_core.store.StoreSendCaps`).
    """

    def __init__(
        self,
        *,
        daily_cap: int = 30,
        per_sender_cap: int = 2,
        timezone: tzinfo = UTC,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if daily_cap < 1 or per_sender_cap < 1:
            raise ValueError("caps must be positive")
        self.daily_cap = daily_cap
        self.per_sender_cap = per_sender_cap
        self._zone = timezone
        self._clock = clock
        self._day: date | None = None
        self._sent = 0
        self._threads: dict[str, set[str]] = {}

    @classmethod
    def from_policy(cls, policy: DeliveryPolicy) -> InMemorySendCaps:
        """Caps with the limits and timezone from a client's delivery policy."""
        return cls(
            daily_cap=policy.daily_send_cap,
            per_sender_cap=policy.per_sender_daily_cap,
            timezone=policy.zone,
        )

    @property
    def sent_today(self) -> int:
        """Sends counted on the current local day."""
        self._roll()
        return self._sent

    def _roll(self) -> None:
        today = self._clock().astimezone(self._zone).date()
        if today != self._day:
            self._day = today
            self._sent = 0
            self._threads = {}

    def allows(self, sender_key: str, thread_key: str) -> CapDecision:
        """Within the daily cap, and within the per-sender conversation cap."""
        self._roll()
        if self._sent >= self.daily_cap:
            return CapDecision.refuse("daily", f"{self._sent} of {self.daily_cap} sent today")
        threads = self._threads.get(sender_key, set())
        if thread_key not in threads and len(threads) >= self.per_sender_cap:
            return CapDecision.refuse(
                "per_sender",
                f"{len(threads)} of {self.per_sender_cap} conversations for this sender today",
            )
        return CapDecision.allow()

    def record_send(self, sender_key: str, thread_key: str) -> None:
        """Count one send."""
        self._roll()
        self._sent += 1
        self._threads.setdefault(sender_key, set()).add(thread_key)


@runtime_checkable
class ReplySink(Protocol):
    """A channel's outbound side: one way to the public, one way to a person.

    ``send_to_public`` delivers to the person who wrote in. ``hold_for_review``
    leaves the reply where a person can approve it (a Gmail draft, a private
    note, a review queue) and must never reach the public. Both return the
    channel's id for what they created, or None.
    """

    def send_to_public(self, reply: OutboundReply) -> str | None:
        """Send ``reply`` to the public. Called only by :class:`Delivery`."""
        ...

    def hold_for_review(self, reply: OutboundReply) -> str | None:
        """Hold ``reply`` for a person to review. Never reaches the public."""
        ...


HANDLER_APPROVAL = "the handler asked for approval"
"""Why a reply was held when its handler set ``requires_approval``."""


def choose_route(
    mode: DeliveryMode,
    language: str,
    auto_languages: frozenset[str],
    *,
    requires_approval: bool = False,
    approval_reason: str = HANDLER_APPROVAL,
) -> tuple[Route, str]:
    """Where a reply may go before caps are considered, and why not further.

    A pure table: ``off`` is nowhere, ``draft`` is held, and ``auto`` sends
    only a reply in a signed-off language that did not ask for approval.
    ``approval_reason`` is the fixed phrase recorded when approval holds it.
    """
    if mode is DeliveryMode.OFF:
        return Route.NONE, "delivery is off"
    if mode is DeliveryMode.DRAFT:
        return Route.HOLD, "draft mode"
    if requires_approval:
        return Route.HOLD, approval_reason
    if language not in auto_languages:
        return Route.HOLD, f"language {language} is not signed off for automatic sending"
    return Route.SEND, ""


class ReleaseRefusedError(RuntimeError):
    """A person's approval cannot be delivered, because delivery is ``off``."""


@dataclass
class Delivery:
    """Delivers replies through a sink under a mode, language gates and caps.

    This is the only object in the package that may call
    :meth:`ReplySink.send_to_public`.
    """

    sink: ReplySink
    mode: DeliveryMode
    auto_languages: frozenset[str]
    caps: SendCaps

    def __post_init__(self) -> None:
        if not isinstance(self.auto_languages, frozenset):
            raise ValueError("auto_languages must be a frozenset of language codes")

    def deliver(
        self,
        reply: OutboundReply,
        *,
        sender_key: str,
        requires_approval: bool = False,
        approval_reason: str = HANDLER_APPROVAL,
    ) -> DeliveryResult:
        """Route ``reply`` and deliver it. A failed send propagates and is not counted."""
        route, why = choose_route(
            self.mode,
            reply.language,
            self.auto_languages,
            requires_approval=requires_approval,
            approval_reason=approval_reason,
        )
        if route is Route.NONE:
            return DeliveryResult(Route.NONE, "none", None, why)
        if route is Route.SEND:
            decision = self.caps.allows(sender_key, reply.thread_key)
            if not decision.allowed:
                route, why = Route.HOLD, f"{decision.cap} cap reached"
        if route is Route.HOLD:
            return DeliveryResult(Route.HOLD, "held", self.sink.hold_for_review(reply), why)
        ref = self._send(reply)
        self.caps.record_send(sender_key, reply.thread_key)
        return DeliveryResult(Route.SEND, "sent", ref, "")

    def release_approved(self, reply: OutboundReply, *, sender_key: str) -> DeliveryResult:
        """Send a held draft a person approved. Refused only when delivery is ``off``.

        The mode, language and handler gates exist to stop the assistant
        sending on its own; a person approving a specific text is the decision
        those gates defer to, so they do not apply. The caps do not apply
        either (they bound the assistant, not staff), but the send is counted.
        ``off`` is the switch that stops all delivery, so it refuses.
        """
        if self.mode is DeliveryMode.OFF:
            raise ReleaseRefusedError("delivery is off")
        ref = self._send(reply)
        self.caps.record_send(sender_key, reply.thread_key)
        return DeliveryResult(Route.SEND, "sent", ref, "")

    def _send(self, reply: OutboundReply) -> str | None:
        return self.sink.send_to_public(reply)

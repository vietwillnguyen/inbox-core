"""Guards: cheap, deterministic checks that run before any model sees a message.

A guard returns a :class:`GuardVerdict` or None. A verdict either drops the
message (``drop``: nothing to answer and nobody to tell, such as an empty
message or a flood) or sends it straight to a person without classifying it
(``hand_off``: something a model should not be trusted with, such as an
oversize message).

The guards here are channel-neutral. A channel adds its own by implementing
:class:`Guard` and passing it to the pipeline after the defaults, typically
reading its own extension::

    class AutoSubmittedGuard:
        name = "email_auto_submitted"

        def check(self, message):
            details = message.extension_as(EmailDetails)
            if details and details.headers.get("auto-submitted", "no") != "no":
                return GuardVerdict("drop", "auto-submitted message")
            return None

Reasons are short fixed phrases. They reach the audit record, so a guard must
never put any part of the message into one.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol, runtime_checkable

from inbox_core.messages import IncomingMessage

__all__ = [
    "EmptyMessageGuard",
    "Guard",
    "GuardAction",
    "GuardResult",
    "GuardVerdict",
    "OversizeGuard",
    "SenderFloodGuard",
    "default_guards",
    "run_guards",
]

logger = logging.getLogger("inbox_core.guards")

GuardAction = Literal["drop", "hand_off"]
"""What a guard decided: ignore the message, or give it to a person unclassified."""

MAX_REASON = 120


@dataclass(frozen=True)
class GuardVerdict:
    """A guard's decision about one message."""

    action: GuardAction
    reason: str

    def __post_init__(self) -> None:
        if self.action not in ("drop", "hand_off"):
            raise ValueError("action must be 'drop' or 'hand_off'")
        if not self.reason or len(self.reason) > MAX_REASON:
            raise ValueError(f"reason must be a fixed phrase of at most {MAX_REASON} characters")


@dataclass(frozen=True)
class GuardResult:
    """A verdict together with the name of the guard that gave it."""

    guard: str
    action: GuardAction
    reason: str


@runtime_checkable
class Guard(Protocol):
    """One check. Returns a verdict to stop the message, or None to let it through."""

    name: str

    def check(self, message: IncomingMessage) -> GuardVerdict | None:
        """The verdict for ``message``, or None."""
        ...


class EmptyMessageGuard:
    """Drops a message with no text and no subject."""

    name = "empty_message"

    def check(self, message: IncomingMessage) -> GuardVerdict | None:
        """``drop`` when there is nothing to read."""
        if message.text.strip() or message.subject.strip():
            return None
        return GuardVerdict("drop", "empty message")


class OversizeGuard:
    """Hands a very long message to a person instead of a model.

    Not a drop: a long message from a person may be the important one. It is
    kept away from the classifier because cost and prompt-injection surface
    both grow with length.
    """

    name = "oversize"

    def __init__(self, max_chars: int = 8000) -> None:
        if max_chars < 1:
            raise ValueError("max_chars must be at least 1")
        self.max_chars = max_chars

    def check(self, message: IncomingMessage) -> GuardVerdict | None:
        """``hand_off`` when text and subject together exceed ``max_chars``."""
        if len(message.text) + len(message.subject) <= self.max_chars:
            return None
        return GuardVerdict("hand_off", f"message longer than {self.max_chars} characters")


class SenderFloodGuard:
    """Drops messages from a sender beyond ``max_messages`` within ``window``.

    This is the loop bound: a misbehaving auto-responder, or someone pasting
    the same question repeatedly, cannot drive more than this many model calls.
    Counts by ``sender_key``, so it never holds an address, and forgets a
    sender once their window has passed. State is in memory and per process.
    """

    name = "sender_flood"

    def __init__(
        self,
        max_messages: int = 5,
        window: timedelta = timedelta(minutes=10),
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if max_messages < 1 or window <= timedelta(0):
            raise ValueError("max_messages and window must be positive")
        self.max_messages = max_messages
        self.window = window
        self._clock = clock
        self._seen: dict[str, deque[datetime]] = {}

    @property
    def tracked_senders(self) -> int:
        """How many senders are currently remembered."""
        return len(self._seen)

    def check(self, message: IncomingMessage) -> GuardVerdict | None:
        """Count this message, then ``drop`` it if the sender is over the limit."""
        now = self._clock()
        self._forget_before(now - self.window)
        times = self._seen.setdefault(message.sender_key, deque())
        times.append(now)
        if len(times) <= self.max_messages:
            return None
        minutes = int(self.window.total_seconds() // 60)
        return GuardVerdict(
            "drop", f"more than {self.max_messages} messages from one sender in {minutes} minutes"
        )

    def _forget_before(self, cutoff: datetime) -> None:
        for key in list(self._seen):
            times = self._seen[key]
            while times and times[0] <= cutoff:
                times.popleft()
            if not times:
                del self._seen[key]


def default_guards() -> tuple[Guard, ...]:
    """The channel-neutral guards with their default limits."""
    return (EmptyMessageGuard(), OversizeGuard(), SenderFloodGuard())


def run_guards(guards: Iterable[Guard], message: IncomingMessage) -> GuardResult | None:
    """The first guard verdict for ``message``, or None if every guard passes.

    A guard that raises fails closed: the message goes to a person, and only
    the exception's type name is kept.
    """
    for guard in guards:
        try:
            verdict = guard.check(message)
        except Exception as exc:
            logger.warning(
                "guard %s failed for %s: %s",
                guard.name,
                message.provider_message_id,
                type(exc).__name__,
            )
            return GuardResult(
                guard.name, "hand_off", f"guard {guard.name} failed ({type(exc).__name__})"
            )
        if verdict is not None:
            return GuardResult(guard.name, verdict.action, verdict.reason)
    return None

"""Channel-neutral guards, and the extension point for channel-specific ones."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from inbox_core.channels.email import EmailDetails
from inbox_core.guards import (
    EmptyMessageGuard,
    Guard,
    GuardResult,
    GuardVerdict,
    OversizeGuard,
    SenderFloodGuard,
    default_guards,
    run_guards,
)
from inbox_core.messages import IncomingMessage
from tests.helpers import message

SECRET = "please call me back about the stolen frame"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class TestEmptyMessage:
    @pytest.mark.parametrize("text", ["", "   ", "\n\t"])
    def test_drops_a_message_with_nothing_in_it(self, text: str) -> None:
        verdict = EmptyMessageGuard().check(message(text))
        assert verdict == GuardVerdict("drop", "empty message")

    def test_a_subject_alone_is_not_empty(self) -> None:
        assert EmptyMessageGuard().check(message("", subject="Hours?")) is None

    def test_passes_a_real_message(self) -> None:
        assert EmptyMessageGuard().check(message("hello")) is None


class TestOversize:
    def test_hands_an_oversize_message_to_a_person_rather_than_dropping_it(self) -> None:
        verdict = OversizeGuard(max_chars=10).check(message("x" * 11))
        assert verdict == GuardVerdict("hand_off", "message longer than 10 characters")

    def test_counts_the_subject(self) -> None:
        assert OversizeGuard(max_chars=10).check(message("x" * 5, subject="y" * 6)) is not None

    def test_at_the_limit_passes(self) -> None:
        assert OversizeGuard(max_chars=10).check(message("x" * 10)) is None

    def test_limit_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="max_chars"):
            OversizeGuard(max_chars=0)


class TestSenderFlood:
    def test_drops_beyond_the_limit_within_the_window(self) -> None:
        clock = Clock()
        guard = SenderFloodGuard(max_messages=2, window=timedelta(minutes=10), clock=clock)
        assert guard.check(message(message_id="1")) is None
        assert guard.check(message(message_id="2")) is None
        verdict = guard.check(message(message_id="3"))
        assert verdict == GuardVerdict("drop", "more than 2 messages from one sender in 10 minutes")

    def test_counts_each_sender_separately(self) -> None:
        guard = SenderFloodGuard(max_messages=1, clock=Clock())
        assert guard.check(message(address="a@example.com")) is None
        assert guard.check(message(address="b@example.com")) is None
        assert guard.check(message(address="a@example.com")) is not None

    def test_the_window_slides(self) -> None:
        clock = Clock()
        guard = SenderFloodGuard(max_messages=1, window=timedelta(minutes=10), clock=clock)
        assert guard.check(message()) is None
        clock.now += timedelta(minutes=10, seconds=1)
        assert guard.check(message()) is None

    def test_old_senders_are_forgotten(self) -> None:
        clock = Clock()
        guard = SenderFloodGuard(max_messages=5, window=timedelta(minutes=1), clock=clock)
        for n in range(50):
            guard.check(message(address=f"s{n}@example.com"))
        clock.now += timedelta(minutes=2)
        guard.check(message(address="late@example.com"))
        assert guard.tracked_senders == 1

    @pytest.mark.parametrize(
        "kwargs", [{"max_messages": 0}, {"window": timedelta(0)}, {"window": timedelta(-1)}]
    )
    def test_bounds_must_be_positive(self, kwargs: dict[str, object]) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            SenderFloodGuard(**kwargs)  # type: ignore[arg-type]


class TestRunGuards:
    def test_first_verdict_wins_and_names_its_guard(self) -> None:
        result = run_guards(default_guards(), message(""))
        assert result == GuardResult(guard="empty_message", action="drop", reason="empty message")

    def test_none_when_every_guard_passes(self) -> None:
        assert run_guards(default_guards(), message("Is the shop open?")) is None

    def test_a_crashing_guard_fails_closed_to_a_person(self) -> None:
        class Broken:
            name = "broken"

            def check(self, message: IncomingMessage) -> GuardVerdict | None:
                raise RuntimeError(SECRET)

        result = run_guards((Broken(),), message(SECRET))
        assert result is not None
        assert result.action == "hand_off"
        assert result.reason == "guard broken failed (RuntimeError)"
        assert "stolen" not in repr(result)

    def test_a_verdict_reason_must_be_a_short_fixed_phrase(self) -> None:
        with pytest.raises(ValueError, match="reason"):
            GuardVerdict("drop", "x" * 121)
        with pytest.raises(ValueError, match="action"):
            GuardVerdict("explode", "nope")  # type: ignore[arg-type]

    def test_defaults_are_the_three_channel_neutral_guards(self) -> None:
        assert [guard.name for guard in default_guards()] == [
            "empty_message",
            "oversize",
            "sender_flood",
        ]


@dataclass
class AutoSubmittedGuard:
    """What a channel-specific guard looks like: email's auto-reply header."""

    name: str = "email_auto_submitted"

    def check(self, message: IncomingMessage) -> GuardVerdict | None:
        details = message.extension_as(EmailDetails)
        if details is None:
            return None
        if details.headers.get("auto-submitted", "no").lower() != "no":
            return GuardVerdict("drop", "auto-submitted message")
        return None


def test_a_channel_specific_guard_plugs_in_through_the_same_protocol() -> None:
    guard = AutoSubmittedGuard()
    assert isinstance(guard, Guard)
    auto = IncomingMessage(
        channel="email",
        thread_key="t",
        provider_message_id="m",
        sender_key="k",
        sender_address="noreply@example.com",
        text="I am away until Monday",
        extension=EmailDetails(
            rfc_message_id="<a@m.example>", headers={"auto-submitted": "auto-replied"}
        ),
    )
    result = run_guards((*default_guards(), guard), auto)
    assert result == GuardResult("email_auto_submitted", "drop", "auto-submitted message")
    assert run_guards((guard,), message("web chat has no headers")) is None

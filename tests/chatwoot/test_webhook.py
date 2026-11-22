"""Webhook authenticity and event sorting, against Chatwoot v4.19.1's own scheme."""

from __future__ import annotations

from typing import Any

import pytest

from inbox_core.chatwoot.webhook import (
    MAX_SKEW_SECONDS,
    DeliveryLog,
    check_webhook,
    classify_event,
    signature_for,
)
from tests.chatwoot.conftest import message_payload

# Computed inside chatwoot/chatwoot:v4.19.1-ce with Chatwoot's own expression
# from lib/webhooks/trigger.rb:
#   OpenSSL::HMAC.hexdigest('SHA256', secret, "#{ts}.#{body}")
RUBY_BODY = '{"event":"message_created","id":7,"content":"Héllo"}'.encode()
RUBY_SIGNATURE = "sha256=25ef833dbc38caadc076241876da512cfbffef091a554371dc9795cd5d123056"
NOW = 1_700_000_000


def test_the_signature_matches_chatwoots_own_computation() -> None:
    assert signature_for("example-bot-secret", "1700000000", RUBY_BODY) == RUBY_SIGNATURE


def check(**changes: Any) -> str | None:
    values: dict[str, Any] = {
        "path_token": "p" * 32,
        "expected_path_token": "p" * 32,
        "secret": "example-bot-secret",
        "raw_body": RUBY_BODY,
        "timestamp": "1700000000",
        "signature": RUBY_SIGNATURE,
        "delivery_id": "d-1",
        "deliveries": DeliveryLog(),
        "now": lambda: float(NOW),
    }
    values.update(changes)
    return check_webhook(**values)


class TestCheckWebhook:
    def test_a_genuine_webhook_passes(self) -> None:
        assert check() is None

    @pytest.mark.parametrize(
        ("changes", "reason"),
        [
            ({"path_token": "q" * 32}, "bad_path"),
            ({"path_token": ""}, "bad_path"),
            ({"expected_path_token": ""}, "bad_path"),
            ({"signature": None}, "unsigned"),
            ({"timestamp": None}, "unsigned"),
            ({"secret": ""}, "unsigned"),
            ({"timestamp": "17e8"}, "bad_timestamp"),
            ({"signature": RUBY_SIGNATURE[:-1] + "0"}, "bad_signature"),
            ({"secret": "another-secret"}, "bad_signature"),
            ({"raw_body": RUBY_BODY + b" "}, "bad_signature"),
            ({"signature": "sha1=" + RUBY_SIGNATURE[7:]}, "bad_signature"),
            ({"now": lambda: float(NOW + MAX_SKEW_SECONDS + 1)}, "stale"),
            ({"now": lambda: float(NOW - MAX_SKEW_SECONDS - 1)}, "stale"),
            ({"delivery_id": None}, "no_delivery_id"),
        ],
    )
    def test_anything_else_is_refused_with_a_reason(
        self, changes: dict[str, Any], reason: str
    ) -> None:
        assert check(**changes) == reason

    def test_a_re_signed_timestamp_needs_the_secret(self) -> None:
        # Moving the timestamp forward invalidates the signature.
        assert check(timestamp=str(NOW + 10)) == "bad_signature"

    def test_a_replayed_delivery_is_refused(self) -> None:
        log = DeliveryLog()
        assert check(deliveries=log) is None
        assert check(deliveries=log) == "replayed"
        assert check(deliveries=log, delivery_id="d-2") is None

    def test_the_delivery_log_forgets_after_its_window_and_stays_bounded(self) -> None:
        log = DeliveryLog(capacity=2, ttl=10)
        assert log.first_time("a", 0)
        assert not log.first_time("a", 5)
        assert log.first_time("a", 20)
        assert log.first_time("b", 21)
        assert log.first_time("c", 22)
        assert log.first_time("a", 23)  # "a" was pushed out by the bound


class TestClassify:
    def test_a_visitor_message(self) -> None:
        event = classify_event(message_payload(10, 200, "hi"))
        assert (event.kind, event.conversation_id, event.message_id, event.account_id) == (
            "visitor_message",
            10,
            200,
            1,
        )

    def test_an_agent_reply(self) -> None:
        event = classify_event(
            message_payload(10, 201, "hi", message_type="outgoing", sender_type="user")
        )
        assert event.kind == "agent_reply"

    @pytest.mark.parametrize(
        ("payload", "why"),
        [
            (
                message_payload(10, 1, "x", message_type="outgoing", sender_type="agent_bot"),
                "the bot's own message",
            ),
            (
                message_payload(10, 1, "x", message_type="outgoing"),
                "outgoing message not from a person",
            ),
            (
                message_payload(
                    10, 1, "x", message_type="outgoing", sender_type="user", private=True
                ),
                "private note",
            ),
            (message_payload(10, 1, "x", message_type="activity"), "activity or template message"),
            (message_payload(10, 1, "x", message_type="template"), "activity or template message"),
            (message_payload(10, 1, "x", event="message_updated"), "not a new message"),
            ({"event": "conversation_status_changed", "id": 10}, "not a new message"),
            ({"event": "webwidget_triggered"}, "not a new message"),
            ({"event": "message_created", "id": "x", "conversation": {}}, "no ids"),
            ({"event": "message_created", "id": True, "conversation": {"id": 3}}, "no ids"),
        ],
    )
    def test_everything_else_is_ignored_with_a_reason(
        self, payload: dict[str, Any], why: str
    ) -> None:
        event = classify_event(payload)
        assert (event.kind, event.why_ignored) == ("ignored", why)

    def test_string_ids_are_read(self) -> None:
        event = classify_event(
            {
                "event": "message_created",
                "id": "9",
                "conversation": {"id": "4"},
                "message_type": "incoming",
            }
        )
        assert (event.conversation_id, event.message_id) == (4, 9)

    def test_the_event_holds_no_content(self) -> None:
        assert "secret phrase" not in repr(classify_event(message_payload(1, 2, "secret phrase")))

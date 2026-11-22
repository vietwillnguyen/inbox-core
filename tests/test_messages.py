"""The channel-neutral message shapes and the channel adapter seam."""

import dataclasses
from datetime import UTC, datetime

import pytest

from inbox_core.channels.email import EmailDetails, EmailReplyDetails
from inbox_core.messages import (
    ChannelAdapter,
    IncomingMessage,
    Labeller,
    OutboundReply,
    PollingChannel,
    make_sender_key,
)

ADDRESS = "visitor@example.com"


def incoming(**overrides: object) -> IncomingMessage:
    values: dict[str, object] = {
        "channel": "web",
        "thread_key": "conv-1",
        "provider_message_id": "msg-1",
        "sender_key": make_sender_key(ADDRESS),
        "sender_address": ADDRESS,
        "text": "Do you lend ladders on weekends?",
    }
    values.update(overrides)
    return IncomingMessage(**values)  # type: ignore[arg-type]


class TestIncomingMessage:
    def test_is_frozen(self) -> None:
        message = incoming()
        with pytest.raises(dataclasses.FrozenInstanceError):
            message.text = "changed"  # type: ignore[misc]

    def test_channel_neutral_defaults(self) -> None:
        message = incoming()
        assert message.subject == ""
        assert message.received_at is None
        assert message.extension is None

    def test_repr_never_shows_content_or_address(self) -> None:
        message = incoming(subject="Ladder question")
        shown = repr(message)
        assert "ladders" not in shown
        assert "Ladder question" not in shown
        assert ADDRESS not in shown
        assert "msg-1" in shown

    def test_required_ids_must_be_present(self) -> None:
        for field in ("channel", "thread_key", "provider_message_id", "sender_key"):
            with pytest.raises(ValueError, match=field):
                incoming(**{field: ""})

    def test_received_at_must_be_timezone_aware(self) -> None:
        with pytest.raises(ValueError, match="received_at"):
            incoming(received_at=datetime(2026, 1, 1))  # noqa: DTZ001
        assert incoming(received_at=datetime(2026, 1, 1, tzinfo=UTC)).received_at

    def test_email_details_live_in_a_typed_extension(self) -> None:
        details = EmailDetails(
            rfc_message_id="<abc@mail.example>",
            references=("<x@mail.example>",),
            headers={"auto-submitted": "no"},
            label_ids=("INBOX",),
        )
        message = incoming(channel="email", extension=details)
        assert message.extension_as(EmailDetails) is details
        assert incoming().extension_as(EmailDetails) is None

    def test_extension_of_another_type_is_not_returned(self) -> None:
        message = incoming(extension=EmailReplyDetails(subject="Re: hi"))
        assert message.extension_as(EmailDetails) is None


class TestOutboundReply:
    def test_is_frozen_and_hides_content_in_repr(self) -> None:
        reply = OutboundReply(
            thread_key="conv-1",
            in_reply_to="msg-1",
            to_address=ADDRESS,
            text="Yes, ladders can be borrowed on Saturdays.",
            language="en",
            kind="grounded_answer",
            sources=("KB-04",),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            reply.text = "x"  # type: ignore[misc]
        assert "ladders" not in repr(reply)
        assert ADDRESS not in repr(reply)
        assert "KB-04" in repr(reply)

    def test_email_reply_details_are_an_extension(self) -> None:
        extra = EmailReplyDetails(subject="Re: Ladder question", references=("<a@m.example>",))
        reply = OutboundReply(
            thread_key="t",
            in_reply_to="m",
            to_address=ADDRESS,
            text="hello",
            language="en",
            kind="template",
            extension=extra,
        )
        assert reply.extension_as(EmailReplyDetails) is extra
        assert "Ladder question" not in repr(reply)


class TestSenderKey:
    def test_is_a_sha256_hex_digest(self) -> None:
        key = make_sender_key(ADDRESS)
        assert len(key) == 64
        int(key, 16)

    def test_normalises_case_and_surrounding_space(self) -> None:
        assert make_sender_key("  Visitor@Example.COM ") == make_sender_key(ADDRESS)

    def test_does_not_contain_the_address(self) -> None:
        assert "visitor" not in make_sender_key(ADDRESS)

    def test_empty_identity_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="identity"):
            make_sender_key("   ")


class FakeWebChannel:
    channel = "web"

    def parse(self, raw: object) -> IncomingMessage:
        assert isinstance(raw, dict)
        return incoming(provider_message_id=str(raw["id"]))

    def list_new(self, *, limit: int) -> list[object]:
        return [{"id": n} for n in range(limit)]

    def label(self, message: IncomingMessage, names: list[str]) -> None:
        self.labelled = (message.provider_message_id, names)


def test_adapter_protocols_are_structural() -> None:
    adapter = FakeWebChannel()
    assert isinstance(adapter, ChannelAdapter)
    assert isinstance(adapter, PollingChannel)
    assert isinstance(adapter, Labeller)
    assert adapter.parse({"id": 7}).provider_message_id == "7"


def test_a_push_channel_need_not_poll() -> None:
    class PushOnly:
        channel = "web"

        def parse(self, raw: object) -> IncomingMessage:
            return incoming()

    assert isinstance(PushOnly(), ChannelAdapter)
    assert not isinstance(PushOnly(), PollingChannel)

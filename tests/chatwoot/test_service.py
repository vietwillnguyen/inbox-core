"""The webhook side of the service, over a fake Chatwoot."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from inbox_core.chatwoot.webhook import signature_for
from tests.chatwoot.conftest import (
    BOT_SECRET,
    PATH_TOKEN,
    Stack,
    build_stack,
    message_payload,
    showing_sources,
)

QUESTION = "What are your opening hours?"
DAMAGE = "The drill I borrowed stopped working and burned my hand"


def last_decision(stack: Stack) -> str:
    return str(stack.audit.records[-1].decision)


def metrics(stack: Stack) -> dict[str, object]:
    response = stack.client.get("/metrics")
    assert response.status_code == 200
    data: dict[str, object] = response.json()
    return data


class TestPublicLinks:
    """``delivery.show_sources``: a link to the public page, never an id or title."""

    def test_off_the_visitor_sees_the_answer_alone(self, stack: Stack) -> None:
        stack.visitor_says(10, 200, QUESTION)
        (reply,) = stack.chatwoot.public_messages(10)
        assert "https://" not in reply
        assert "More:" not in reply

    def test_on_the_visitor_sees_the_public_link_and_staff_keep_the_source(
        self, tmp_path: Path
    ) -> None:
        stack = build_stack(tmp_path, env={"INBOX_CORE_CONFIG": str(showing_sources(tmp_path))})
        try:
            stack.visitor_says(10, 200, QUESTION)
            (reply,) = stack.chatwoot.public_messages(10)
            assert reply.startswith("The library is open on Wednesdays")
            assert reply.endswith("\n\nMore: https://brambleford-tools.example/visit")
            assert "TL-01" not in reply
            assert "Opening hours" not in reply
            assert stack.chatwoot.notes(10) == [
                "inbox-core answered this message automatically.\n"
                "Category: faq. Tier: auto_answer.\n"
                "Sources: TL-01 Opening hours."
            ]
            assert stack.audit.records[-1].sources == ("TL-01",)
        finally:
            stack.parts.store.close()

    def test_on_an_answer_from_an_entry_without_a_page_has_no_line(self, tmp_path: Path) -> None:
        stack = build_stack(tmp_path, env={"INBOX_CORE_CONFIG": str(showing_sources(tmp_path))})
        try:
            stack.visitor_says(10, 200, "How long can I keep a tool?")
            (reply,) = stack.chatwoot.public_messages(10)
            assert stack.audit.records[-1].sources == ("TL-07",)
            assert "More:" not in reply
            assert "https://" not in reply
        finally:
            stack.parts.store.close()

    def test_a_knowledge_file_with_a_bad_url_stops_the_service_starting(
        self, tmp_path: Path
    ) -> None:
        knowledge = tmp_path / "knowledge.md"
        knowledge.write_text("## KB-1 Opening hours\nURL: http://shop.example/hours\nNine.\n")
        with pytest.raises(ValueError, match=r"KB-1.*absolute https URL"):
            build_stack(tmp_path, env={"INBOX_CORE_KNOWLEDGE": str(knowledge)})


class TestAnswering:
    def test_a_visitor_question_is_answered_and_its_source_kept_for_staff(
        self, stack: Stack
    ) -> None:
        response = stack.visitor_says(10, 200, QUESTION)
        assert response.status_code == 200
        assert response.json() == {"status": "accepted"}
        (reply,) = stack.chatwoot.public_messages(10)
        assert reply.startswith("The library is open on Wednesdays")
        assert "Source" not in reply
        assert "TL-01" not in reply
        assert stack.chatwoot.notes(10) == [
            "inbox-core answered this message automatically.\n"
            "Category: faq. Tier: auto_answer.\n"
            "Sources: TL-01 Opening hours."
        ]
        (record,) = stack.audit.records
        assert (record.channel, record.thread_key, record.message_id) == ("chatwoot", "10", "200")
        assert record.decision == "answered"
        assert record.sources == ("TL-01",)
        assert metrics(stack)["processed"] == {"answered": 1}

    def test_the_text_acted_on_is_chatwoots_not_the_webhooks(self, stack: Stack) -> None:
        # A webhook whose body says one thing while Chatwoot holds another: the
        # service re-fetches and acts on what Chatwoot holds.
        stack.chatwoot.conversation(10)
        stack.chatwoot.message(200, 10, DAMAGE)
        stack.webhook(message_payload(10, 200, QUESTION))
        assert stack.audit.records[-1].category == "damage_report"

    def test_a_sensitive_message_is_handed_off_labelled_opened_then_assigned(
        self, stack: Stack
    ) -> None:
        stack.visitor_says(11, 201, DAMAGE)
        writes = [(kind, body) for kind, cid, body in stack.chatwoot.writes if cid == 11]
        kinds = [kind for kind, _ in writes]
        # Opened before it is assigned: Chatwoot does not notify an assignment
        # made while a conversation is still pending.
        assert kinds == ["labels", "message", "message", "labels", "status", "assign"]
        assert writes[0][1] == ["inbox-core"]
        assert writes[1][1]["private"] is False
        assert "A volunteer will read your message" in writes[1][1]["content"]
        assert writes[2][1]["private"] is True
        assert "Category: damage_report. Tier: needs_executive." in writes[2][1]["content"]
        # inbox-core-assigns tells the seed's hand-off rule that this service assigns.
        assert writes[3][1] == ["inbox-core", "handoff", "damage_report", "inbox-core-assigns"]
        assert writes[4][1] == "open"
        assert writes[5][1] == 5
        assert last_decision(stack) == "handed_off"

    def test_labels_are_added_to_the_existing_ones(self, stack: Stack) -> None:
        stack.chatwoot.conversation(11)
        stack.chatwoot.conversations[11]["labels"] = ["vip"]
        stack.visitor_says(11, 201, DAMAGE)
        assert stack.chatwoot.conversations[11]["labels"] == [
            "vip",
            "inbox-core",
            "handoff",
            "damage_report",
            "inbox-core-assigns",
        ]

    def test_every_processed_conversation_is_labelled_once(self, stack: Stack) -> None:
        stack.visitor_says(10, 200, QUESTION)
        stack.visitor_says(10, 201, "And where are you?")
        labels = [body for kind, cid, body in stack.chatwoot.writes if kind == "labels"]
        assert labels == [["inbox-core"]]

    def test_failing_to_label_does_not_stop_the_answer(self, stack: Stack) -> None:
        stack.chatwoot.failures["/labels"] = 1
        stack.visitor_says(10, 200, QUESTION)
        assert last_decision(stack) == "answered"

    def test_the_note_and_labels_hold_no_visitor_text(self, stack: Stack) -> None:
        stack.visitor_says(11, 201, DAMAGE)
        for kind, _, body in stack.chatwoot.writes:
            assert "drill" not in json.dumps(body), kind


class TestAPersonReplying:
    def test_an_agent_reply_silences_the_bot_in_that_conversation(self, stack: Stack) -> None:
        stack.visitor_says(12, 300, DAMAGE)
        stack.chatwoot.message(301, 12, "Sorry to hear that", message_type=1, sender_type="User")
        stack.webhook(message_payload(12, 301, "x", message_type="outgoing", sender_type="user"))
        assert last_decision(stack) == "person_replied"
        before = len(stack.chatwoot.writes)
        stack.visitor_says(12, 302, QUESTION)
        assert last_decision(stack) == "left_for_person"
        assert len(stack.chatwoot.writes) == before

    def test_a_forged_agent_reply_is_refused_after_the_re_fetch(self, stack: Stack) -> None:
        # Signed, but Chatwoot says message 301 came from the visitor.
        stack.visitor_says(12, 300, QUESTION)
        stack.chatwoot.message(301, 12, "hello")
        stack.webhook(message_payload(12, 301, "x", message_type="outgoing", sender_type="user"))
        assert metrics(stack)["webhooks_rejected"] == {"re-fetched message is not from a person": 1}
        assert last_decision(stack) == "answered"


class TestIgnoring:
    @pytest.mark.parametrize(
        ("payload", "why"),
        [
            (
                message_payload(13, 1, "x", message_type="outgoing", sender_type="agent_bot"),
                "the bot's own message",
            ),
            (
                message_payload(
                    13, 1, "x", message_type="outgoing", sender_type="user", private=True
                ),
                "private note",
            ),
            (message_payload(13, 1, "x", event="conversation_status_changed"), "not a new message"),
            (message_payload(13, 1, "x", account=99), "another account"),
        ],
    )
    def test_events_that_are_not_ours_to_act_on(
        self, stack: Stack, payload: dict[str, object], why: str
    ) -> None:
        response = stack.webhook(payload)
        assert response.status_code == 200
        assert response.json() == {"status": "ignored"}
        assert stack.chatwoot.writes == []
        assert metrics(stack)["webhooks_ignored"] == {why: 1}

    def test_a_message_newer_than_chatwoots_latest_is_refused(self, stack: Stack) -> None:
        stack.chatwoot.conversation(13)
        stack.chatwoot.message(5, 13, QUESTION)
        stack.webhook(message_payload(13, 999, QUESTION))
        assert metrics(stack)["webhooks_rejected"] == {"message not found in Chatwoot": 1}
        assert stack.chatwoot.writes == []

    def test_a_private_message_on_re_fetch_is_refused(self, stack: Stack) -> None:
        stack.chatwoot.conversation(13)
        stack.chatwoot.message(5, 13, QUESTION, private=True)
        stack.webhook(message_payload(13, 5, QUESTION))
        assert metrics(stack)["webhooks_rejected"] == {"re-fetched message is private": 1}

    def test_an_incoming_claim_for_an_agents_message_is_refused(self, stack: Stack) -> None:
        stack.chatwoot.conversation(13)
        stack.chatwoot.message(5, 13, QUESTION, message_type=1, sender_type="User")
        stack.webhook(message_payload(13, 5, QUESTION))
        assert metrics(stack)["webhooks_rejected"] == {
            "re-fetched message is not from the visitor": 1
        }

    def test_a_conversation_in_another_account_is_refused(self, stack: Stack) -> None:
        stack.chatwoot.conversation(13, account=99)
        stack.chatwoot.message(5, 13, QUESTION)
        stack.webhook(message_payload(13, 5, QUESTION))
        assert metrics(stack)["webhooks_rejected"] == {"another account": 1}

    def test_a_message_in_an_empty_conversation_is_refused(self, stack: Stack) -> None:
        stack.chatwoot.conversation(13)
        stack.webhook(message_payload(13, 1, QUESTION))
        assert metrics(stack)["webhooks_rejected"] == {"message not found in Chatwoot": 1}

    def test_an_older_message_is_acted_on_from_the_signed_body(self, stack: Stack) -> None:
        # Chatwoot's latest is already a newer message; the signed body is used.
        stack.chatwoot.conversation(13)
        stack.chatwoot.message(5, 13, "placeholder")
        stack.chatwoot.message(6, 13, "a newer message")
        stack.webhook(message_payload(13, 5, DAMAGE))
        assert last_decision(stack) == "handed_off"
        assert stack.audit.records[-1].category == "damage_report"


class TestUnverified:
    def test_unverified_requests_are_refused_counted_and_never_acted_on(self, stack: Stack) -> None:
        stack.chatwoot.conversation(14)
        stack.chatwoot.message(1, 14, QUESTION)
        payload = message_payload(14, 1, QUESTION)
        attempts = [
            stack.webhook(payload, secret="wrong-secret"),
            stack.webhook(payload, path_token="q" * 32),
            stack.webhook(payload, timestamp=int(time.time()) - 3600),
            stack.webhook(payload, headers={"X-Chatwoot-Signature": ""}),
            stack.webhook(payload, delivery="same"),
            stack.webhook(payload, delivery="same"),
        ]
        statuses = [r.status_code for r in attempts]
        assert statuses == [401, 401, 401, 401, 200, 401]
        assert all(r.json() == {"error": "not verified"} for r in attempts if r.status_code == 401)
        assert metrics(stack)["webhooks_rejected"] == {
            "bad_signature": 1,
            "bad_path": 1,
            "stale": 1,
            "unsigned": 1,
            "replayed": 1,
        }
        assert len(stack.chatwoot.public_messages(14)) == 1

    def test_a_malformed_body_is_unverified_not_a_422_echo(self, stack: Stack) -> None:
        stamp = str(int(time.time()))
        raw = b"not json"
        response = stack.client.post(
            f"/chatwoot/webhook/{PATH_TOKEN}",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Chatwoot-Timestamp": stamp,
                "X-Chatwoot-Signature": signature_for(BOT_SECRET, stamp, raw),
                "X-Chatwoot-Delivery": "d",
            },
        )
        assert response.status_code == 401
        assert "not json" not in response.text
        assert metrics(stack)["webhooks_rejected"] == {"malformed": 1}

    def test_a_signed_body_that_is_not_an_object_is_ignored(self, stack: Stack) -> None:
        response = stack.webhook({}, raw=b"[1, 2]")
        assert response.status_code in (200, 401)
        assert stack.chatwoot.writes == []

    def test_an_internal_error_still_answers_200(self, stack: Stack) -> None:
        def broken(work: object) -> None:
            raise RuntimeError("queue full")

        stack.parts.service._submit = broken
        stack.chatwoot.conversation(14)
        stack.chatwoot.message(1, 14, QUESTION)
        response = stack.webhook(message_payload(14, 1, QUESTION))
        assert response.status_code == 200
        assert metrics(stack)["webhooks_ignored"] == {"internal error (RuntimeError)": 1}


class TestWhenTheCoreCannotFinish:
    def test_chatwoot_failing_to_open_falls_back_after_retries(self, tmp_path: Path) -> None:
        stack = build_stack(tmp_path)
        stack.chatwoot.conversation(15)
        stack.chatwoot.message(1, 15, DAMAGE)
        # Opening fails on the first try and on every retry.
        stack.chatwoot.failures["/toggle_status"] = 5
        stack.webhook(message_payload(15, 1, DAMAGE))
        # Retried with back-off; the holding message went out once, not again.
        assert stack.slept == [0.5, 1.0, 2.0, 4.0]
        holding = [m for m in stack.chatwoot.public_messages(15) if "volunteer" in m]
        assert len(holding) == 1
        # The fallback's own attempt to open went through.
        assert stack.chatwoot.conversations[15]["status"] == "open"
        assert stack.chatwoot.notes(15)[-1].startswith("inbox-core could not process")
        stack.parts.store.close()

    def test_the_store_down_sends_the_holding_message_and_opens(self, tmp_path: Path) -> None:
        stack = build_stack(tmp_path)

        def down(*args: object, **kwargs: object) -> object:
            raise ConnectionError("database unavailable")

        stack.parts.store.is_handled = down  # type: ignore[method-assign,assignment]
        stack.visitor_says(16, 1, QUESTION)
        assert stack.slept == [0.5, 1.0, 2.0, 4.0]
        (holding,) = stack.chatwoot.public_messages(16)
        assert "A volunteer will read your message" in holding
        (note,) = stack.chatwoot.notes(16)
        assert note.startswith("inbox-core could not process the latest message")
        assert "internal error (ConnectionError)" in note
        assert stack.chatwoot.conversations[16]["labels"] == [
            "inbox-core",
            "handoff",
            "inbox-core-unavailable",
            "inbox-core-assigns",
        ]
        assert stack.chatwoot.conversations[16]["status"] == "open"
        assert [kind for kind, cid, _ in stack.chatwoot.writes if cid == 16][-2:] == [
            "status",
            "assign",
        ]
        assert metrics(stack)["processed"] == {"fallback": 1}
        # A second failing message in the same conversation does not repeat it.
        stack.visitor_says(16, 2, QUESTION)
        assert len(stack.chatwoot.public_messages(16)) == 1
        stack.parts.store.close()

    def test_chatwoot_down_ends_in_a_quiet_fallback(self, tmp_path: Path) -> None:
        stack = build_stack(tmp_path)
        stack.chatwoot.conversation(17)
        stack.chatwoot.message(1, 17, QUESTION)
        stack.chatwoot.down = True
        response = stack.webhook(message_payload(17, 1, QUESTION))
        assert response.status_code == 200
        assert metrics(stack)["processed"] == {"fallback": 1}
        stack.parts.store.close()

    def test_draft_mode_fallback_sends_nothing_but_still_opens(self, tmp_path: Path) -> None:
        stack = build_stack(tmp_path, mode="draft")

        def down(*args: object, **kwargs: object) -> object:
            raise ConnectionError("database unavailable")

        stack.parts.store.is_handled = down  # type: ignore[method-assign,assignment]
        stack.visitor_says(18, 1, QUESTION)
        assert stack.chatwoot.public_messages(18) == []
        assert stack.chatwoot.conversations[18]["status"] == "open"
        stack.parts.store.close()


def test_health_reports_the_mode(stack: Stack) -> None:
    assert stack.client.get("/healthz").json() == {"status": "ok", "mode": "auto"}


def test_the_docs_pages_are_off(stack: Stack) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert stack.client.get(path).status_code == 404

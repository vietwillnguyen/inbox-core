"""The draft tab, attacked. A flaw here would let someone send as the organisation.

Every test that expects a refusal also checks that nothing reached the visitor.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import pytest

from inbox_core.chatwoot.tab_auth import TabSigner
from tests.chatwoot.conftest import (
    CHATWOOT_ORIGIN,
    PUBLIC_ORIGIN,
    TAB_SECRET,
    Stack,
    message_payload,
)
from tests.chatwoot.fake import (
    AGENT_TOKEN,
    BOT_TOKEN,
    OTHER_AGENT_TOKEN,
    OUTSIDER_TOKEN,
)

QUESTION = "What are your opening hours?"
SAME_ORIGIN = {"Origin": PUBLIC_ORIGIN}


def sign_in(stack: Stack, token: str = AGENT_TOKEN, origin: str | None = PUBLIC_ORIGIN) -> Any:
    headers = {"Origin": origin} if origin else {}
    return stack.client.post("/tab/session", json={"chatwoot_token": token}, headers=headers)


def session_of(stack: Stack, token: str = AGENT_TOKEN) -> str:
    response = sign_in(stack, token)
    assert response.status_code == 200, response.text
    value: str = response.json()["session_token"]
    return value


def bearer(session: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {session}", **SAME_ORIGIN}


def drafts(stack: Stack, session: str, conversation_id: int) -> Any:
    return stack.client.get(f"/tab/conversations/{conversation_id}/drafts", headers=bearer(session))


def stored(stack: Stack, draft_id: int) -> Any:
    row = stack.parts.store.get_message(draft_id)
    assert row is not None
    return row


def held(stack: Stack, conversation_id: int = 20, message_id: int = 400, inbox: int = 1) -> None:
    stack.chatwoot.conversation(conversation_id, inbox=inbox)
    stack.visitor_says(conversation_id, message_id, QUESTION)


def first_draft(stack: Stack, session: str, conversation_id: int = 20) -> dict[str, Any]:
    response = drafts(stack, session, conversation_id)
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()["drafts"][0]
    return found


def send(
    stack: Stack,
    session: str,
    draft: dict[str, Any],
    *,
    conversation_id: int = 20,
    text: str | None = None,
    token: str | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    return stack.client.post(
        f"/tab/conversations/{conversation_id}/drafts/{draft['id']}/send",
        json={
            "text": draft["text"] if text is None else text,
            "action_token": token or draft["action_token"],
        },
        headers=headers if headers is not None else bearer(session),
    )


def discard(stack: Stack, session: str, draft: dict[str, Any], *, conversation_id: int = 20) -> Any:
    return stack.client.post(
        f"/tab/conversations/{conversation_id}/drafts/{draft['id']}/discard",
        json={"action_token": draft["action_token"]},
        headers=bearer(session),
    )


def rejected(stack: Stack) -> dict[str, int]:
    found: dict[str, int] = stack.client.get("/metrics").json()["tab_rejected"]
    return found


class TestThePage:
    def test_it_can_be_framed_only_by_chatwoot(self, draft_stack: Stack) -> None:
        response = draft_stack.client.get("/tab")
        assert response.status_code == 200
        policy = response.headers["content-security-policy"]
        assert f"frame-ancestors {CHATWOOT_ORIGIN}" in policy
        assert "script-src 'self'" in policy
        assert "default-src 'none'" in policy
        assert "unsafe-inline" not in policy
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "no-store"
        assert f'data-chatwoot-origin="{CHATWOOT_ORIGIN}"' in response.text
        assert "<script>" not in response.text  # no inline script for the policy to allow

    def test_its_assets(self, draft_stack: Stack) -> None:
        script = draft_stack.client.get("/tab/assets/tab.js")
        assert script.status_code == 200
        assert script.headers["content-type"].startswith("text/javascript")
        for sink in (".innerHTML", ".outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            assert sink not in script.text
        assert "event.origin !== CHATWOOT_ORIGIN" in script.text
        assert draft_stack.client.get("/tab/assets/tab.css").status_code == 200
        assert draft_stack.client.get("/tab/assets/other.js").status_code == 422

    def test_validation_errors_do_not_echo_the_input(self, draft_stack: Stack) -> None:
        response = draft_stack.client.post(
            "/tab/session", json={"chatwoot_token": 12345678901}, headers=SAME_ORIGIN
        )
        assert response.status_code == 422
        assert response.json() == {"error": "invalid request"}


class TestSigningIn:
    def test_a_chatwoot_verified_agent_gets_a_session(self, draft_stack: Stack) -> None:
        response = sign_in(draft_stack)
        assert response.status_code == 200
        body = response.json()
        assert body["agent_id"] == 5
        assert body["agent_name"] == "Example Agent"
        assert AGENT_TOKEN not in json.dumps(body)

    @pytest.mark.parametrize(
        ("token", "status", "reason"),
        [
            ("not-a-real-token-at-all", 401, "token refused"),
            (BOT_TOKEN, 401, "token refused"),
            (OUTSIDER_TOKEN, 403, "not in account"),
        ],
    )
    def test_anything_chatwoot_does_not_vouch_for_is_refused(
        self, draft_stack: Stack, token: str, status: int, reason: str
    ) -> None:
        response = sign_in(draft_stack, token)
        assert response.status_code == status
        assert "session_token" not in response.json()
        assert rejected(draft_stack) == {reason: 1}

    @pytest.mark.parametrize("origin", ["https://evil.example", None, CHATWOOT_ORIGIN])
    def test_only_the_tabs_own_origin_may_sign_in(
        self, draft_stack: Stack, origin: str | None
    ) -> None:
        response = sign_in(draft_stack, origin=origin)
        assert response.status_code == 403
        assert rejected(draft_stack) == {"bad origin": 1}

    def test_sign_in_attempts_are_rate_limited(self, draft_stack: Stack) -> None:
        statuses = [sign_in(draft_stack, "wrong-token-xxxxxxxx").status_code for _ in range(11)]
        assert statuses == [401] * 10 + [429]

    def test_chatwoot_unreachable_is_a_502(self, draft_stack: Stack) -> None:
        draft_stack.chatwoot.down = True
        assert sign_in(draft_stack).status_code == 502

    def test_the_chatwoot_token_never_reaches_a_log(
        self, draft_stack: Stack, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG):
            sign_in(draft_stack)
            sign_in(draft_stack, "not-a-real-token-at-all")
        assert AGENT_TOKEN not in caplog.text
        assert "not-a-real-token-at-all" not in caplog.text


class TestHappyPath:
    def test_list_send_as_written_and_who_sent_it_is_recorded(self, draft_stack: Stack) -> None:
        held(draft_stack)
        assert draft_stack.chatwoot.public_messages(20) == []
        session = session_of(draft_stack)
        draft = first_draft(draft_stack, session)
        assert draft["category"] == "faq"
        assert draft["tier"] == "auto_answer"
        assert draft["held_because"] == "draft mode"
        assert draft["sources"] == [{"id": "TL-01", "title": "Opening hours"}]
        response = send(draft_stack, session, draft)
        assert response.status_code == 200
        assert response.json() == {
            "draft_id": draft["id"],
            "outcome": "sent_as_written",
            "reviewer": "chatwoot-user:5",
        }
        assert draft_stack.chatwoot.public_messages(20) == [draft["text"]]
        row = stored(draft_stack, draft["id"])
        assert (row.review_outcome, row.reviewed_by) == ("sent_as_written", "chatwoot-user:5")
        assert draft_stack.chatwoot.notes(20)[-1] == (
            f"inbox-core draft {draft['id']} sent as written by agent 5."
        )
        assert drafts(draft_stack, session, 20).json()["drafts"] == []
        assert "draft-pending" not in draft_stack.chatwoot.conversations[20]["labels"]

    def test_the_pending_label_stays_while_a_draft_still_waits(self, draft_stack: Stack) -> None:
        held(draft_stack, 20, 400)
        # Two drafts in one conversation: give it back to the bot after the first.
        found = draft_stack.parts.store.find_conversation("chatwoot", "20")
        assert found is not None
        draft_stack.parts.store.resume(found.id)  # let the bot draft a second reply
        draft_stack.chatwoot.message(401, 20, "And on Saturdays?")
        draft_stack.webhook(message_payload(20, 401, "And on Saturdays?"))
        session = session_of(draft_stack)
        listed = drafts(draft_stack, session, 20).json()["drafts"]
        assert len(listed) == 2
        discard(draft_stack, session, listed[0])
        assert "draft-pending" in draft_stack.chatwoot.conversations[20]["labels"]
        discard(draft_stack, session, listed[1])
        assert "draft-pending" not in draft_stack.chatwoot.conversations[20]["labels"]

    def test_a_failure_clearing_the_label_does_not_undo_the_send(self, draft_stack: Stack) -> None:
        held(draft_stack)
        session = session_of(draft_stack)
        draft = first_draft(draft_stack, session)
        draft_stack.chatwoot.failures["/labels"] = 1
        assert send(draft_stack, session, draft).status_code == 200

    def test_send_edited(self, draft_stack: Stack) -> None:
        held(draft_stack)
        session = session_of(draft_stack)
        draft = first_draft(draft_stack, session)
        response = send(
            draft_stack, session, draft, text="We open Wednesday evenings and Saturday mornings."
        )
        assert response.json()["outcome"] == "sent_edited"
        assert draft_stack.chatwoot.public_messages(20) == [
            "We open Wednesday evenings and Saturday mornings."
        ]

    def test_discard(self, draft_stack: Stack) -> None:
        held(draft_stack)
        session = session_of(draft_stack)
        draft = first_draft(draft_stack, session)
        response = discard(draft_stack, session, draft)
        assert response.json()["outcome"] == "discarded"
        assert draft_stack.chatwoot.public_messages(20) == []
        assert stored(draft_stack, draft["id"]).reviewed_by == "chatwoot-user:5"

    def test_an_agent_with_no_drafts_sees_an_empty_list(self, draft_stack: Stack) -> None:
        draft_stack.chatwoot.conversation(21)
        session = session_of(draft_stack)
        assert drafts(draft_stack, session, 21).json() == {
            "conversation_id": 21,
            "mode": "draft",
            "drafts": [],
        }


class TestForgedIdentity:
    def test_no_session_is_refused(self, draft_stack: Stack) -> None:
        held(draft_stack)
        response = draft_stack.client.get("/tab/conversations/20/drafts", headers=SAME_ORIGIN)
        assert response.status_code == 401
        assert "Opening hours" not in response.text

    def test_a_posted_agent_identity_is_not_trusted(self, draft_stack: Stack) -> None:
        # What Chatwoot's frame posts (or a forger posts) is not a credential.
        held(draft_stack)
        forged = {
            "Authorization": "Bearer " + json.dumps({"currentAgent": {"id": 1}}),
            **SAME_ORIGIN,
        }
        assert (
            draft_stack.client.get("/tab/conversations/20/drafts", headers=forged).status_code
            == 401
        )

    def test_a_session_signed_with_another_secret_is_refused(self, draft_stack: Stack) -> None:
        held(draft_stack)
        forger = TabSigner("x" * 40)
        token, _ = forger.mint_session(
            agent_id=1, account_id=1, inbox_ids=frozenset({1, 2}), ttl=600
        )
        assert drafts(draft_stack, token, 20).status_code == 401
        assert rejected(draft_stack) == {"bad token signature": 1}

    def test_a_tampered_session_is_refused(self, draft_stack: Stack) -> None:
        held(draft_stack)
        session = session_of(draft_stack, OTHER_AGENT_TOKEN)  # an agent of inbox 2 only
        version, body, mac = session.split(".")
        claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        claims["inb"] = [1, 2]
        claims["sub"] = 5
        forged_body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        assert drafts(draft_stack, f"{version}.{forged_body}.{mac}", 20).status_code == 401

    def test_an_agent_without_the_inbox_cannot_see_or_act(self, draft_stack: Stack) -> None:
        held(draft_stack)
        owner = session_of(draft_stack)
        draft = first_draft(draft_stack, owner)
        intruder = session_of(draft_stack, OTHER_AGENT_TOKEN)
        assert drafts(draft_stack, intruder, 20).status_code == 403
        # Even holding a valid action token, minted for someone else's session.
        assert send(draft_stack, intruder, draft).status_code == 403
        assert draft_stack.chatwoot.public_messages(20) == []

    def test_extra_identity_fields_in_the_body_change_nothing(self, draft_stack: Stack) -> None:
        held(draft_stack)
        session = session_of(draft_stack)
        draft = first_draft(draft_stack, session)
        response = draft_stack.client.post(
            f"/tab/conversations/20/drafts/{draft['id']}/send",
            json={
                "text": draft["text"],
                "action_token": draft["action_token"],
                "agent_id": 1,
                "reviewer": "chatwoot-user:1",
            },
            headers=bearer(session),
        )
        assert response.status_code == 200
        assert response.json()["reviewer"] == "chatwoot-user:5"


class TestReplayAndState:
    def test_a_replayed_send_does_not_send_twice(self, draft_stack: Stack) -> None:
        held(draft_stack)
        session = session_of(draft_stack)
        draft = first_draft(draft_stack, session)
        first = send(draft_stack, session, draft)
        replay = send(draft_stack, session, draft)
        assert (first.status_code, replay.status_code) == (200, 409)
        assert len(draft_stack.chatwoot.public_messages(20)) == 1
        assert rejected(draft_stack) == {"draft not pending": 1}

    def test_a_discard_replayed_after_a_send_is_refused(self, draft_stack: Stack) -> None:
        held(draft_stack)
        session = session_of(draft_stack)
        draft = first_draft(draft_stack, session)
        send(draft_stack, session, draft)
        assert discard(draft_stack, session, draft).status_code == 409
        assert stored(draft_stack, draft["id"]).review_outcome == "sent_as_written"

    def test_a_draft_already_discarded_cannot_be_sent(self, draft_stack: Stack) -> None:
        held(draft_stack)
        session = session_of(draft_stack)
        draft = first_draft(draft_stack, session)
        discard(draft_stack, session, draft)
        assert send(draft_stack, session, draft).status_code == 409
        assert draft_stack.chatwoot.public_messages(20) == []

    def test_an_action_token_from_another_session_is_refused(self, draft_stack: Stack) -> None:
        held(draft_stack)
        first = session_of(draft_stack)
        draft = first_draft(draft_stack, first)
        second = session_of(draft_stack)
        assert send(draft_stack, second, draft).status_code == 403
        assert rejected(draft_stack) == {"action token from another session": 1}

    def test_a_failed_send_is_not_retried(self, draft_stack: Stack) -> None:
        held(draft_stack)
        session = session_of(draft_stack)
        draft = first_draft(draft_stack, session)
        draft_stack.chatwoot.fail_posts = True
        assert send(draft_stack, session, draft).status_code == 502
        draft_stack.chatwoot.fail_posts = False
        assert send(draft_stack, session, draft).status_code == 409
        assert draft_stack.chatwoot.public_messages(20) == []

    def test_empty_text_is_refused_and_the_draft_stays(self, draft_stack: Stack) -> None:
        held(draft_stack)
        session = session_of(draft_stack)
        draft = first_draft(draft_stack, session)
        assert send(draft_stack, session, draft, text="   ").status_code == 400
        assert len(drafts(draft_stack, session, 20).json()["drafts"]) == 1


class TestAnotherConversationsDraft:
    def test_a_token_for_one_draft_cannot_send_another(self, draft_stack: Stack) -> None:
        held(draft_stack, 20, 400)
        held(draft_stack, 22, 401)
        session = session_of(draft_stack)
        mine = first_draft(draft_stack, session, 20)
        other = first_draft(draft_stack, session, 22)
        response = send(draft_stack, session, other, conversation_id=20, token=mine["action_token"])
        assert response.status_code == 403
        assert rejected(draft_stack) == {"action token for another draft": 1}

    def test_a_draft_id_from_another_conversation_is_not_found_there(
        self, draft_stack: Stack
    ) -> None:
        # Even with a correctly signed token for (conversation 20, the other
        # conversation's draft), the draft must belong to the path's conversation.
        held(draft_stack, 20, 400)
        held(draft_stack, 23, 402, inbox=2)
        admin_like = session_of(draft_stack)
        other = draft_stack.parts.pipeline.drafts.pending(
            draft_stack.parts.store.find_conversation("chatwoot", "23").id  # type: ignore[union-attr]
        )[0]
        claims = draft_stack.parts.service._signer.verify_session(admin_like, account_id=1)
        token = draft_stack.parts.service._signer.mint_action(
            claims, conversation_id=20, draft_id=other.id
        )
        response = send(
            draft_stack,
            admin_like,
            {"id": other.id, "text": other.text},
            conversation_id=20,
            token=token,
        )
        assert response.status_code == 404
        assert draft_stack.chatwoot.public_messages(23) == []
        assert draft_stack.chatwoot.public_messages(20) == []

    def test_an_unknown_draft(self, draft_stack: Stack) -> None:
        held(draft_stack)
        session = session_of(draft_stack)
        claims = draft_stack.parts.service._signer.verify_session(session, account_id=1)
        token = draft_stack.parts.service._signer.mint_action(
            claims, conversation_id=20, draft_id=999
        )
        assert send(draft_stack, session, {"id": 999, "text": "x"}, token=token).status_code == 404

    def test_a_conversation_chatwoot_does_not_know(self, draft_stack: Stack) -> None:
        session = session_of(draft_stack)
        assert drafts(draft_stack, session, 777).status_code == 403


class TestExpiry:
    def test_an_expired_session_is_refused(self, draft_stack: Stack) -> None:
        held(draft_stack)
        session = session_of(draft_stack)
        draft = first_draft(draft_stack, session)
        draft_stack.clock.offset = 1801
        assert drafts(draft_stack, session, 20).status_code == 401
        assert send(draft_stack, session, draft).status_code == 401
        assert draft_stack.chatwoot.public_messages(20) == []

    def test_an_expired_action_token_is_refused(self, draft_stack: Stack) -> None:
        held(draft_stack)
        session = session_of(draft_stack)
        draft = first_draft(draft_stack, session)
        draft_stack.clock.offset = 601
        response = send(draft_stack, session, draft)
        assert response.status_code == 401
        assert rejected(draft_stack) == {"expired token": 1}


class TestCrossSite:
    @pytest.mark.parametrize("origin", ["https://evil.example", CHATWOOT_ORIGIN, None])
    def test_a_send_from_any_other_origin_is_refused(
        self, draft_stack: Stack, origin: str | None
    ) -> None:
        held(draft_stack)
        session = session_of(draft_stack)
        draft = first_draft(draft_stack, session)
        headers = {"Authorization": f"Bearer {session}"}
        if origin:
            headers["Origin"] = origin
        assert send(draft_stack, session, draft, headers=headers).status_code == 403
        assert draft_stack.chatwoot.public_messages(20) == []

    def test_a_cookie_is_not_a_credential(self, draft_stack: Stack) -> None:
        held(draft_stack)
        session = session_of(draft_stack)
        draft = first_draft(draft_stack, session)
        draft_stack.client.cookies.set("session", session)
        response = send(draft_stack, session, draft, headers=SAME_ORIGIN)
        assert response.status_code == 401
        assert draft_stack.chatwoot.public_messages(20) == []

    def test_api_responses_never_carry_cors_grants(self, draft_stack: Stack) -> None:
        response = draft_stack.client.post(
            "/tab/session",
            json={"chatwoot_token": AGENT_TOKEN},
            headers={"Origin": "https://evil.example"},
        )
        assert "access-control-allow-origin" not in response.headers


def test_delivery_off_refuses_a_send(tmp_path: Any) -> None:
    from tests.chatwoot.conftest import build_stack

    stack = build_stack(tmp_path, mode="draft")
    held(stack)
    stack.parts.pipeline._delivery.mode = stack.parts.pipeline._delivery.mode.__class__("off")
    session = session_of(stack)
    draft = first_draft(stack, session)
    assert send(stack, session, draft).status_code == 409
    assert stack.chatwoot.public_messages(20) == []
    stack.parts.store.close()


def test_signer_rejects_a_short_secret() -> None:
    with pytest.raises(ValueError, match="32"):
        TabSigner("short")
    assert TAB_SECRET  # the fixture's secret is long enough

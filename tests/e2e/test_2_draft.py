"""Draft mode in the real stack: held, then sent, edited or discarded from the tab; and attacked."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import pytest

from inbox_core.chatwoot.tab_auth import TabSigner
from tests.e2e.stack import CHATWOOT, SERVICE, Agent, Visitor, quiet_for, tab, until

MODE = "draft"
pytestmark = pytest.mark.usefixtures("mode")
QUESTION = "What are your opening hours?"


def sign_in(token: str) -> str:
    response = tab("POST", "/tab/session", body={"chatwoot_token": token})
    assert response.status_code == 200, response.json().get("error")
    session: str = response.json()["session_token"]
    return session


def held_draft(person: Visitor, session: str) -> dict[str, Any]:
    def listed() -> list[dict[str, Any]] | None:
        response = tab(
            "GET", f"/tab/conversations/{person.conversation_id}/drafts", session=session
        )
        assert response.status_code == 200, response.text
        found: list[dict[str, Any]] = response.json()["drafts"]
        return found or None

    return until(listed, timeout=30)[0]


def act(person: Visitor, session: str, draft: dict[str, Any], action: str, **body: Any) -> Any:
    return tab(
        "POST",
        f"/tab/conversations/{person.conversation_id}/drafts/{draft['id']}/{action}",
        session=session,
        body={"action_token": draft["action_token"], **body},
    )


@pytest.fixture(scope="module")
def session(mode: str, tokens: dict[str, str]) -> str:
    # One sign-in for the module: the service allows ten a minute per address.
    return sign_in(tokens["CHATWOOT_AGENT_TOKEN"])


@pytest.fixture
def drafted(visitor: Callable[[], Visitor], session: str) -> tuple[Visitor, str, dict[str, Any]]:
    person = visitor()
    person.say(QUESTION)
    return person, session, held_draft(person, session)


def test_a_draft_is_held_and_nothing_reaches_the_visitor(
    drafted: tuple[Visitor, str, dict[str, Any]], admin: Agent
) -> None:
    person, _, draft = drafted
    quiet_for(lambda: bool(person.replies()), 5)
    assert (draft["category"], draft["tier"], draft["held_because"]) == (
        "faq",
        "auto_answer",
        "draft mode",
    )
    assert draft["sources"] == [{"id": "TL-01", "title": "Opening hours"}]
    assert "Source" not in draft["text"]
    assert "TL-01" not in draft["text"]
    notes = [m["content"] for m in admin.messages(person.conversation_id or 0) if m["private"]]
    assert any("Sources: TL-01 Opening hours." in n for n in notes)
    found = admin.conversation(person.conversation_id or 0)
    assert found["status"] == "open"
    assert "draft-pending" in found["labels"]


def test_a_draft_sent_as_written_reaches_the_widget(
    drafted: tuple[Visitor, str, dict[str, Any]], admin: Agent, tokens: dict[str, str]
) -> None:
    person, session, draft = drafted
    response = act(person, session, draft, "send", text=draft["text"])
    assert response.json()["outcome"] == "sent_as_written"
    (reply,) = until(person.replies, timeout=15)
    assert reply == draft["text"]
    for text in (str(m.get("content") or "") for m in person.messages()):
        assert "Source" not in text
        assert "TL-01" not in text
    agent_id = tokens["CHATWOOT_AGENT_USER_ID"]
    notes = [m["content"] for m in admin.messages(person.conversation_id or 0) if m["private"]]
    assert f"inbox-core draft {draft['id']} sent as written by agent {agent_id}." in notes


def test_an_edited_draft_is_sent_as_edited(drafted: tuple[Visitor, str, dict[str, Any]]) -> None:
    person, session, draft = drafted
    edited = "We open on Wednesday evenings and Saturday mornings. See you there!"
    assert act(person, session, draft, "send", text=edited).json()["outcome"] == "sent_edited"
    assert until(person.replies, timeout=15) == [edited]


def test_a_discarded_draft_sends_nothing(drafted: tuple[Visitor, str, dict[str, Any]]) -> None:
    person, session, draft = drafted
    assert act(person, session, draft, "discard").json()["outcome"] == "discarded"
    quiet_for(lambda: bool(person.replies()), 5)


class TestHostile:
    def test_no_session_and_a_forged_session_are_refused(
        self, drafted: tuple[Visitor, str, dict[str, Any]]
    ) -> None:
        person, _, draft = drafted
        path = f"/tab/conversations/{person.conversation_id}/drafts"
        assert tab("GET", path).status_code == 401
        forged, _ = TabSigner("f" * 48).mint_session(
            agent_id=1, account_id=1, inbox_ids=frozenset({1, 2}), ttl=600
        )
        assert tab("GET", path, session=forged).status_code == 401
        assert act(person, forged, draft, "send", text="Sent by a forger").status_code == 401
        quiet_for(lambda: bool(person.replies()), 3)

    def test_the_bot_token_cannot_sign_in(self, tokens: dict[str, str]) -> None:
        response = tab(
            "POST", "/tab/session", body={"chatwoot_token": tokens["CHATWOOT_BOT_TOKEN"]}
        )
        assert response.status_code == 401

    def test_a_replayed_send_sends_once(self, drafted: tuple[Visitor, str, dict[str, Any]]) -> None:
        person, session, draft = drafted
        first = act(person, session, draft, "send", text=draft["text"])
        replay = act(person, session, draft, "send", text=draft["text"])
        assert (first.status_code, replay.status_code) == (200, 409)
        until(person.replies, timeout=15)
        quiet_for(lambda: len(person.replies()) > 1, 4)

    def test_another_conversations_draft_with_this_token_is_refused(
        self, visitor: Callable[[], Visitor], drafted: tuple[Visitor, str, dict[str, Any]]
    ) -> None:
        person, session, draft = drafted
        other = visitor()
        other.say("Do you have a ladder I could borrow?")
        theirs = held_draft(other, session)
        response = tab(
            "POST",
            f"/tab/conversations/{person.conversation_id}/drafts/{theirs['id']}/send",
            session=session,
            body={"action_token": draft["action_token"], "text": "Wrong conversation"},
        )
        assert response.status_code == 403
        response = tab(
            "POST",
            f"/tab/conversations/{person.conversation_id}/drafts/{theirs['id']}/send",
            session=session,
            body={"action_token": theirs["action_token"], "text": "Wrong conversation"},
        )
        assert response.status_code == 403
        quiet_for(lambda: bool(person.replies() or other.replies()), 3)

    def test_an_expired_session_signed_with_the_real_secret_is_refused(
        self, drafted: tuple[Visitor, str, dict[str, Any]], tokens: dict[str, str]
    ) -> None:
        person, _, draft = drafted
        long_ago = time.time() - 7200
        signer = TabSigner(tokens["INBOX_CORE_TAB_SECRET"], clock=lambda: long_ago)
        stale, _ = signer.mint_session(
            agent_id=int(tokens["CHATWOOT_AGENT_USER_ID"]),
            account_id=int(tokens["CHATWOOT_ACCOUNT_ID"]),
            inbox_ids=frozenset({int(tokens["CHATWOOT_INBOX_ID"])}),
            ttl=600,
        )
        assert act(person, stale, draft, "send", text=draft["text"]).status_code == 401
        quiet_for(lambda: bool(person.replies()), 3)

    def test_a_draft_already_sent_cannot_be_discarded_or_sent_again(
        self, drafted: tuple[Visitor, str, dict[str, Any]]
    ) -> None:
        person, session, draft = drafted
        act(person, session, draft, "send", text=draft["text"])
        assert act(person, session, draft, "discard").status_code == 409
        assert act(person, session, draft, "send", text="Again").status_code == 409

    def test_cross_origin_and_framing(self, drafted: tuple[Visitor, str, dict[str, Any]]) -> None:
        person, session, draft = drafted
        for origin in ("https://evil.example", CHATWOOT, None):
            response = tab(
                "POST",
                f"/tab/conversations/{person.conversation_id}/drafts/{draft['id']}/send",
                session=session,
                origin=origin,
                body={"action_token": draft["action_token"], "text": draft["text"]},
            )
            assert response.status_code == 403
        page = tab("GET", "/tab", origin=None)
        assert f"frame-ancestors {CHATWOOT}" in page.headers["content-security-policy"]
        assert SERVICE not in page.headers["content-security-policy"].split("frame-ancestors")[1]
        quiet_for(lambda: bool(person.replies()), 2)

    def test_an_agent_who_cannot_see_the_conversation_is_refused(
        self, drafted: tuple[Visitor, str, dict[str, Any]], tokens: dict[str, str], admin: Agent
    ) -> None:
        person, _, draft = drafted
        inbox = int(tokens["CHATWOOT_INBOX_ID"])
        agent = int(tokens["CHATWOOT_AGENT_USER_ID"])
        # Take the volunteer out of the website inbox, then put them back.
        assert admin.call(
            "DELETE", "/inbox_members", {"inbox_id": inbox, "user_ids": [agent]}
        ).is_success
        try:
            session = sign_in(tokens["CHATWOOT_AGENT_TOKEN"])
            path = f"/tab/conversations/{person.conversation_id}/drafts"
            assert tab("GET", path, session=session).status_code == 403
            assert act(person, session, draft, "send", text=draft["text"]).status_code == 403
        finally:
            assert admin.call(
                "POST", "/inbox_members", {"inbox_id": inbox, "user_ids": [agent]}
            ).is_success
        quiet_for(lambda: bool(person.replies()), 2)

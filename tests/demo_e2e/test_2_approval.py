"""The approval path: repair advice is drafted, held, and sent only when the owner approves."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from tests.demo_e2e.bundle import Owner, Visitor, audit_for, quiet_for, until

QUESTION = "My gears keep skipping when I pedal hard. Anything I can try at home?"


def tab(bundle: dict[str, str], method: str, path: str, session: str, body: Any = None) -> Any:
    response = httpx.request(
        method,
        f"{bundle['BOT_ORIGIN']}{path}",
        headers={"Origin": bundle["BOT_ORIGIN"], "Authorization": f"Bearer {session}"},
        json=body,
        timeout=20,
    )
    assert response.status_code == 200, response.text
    return response.json()


def held(bundle: dict[str, str], person: Visitor, session: str) -> dict[str, Any]:
    path = f"/tab/conversations/{person.conversation_id}/drafts"
    found: dict[str, Any] = until(lambda: tab(bundle, "GET", path, session)["drafts"])[0]
    return found


def test_repair_advice_is_held_until_the_owner_approves_it(
    visitor: Callable[[], Visitor], owner: Owner, bundle: dict[str, str], tab_session: str
) -> None:
    person = visitor()
    person.say(QUESTION)
    draft = held(bundle, person, tab_session)
    assert (draft["category"], draft["held_because"]) == (
        "repair_advice",
        "category repair_advice needs approval",
    )
    assert "barrel adjuster" in draft["text"]
    assert draft["sources"][0]["id"] == "QCW-25"
    assert "Source" not in draft["text"]
    assert "QCW-" not in draft["text"]
    assert any("Sources: QCW-25" in note for note in owner.notes(person.conversation_id or 0))
    quiet_for(lambda: bool(person.replies()), 4)
    found = owner.conversation(person.conversation_id or 0)
    assert "draft-pending" in found["labels"]
    (record,) = audit_for(person.conversation_id or 0)
    assert (record["decision"], record["sources"][0]) == ("answer_held", "QCW-25")

    edited = draft["text"] + "\n\nChecked by a mechanic."
    path = f"/tab/conversations/{person.conversation_id}/drafts/{draft['id']}/send"
    sent = tab(
        bundle, "POST", path, tab_session, {"action_token": draft["action_token"], "text": edited}
    )
    assert sent["outcome"] == "sent_edited"
    assert until(person.replies) == [edited]
    assert not any("QCW-" in text for text in person.everything())
    admin_id = bundle["CHATWOOT_ADMIN_USER_ID"]
    assert any(
        f"sent edited by agent {admin_id}" in note
        for note in owner.notes(person.conversation_id or 0)
    )
    until(lambda: "draft-pending" not in owner.conversation(person.conversation_id or 0)["labels"])


def test_a_discarded_draft_never_reaches_the_visitor(
    visitor: Callable[[], Visitor], bundle: dict[str, str], tab_session: str
) -> None:
    person = visitor()
    person.say("How often should I oil my chain?")
    draft = held(bundle, person, tab_session)
    path = f"/tab/conversations/{person.conversation_id}/drafts/{draft['id']}/discard"
    assert (
        tab(bundle, "POST", path, tab_session, {"action_token": draft["action_token"]})["outcome"]
        == "discarded"
    )
    quiet_for(lambda: bool(person.replies()), 4)

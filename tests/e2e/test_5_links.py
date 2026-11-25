"""``delivery.show_sources`` in the real widget: a public link, never an id or title."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from tests.e2e.stack import Agent, Visitor, audit_for, stack, tab, until

MODE = "auto"
pytestmark = pytest.mark.usefixtures("mode", "sources_on")

VISIT = "https://brambleford-tools.example/visit"
LINE = f"More: {VISIT}"


@pytest.fixture(scope="module")
def sources_on(mode: str) -> Iterator[None]:
    stack("sources", "on")
    try:
        yield
    finally:
        stack("sources", "off")


def assert_shows_no_id_or_title(person: Visitor) -> None:
    seen = [str(m.get("content") or "") for m in person.messages()]
    for text in seen:
        assert "TL-0" not in text
        assert "Opening hours" not in text
        assert "Location" not in text
        assert "Source" not in text


def test_an_answer_in_the_widget_ends_with_its_public_link(
    visitor: Callable[[], Visitor], admin: Agent
) -> None:
    person = visitor()
    person.say("What are your opening hours?")
    (answer,) = until(person.replies, timeout=30)
    assert answer.startswith("The library is open on Wednesdays from 5pm to 8pm")
    assert answer.endswith(f"\n\n{LINE}")
    assert_shows_no_id_or_title(person)
    conversation_id = person.conversation_id or 0
    record = until(lambda: audit_for(conversation_id), timeout=10)[-1]
    assert (record["decision"], record["sources"]) == ("answered", ["TL-01"])

    # Staff tracking is unchanged: the private note still names the entry.
    def staff_notes() -> list[str] | None:
        found = [m["content"] for m in admin.messages(conversation_id) if m["private"]]
        return found or None

    assert until(staff_notes, timeout=10) == [
        "inbox-core answered this message automatically.\n"
        "Category: faq. Tier: auto_answer.\n"
        "Sources: TL-01 Opening hours."
    ]


def test_an_answer_from_an_entry_without_a_page_has_no_line(
    visitor: Callable[[], Visitor],
) -> None:
    person = visitor()
    person.say("How long can I keep a tool?")
    (answer,) = until(person.replies, timeout=30)
    assert answer.startswith("A loan lasts seven days.")
    assert "More:" not in answer
    assert "https://" not in answer
    assert_shows_no_id_or_title(person)


def test_an_approved_draft_reaches_the_widget_with_the_line_the_reviewer_saw(
    visitor: Callable[[], Visitor], tokens: dict[str, str]
) -> None:
    stack("mode", "draft")
    try:
        response = tab(
            "POST", "/tab/session", body={"chatwoot_token": tokens["CHATWOOT_AGENT_TOKEN"]}
        )
        assert response.status_code == 200, response.text
        session = response.json()["session_token"]
        person = visitor()
        person.say("Where are you located?")

        def listed() -> list[dict[str, Any]] | None:
            found = tab(
                "GET", f"/tab/conversations/{person.conversation_id}/drafts", session=session
            )
            assert found.status_code == 200, found.text
            drafts: list[dict[str, Any]] = found.json()["drafts"]
            return drafts or None

        (draft,) = until(listed, timeout=30)
        assert draft["sources"] == [{"id": "TL-02", "title": "Location"}]
        assert draft["text"].endswith(f"\n\n{LINE}")
        sent = tab(
            "POST",
            f"/tab/conversations/{person.conversation_id}/drafts/{draft['id']}/send",
            session=session,
            body={"text": draft["text"], "action_token": draft["action_token"]},
        )
        assert sent.status_code == 200, sent.text
        (reply,) = until(person.replies, timeout=20)
        assert reply == draft["text"]
        assert_shows_no_id_or_title(person)
    finally:
        stack("mode", MODE)

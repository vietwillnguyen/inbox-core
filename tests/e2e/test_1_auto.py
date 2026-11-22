"""Auto mode in the real widget: answers with sources, hand-off, a person taking over."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from tests.e2e.stack import Agent, Visitor, audit_for, quiet_for, until

MODE = "auto"
pytestmark = pytest.mark.usefixtures("mode")


def test_a_question_is_answered_in_the_widget_with_its_source(
    visitor: Callable[[], Visitor], admin: Agent
) -> None:
    person = visitor()
    person.say("What are your opening hours?")
    (answer,) = until(person.replies, timeout=30)
    assert "Wednesdays from 5pm to 8pm" in answer
    assert answer.endswith("Source: TL-01 Opening hours")
    assert person.conversation_id is not None
    record = until(lambda: audit_for(person.conversation_id or 0), timeout=10)[-1]
    assert (record["decision"], record["sources"]) == ("answered", ["TL-01"])
    # An answered conversation stays the bot's and is not put in agents' queues.
    assert admin.conversation(person.conversation_id)["status"] == "pending"


def test_a_sensitive_message_is_handed_off_with_labels_and_assignment(
    visitor: Callable[[], Visitor], admin: Agent, tokens: dict[str, str]
) -> None:
    person = visitor()
    person.say("The drill I borrowed stopped working and the battery was burning hot.")
    (holding,) = until(person.replies, timeout=30)
    assert holding.startswith("Thanks for writing to the Brambleford Tool Library.")
    conversation_id = person.conversation_id or 0

    def handed() -> dict[str, Any] | None:
        found = admin.conversation(conversation_id)
        return found if found["status"] == "open" else None

    found = until(handed, timeout=20)
    assert set(found["labels"]) >= {"handoff", "damage_report"}
    assignee = found["meta"]["assignee"]
    assert assignee["id"] == int(tokens["CHATWOOT_AGENT_USER_ID"])
    notes = [m["content"] for m in admin.messages(conversation_id) if m["private"]]
    assert any("Category: damage_report. Tier: needs_executive." in n for n in notes)
    assert not any("drill" in n for n in notes)


def test_a_person_replying_silences_the_bot(
    visitor: Callable[[], Visitor], volunteer: Agent
) -> None:
    person = visitor()
    person.say("I would like to reserve the hedge trimmer for Saturday.")
    until(person.replies, timeout=30)  # the holding message
    conversation_id = person.conversation_id or 0
    volunteer.reply(conversation_id, "Hello, it is free on Saturday; I have put your name on it.")
    until(lambda: len(person.replies()) == 2, timeout=10)
    until(
        lambda: any(r["decision"] == "person_replied" for r in audit_for(conversation_id)),
        timeout=15,
    )
    person.say("Thanks! Also, what are your opening hours?")
    quiet_for(lambda: len(person.replies()) > 2, 8)
    last = until(
        lambda: [r for r in audit_for(conversation_id) if r["decision"] == "left_for_person"],
        timeout=10,
    )
    assert last[-1]["classifier"] == ""  # not even classified

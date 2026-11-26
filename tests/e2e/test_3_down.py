"""When the inbox-core service is down, Chatwoot itself tells the visitor a person will reply."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from tests.e2e.stack import Agent, Visitor, quiet_for, stack, until

MODE = "auto"
pytestmark = pytest.mark.usefixtures("mode")


@pytest.fixture
def service_down(mode: str) -> Iterator[None]:
    stack("stop-service")
    try:
        yield
    finally:
        stack("start-service")


@pytest.mark.usefixtures("service_down")
def test_chatwoots_fallback_rule_sends_a_holding_message(
    visitor: Callable[[], Visitor], admin: Agent
) -> None:
    person = visitor()
    person.say("Hello, can I borrow a pressure washer this weekend?")
    (holding,) = until(person.replies, timeout=60)
    assert "Our assistant is unavailable right now" in holding

    def opened_and_labelled() -> dict[str, Any] | None:
        # Chatwoot opens the conversation first; the rule labels it a moment later.
        found = admin.conversation(person.conversation_id or 0)
        ready = found["status"] == "open" and "inbox-core-unavailable" in found["labels"]
        return found if ready else None

    until(opened_and_labelled, timeout=20)
    activity = [
        m["content"] for m in admin.messages(person.conversation_id or 0) if m["message_type"] == 2
    ]
    assert any("error with the agent bot" in a for a in activity)


def test_a_normal_hand_off_does_not_trigger_the_fallback_rule(
    visitor: Callable[[], Visitor], admin: Agent
) -> None:
    person = visitor()
    person.say("I want to make a complaint about how a volunteer spoke to me.")
    (holding,) = until(person.replies, timeout=30)
    assert "Our assistant is unavailable" not in holding
    found = until(
        lambda: (c := admin.conversation(person.conversation_id or 0))["status"] == "open" and c,
        timeout=20,
    )
    # Give the rule time to misfire if it were going to.
    quiet_for(lambda: len(person.replies()) > 1, 5)
    found = admin.conversation(person.conversation_id or 0)
    assert "inbox-core-unavailable" not in found["labels"]


def test_an_agent_taking_over_does_not_trigger_the_fallback_rule(
    visitor: Callable[[], Visitor], volunteer: Agent, tokens: dict[str, str]
) -> None:
    # What the dashboard's "Take over" does: assign to yourself, then open.
    person = visitor()
    person.say("Do you run workshops for beginners?")
    until(person.replies, timeout=30)
    conversation_id = person.conversation_id or 0
    me = int(tokens["CHATWOOT_AGENT_USER_ID"])
    assert volunteer.call(
        "POST", f"/conversations/{conversation_id}/assignments", {"assignee_id": me}
    ).is_success
    assert volunteer.call(
        "POST", f"/conversations/{conversation_id}/toggle_status", {"status": "open"}
    ).is_success
    quiet_for(lambda: len(person.replies()) > 1, 6)
    assert "inbox-core-unavailable" not in volunteer.conversation(conversation_id)["labels"]

"""Hand-off alerts with the service's own assignee, in the real Chatwoot of the local stack.

The stack configures both ways of assigning a hand-off, to different people:
the service assigns the volunteer (``INBOX_CORE_ASSIGNEE_ID``), and the seed's
``inbox-core hand-off`` rule would assign the administrator. The service opens
the conversation before it assigns it, so Chatwoot sends its ordinary
assignment notification, and it labels the conversation ``inbox-core-assigns``
so the rule stands down: the service's assignee wins, and exactly one person is
notified, once.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from tests.e2e.stack import Agent, Visitor, audit_for, quiet_for, rails, until

MODE = "auto"
pytestmark = pytest.mark.usefixtures("mode")


def assignments(agent: Agent, conversation_id: int) -> list[dict[str, Any]]:
    response = agent.call("GET", "/notifications")
    response.raise_for_status()
    return [
        n
        for n in response.json()["data"]["payload"]
        if n["primary_actor_id"] == conversation_id
        and n["notification_type"] == "conversation_assignment"
    ]


def assignee_of(agent: Agent, conversation_id: int) -> int | None:
    meta = agent.conversation(conversation_id)["meta"]
    return int(meta["assignee"]["id"]) if meta.get("assignee_type") == "User" else None


def test_both_ways_of_assigning_are_configured(tokens: dict[str, str]) -> None:
    found = rails(
        "r = AutomationRule.find_by!(name: 'inbox-core hand-off'); "
        "puts [r.active, r.event_name, r.actions].to_json"
    )
    active, event, actions = json.loads(found.strip().splitlines()[-1])
    assert (active, event) == (True, "conversation_opened")
    # The rule would give hand-offs to the administrator, not the volunteer.
    assert actions == [
        {"action_name": "assign_agent", "action_params": [int(tokens["CHATWOOT_ADMIN_USER_ID"])]}
    ]


def test_a_hand_off_notifies_the_services_assignee_exactly_once(
    visitor: Callable[[], Visitor], admin: Agent, volunteer: Agent, tokens: dict[str, str]
) -> None:
    person = visitor()
    person.say("The sander I borrowed stopped working and the motor was burning hot.")
    until(person.replies, timeout=30)
    conversation_id = person.conversation_id or 0
    assert until(lambda: assignments(volunteer, conversation_id), timeout=30)
    # Give the rule's background job, and any second notification, time to land.
    quiet_for(lambda: len(assignments(volunteer, conversation_id)) > 1, 8)
    assert len(assignments(volunteer, conversation_id)) == 1
    assert assignments(admin, conversation_id) == []
    assert assignee_of(admin, conversation_id) == int(tokens["CHATWOOT_AGENT_USER_ID"])
    found = admin.conversation(conversation_id)
    assert found["status"] == "open"
    assert {"handoff", "inbox-core-assigns"} <= set(found["labels"])
    (record,) = audit_for(conversation_id)
    assert (record["decision"], record["handoff_failures"]) == ("handed_off", [])


def test_an_answered_conversation_is_assigned_to_nobody_and_notifies_nobody(
    visitor: Callable[[], Visitor], admin: Agent, volunteer: Agent
) -> None:
    person = visitor()
    person.say("What are your opening hours?")
    until(person.replies, timeout=30)
    conversation_id = person.conversation_id or 0
    quiet_for(lambda: bool(assignments(volunteer, conversation_id)), 5)
    assert assignments(admin, conversation_id) == []
    assert assignee_of(admin, conversation_id) is None
    found = admin.conversation(conversation_id)
    assert found["status"] == "pending"
    assert "inbox-core-assigns" not in found["labels"]

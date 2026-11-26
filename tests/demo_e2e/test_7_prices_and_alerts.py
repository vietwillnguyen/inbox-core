"""Prices, hand-off alerts and out-of-hours replies, in the real Chatwoot of the demo bundle.

The shop answers the prices its knowledge base lists (``triage.prices``), and
the seed configures Chatwoot to tell a person (``deploy/chatwoot/seed.rb``):
an automation rule assigns every hand-off and held draft to the owner once it
is open, which makes Chatwoot notify them, and the inbox's business hours send
an out-of-office message to a visitor who writes while the shop is closed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from tests.demo_e2e.bundle import Owner, Visitor, audit_for, rails, until

HOLDING = "This one needs a person"
AWAY = "The Quillmoor Cycle Works team is away right now"


def only_record(person: Visitor) -> dict[str, Any]:
    (record,) = until(lambda: audit_for(person.conversation_id or 0))
    return record


def notifications(owner: Owner) -> list[dict[str, Any]]:
    response = owner.call("GET", "/notifications")
    response.raise_for_status()
    found: list[dict[str, Any]] = response.json()["data"]["payload"]
    return found


def assigned_to(owner: Owner, conversation_id: int) -> int | None:
    """The person a conversation is assigned to; a pending one shows the bot, which is no one."""
    meta = owner.conversation(conversation_id)["meta"]
    if meta.get("assignee_type") != "User":
        return None
    return int(meta["assignee"]["id"])


class TestPrices:
    def test_a_listed_price_is_answered_with_its_page(
        self, visitor: Callable[[], Visitor], owner: Owner
    ) -> None:
        person = visitor()
        person.say("How much does a basic service cost?")
        (reply,) = until(person.replies)
        assert "A basic service costs £45" in reply
        assert reply.endswith("\n\nMore: https://quillmoor-cycles.example/prices")
        record = only_record(person)
        assert (record["category"], record["tier"], record["decision"]) == (
            "faq",
            "auto_answer",
            "answered",
        )
        assert record["sources"][0] == "QCW-31"
        assert "price:stated" in record["tags"]
        assert "handoff" not in owner.conversation(person.conversation_id or 0)["labels"]

    @pytest.mark.parametrize(
        "question",
        [
            "Is there a discount on a full service if I bring two bikes?",
            "Would you do a basic service for £30 instead?",
        ],
    )
    def test_anything_else_about_money_goes_to_a_person(
        self, visitor: Callable[[], Visitor], question: str
    ) -> None:
        person = visitor()
        person.say(question)
        (reply,) = until(person.replies)
        assert HOLDING in reply
        assert "£" not in reply
        record = only_record(person)
        assert (record["tier"], record["decision"]) == ("needs_executive", "handed_off")
        assert record["reason"] == "mentions money or a commitment"


class TestTellingAPerson:
    def test_a_hand_off_is_assigned_to_the_owner_who_is_notified(
        self, visitor: Callable[[], Visitor], owner: Owner, bundle: dict[str, str]
    ) -> None:
        admin = int(bundle["CHATWOOT_ADMIN_USER_ID"])
        person = visitor()
        person.say("Can I book my bike in for a service next Thursday morning?")
        (reply,) = until(person.replies)
        assert HOLDING in reply
        conversation_id = person.conversation_id or 0
        assert until(lambda: assigned_to(owner, conversation_id) == admin, timeout=60)
        found = until(
            lambda: [
                n
                for n in notifications(owner)
                if n["primary_actor_id"] == conversation_id
                and n["notification_type"] == "conversation_assignment"
            ],
            timeout=60,
        )
        assert len(found) == 1
        conversation = owner.conversation(conversation_id)
        assert conversation["status"] == "open"
        assert "handoff" in conversation["labels"]
        # The service did not assign it (no INBOX_CORE_ASSIGNEE_ID): Chatwoot's rule did.
        assert only_record(person)["handoff_failures"] == []

    def test_a_held_draft_is_assigned_and_notified_too(
        self, visitor: Callable[[], Visitor], owner: Owner, bundle: dict[str, str]
    ) -> None:
        admin = int(bundle["CHATWOOT_ADMIN_USER_ID"])
        person = visitor()
        person.say("How often should I oil my chain?")
        conversation_id = until(lambda: person.conversation_id)
        until(lambda: "draft-pending" in owner.conversation(conversation_id)["labels"])
        assert until(lambda: assigned_to(owner, conversation_id) == admin, timeout=60)
        assert until(
            lambda: [
                n
                for n in notifications(owner)
                if n["primary_actor_id"] == conversation_id
                and n["notification_type"] == "conversation_assignment"
            ],
            timeout=60,
        )
        assert person.replies() == []

    def test_an_answered_question_is_not_assigned(
        self, visitor: Callable[[], Visitor], owner: Owner
    ) -> None:
        person = visitor()
        person.say("Where is the shop exactly?")
        until(person.replies)
        conversation_id = person.conversation_id or 0
        assert assigned_to(owner, conversation_id) is None
        assert not [n for n in notifications(owner) if n["primary_actor_id"] == conversation_id]


HOURS = """
inbox = Inbox.find({inbox})
puts inbox.working_hours.order(:day_of_week).map {{ |h|
  h.slice('day_of_week', 'closed_all_day', 'open_all_day', 'open_hour', 'open_minutes',
          'close_hour', 'close_minutes')
}}.to_json
"""

SET_TODAY = """
inbox = Inbox.find({inbox})
today = Time.zone.now.in_time_zone(inbox.timezone).to_date.wday
inbox.working_hours.find_by(day_of_week: today).update!({change})
"""

RESTORE = """
inbox = Inbox.find({inbox})
JSON.parse({rows!r}).each {{ |row|
  inbox.working_hours.find_by(day_of_week: row['day_of_week']).update!(row)
}}
"""


@pytest.fixture
def saved_hours(bundle: dict[str, str]) -> Iterator[str]:
    inbox = bundle["CHATWOOT_INBOX_ID"]
    rows = rails(HOURS.format(inbox=inbox)).strip().splitlines()[-1]
    yield inbox
    rails(RESTORE.format(inbox=inbox, rows=rows))


def set_today(inbox: str, change: str) -> None:
    rails(SET_TODAY.format(inbox=inbox, change=change))


class TestOutOfHours:
    def test_the_inbox_has_the_shops_hours(self, saved_hours: str) -> None:
        rows = json.loads(rails(HOURS.format(inbox=saved_hours)).strip().splitlines()[-1])
        by_day = {row["day_of_week"]: row for row in rows}
        assert by_day[0]["closed_all_day"]
        assert by_day[1]["closed_all_day"]
        assert (by_day[2]["open_hour"], by_day[2]["close_hour"]) == (8, 18)
        assert (by_day[6]["open_hour"], by_day[6]["close_hour"]) == (9, 16)
        settings = rails(
            f"i = Inbox.find({saved_hours}); "
            "puts [i.working_hours_enabled, i.timezone, i.out_of_office_message].to_json"
        )
        enabled, zone, text = json.loads(settings.strip().splitlines()[-1])
        assert (enabled, zone) == (True, "Europe/London")
        assert text.startswith(AWAY)

    def test_a_visitor_who_writes_while_the_shop_is_closed_is_told_and_still_answered(
        self, visitor: Callable[[], Visitor], saved_hours: str
    ) -> None:
        set_today(saved_hours, "closed_all_day: true, open_all_day: false")
        person = visitor()
        person.say("What are your opening hours?")
        until(lambda: any(text.startswith(AWAY) for text in person.everything()))
        (reply,) = until(person.replies)
        assert "Tuesday to Friday from 8am to 6pm" in reply
        # Once a day per conversation, not on every message.
        person.say("And where is the shop?")
        until(lambda: len(person.replies()) == 2)
        assert sum(text.startswith(AWAY) for text in person.everything()) == 1

    def test_a_visitor_who_writes_while_the_shop_is_open_is_not(
        self, visitor: Callable[[], Visitor], saved_hours: str
    ) -> None:
        set_today(saved_hours, "open_all_day: true, closed_all_day: false")
        person = visitor()
        person.say("What are your opening hours?")
        until(person.replies)
        assert not any(text.startswith(AWAY) for text in person.everything())

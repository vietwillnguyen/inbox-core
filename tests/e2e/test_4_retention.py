"""The retention job against the running stack: old transcripts go, recent ones stay."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from tests.e2e.stack import Agent, Visitor, compose, rails, stack, until

MODE = "auto"
pytestmark = pytest.mark.usefixtures("mode")


# Run inside the service container; the thread key is a bound parameter.
BACKDATE = """
import sqlite3, sys
db = sqlite3.connect("/data/inbox-core.db")
db.execute(
    "update inbox_messages set created_at = datetime('now', '-40 days') where conversation_id ="
    " (select id from inbox_conversations where channel = 'chatwoot' and thread_key = ?)",
    (sys.argv[1],),
)
db.commit()
"""
CONTENT = """
import json, sqlite3, sys
db = sqlite3.connect("/data/inbox-core.db")
rows = db.execute(
    "select body_encrypted is not null from inbox_messages where conversation_id ="
    " (select id from inbox_conversations where channel = 'chatwoot' and thread_key = ?)",
    (sys.argv[1],),
)
print(json.dumps([r[0] for r in rows]))
"""


def in_service(script: str, thread_key: str) -> str:
    python = "/app/.venv/bin/python"
    return compose("exec", "-T", "inbox-core", python, "-c", script, thread_key)


def backdate_core(thread_key: str) -> None:
    in_service(BACKDATE, thread_key)


def core_content(thread_key: str) -> list[int]:
    found: list[int] = json.loads(in_service(CONTENT, thread_key))
    return found


def test_old_transcripts_are_deleted_in_chatwoot_and_erased_in_the_core(
    visitor: Callable[[], Visitor], admin: Agent
) -> None:
    old, recent = visitor(), visitor()
    old.say("What are your opening hours?")
    recent.say("Where is the library?")
    until(old.replies, timeout=30)
    until(recent.replies, timeout=30)
    old_id, recent_id = old.conversation_id or 0, recent.conversation_id or 0
    contact = admin.conversation(old_id)["meta"]["sender"]["id"]
    rails(
        f"Conversation.find_by!(display_id: {old_id}).update_columns(last_activity_at: 40.days.ago)"
    )
    backdate_core(str(old_id))

    report = json.loads(stack("retention", "30"))
    assert report["chatwoot"]["conversations_deleted"] >= 1
    assert report["chatwoot"]["failures"] == 0
    assert report["core"]["messages_erased"] >= 2

    until(lambda: admin.call("GET", f"/conversations/{old_id}").status_code == 404, timeout=60)
    assert admin.call("GET", f"/conversations/{recent_id}").status_code == 200
    until(lambda: admin.call("GET", f"/contacts/{contact}").status_code == 404, timeout=60)
    # The core keeps the skeleton (dedupe and metrics read it) but not the text.
    erased = core_content(str(old_id))
    assert erased
    assert not any(erased)
    assert all(core_content(str(recent_id)))

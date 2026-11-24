"""The periodic reset: conversations older than a day are deleted, recent ones stay."""

from __future__ import annotations

import json
from collections.abc import Callable

from tests.demo_e2e.bundle import Owner, Visitor, compose, demo, rails, until


def test_old_conversations_and_their_contacts_are_deleted(
    visitor: Callable[[], Visitor], owner: Owner
) -> None:
    old, recent = visitor(), visitor()
    old.say("Are you open on Sunday?")
    recent.say("Which bus gets me to the shop?")
    until(old.replies)
    until(recent.replies)
    old_id, recent_id = old.conversation_id or 0, recent.conversation_id or 0
    contact = owner.conversation(old_id)["meta"]["sender"]["id"]
    rails(
        f"Conversation.find_by!(display_id: {old_id}).update_columns(last_activity_at: 2.days.ago)"
    )

    report = json.loads(demo("reset").strip().splitlines()[-1])
    assert report["chatwoot"]["conversations_deleted"] >= 1
    assert report["chatwoot"]["failures"] == 0

    until(lambda: owner.call("GET", f"/conversations/{old_id}").status_code == 404, timeout=60)
    until(lambda: owner.call("GET", f"/contacts/{contact}").status_code == 404, timeout=60)
    assert owner.call("GET", f"/conversations/{recent_id}").status_code == 200


def test_the_reset_job_runs_on_its_own(bundle: dict[str, str]) -> None:
    # The job's first run happens when the bundle starts, then every hour.
    logs = compose("logs", "--no-color", "--no-log-prefix", "reset")
    reports = [json.loads(line) for line in logs.splitlines() if line.startswith("{")]
    assert reports
    assert {"chatwoot", "core"} <= set(reports[0])

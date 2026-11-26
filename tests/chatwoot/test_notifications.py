"""Notifications from the Chatwoot service: wired from the config, linking into Chatwoot.

Apprise is driven through its own custom-notification decorator (registered by
``tests.test_notify``), so nothing is sent anywhere.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from inbox_core.chatwoot import __main__ as command
from inbox_core.examples.demo import EXAMPLE_DIR
from tests.chatwoot.conftest import CHATWOOT_ORIGIN, build_stack
from tests.chatwoot.test_operations import env
from tests.test_notify import RECEIVED

DAMAGE = "The drill I borrowed stopped working and burned my hand"
QUESTION = "What are your opening hours?"


def notifying(tmp_path: Path, *, link: str = "", reminders: bool = False) -> Path:
    """The worked example's configuration with a ``[notifications]`` section."""
    text = (EXAMPLE_DIR / "client.toml").read_text(encoding="utf-8")
    events = '["hand_off", "draft_held", "reminder"]' if reminders else '["hand_off", "draft_held"]'
    section = f'\n[notifications]\nurls = ["inboxcoretest://${{CW_NOTIFY}}/"]\nevents = {events}\n'
    if reminders:
        section += "remind_after_minutes = 30\n"
    if link:
        section += f'link = "{link}"\n'
    path = tmp_path / "notifying.toml"
    path.write_text(text + section)
    return path


@pytest.fixture(autouse=True)
def clear() -> None:
    RECEIVED.clear()


class TestTheService:
    def test_a_hand_off_is_notified_with_a_link_to_the_conversation(self, tmp_path: Path) -> None:
        stack = build_stack(
            tmp_path,
            env={"INBOX_CORE_CONFIG": str(notifying(tmp_path)), "CW_NOTIFY": "staff"},
        )
        stack.visitor_says(11, 201, DAMAGE)
        record = stack.audit.records[-1]
        assert (record.decision, record.notifications) == ("handed_off", ("hand_off:sent",))
        (sent,) = RECEIVED
        assert f"Open: {CHATWOOT_ORIGIN}/app/accounts/1/conversations/11" in sent["body"]
        assert "Category: damage_report" in sent["body"]
        assert "drill" not in json.dumps(RECEIVED)
        assert "burned" not in json.dumps(RECEIVED)
        stack.parts.store.close()

    def test_a_held_draft_is_notified(self, tmp_path: Path) -> None:
        stack = build_stack(
            tmp_path,
            mode="draft",
            env={"INBOX_CORE_CONFIG": str(notifying(tmp_path)), "CW_NOTIFY": "staff"},
        )
        stack.visitor_says(10, 200, QUESTION)
        assert stack.audit.records[-1].notifications == ("draft_held:sent",)
        assert "Event: draft_held" in RECEIVED[0]["body"]
        assert "/conversations/10" in RECEIVED[0]["body"]
        stack.parts.store.close()

    def test_the_clients_own_link_template_wins(self, tmp_path: Path) -> None:
        config = notifying(tmp_path, link="https://ops.example/c/{thread_key}")
        stack = build_stack(tmp_path, env={"INBOX_CORE_CONFIG": str(config), "CW_NOTIFY": "staff"})
        stack.visitor_says(11, 201, DAMAGE)
        assert "Open: https://ops.example/c/11" in RECEIVED[0]["body"]
        stack.parts.store.close()

    def test_a_failing_notification_changes_nothing_in_chatwoot(self, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        quiet = build_stack(tmp_path / "a")
        failing = build_stack(
            tmp_path / "b",
            env={"INBOX_CORE_CONFIG": str(notifying(tmp_path)), "CW_NOTIFY": "fail"},
        )
        for stack in (quiet, failing):
            stack.visitor_says(11, 201, DAMAGE)
        assert [w[:2] for w in failing.chatwoot.writes] == [w[:2] for w in quiet.chatwoot.writes]
        record = failing.audit.records[-1]
        assert record.decision == "handed_off"
        assert record.handoff_failures == ("notification",)
        quiet.parts.store.close()
        failing.parts.store.close()

    def test_without_the_section_nothing_is_built(self, tmp_path: Path) -> None:
        stack = build_stack(tmp_path)
        stack.visitor_says(11, 201, DAMAGE)
        assert stack.audit.records[-1].notifications == ()
        assert RECEIVED == []
        stack.parts.store.close()


class TestTheRemindCommand:
    def test_it_reminds_once_about_a_hand_off_left_waiting(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from sqlalchemy import create_engine

        from inbox_core.store.sqlalchemy import SqlAlchemyConversationStore, create_schema

        values = env(
            tmp_path,
            INBOX_CORE_CONFIG=str(notifying(tmp_path, reminders=True)),
            CW_NOTIFY="staff",
        )
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        engine = create_engine(values["INBOX_CORE_DATABASE_URL"])
        create_schema(engine)
        hour_ago = datetime.now(UTC) - timedelta(hours=1)
        store = SqlAlchemyConversationStore(engine, clock=lambda: hour_ago)
        conversation = store.conversation_for("chatwoot", "42", "sender")
        store.pause(conversation.id, "needs_executive: executive category damage_report")
        engine.dispose()

        assert command.main(["remind"]) == 0
        assert json.loads(capsys.readouterr().out)["sent"] == 1
        assert command.main(["remind"]) == 0
        assert json.loads(capsys.readouterr().out)["already_reminded"] == 1
        (sent,) = RECEIVED
        assert "Event: reminder" in sent["body"]
        assert "Tier: needs_executive" in sent["body"]
        assert f"{CHATWOOT_ORIGIN}/app/accounts/1/conversations/42" in sent["body"]

    def test_it_refuses_a_config_without_reminders(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        values = env(tmp_path, INBOX_CORE_CONFIG=str(notifying(tmp_path)), CW_NOTIFY="staff")
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        with pytest.raises(SystemExit):
            command.main(["remind"])

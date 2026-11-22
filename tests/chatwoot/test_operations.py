"""Settings, the Chatwoot retention job and the command line."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from inbox_core.chatwoot import __main__ as command
from inbox_core.chatwoot.api import ChatwootApi
from inbox_core.chatwoot.retention import run_chatwoot_retention
from inbox_core.chatwoot.settings import ChatwootSettings, SettingsError
from inbox_core.crypto import generate_key_entry
from tests.chatwoot.fake import ACCOUNT, ADMIN_TOKEN, BOT_TOKEN, FakeChatwoot

NOW = datetime(2023, 12, 31, tzinfo=UTC)  # the fake's conversations are from 2023-11-14


def env(tmp_path: Path, **changes: str) -> dict[str, str]:
    values = {
        "CHATWOOT_URL": "http://chatwoot.test/",
        "CHATWOOT_ORIGIN": "http://127.0.0.1:3910",
        "INBOX_CORE_PUBLIC_ORIGIN": "http://127.0.0.1:3912/",
        "CHATWOOT_ACCOUNT_ID": "1",
        "CHATWOOT_BOT_TOKEN": BOT_TOKEN,
        "CHATWOOT_BOT_SECRET": "example-bot-secret",
        "INBOX_CORE_WEBHOOK_PATH_TOKEN": "p" * 32,
        "INBOX_CORE_TAB_SECRET": "t" * 40,
        "INBOX_CORE_DATABASE_URL": f"sqlite:///{tmp_path / 'ops.db'}",
        "INBOX_CORE_ENCRYPTION_KEYS": generate_key_entry("k1"),
    }
    values.update(changes)
    return values


class TestSettings:
    def test_a_complete_environment(self, tmp_path: Path) -> None:
        settings = ChatwootSettings.from_env(env(tmp_path, INBOX_CORE_ASSIGNEE_ID="5"))
        assert settings.chatwoot_url == "http://chatwoot.test"
        assert settings.public_origin == "http://127.0.0.1:3912"
        assert (settings.account_id, settings.assignee_id, settings.session_seconds) == (1, 5, 1800)
        for secret in (BOT_TOKEN, "example-bot-secret", "p" * 32, "t" * 40):
            assert secret not in repr(settings)

    @pytest.mark.parametrize(
        ("changes", "message"),
        [
            ({"CHATWOOT_URL": ""}, "CHATWOOT_URL is not set"),
            ({"CHATWOOT_ACCOUNT_ID": "one"}, "CHATWOOT_ACCOUNT_ID must be a whole number"),
            ({"INBOX_CORE_WEBHOOK_PATH_TOKEN": "short"}, "at least 24"),
            ({"INBOX_CORE_TAB_SECRET": "short"}, "at least 32"),
            ({"CHATWOOT_ORIGIN": "http://127.0.0.1:3910/app"}, "must be an origin"),
            ({"CHATWOOT_ORIGIN": "javascript:alert(1)"}, "must be an origin"),
            ({"INBOX_CORE_TAB_SESSION_SECONDS": "30"}, "between 60 and 28800"),
            ({"INBOX_CORE_ASSIGNEE_ID": "me"}, "INBOX_CORE_ASSIGNEE_ID"),
        ],
    )
    def test_problems_name_the_variable_not_the_value(
        self, tmp_path: Path, changes: dict[str, str], message: str
    ) -> None:
        with pytest.raises(SettingsError, match=message) as caught:
            ChatwootSettings.from_env(env(tmp_path, **changes))
        assert "short" not in str(caught.value)

    def test_it_reads_the_process_environment_by_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key, value in env(tmp_path).items():
            monkeypatch.setenv(key, value)
        assert ChatwootSettings.from_env().account_id == 1


class TestChatwootRetention:
    def test_old_conversations_and_their_orphaned_contacts_go(self) -> None:
        fake = FakeChatwoot()
        fake.conversation(1, contact=70)
        fake.conversation(2, contact=71)
        fake.conversation(3, contact=71)
        fake.conversation(4, contact=72)
        fake.conversations[3]["last_activity_at"] = int(NOW.timestamp()) - 3600
        fake.conversations[4]["last_activity_at"] = int(NOW.timestamp())
        admin = ChatwootApi(
            "http://chatwoot.test", ACCOUNT, ADMIN_TOKEN, transport=fake.transport()
        )
        report = run_chatwoot_retention(admin, days=30, clock=lambda: NOW)
        assert report.to_dict() == {
            "cutoff": "2023-12-01T00:00:00+00:00",
            "conversations_deleted": 2,
            "contacts_deleted": 1,
            "failures": 0,
        }
        assert sorted(fake.conversations) == [3, 4]
        assert fake.contacts == {71, 72}

    def test_it_waits_for_chatwoots_background_delete_before_checking_contacts(self) -> None:
        fake = FakeChatwoot(delete_lag=3)
        fake.conversation(1, contact=70)
        admin = ChatwootApi(
            "http://chatwoot.test", ACCOUNT, ADMIN_TOKEN, transport=fake.transport()
        )
        slept: list[float] = []
        report = run_chatwoot_retention(admin, days=30, clock=lambda: NOW, sleep=slept.append)
        assert (report.conversations_deleted, report.contacts_deleted) == (1, 1)
        assert fake.contacts == set()
        assert slept

    def test_a_delete_that_never_lands_keeps_the_contact_and_counts_a_failure(self) -> None:
        fake = FakeChatwoot(delete_lag=10_000)
        fake.conversation(1, contact=70)
        admin = ChatwootApi(
            "http://chatwoot.test", ACCOUNT, ADMIN_TOKEN, transport=fake.transport()
        )
        report = run_chatwoot_retention(
            admin, days=30, clock=lambda: NOW, sleep=lambda _: None, wait_seconds=1.0
        )
        assert (report.contacts_deleted, report.failures) == (0, 1)
        assert 70 in fake.contacts

    def test_the_bots_token_cannot_delete_and_failures_are_counted(self) -> None:
        fake = FakeChatwoot()
        fake.conversation(1, contact=70)
        bot = ChatwootApi("http://chatwoot.test", ACCOUNT, BOT_TOKEN, transport=fake.transport())
        report = run_chatwoot_retention(bot, days=30, clock=lambda: NOW)
        # The delete is refused; the contact still has a conversation, so is kept.
        assert (report.conversations_deleted, report.contacts_deleted, report.failures) == (0, 0, 1)
        assert 1 in fake.conversations

    def test_days_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="days"):
            run_chatwoot_retention(None, days=0)  # type: ignore[arg-type]


class TestCommand:
    @pytest.fixture
    def fake(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeChatwoot:
        fake = FakeChatwoot()
        for key, value in env(tmp_path, CHATWOOT_ADMIN_TOKEN=ADMIN_TOKEN).items():
            monkeypatch.setenv(key, value)
        real = ChatwootApi.__init__

        def with_fake(self: ChatwootApi, *args: Any, **kwargs: Any) -> None:
            kwargs["transport"] = fake.transport()
            real(self, *args, **kwargs)

        monkeypatch.setattr(ChatwootApi, "__init__", with_fake)
        return fake

    def test_retention_runs_both_jobs_and_prints_counts(
        self, fake: FakeChatwoot, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fake.conversation(1)
        assert command.main(["retention", "--days", "1"]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["chatwoot"]["conversations_deleted"] == 1
        assert report["core"]["messages_erased"] == 0
        assert fake.conversations == {}

    def test_retention_needs_an_admin_token_and_positive_days(
        self, fake: FakeChatwoot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with pytest.raises(SystemExit):
            command.main(["retention", "--days", "0"])
        monkeypatch.delenv("CHATWOOT_ADMIN_TOKEN")
        with pytest.raises(SystemExit):
            command.main(["retention", "--days", "3"])

    def test_serve_builds_the_app_and_runs_uvicorn_without_an_access_log(
        self, fake: FakeChatwoot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import uvicorn

        ran: dict[str, Any] = {}
        monkeypatch.setenv("INBOX_CORE_CLASSIFIER", "example-keywords")
        monkeypatch.setattr(uvicorn, "run", lambda app, **kw: ran.update(app=app, **kw))
        assert command.main(["serve", "--port", "3999"]) == 0
        assert ran["access_log"] is False
        assert ran["port"] == 3999
        from fastapi.testclient import TestClient

        assert TestClient(ran["app"]).get("/healthz").json()["mode"] == "draft"

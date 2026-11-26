"""Retention: content older than N days is deleted, the skeleton is kept."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from inbox_core.retention import RetentionReport, main, run_retention
from tests.helpers import message
from tests.test_pipeline import QUESTION, harness
from tests.test_review import Clock, make_store

NOW = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)


@pytest.fixture(params=["memory", "sqlalchemy"])
def store_kind(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def two_ages(store_kind: str, tmp_path: Path, *, mode: str = "auto") -> tuple[Any, Clock]:
    clock = Clock()
    store = make_store(store_kind, tmp_path, clock)
    h = harness(mode=mode, store=store, clock=clock)
    h.pipeline.process(message(QUESTION, message_id="old", thread="t-old"))
    clock.now = NOW + timedelta(days=40)
    h.pipeline.process(message(QUESTION, message_id="new", thread="t-new"))
    return h, clock


class TestTheStore:
    def test_erasing_before_a_cutoff_keeps_newer_content_and_every_row(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        h, _ = two_ages(store_kind, tmp_path)
        before = len(h.store.messages_in(1)) + len(h.store.messages_in(2))
        erased = h.store.erase_content_before(NOW + timedelta(days=10))
        assert erased == 2  # the old inbound message and its answer
        assert all(not m.has_content for m in h.store.messages_in(1))
        assert all(m.content_erased_at is not None for m in h.store.messages_in(1))
        assert all(m.has_content for m in h.store.messages_in(2))
        assert len(h.store.messages_in(1)) + len(h.store.messages_in(2)) == before
        # Dedupe still reads the skeleton.
        assert h.store.is_handled("web", "old")
        assert h.store.erase_content_before(NOW + timedelta(days=10)) == 0

    def test_an_aware_cutoff_is_compared_in_utc(self, store_kind: str, tmp_path: Path) -> None:
        h, _ = two_ages(store_kind, tmp_path)
        from zoneinfo import ZoneInfo

        aware = (NOW + timedelta(days=10)).astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
        assert h.store.erase_content_before(aware) == 2


class TestTheJob:
    def test_it_expires_old_drafts_then_erases_old_content(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        h, clock = two_ages(store_kind, tmp_path, mode="draft")
        report = run_retention(h.store, days=30, clock=clock)
        assert report == RetentionReport(
            cutoff=(NOW + timedelta(days=10)).replace(tzinfo=None).isoformat(),
            drafts_expired=1,
            messages_erased=2,
        )
        old_draft = h.store.messages_in(1)[-1]
        assert (old_draft.action, old_draft.review_outcome) == ("expired", "expired")
        assert old_draft.reviewed_by == "retention"
        assert len(h.pipeline.drafts.pending(2)) == 1

    def test_days_must_be_positive(self, store_kind: str, tmp_path: Path) -> None:
        h, clock = two_ages(store_kind, tmp_path)
        with pytest.raises(ValueError, match="days"):
            run_retention(h.store, days=0, clock=clock)

    def test_the_report_is_numbers_only(self) -> None:
        report = RetentionReport(cutoff="2026-01-01T00:00:00", drafts_expired=1, messages_erased=2)
        assert report.to_dict() == {
            "cutoff": "2026-01-01T00:00:00",
            "drafts_expired": 1,
            "messages_erased": 2,
        }


class TestTheCommand:
    def test_it_runs_against_a_database(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        two_ages("sqlalchemy", tmp_path)
        url = f"sqlite:///{tmp_path / 'review.db'}"
        assert main(["--database-url", url, "--days", "1"]) == 0
        printed = json.loads(capsys.readouterr().out)
        assert printed["messages_erased"] == 4
        assert printed["drafts_expired"] == 0

    @pytest.mark.parametrize("days", ["0", "thirty"])
    def test_it_refuses_a_bad_day_count(
        self, days: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            main(["--database-url", "sqlite://", "--days", days])
        assert "days" in capsys.readouterr().err

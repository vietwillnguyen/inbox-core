"""Two deliveries for one conversation never produce two replies.

The guarantee: at most one ``Pipeline.process`` call works on a conversation at
a time. Within a process it holds for any store; across processes it holds
for the SQL store, because the lease is one conditional ``UPDATE`` in the
shared database.
"""

from __future__ import annotations

import multiprocessing
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from inbox_core.crypto import FieldCipher
from inbox_core.messages import IncomingMessage
from inbox_core.store.memory import InMemoryConversationStore
from inbox_core.testing.fakes import RecordingSink, signals
from inbox_core.triage import TriageSignals
from tests.helpers import message
from tests.test_pipeline import QUESTION, harness
from tests.test_review import Clock, make_store


@dataclass
class SlowClassifier:
    """Classifies slowly, so two calls overlap if nothing serialises them."""

    delay: float = 0.2
    name: str = "slow"
    calls: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def classify(self, incoming: IncomingMessage) -> TriageSignals:
        with self.lock:
            self.calls += 1
        time.sleep(self.delay)
        return signals("faq")


@pytest.fixture(params=["memory", "sqlalchemy"])
def store_kind(request: pytest.FixtureRequest) -> str:
    return str(request.param)


class TestLeases:
    def test_one_owner_at_a_time(self, store_kind: str, tmp_path: Path) -> None:
        clock = Clock()
        store = make_store(store_kind, tmp_path, clock)
        conversation = store.conversation_for("web", "t", "s" * 64)
        ttl = timedelta(seconds=30)
        assert store.acquire_lease(conversation.id, "a", ttl=ttl) is True
        assert store.acquire_lease(conversation.id, "b", ttl=ttl) is False
        assert store.renew_lease(conversation.id, "a", ttl=ttl) is True
        assert store.renew_lease(conversation.id, "b", ttl=ttl) is False
        store.release_lease(conversation.id, "b")  # not the owner: no effect
        assert store.acquire_lease(conversation.id, "b", ttl=ttl) is False
        store.release_lease(conversation.id, "a")
        assert store.acquire_lease(conversation.id, "b", ttl=ttl) is True

    def test_an_expired_lease_can_be_taken_and_the_old_owner_loses_it(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        clock = Clock()
        store = make_store(store_kind, tmp_path, clock)
        conversation = store.conversation_for("web", "t", "s" * 64)
        ttl = timedelta(seconds=30)
        assert store.acquire_lease(conversation.id, "a", ttl=ttl)
        clock.now += timedelta(seconds=31)
        assert store.acquire_lease(conversation.id, "b", ttl=ttl) is True
        assert store.renew_lease(conversation.id, "a", ttl=ttl) is False

    def test_an_unknown_conversation_cannot_be_leased(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        store = make_store(store_kind, tmp_path, Clock())
        assert store.acquire_lease(999, "a", ttl=timedelta(seconds=1)) is False


class TestWithinAProcess:
    def test_two_messages_racing_in_one_conversation_get_one_answer(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        store = make_store(store_kind, tmp_path, Clock())
        sink = RecordingSink()
        h = harness(classifier=SlowClassifier(), store=store, sink=sink, sleep=time.sleep)
        results: list[str] = []

        def run(message_id: str) -> None:
            results.append(h.pipeline.process(message(QUESTION, message_id=message_id)).decision)

        threads = [threading.Thread(target=run, args=(f"m{n}",)) for n in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sorted(results) == ["answered", "handed_off"]
        assert [r.kind for r in sink.sent].count("grounded_answer") == 1

    def test_the_same_message_delivered_twice_at_once_is_answered_once(
        self, store_kind: str, tmp_path: Path
    ) -> None:
        store = make_store(store_kind, tmp_path, Clock())
        sink = RecordingSink()
        h = harness(classifier=SlowClassifier(), store=store, sink=sink, sleep=time.sleep)
        results: list[str] = []

        def run() -> None:
            results.append(h.pipeline.process(message(QUESTION)).decision)

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sorted(results) == ["answered", "duplicate"]
        assert len(sink.sent) == 1

    def test_a_caller_that_cannot_get_the_lease_is_busy_and_retried(self) -> None:
        store = InMemoryConversationStore(cipher=FieldCipher({"k": secrets.token_bytes(32)}, "k"))
        h = harness(store=store, lease_wait=0.0)
        conversation = store.conversation_for("web", "conv-1", message().sender_key)
        assert store.acquire_lease(conversation.id, "someone-else", ttl=timedelta(minutes=1))
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "busy"
        assert record.reason == "another worker is processing this conversation"
        assert not store.is_handled("web", "msg-1")
        assert h.sink.sent == []
        store.release_lease(conversation.id, "someone-else")
        assert h.pipeline.process(message(QUESTION)).decision == "answered"

    def test_losing_the_lease_before_delivering_sends_nothing(self) -> None:
        h = harness()
        real = h.store.renew_lease
        h.store.renew_lease = lambda *a, **k: False  # type: ignore[method-assign]
        record = h.pipeline.process(message(QUESTION))
        assert record.decision == "incomplete"
        assert record.reason == "lost the conversation lease before delivering"
        assert h.sink.sent == []
        h.store.renew_lease = real  # type: ignore[method-assign]
        assert h.pipeline.process(message(QUESTION)).decision == "answered"

    def test_the_lease_is_released_even_when_processing_fails(self) -> None:
        h = harness()

        def broken(*args: Any) -> None:
            raise RuntimeError("boom")

        h.store.record_triage = broken  # type: ignore[method-assign,assignment]
        assert h.pipeline.process(message(QUESTION)).decision == "incomplete"
        assert h.store.acquire_lease(1, "next", ttl=timedelta(seconds=1)) is True


def _worker(database: str, key: bytes, message_id: str, start: Any, out: Any) -> None:
    from sqlalchemy import create_engine

    from inbox_core.store.sqlalchemy import SqlAlchemyConversationStore

    store = SqlAlchemyConversationStore(
        create_engine(f"sqlite:///{database}", connect_args={"timeout": 30}),
        cipher=FieldCipher({"k": key}, "k"),
    )
    sink = RecordingSink()
    h = harness(classifier=SlowClassifier(), store=store, sink=sink, sleep=time.sleep)  # type: ignore[arg-type]
    start.wait()
    record = h.pipeline.process(message(QUESTION, message_id=message_id))
    out.put((record.decision, [r.kind for r in sink.sent]))


@pytest.mark.parametrize("ids", [("m1", "m2"), ("m1", "m1")], ids=["two-messages", "same-message"])
def test_across_processes_the_sql_store_allows_one_answer(
    tmp_path: Path, ids: tuple[str, str]
) -> None:
    from sqlalchemy import create_engine

    from inbox_core.store.sqlalchemy import create_schema

    database = str(tmp_path / "shared.db")
    engine = create_engine(f"sqlite:///{database}")
    create_schema(engine)
    engine.dispose()
    key = secrets.token_bytes(32)
    context = multiprocessing.get_context("spawn")
    start, out = context.Event(), context.Queue()
    workers = [
        context.Process(target=_worker, args=(database, key, mid, start, out)) for mid in ids
    ]
    for worker in workers:
        worker.start()
    start.set()
    results = [out.get(timeout=60) for _ in workers]
    for worker in workers:
        worker.join(timeout=60)
        assert worker.exitcode == 0
    answers = sum(kinds.count("grounded_answer") for _, kinds in results)
    assert answers == 1
    decisions = sorted(decision for decision, _ in results)
    expected = ["answered", "handed_off"] if ids[0] != ids[1] else ["answered", "duplicate"]
    assert decisions == expected


@pytest.mark.parametrize(
    "settings",
    [
        {"lease_ttl": timedelta(0)},
        {"lease_wait": -1.0},
        {"lease_poll": 0.0},
    ],
)
def test_lease_settings_are_validated(settings: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="lease"):
        harness(**settings)


def test_a_conversation_that_vanishes_under_the_lease_is_incomplete() -> None:
    h = harness()
    h.store.get_conversation = lambda conversation_id: None  # type: ignore[method-assign]
    record = h.pipeline.process(message(QUESTION))
    assert record.decision == "incomplete"
    assert record.reason == "internal error (LookupError)"
    assert h.sink.sent == []

"""Notifications for hand-offs, held drafts and reminders, over Apprise.

Nothing here sends to a real service: Apprise is driven through its own
custom-notification decorator and through a JSON endpoint on 127.0.0.1.
"""

from __future__ import annotations

import dataclasses
import json
import secrets
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from inbox_core.adapters.apprise import AppriseTransport, NotificationFailedError
from inbox_core.config import (
    ClientConfig,
    ConfigError,
    DeliveryPolicy,
    NotificationPolicy,
    QuietHours,
)
from inbox_core.crypto import FieldCipher
from inbox_core.delivery import DeliveryMode
from inbox_core.handlers import (
    ExtractiveGenerator,
    GroundedAnswer,
    HandlerRegistry,
)
from inbox_core.knowledge import InMemoryRetriever, KnowledgeEntry
from inbox_core.messages import IncomingMessage, make_sender_key
from inbox_core.notify import (
    Notifications,
    RecordingTransport,
    build_notifications,
    run_reminders,
)
from inbox_core.pipeline import InMemoryAuditSink, Pipeline
from inbox_core.store.memory import InMemoryConversationStore
from inbox_core.testing.fakes import FakeClassifier, RecordingNotifier, RecordingSink, signals
from tests.helpers import bike_config

ENTRIES = (
    KnowledgeEntry("KB-01", "Opening hours", "We are open Tuesday to Saturday, 9am to 6pm."),
)
HOLDING = "Thanks for writing. A person from the workshop will reply here."
URL = "json://${NOTIFY_HOST}/hook"


def policy(**values: Any) -> NotificationPolicy:
    return NotificationPolicy(**{"urls": (URL,), **values})


def client(*, mode: str = "auto", **notifications: Any) -> ClientConfig:
    base = bike_config()
    return dataclasses.replace(
        base,
        delivery=DeliveryPolicy(
            mode=DeliveryMode(mode),
            auto_languages=frozenset({"en"}),
            holding={"en": HOLDING},
            timezone="Europe/London",
        ),
        notifications=policy(**notifications),
    )


class Clock:
    def __init__(self, at: datetime) -> None:
        self.now = at

    def __call__(self) -> datetime:
        return self.now


NOON = datetime(2026, 6, 2, 11, 0, tzinfo=UTC)  # 12:00 in London (summer time)
NIGHT = datetime(2026, 6, 2, 22, 30, tzinfo=UTC)  # 23:30 in London


@dataclasses.dataclass
class Wired:
    pipeline: Pipeline
    transport: RecordingTransport
    store: InMemoryConversationStore
    sink: RecordingSink
    config: ClientConfig
    notifications: Notifications


def wired(
    config: ClientConfig | None = None,
    *,
    fail: bool = False,
    clock: Clock | None = None,
    classifier: FakeClassifier | None = None,
) -> Wired:
    config = config or client()
    transport = RecordingTransport(fail=fail)
    now = clock or Clock(NOON)
    notifications = Notifications(config, transport, clock=now)
    store = InMemoryConversationStore(
        cipher=FieldCipher({"k1": secrets.token_bytes(32)}, "k1"), clock=now
    )
    sink = RecordingSink()
    pipeline = Pipeline(
        config=config,
        classifier=classifier or FakeClassifier(default=signals("faq")),
        handlers=HandlerRegistry(
            {
                "faq": GroundedAnswer(
                    InMemoryRetriever(ENTRIES), ExtractiveGenerator(), min_score=0.1
                )
            }
        ),
        sink=sink,
        store=store,
        notifier=RecordingNotifier(),
        audit=InMemoryAuditSink(),
        notifications=notifications,
        sleep=lambda _: None,
        clock=now,
    )
    return Wired(pipeline, transport, store, sink, config, notifications)


# A visitor who writes their name, email address and phone number into the message.
NAME = "Annika Thorsby-Vale"
EMAIL = "annika.thorsby@example.com"
PHONE = "+44 7700 900461"
TEXT = (
    f"Hi, this is {NAME}, please call me on {PHONE} or email {EMAIL} about the "
    "squeaky wheel on my grandmother's tandem"
)


def visitor(text: str = TEXT, *, message_id: str = "m-1", thread: str = "77") -> IncomingMessage:
    return IncomingMessage(
        channel="web",
        thread_key=thread,
        provider_message_id=message_id,
        sender_key=make_sender_key(EMAIL),
        sender_address=EMAIL,
        subject=f"From {NAME}",
        text=text,
    )


def assert_no_customer_data(payload: str) -> None:
    for secret in (NAME, "Annika", "Thorsby", EMAIL, "example.com", PHONE, "7700", "tandem"):
        assert secret not in payload, secret
    assert "squeaky" not in payload


class TestThePolicy:
    def test_it_is_off_by_default(self) -> None:
        assert not bike_config().notifications.enabled
        assert not bike_config().notifications.notifies("hand_off")

    def test_urls_default_to_hand_offs_and_held_drafts(self) -> None:
        built = policy()
        assert built.notifies("hand_off")
        assert built.notifies("draft_held")
        assert not built.notifies("reminder")
        assert built.variables == ("NOTIFY_HOST",)

    @pytest.mark.parametrize(
        ("url", "problem"),
        [
            ("ntfy://ntfy.example/alerts", "names no environment variable"),
            ("mailtos://user:hunter2@${MAIL_HOST}", "has a password written into it"),
            ("json://${HOST}/hook?token=abc123", "has a secret query value"),
            ("json://$HOST/hook", "'$' that is not a ${VARIABLE}"),
            ("not a url ${X}", "must start with an Apprise scheme"),
        ],
    )
    def test_secrets_written_into_a_url_are_refused(self, url: str, problem: str) -> None:
        with pytest.raises(ConfigError) as caught:
            policy(urls=(url,))
        assert problem in str(caught.value)
        # The problem names the URL's position, never what it holds.
        assert "hunter2" not in str(caught.value)
        assert "abc123" not in str(caught.value)

    def test_a_whole_url_may_come_from_one_variable(self) -> None:
        assert policy(urls=("${INBOX_CORE_NOTIFY_URL}",)).variables == ("INBOX_CORE_NOTIFY_URL",)

    def test_reminders_need_a_delay_and_the_event(self) -> None:
        with pytest.raises(ConfigError, match="no remind_after_minutes"):
            policy(events=frozenset({"reminder"}))
        with pytest.raises(ConfigError, match="events has no 'reminder'"):
            policy(remind_after_minutes=30)
        with pytest.raises(ConfigError, match="at least 1"):
            policy(events=frozenset({"reminder"}), remind_after_minutes=0)

    def test_unknown_events_links_and_quiet_hours_are_refused(self) -> None:
        with pytest.raises(ConfigError, match="unknown event 'sms'"):
            policy(events=frozenset({"sms"}))
        with pytest.raises(ConfigError, match="only the placeholders"):
            policy(link="https://inbox.example/{sender}")
        with pytest.raises(ConfigError, match="time such as"):
            QuietHours("25:00", "07:00")
        with pytest.raises(ConfigError, match="same time"):
            QuietHours("07:00", "07:00")

    def test_quiet_hours_may_run_past_midnight(self) -> None:
        night = QuietHours("22:00", "07:00")
        assert night.contains(23, 30)
        assert night.contains(6, 59)
        assert not night.contains(7, 0)
        assert not night.contains(12, 0)
        lunch = QuietHours("12:00", "13:00")
        assert lunch.contains(12, 30)
        assert not lunch.contains(13, 0)

    def test_it_loads_from_a_file(self) -> None:
        loaded = ClientConfig.from_mapping(
            {
                "organisation": {"name": "Shop", "summary": "a made-up shop"},
                "triage": {
                    "confidence_threshold": 0.6,
                    "fallback_category": "other",
                    "languages": {"en": "English"},
                    "categories": [{"name": "other", "description": "anything"}],
                },
                "notifications": {
                    "urls": [URL, "${SECOND_URL}"],
                    "events": ["hand_off", "reminder"],
                    "remind_after_minutes": 45,
                    "quiet_hours": {"start": "21:00", "end": "08:00"},
                    "link": "https://inbox.example/threads/{thread_key}",
                },
            }
        )
        assert loaded.notifications.events == frozenset({"hand_off", "reminder"})
        assert loaded.notifications.quiet_hours == QuietHours("21:00", "08:00")
        assert loaded.notifications.variables == ("NOTIFY_HOST", "SECOND_URL")

    def test_a_section_with_no_urls_or_an_unknown_key_is_refused(self) -> None:
        base: dict[str, Any] = {
            "organisation": {"name": "Shop", "summary": "a made-up shop"},
            "triage": {
                "confidence_threshold": 0.6,
                "fallback_category": "other",
                "languages": {"en": "English"},
                "categories": [{"name": "other", "description": "anything"}],
            },
        }
        with pytest.raises(ConfigError, match="needs at least one url"):
            ClientConfig.from_mapping({**base, "notifications": {"events": ["hand_off"]}})
        with pytest.raises(ConfigError, match="unknown key 'url'"):
            ClientConfig.from_mapping({**base, "notifications": {"urls": [URL], "url": URL}})


class TestThePipelineNotifies:
    def test_a_hand_off_is_notified_after_it_is_finished(self) -> None:
        w = wired(classifier=FakeClassifier(default=signals("booking")))
        record = w.pipeline.process(visitor(thread="77"))
        assert record.decision == "handed_off"
        assert record.notifications == ("hand_off:sent",)
        title, body = w.transport.sent[0]
        assert title == "Example Bike Workshop: a conversation was handed to a person"
        assert body.splitlines()[:4] == [
            "Event: hand_off",
            "Category: booking",
            "Tier: needs_admin",
            "Reason: category booking is handled by a person",
        ]

    def test_a_held_draft_is_notified(self) -> None:
        w = wired(client(mode="draft"))
        record = w.pipeline.process(visitor("What are your opening hours?"))
        assert (record.decision, record.notifications) == ("answer_held", ("draft_held:sent",))
        title, body = w.transport.sent[0]
        assert title == "Example Bike Workshop: a drafted reply is waiting for approval"
        assert "Reason: draft mode" in body

    def test_an_answer_sent_is_not_notified(self) -> None:
        w = wired()
        record = w.pipeline.process(visitor("What are your opening hours?"))
        assert record.decision == "answered"
        assert (record.notifications, w.transport.sent) == ((), [])

    def test_only_the_chosen_events_are_notified(self) -> None:
        w = wired(client(mode="draft", events=frozenset({"hand_off"})))
        record = w.pipeline.process(visitor("What are your opening hours?"))
        assert record.decision == "answer_held"
        assert (record.notifications, w.transport.sent) == ((), [])

    def test_the_link_comes_from_the_template(self) -> None:
        w = wired(
            client(link="https://inbox.example/{channel}/{thread_key}?c={conversation_id}"),
            classifier=FakeClassifier(default=signals("booking")),
        )
        record = w.pipeline.process(visitor(thread="77"))
        _, body = w.transport.sent[0]
        assert f"Open: https://inbox.example/web/77?c={record.conversation_id}" in body

    def test_a_failed_notification_changes_nothing_but_the_audit(self) -> None:
        ok = wired(classifier=FakeClassifier(default=signals("booking")))
        failing = wired(fail=True, classifier=FakeClassifier(default=signals("booking")))
        good = ok.pipeline.process(visitor())
        bad = failing.pipeline.process(visitor())
        assert bad.decision == good.decision == "handed_off"
        assert bad.delivery == good.delivery == "sent"
        assert [r.text for r in failing.sink.sent] == [r.text for r in ok.sink.sent]
        assert failing.store.get_conversation(bad.conversation_id or 0).status == "paused_handoff"  # type: ignore[union-attr]
        assert bad.handoff_failures == ("notification",)
        assert bad.notifications == ("hand_off:failed",)
        # Handled: a retry is a duplicate, not a second hand-off.
        assert failing.pipeline.process(visitor()).decision == "duplicate"

    def test_a_failed_draft_notification_leaves_the_draft_held(self) -> None:
        w = wired(client(mode="draft"), fail=True)
        record = w.pipeline.process(visitor("What are your opening hours?"))
        assert (record.decision, record.delivery) == ("answer_held", "held")
        assert record.handoff_failures == ("notification",)
        assert len(w.sink.held) == 1

    def test_quiet_hours_hold_notifications_back(self) -> None:
        quiet = QuietHours("22:00", "07:00")
        w = wired(
            client(quiet_hours=quiet),
            clock=Clock(NIGHT),
            classifier=FakeClassifier(default=signals("booking")),
        )
        record = w.pipeline.process(visitor())
        assert record.notifications == ("hand_off:quiet",)
        assert w.transport.sent == []

    def test_no_notifications_without_the_section(self) -> None:
        config = dataclasses.replace(client(), notifications=NotificationPolicy())
        assert build_notifications(config) is None


class TestNoCustomerDataLeaves:
    """The notification has no field that could carry what the visitor wrote or who they are."""

    @pytest.mark.parametrize(
        ("category", "mode"),
        [("booking", "auto"), ("refund", "auto"), ("faq", "draft"), ("faq", "off")],
    )
    def test_through_the_pipeline_on_every_notified_path(self, category: str, mode: str) -> None:
        w = wired(client(mode=mode), classifier=FakeClassifier(default=signals(category)))
        record = w.pipeline.process(visitor())
        assert record.notifications, record
        assert_no_customer_data(json.dumps(w.transport.sent))

    def test_classifier_unavailable_and_guards(self) -> None:
        w = wired(classifier=FakeClassifier())
        w.pipeline.process(visitor())
        w.pipeline.process(visitor("x" * 20000, message_id="m-2", thread="78"))
        assert len(w.transport.sent) == 2
        assert_no_customer_data(json.dumps(w.transport.sent))


class Endpoint:
    """A JSON endpoint on 127.0.0.1 that keeps every request body it receives."""

    def __init__(self) -> None:
        self.bodies: list[bytes] = []
        self.status = 200
        received = self.bodies
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                received.append(self.rfile.read(length))
                self.send_response(outer.status)
                self.end_headers()

            def log_message(self, *args: object) -> None:
                return

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def host(self) -> str:
        return f"127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def endpoint() -> Iterator[Endpoint]:
    server = Endpoint()
    yield server
    server.close()


RECEIVED: list[dict[str, Any]] = []


def _register_test_scheme() -> None:
    from apprise.decorators import notify

    @notify(on="inboxcoretest")  # type: ignore[untyped-decorator,no-untyped-call]
    def record(body: str, title: str, notify_type: str, *args: Any, **kwargs: Any) -> bool:
        meta = kwargs.get("meta") or {}
        RECEIVED.append({"title": title, "body": body, "url": meta.get("url", "")})
        return "fail" not in str(meta.get("host", ""))


_register_test_scheme()


class TestApprise:
    def test_a_hand_off_reaches_a_local_json_endpoint_with_no_customer_data(
        self, endpoint: Endpoint
    ) -> None:
        config = client()
        transport = AppriseTransport.from_policy(
            config.notifications, {"NOTIFY_HOST": endpoint.host}
        )
        notifications = Notifications(config, transport, clock=Clock(NOON))
        pipeline = Pipeline(
            config=config,
            classifier=FakeClassifier(default=signals("booking")),
            handlers=HandlerRegistry({}),
            sink=RecordingSink(),
            store=InMemoryConversationStore(),
            notifier=RecordingNotifier(),
            audit=InMemoryAuditSink(),
            notifications=notifications,
        )
        record = pipeline.process(visitor())
        assert record.notifications == ("hand_off:sent",)
        assert len(endpoint.bodies) == 1
        raw = endpoint.bodies[0].decode()
        sent = json.loads(raw)
        assert sent["title"] == "Example Bike Workshop: a conversation was handed to a person"
        assert "Event: hand_off" in sent["message"]
        assert_no_customer_data(raw)

    def test_an_endpoint_that_fails_is_a_recorded_failure(self, endpoint: Endpoint) -> None:
        endpoint.status = 500
        config = client()
        transport = AppriseTransport.from_policy(
            config.notifications, {"NOTIFY_HOST": endpoint.host}
        )
        with pytest.raises(NotificationFailedError):
            transport.notify_staff("t", "b")
        pipeline = Pipeline(
            config=config,
            classifier=FakeClassifier(default=signals("booking")),
            handlers=HandlerRegistry({}),
            sink=RecordingSink(),
            store=InMemoryConversationStore(),
            notifier=RecordingNotifier(),
            audit=InMemoryAuditSink(),
            notifications=Notifications(config, transport, clock=Clock(NOON)),
        )
        record = pipeline.process(visitor())
        assert (record.decision, record.handoff_failures) == ("handed_off", ("notification",))

    def test_every_url_is_notified_through_apprise_itself(self) -> None:
        RECEIVED.clear()
        config = client(urls=("inboxcoretest://${FIRST}/", "inboxcoretest://${SECOND}/"))
        transport = AppriseTransport.from_policy(
            config.notifications, {"FIRST": "one", "SECOND": "two"}
        )
        Notifications(config, transport, clock=Clock(NOON)).notify(
            "draft_held",
            channel="web",
            thread_key="9",
            conversation_id=3,
            category="faq",
            tier="auto_answer",
            reason="delivery mode is draft",
        )
        assert len(RECEIVED) == 2
        assert all("Event: draft_held" in item["body"] for item in RECEIVED)

    def test_one_failing_url_fails_the_send(self) -> None:
        config = client(urls=("inboxcoretest://${FIRST}/", "inboxcoretest://${SECOND}/"))
        transport = AppriseTransport.from_policy(
            config.notifications, {"FIRST": "ok", "SECOND": "fail"}
        )
        with pytest.raises(NotificationFailedError):
            transport.notify_staff("t", "b")

    def test_a_missing_variable_is_named_and_no_value_is_shown(self) -> None:
        config = client(urls=("json://${NOTIFY_HOST}/${NOTIFY_TOKEN}",))
        with pytest.raises(ConfigError) as caught:
            build_notifications(config, env={"NOTIFY_HOST": "127.0.0.1:9"})
        assert "NOTIFY_TOKEN is not set" in str(caught.value)
        assert "127.0.0.1" not in str(caught.value)

    def test_a_url_apprise_does_not_accept_is_refused_by_position(self) -> None:
        config = client(urls=("nosuchscheme://${TOKEN}/",))
        with pytest.raises(ConfigError) as caught:
            build_notifications(config, env={"TOKEN": "s3cr3t-value"})
        assert "notifications.urls[0] is not a URL Apprise accepts" in str(caught.value)
        assert "s3cr3t-value" not in str(caught.value)

    def test_the_transport_never_shows_its_urls(self) -> None:
        config = client(urls=("inboxcoretest://${FIRST}/",))
        transport = AppriseTransport.from_policy(config.notifications, {"FIRST": "s3cr3t"})
        assert "s3cr3t" not in repr(transport)

    def test_build_notifications_uses_apprise_from_the_environment(
        self, endpoint: Endpoint
    ) -> None:
        built = build_notifications(client(), env={"NOTIFY_HOST": endpoint.host})
        assert built is not None
        built.notify(
            "hand_off",
            channel="web",
            thread_key="1",
            conversation_id=1,
            category="booking",
            tier="needs_admin",
            reason="x",
        )
        assert len(endpoint.bodies) == 1


class TestReminders:
    def config(self, **values: Any) -> ClientConfig:
        return client(
            mode=values.pop("mode", "auto"),
            events=frozenset({"hand_off", "draft_held", "reminder"}),
            remind_after_minutes=30,
            **values,
        )

    def test_a_hand_off_still_waiting_is_reminded_once(self) -> None:
        clock = Clock(NOON)
        w = wired(self.config(), clock=clock, classifier=FakeClassifier(default=signals("booking")))
        w.pipeline.process(visitor())
        w.transport.sent.clear()
        clock.now += timedelta(minutes=10)
        assert run_reminders(w.store, w.notifications, w.config, now=clock.now).sent == 0
        clock.now += timedelta(minutes=25)
        report = run_reminders(w.store, w.notifications, w.config, now=clock.now)
        assert report.sent == 1
        title, body = w.transport.sent[0]
        assert title == "Example Bike Workshop: still waiting for a person"
        assert "Waiting: a handed-off conversation" in body
        assert "Waiting for: 35 minutes" in body
        assert "Category: booking" in body
        assert "Tier: needs_admin" in body
        again = run_reminders(w.store, w.notifications, w.config, now=clock.now)
        assert (again.sent, again.already_reminded) == (0, 1)
        assert_no_customer_data(json.dumps(w.transport.sent))

    def test_a_person_replying_ends_the_wait(self) -> None:
        clock = Clock(NOON)
        w = wired(self.config(), clock=clock, classifier=FakeClassifier(default=signals("booking")))
        record = w.pipeline.process(visitor())
        w.pipeline.person_replied("web", "77", make_sender_key(EMAIL), message_id="staff-1")
        clock.now += timedelta(hours=2)
        assert run_reminders(w.store, w.notifications, w.config, now=clock.now).sent == 0
        assert record.decision == "handed_off"

    def test_a_held_draft_still_waiting_is_reminded_and_a_resolved_one_is_not(self) -> None:
        clock = Clock(NOON)
        w = wired(self.config(mode="draft"), clock=clock)
        w.pipeline.process(visitor("What are your opening hours?", thread="1", message_id="a"))
        w.pipeline.process(visitor("What are your opening hours?", thread="2", message_id="b"))
        drafts = w.pipeline.drafts
        resolved = drafts.pending(w.store.find_conversation("web", "2").id)[0]  # type: ignore[union-attr]
        drafts.discard(resolved.id, reviewer="test:1")
        w.transport.sent.clear()
        clock.now += timedelta(minutes=31)
        report = run_reminders(w.store, w.notifications, w.config, now=clock.now)
        assert report.sent == 1
        _, body = w.transport.sent[0]
        assert "Waiting: a drafted reply to approve" in body
        assert "Category: faq" in body
        assert "Reason: draft mode" in body

    def test_quiet_hours_claim_nothing_and_the_next_run_sends(self) -> None:
        clock = Clock(datetime(2026, 6, 2, 20, 0, tzinfo=UTC))  # 21:00 London
        config = self.config(quiet_hours=QuietHours("22:00", "07:00"))
        w = wired(config, clock=clock, classifier=FakeClassifier(default=signals("booking")))
        w.pipeline.process(visitor())
        w.transport.sent.clear()
        clock.now += timedelta(hours=2)  # 23:00 London, quiet
        assert run_reminders(w.store, w.notifications, w.config, now=clock.now).quiet == 1
        assert w.transport.sent == []
        clock.now += timedelta(hours=8)  # 07:00 London
        assert run_reminders(w.store, w.notifications, w.config, now=clock.now).sent == 1

    def test_a_failed_reminder_is_tried_again(self) -> None:
        clock = Clock(NOON)
        w = wired(self.config(), clock=clock, classifier=FakeClassifier(default=signals("booking")))
        w.pipeline.process(visitor())
        clock.now += timedelta(hours=1)
        w.transport.fail = True
        assert run_reminders(w.store, w.notifications, w.config, now=clock.now).failed == 1
        w.transport.fail = False
        assert run_reminders(w.store, w.notifications, w.config, now=clock.now).sent == 1

    def test_nothing_happens_without_the_reminder_event(self) -> None:
        clock = Clock(NOON)
        w = wired(clock=clock, classifier=FakeClassifier(default=signals("booking")))
        w.pipeline.process(visitor())
        clock.now += timedelta(days=1)
        assert run_reminders(w.store, w.notifications, w.config, now=clock.now).to_dict() == {
            "sent": 0,
            "quiet": 0,
            "failed": 0,
            "already_reminded": 0,
        }

    def test_two_runners_on_one_database_send_once(self, tmp_path: Path) -> None:
        from sqlalchemy import create_engine

        from inbox_core.store.sqlalchemy import SqlAlchemyConversationStore, create_schema

        clock = Clock(NOON)
        engine = create_engine(f"sqlite:///{tmp_path / 'r.db'}")
        create_schema(engine)
        store = SqlAlchemyConversationStore(engine, clock=clock)
        try:
            config = self.config()
            transport = RecordingTransport()
            notifications = Notifications(config, transport, clock=clock)
            Pipeline(
                config=config,
                classifier=FakeClassifier(default=signals("booking")),
                handlers=HandlerRegistry({}),
                sink=RecordingSink(),
                store=store,
                notifier=RecordingNotifier(),
                audit=InMemoryAuditSink(),
                notifications=notifications,
                clock=clock,
            ).process(visitor())
            transport.sent.clear()
            clock.now += timedelta(hours=1)
            other = SqlAlchemyConversationStore(engine, clock=clock)
            first = run_reminders(store, notifications, config, now=clock.now)
            second = run_reminders(other, notifications, config, now=clock.now)
            assert (first.sent, second.sent, second.already_reminded) == (1, 0, 1)
            assert len(transport.sent) == 1
        finally:
            store.close()


def test_without_apprise_the_extra_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "apprise", None)
    with pytest.raises(ImportError, match=r"inbox-core\[notify\]"):
        build_notifications(client(), env={"NOTIFY_HOST": "127.0.0.1:9"})


class TestTheReminderCommand:
    def write_config(self, tmp_path: Path, events: str) -> Path:
        from inbox_core.examples.demo import EXAMPLE_DIR

        text = (EXAMPLE_DIR / "client.toml").read_text(encoding="utf-8")
        text += (
            '\n[notifications]\nurls = ["inboxcoretest://${CLI_NOTIFY}/"]\n'
            f"events = {events}\n"
            "link = 'https://mail.example/threads/{thread_key}'\n"
        )
        if "reminder" in events:
            text += "remind_after_minutes = 15\n"
        path = tmp_path / "client.toml"
        path.write_text(text)
        return path

    def test_it_runs_once_and_prints_counts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from sqlalchemy import create_engine

        from inbox_core.notify import main
        from inbox_core.store.sqlalchemy import SqlAlchemyConversationStore, create_schema

        RECEIVED.clear()
        url = f"sqlite:///{tmp_path / 'cli.db'}"
        engine = create_engine(url)
        create_schema(engine)
        earlier = datetime.now(UTC) - timedelta(hours=1)
        store = SqlAlchemyConversationStore(engine, clock=lambda: earlier)
        conversation = store.conversation_for("email", "thread-abc", "sender")
        store.pause(conversation.id, "needs_admin: the sender asked for a person")
        engine.dispose()
        config = self.write_config(tmp_path, '["hand_off", "reminder"]')
        args = ["--config", str(config), "--database-url", url]
        assert main(args, env={"CLI_NOTIFY": "staff"}) == 0
        assert json.loads(capsys.readouterr().out)["sent"] == 1
        assert "Open: https://mail.example/threads/thread-abc" in RECEIVED[0]["body"]

    def test_it_refuses_a_config_without_reminders(self, tmp_path: Path) -> None:
        from inbox_core.notify import main

        config = self.write_config(tmp_path, '["hand_off"]')
        with pytest.raises(SystemExit):
            main(["--config", str(config), "--database-url", "sqlite://"], env={"CLI_NOTIFY": "x"})

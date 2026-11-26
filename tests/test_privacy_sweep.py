"""The packaged privacy sweep: it passes on the core's own wiring and catches every kind of leak."""

from __future__ import annotations

import dataclasses
import logging
import secrets
from collections.abc import Iterator
from typing import Any

import pytest

from inbox_core.config import NotificationPolicy
from inbox_core.crypto import FieldCipher
from inbox_core.handlers import (
    ExtractiveGenerator,
    GroundedAnswer,
    HandlerRegistry,
    HandlerRequest,
    HandlerResult,
)
from inbox_core.knowledge import InMemoryRetriever, KnowledgeEntry
from inbox_core.messages import IncomingMessage
from inbox_core.notify import Notifications, RecordingTransport
from inbox_core.pipeline import AuditSink, Notifier, Pipeline
from inbox_core.store.memory import InMemoryConversationStore
from inbox_core.testing.fakes import FakeClassifier, RecordingSink, signals
from inbox_core.testing.privacy import PrivacyLeak, forbidden_strings, run_privacy_sweep
from inbox_core.triage import TriageUnavailable
from tests.helpers import message
from tests.test_pipeline import config

QUESTION_ID_TEXT = "What are your opening hours on Saturday morning?"
ENTRIES = (
    KnowledgeEntry("KB-01", "Opening hours", "We are open Tuesday to Saturday, 9am to 6pm."),
)

CORPUS = (
    message(
        "What are your opening hours on Saturday morning?",
        message_id="faq",
        subject="Saturday opening hours",
        address="ana.lopez@example.com",
        thread="a",
    ),
    message(
        "Quiero que me devuelvan el dinero de la reparacion",
        message_id="refund",
        address="beto@example.org",
        thread="b",
    ),
    message(
        "Weekly digest from a mailing list you joined",
        message_id="auto",
        address="digest@lists.example",
        thread="c",
    ),
    message("   ", message_id="empty", address="blank@example.com", thread="d"),
    message(
        "Is it possible to bring my cargo bike for a full service soon?",
        message_id="down",
        address="carla@example.net",
        thread="e",
    ),
    message(
        "My son crashed and the brakes you fitted failed on the hill",
        message_id="crash",
        address="dev@example.com",
        thread="f",
    ),
)

CLASSIFIER = FakeClassifier(
    by_message={
        "faq": signals("faq"),
        "refund": signals("refund", language="es", money=True),
        "auto": signals("automated"),
        "crash": signals("faq"),
    },
)


class Leaky:
    """A handler that writes the message where it must not, in one chosen way."""

    name = "leaky"

    def __init__(self, how: str) -> None:
        self.how = how

    def handle(self, request: HandlerRequest) -> HandlerResult:
        text = request.message.text
        if self.how == "log":
            logging.getLogger("inbox_core.handlers").info("answering: %s", text)
        if self.how == "client_log":
            logging.getLogger("client_app.inbox").warning("got %s", text)
        if self.how == "reason":
            return HandlerResult.hand_off(self.name, text[:100])
        if self.how == "traceback":
            try:
                raise ValueError(text)
            except ValueError:
                logging.getLogger("inbox_core.handlers").exception("handler failed")
        if self.how == "address":
            logging.getLogger("inbox_core.handlers").info("for %s", request.message.sender_address)
        raise RuntimeError(text)


def builder(
    handlers: HandlerRegistry | None = None, notify: RecordingTransport | None = None
) -> Any:
    def build(notifier: Notifier, audit: AuditSink) -> Pipeline:
        client = config("auto")
        if notify is not None:
            client = dataclasses.replace(
                client, notifications=NotificationPolicy(urls=("json://${NOTIFY_HOST}/",))
            )
        return Pipeline(
            config=client,
            notifications=Notifications(client, notify) if notify is not None else None,
            classifier=FakeClassifier(by_message=dict(CLASSIFIER.by_message)),
            handlers=handlers
            or HandlerRegistry(
                {
                    "faq": GroundedAnswer(
                        InMemoryRetriever(ENTRIES), ExtractiveGenerator(), min_score=0.5
                    )
                }
            ),
            sink=RecordingSink(),
            store=InMemoryConversationStore(
                cipher=FieldCipher({"k1": secrets.token_bytes(32)}, "k1")
            ),
            notifier=notifier,
            audit=audit,
            sleep=lambda _: None,
        )

    return build


@pytest.fixture
def client_logger() -> Iterator[logging.Logger]:
    logger = logging.getLogger("client_app.inbox")
    logger.propagate = False
    yield logger
    logger.propagate = True


class TestTheCoreIsClean:
    def test_the_whole_corpus_runs_and_nothing_is_written_down(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        report = run_privacy_sweep(builder(), CORPUS, caplog)
        assert report.processed == len(CORPUS)
        assert report.log_records > 0
        assert report.checked_phrases >= len(CORPUS)
        # The corpus exercises the answer, hand-off, skip, drop and
        # classifier-down paths, so the sweep is not only over the happy path.
        assert report.decisions["answered"] >= 1
        assert report.decisions["handed_off"] >= 3
        assert report.decisions["skipped"] == 1
        assert report.decisions["dropped"] == 1

    def test_notifications_leak_nothing(self, caplog: pytest.LogCaptureFixture) -> None:
        transport = RecordingTransport()
        report = run_privacy_sweep(
            builder(notify=transport), CORPUS, caplog, notifications=transport
        )
        assert report.decisions["handed_off"] >= 3
        assert len(transport.sent) >= 3
        assert "notifications" in report.places

    def test_a_crashing_handler_with_content_in_its_exception_still_leaks_nothing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        handlers = HandlerRegistry({"faq": Leaky("raise")})
        report = run_privacy_sweep(builder(handlers), CORPUS, caplog)
        assert report.decisions["handed_off"] >= 4


class TestTheSweepCatchesLeaks:
    def test_a_logged_message_body(self, caplog: pytest.LogCaptureFixture) -> None:
        with pytest.raises(PrivacyLeak, match="log records"):
            run_privacy_sweep(builder(HandlerRegistry({"faq": Leaky("log")})), CORPUS, caplog)

    def test_a_logged_address(self, caplog: pytest.LogCaptureFixture) -> None:
        with pytest.raises(PrivacyLeak, match=r"example\.com"):
            run_privacy_sweep(builder(HandlerRegistry({"faq": Leaky("address")})), CORPUS, caplog)

    def test_content_inside_a_logged_traceback(self, caplog: pytest.LogCaptureFixture) -> None:
        handlers = HandlerRegistry({"faq": Leaky("traceback")})
        with pytest.raises(PrivacyLeak, match="log records"):
            run_privacy_sweep(builder(handlers), CORPUS, caplog)

    def test_a_non_propagating_client_logger(
        self, caplog: pytest.LogCaptureFixture, client_logger: logging.Logger
    ) -> None:
        handlers = HandlerRegistry({"faq": Leaky("client_log")})
        with pytest.raises(PrivacyLeak, match="log records"):
            run_privacy_sweep(builder(handlers), CORPUS, caplog, logger_names=("client_app.inbox",))

    def test_content_in_a_reason_reaches_the_notifier_and_audit(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with pytest.raises(PrivacyLeak) as caught:
            run_privacy_sweep(builder(HandlerRegistry({"faq": Leaky("reason")})), CORPUS, caplog)
        assert "notifier payloads" in str(caught.value)
        assert "audit records" in str(caught.value)

    def test_content_in_a_reason_reaches_a_notification(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        transport = RecordingTransport()
        with pytest.raises(PrivacyLeak) as caught:
            run_privacy_sweep(
                builder(HandlerRegistry({"faq": Leaky("reason")}), transport),
                CORPUS,
                caplog,
                notifications=transport,
            )
        assert "notifications:" in str(caught.value)

    def test_an_exception_that_escapes(self, caplog: pytest.LogCaptureFixture) -> None:
        class Escaping(Pipeline):
            def process(self, message: IncomingMessage) -> Any:
                result = super().process(message)
                if message.provider_message_id == "down":
                    raise RuntimeError(message.text)
                return result

        def build(notifier: Notifier, audit: AuditSink) -> Pipeline:
            built: Pipeline = builder()(notifier, audit)
            built.__class__ = Escaping
            return built

        with pytest.raises(PrivacyLeak, match="exceptions"):
            run_privacy_sweep(build, CORPUS, caplog)

    def test_extra_forbidden_strings(self, caplog: pytest.LogCaptureFixture) -> None:
        with pytest.raises(PrivacyLeak, match="msg-"):
            run_privacy_sweep(
                builder(), (message(QUESTION_ID_TEXT),), caplog, extra_forbidden=("msg-1",)
            )


class TestTheSweepRefusesToProveNothing:
    def test_silence_is_not_a_pass(self, caplog: pytest.LogCaptureFixture) -> None:
        class Silent:
            def process(self, message: IncomingMessage) -> Any:
                return None

        with pytest.raises(PrivacyLeak, match="vacuous"):
            run_privacy_sweep(lambda n, a: Silent(), CORPUS, caplog)  # type: ignore[arg-type, return-value]

    def test_logging_without_auditing_is_not_a_pass(self, caplog: pytest.LogCaptureFixture) -> None:
        class LogsOnly:
            def process(self, message: IncomingMessage) -> Any:
                logging.getLogger("inbox_core.pipeline").info("id %s", message.provider_message_id)

        with pytest.raises(PrivacyLeak, match="no audit records"):
            run_privacy_sweep(lambda n, a: LogsOnly(), CORPUS, caplog)  # type: ignore[arg-type, return-value]

    def test_an_empty_corpus_is_refused(self, caplog: pytest.LogCaptureFixture) -> None:
        with pytest.raises(ValueError, match="empty"):
            run_privacy_sweep(builder(), (), caplog)


def test_forbidden_strings_are_addresses_subjects_and_long_lines() -> None:
    found = forbidden_strings(
        [
            message(
                "short\nThis line is definitely long enough to count",
                subject="Hi",
                address="x@example.com",
            ),
            message("tiny", subject="A subject long enough", address="x@example.com"),
            IncomingMessage(
                channel="web",
                thread_key="t",
                provider_message_id="p",
                sender_key="k",
                sender_address="",
                text="tiny",
            ),
        ]
    )
    assert found == [
        "x@example.com",
        "This line is definitely long enough to count",
        "A subject long enough",
    ]


def test_the_down_classifier_path_is_in_the_corpus() -> None:
    with pytest.raises(TriageUnavailable):
        CLASSIFIER.classify(CORPUS[4])


def test_the_pytest_plugin_fixture(privacy_sweep: Any) -> None:
    report = privacy_sweep(builder(), CORPUS)
    assert report.processed == len(CORPUS)

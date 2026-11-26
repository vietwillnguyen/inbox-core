"""The privacy sweep: prove that no message content reaches a log, an exception or a notifier.

Any client of the core can run this against its own corpus and its own wiring::

    from inbox_core.testing.privacy import run_privacy_sweep


    def test_nothing_from_a_message_is_written_down(caplog):
        report = run_privacy_sweep(build_my_pipeline, my_corpus, caplog, logger_names=("my_app",))
        assert report.processed == len(my_corpus)

``build`` receives a notifier and an audit sink to wire in, so the sweep sees
every escalation and every audit record. The sweep drives each message through
the pipeline, then fails if any forbidden string - each sender address, each
subject, and each line of each message's text long enough to be unambiguous -
appears in:

- a log record from the core's loggers or the ones named (message, arguments
  and any formatted traceback), captured with
  :func:`inbox_core.testing.logs.attached_caplog` so non-propagating loggers are
  not silently missed;
- the message or ``repr`` of any exception that escaped the pipeline;
- any notifier payload;
- any notification sent through ``notifications``, a
  :class:`inbox_core.notify.RecordingTransport` the caller wired into the
  pipeline's :class:`inbox_core.notify.Notifications` (optional);
- any audit record.

It also fails if nothing was logged or audited at all, because a sweep over
silence proves nothing.
"""

from __future__ import annotations

import json
import logging
import traceback
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field

from inbox_core.messages import IncomingMessage
from inbox_core.notify import RecordingTransport
from inbox_core.pipeline import AuditSink, InMemoryAuditSink, Notifier, Pipeline
from inbox_core.testing.fakes import RecordingNotifier
from inbox_core.testing.logs import CORE_LOGGERS, LogCapture, attached_caplog

__all__ = ["PrivacyLeak", "SweepReport", "forbidden_strings", "run_privacy_sweep"]

MIN_PHRASE = 20
"""Text lines shorter than this are not checked: "Hello" in a log proves nothing."""

MIN_SUBJECT = 10


class PrivacyLeak(AssertionError):  # noqa: N818 - reads as the finding it reports
    """Content from the corpus was found somewhere it must never be."""


@dataclass(frozen=True)
class SweepReport:
    """What the sweep drove and captured."""

    processed: int
    decisions: Counter[str]
    log_records: int
    checked_phrases: int
    escaped_exceptions: int = 0
    places: tuple[str, ...] = field(default=())


def forbidden_strings(
    corpus: Iterable[IncomingMessage], *, min_phrase: int = MIN_PHRASE
) -> list[str]:
    """The strings from ``corpus`` that must never be written down."""
    found: list[str] = []
    for message in corpus:
        if message.sender_address:
            found.append(message.sender_address)
        if len(message.subject.strip()) >= MIN_SUBJECT:
            found.append(message.subject.strip())
        found.extend(
            line.strip() for line in message.text.splitlines() if len(line.strip()) >= min_phrase
        )
    return sorted(set(found), key=found.index)


def _render(record: logging.LogRecord) -> str:
    parts = [record.getMessage(), repr(record.args)]
    if record.exc_info:
        parts.append("".join(traceback.format_exception(*record.exc_info)))
    if record.exc_text:
        parts.append(record.exc_text)
    return "\n".join(parts)


def run_privacy_sweep(
    build: Callable[[Notifier, AuditSink], Pipeline],
    corpus: Sequence[IncomingMessage],
    caplog: LogCapture,
    *,
    logger_names: Iterable[str] = (),
    extra_forbidden: Iterable[str] = (),
    min_phrase: int = MIN_PHRASE,
    notifications: RecordingTransport | None = None,
) -> SweepReport:
    """Drive ``corpus`` through a pipeline and fail on any leak. See the module docstring."""
    if not corpus:
        raise ValueError("the corpus is empty; a sweep over nothing proves nothing")
    notifier = RecordingNotifier()
    audit = InMemoryAuditSink()
    pipeline = build(notifier, audit)
    names = (*CORE_LOGGERS, *logger_names)
    escaped: list[BaseException] = []
    decisions: Counter[str] = Counter()

    already = len(caplog.records)
    with attached_caplog(caplog, *names):
        for message in corpus:
            try:
                decisions[pipeline.process(message).decision] += 1
            except Exception as exc:
                escaped.append(exc)
    records = list(caplog.records[already:])

    if not records:
        raise PrivacyLeak("no log records were captured; the sweep would be vacuous")
    if not audit.records:
        raise PrivacyLeak("no audit records were emitted; the sweep would be vacuous")

    places = {
        "log records": "\n".join(_render(record) for record in records),
        "exceptions": "\n".join(f"{exc}\n{exc!r}" for exc in escaped),
        "notifier payloads": "\n".join(
            json.dumps(asdict(item), sort_keys=True) + repr(item) for item in notifier.escalations
        ),
        "notifications": "\n".join(
            f"{title}\n{body}" for title, body in (notifications.sent if notifications else [])
        ),
        "audit records": "\n".join(
            json.dumps(record.to_dict(), sort_keys=True) + repr(record) for record in audit.records
        ),
    }
    forbidden = [*forbidden_strings(corpus, min_phrase=min_phrase), *extra_forbidden]
    leaks = [
        f"{place}: {phrase[:24]!r}..."
        for place, text in places.items()
        for phrase in forbidden
        if phrase and phrase in text
    ]
    if leaks:
        raise PrivacyLeak("message content was written down:\n  " + "\n  ".join(leaks))
    return SweepReport(
        processed=sum(decisions.values()),
        decisions=decisions,
        log_records=len(records),
        checked_phrases=len(forbidden),
        escaped_exceptions=len(escaped),
        places=tuple(places),
    )

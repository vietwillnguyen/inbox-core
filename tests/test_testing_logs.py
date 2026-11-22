"""``attached_caplog`` captures loggers that do not propagate, where plain caplog sees nothing."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from inbox_core.testing.logs import CORE_LOGGERS, attached_caplog


@pytest.fixture
def isolated_logger() -> Iterator[logging.Logger]:
    logger = logging.getLogger("client_app.inbox")
    logger.propagate = False
    yield logger
    logger.propagate = True


def test_plain_caplog_is_vacuous_for_a_logger_made_non_propagating_later(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The trap this helper exists for: the assertion a privacy test would make
    # ("this phrase is not in the log") passes because nothing was captured.
    # pytest 9 attaches caplog to loggers that are already non-propagating when
    # the test starts, but not to one configured afterwards - which is what a
    # logger factory that builds loggers on first use does.
    lazily_built = logging.getLogger("client_app.lazy")
    lazily_built.propagate = False
    try:
        with caplog.at_level(logging.DEBUG):
            lazily_built.warning("visible only to an attached handler")
    finally:
        lazily_built.propagate = True
    assert caplog.records == []
    assert "visible" not in caplog.text


def test_attached_caplog_captures_it(
    isolated_logger: logging.Logger, caplog: pytest.LogCaptureFixture
) -> None:
    with attached_caplog(caplog, "client_app.inbox"):
        isolated_logger.debug("message id=7 decided")
    assert [record.getMessage() for record in caplog.records] == ["message id=7 decided"]


def test_handlers_and_levels_are_restored(
    isolated_logger: logging.Logger, caplog: pytest.LogCaptureFixture
) -> None:
    isolated_logger.setLevel(logging.ERROR)
    with attached_caplog(caplog, "client_app.inbox", level="INFO"):
        assert caplog.handler in isolated_logger.handlers
        assert isolated_logger.level == logging.INFO
    assert caplog.handler not in isolated_logger.handlers
    assert isolated_logger.level == logging.ERROR


def test_defaults_to_every_core_logger(caplog: pytest.LogCaptureFixture) -> None:
    with attached_caplog(caplog):
        for name in CORE_LOGGERS:
            assert caplog.handler in logging.getLogger(name).handlers

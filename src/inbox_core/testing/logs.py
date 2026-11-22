"""Capturing log output from loggers that do not propagate.

Many applications set ``propagate = False`` on their loggers so a line is not
emitted once per ancestor. pytest's ``caplog`` installs its handler on the
root logger, so a test written as::

    with caplog.at_level("WARNING"):
        ...
    assert "something" not in caplog.text

can capture nothing from such a logger and, worse for a test whose job is to
prove that an address never reaches a log line, pass vacuously. Recent pytest
attaches its handler to loggers that are already non-propagating when a test
starts, but not to one that becomes non-propagating later, such as a logger a
factory builds on first use.

:func:`attached_caplog` hangs ``caplog``'s own handler directly on the named
loggers for the duration of the block, so ``caplog.records`` and
``caplog.text`` see everything they emit, propagating or not.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol

__all__ = ["CORE_LOGGERS", "LogCapture", "attached_caplog"]

CORE_LOGGERS: tuple[str, ...] = (
    "inbox_core",
    "inbox_core.pipeline",
    "inbox_core.delivery",
    "inbox_core.handlers",
    "inbox_core.guards",
    "inbox_core.shadow",
    "inbox_core.store",
)
"""Every logger the core writes through, named explicitly so the list is a decision."""


class LogCapture(Protocol):
    """The part of pytest's ``LogCaptureFixture`` this helper uses."""

    @property
    def handler(self) -> logging.Handler:
        """The capturing handler."""
        ...

    @property
    def records(self) -> list[logging.LogRecord]:
        """Every record captured so far in this test phase."""
        ...

    def set_level(self, level: int | str, logger: str | None = None) -> None:
        """Set the capture level."""
        ...


@contextmanager
def attached_caplog(
    caplog: LogCapture, *names: str, level: int | str = logging.DEBUG
) -> Iterator[None]:
    """Attach ``caplog``'s handler to ``names`` (default: :data:`CORE_LOGGERS`)."""
    targets = [logging.getLogger(name) for name in (names or CORE_LOGGERS)]
    previous = [(logger, logger.level) for logger in targets]
    numeric = logging.getLevelName(level) if isinstance(level, str) else level
    caplog.set_level(numeric)
    for logger in targets:
        logger.addHandler(caplog.handler)
        logger.setLevel(numeric)
    try:
        yield
    finally:
        for logger, original in previous:
            logger.removeHandler(caplog.handler)
            logger.setLevel(original)

"""Retention: delete stored content older than N days, keep the record of what happened.

The store deletes content when asked; this module is the asking. One run:

1. expires every held draft older than the cutoff, so nobody can send a
   reply to a message whose text is about to be deleted, and so it is counted
   as ``expired`` in the acceptance rate; then
2. erases the encrypted content of every message older than the cutoff,
   keeping its row, because dedupe, the send caps and the metrics read it.

Call :func:`run_retention` from your scheduler, or run it as a command
against a SQL store (needs ``inbox-core[sqlalchemy]``)::

    python -m inbox_core.retention --database-url sqlite:///inbox.db --days 30

It prints a JSON report of numbers only. Erasing needs no encryption key.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from inbox_core.store import ConversationStore, as_naive_utc

__all__ = ["RETENTION_REVIEWER", "RetentionReport", "main", "run_retention"]

logger = logging.getLogger("inbox_core.retention")

RETENTION_REVIEWER = "retention"
"""The reviewer recorded on drafts that retention expired."""


@dataclass(frozen=True)
class RetentionReport:
    """What one retention run did. ``cutoff`` is naive UTC in ISO format."""

    cutoff: str
    drafts_expired: int
    messages_erased: int

    def to_dict(self) -> dict[str, object]:
        """A JSON-ready dictionary."""
        return asdict(self)


def run_retention(
    store: ConversationStore,
    *,
    days: int,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RetentionReport:
    """Expire drafts and erase content older than ``days`` days."""
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise ValueError("days must be a whole number of at least 1")
    cutoff = as_naive_utc(clock()) - timedelta(days=days)
    expired = store.expire_held(cutoff, reviewer=RETENTION_REVIEWER)
    erased = store.erase_content_before(cutoff)
    logger.info("retention before %s: %d drafts expired, %d erased", cutoff, expired, erased)
    return RetentionReport(cutoff.isoformat(), expired, erased)


def _positive(value: str) -> int:
    try:
        days = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("days must be a whole number") from None
    if days < 1:
        raise argparse.ArgumentTypeError("days must be at least 1")
    return days


def main(argv: Sequence[str] | None = None) -> int:
    """Run retention once against a SQL store and print the report."""
    parser = argparse.ArgumentParser(
        prog="python -m inbox_core.retention",
        description="Delete stored message content older than N days, keeping the skeleton.",
    )
    parser.add_argument("--database-url", required=True, help="a SQLAlchemy database URL")
    parser.add_argument("--days", required=True, type=_positive, help="keep this many days")
    args = parser.parse_args(argv)

    from sqlalchemy import create_engine

    from inbox_core.store.sqlalchemy import SqlAlchemyConversationStore, create_schema

    engine = create_engine(args.database_url)
    try:
        create_schema(engine)
        report = run_retention(SqlAlchemyConversationStore(engine), days=args.days)
    finally:
        engine.dispose()
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())

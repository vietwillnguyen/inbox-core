"""Transcript retention for Chatwoot's own database, through Chatwoot's API.

Chatwoot Community Edition keeps every transcript forever: its scheduled jobs
(``config/schedule.yml`` at v4.19.1) resolve conversations but never delete
them. :func:`run_chatwoot_retention` deletes every conversation whose last
activity is older than N days, then every contact of those conversations that
has none left, so a visitor's name and email do not outlive their messages.

Chatwoot deletes a conversation in a background job (``DeleteObjectJob``),
so the job waits, for a bounded time, until each deletion has landed before it
looks at the contacts; a contact whose conversation is still there is kept and
counted as a failure, and the next run takes it.

Deleting conversations and contacts is for administrators only
(``app/policies/conversation_policy.rb``), so this runs with an administrator's
access token, never the bot's. The core's own store is a separate job
(:mod:`inbox_core.retention`); ``python -m inbox_core.chatwoot retention``
runs both. The report holds counts only.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from inbox_core.chatwoot.api import ChatwootApi, ChatwootError

__all__ = ["ChatwootRetentionReport", "run_chatwoot_retention"]

logger = logging.getLogger("inbox_core.chatwoot.retention")

MAX_PAGES = 1000


@dataclass(frozen=True)
class ChatwootRetentionReport:
    """What one run deleted, and what it could not."""

    cutoff: str
    conversations_deleted: int
    contacts_deleted: int
    failures: int

    def to_dict(self) -> dict[str, object]:
        """A JSON-ready dictionary."""
        return asdict(self)


def _still_there(admin: ChatwootApi, conversation_id: int) -> bool:
    try:
        admin.get_conversation(conversation_id)
    except ChatwootError as exc:
        if exc.status == 404:
            return False
        raise
    return True


def run_chatwoot_retention(
    admin: ChatwootApi,
    *,
    days: int,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], object] = time.sleep,
    wait_seconds: float = 60.0,
) -> ChatwootRetentionReport:
    """Delete conversations inactive for more than ``days`` days, and their orphaned contacts."""
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise ValueError("days must be a whole number of at least 1")
    cutoff = clock() - timedelta(days=days)
    old: list[int] = []
    contacts: set[int] = set()
    for page in range(1, MAX_PAGES + 1):
        listed = admin.list_conversations(page)
        if not listed:
            break
        for summary in listed:
            if summary.last_activity_at < cutoff:
                old.append(summary.id)
                if summary.contact_id is not None:
                    contacts.add(summary.contact_id)
    deleted = failures = 0
    accepted: list[int] = []
    for conversation_id in old:
        try:
            admin.delete_conversation(conversation_id)
            accepted.append(conversation_id)
        except ChatwootError as exc:
            failures += 1
            logger.warning("could not delete conversation %s: %s", conversation_id, exc.status)
    waited = 0.0
    while accepted:
        accepted = [c for c in accepted if _still_there(admin, c)]
        if not accepted or waited >= wait_seconds:
            break
        sleep(0.5)
        waited += 0.5
    deleted = len(old) - failures - len(accepted)
    failures += len(accepted)
    removed = 0
    for contact_id in sorted(contacts):
        try:
            if admin.contact_conversation_count(contact_id) == 0:
                admin.delete_contact(contact_id)
                removed += 1
        except ChatwootError as exc:
            failures += 1
            logger.warning("could not delete contact %s: %s", contact_id, exc.status)
    report = ChatwootRetentionReport(cutoff.isoformat(), deleted, removed, failures)
    logger.info("chatwoot retention: %s", report.to_dict())
    return report

"""Notifications: telling a person, outside the inbox, that they are needed.

A shared inbox such as Chatwoot tells its agents itself (assignment
notifications, automation rules; see ``docs/chatwoot.md``). A held draft, and
a client with no shared inbox (a mailbox, say), needs someone told another
way. This module is that, built on Apprise behind a one-method transport
(:mod:`inbox_core.adapters.apprise`, the ``notify`` extra), so the core keeps
no dependency on it.

Three events, chosen per client in ``[notifications]``
(:class:`inbox_core.config.NotificationPolicy`):

- ``hand_off``: a message was handed to a person.
- ``draft_held``: a reply was drafted and is held for a person to approve.
- ``reminder``: a hand-off or held draft is still waiting after
  ``remind_after_minutes`` (:func:`run_reminders`, run on a schedule).

A notification is built here, from fixed phrases, the category and tier names,
the pipeline's own reason (a fixed phrase, category names and numbers), a
count of minutes, the organisation's name and a link to the conversation. It
has no field for anything the sender wrote or who they are, so it cannot carry
their text, name, email address or phone number.

Notifying is best effort. In the pipeline it runs after the reply or hand-off
is finished, a failure is logged by exception type and recorded as
``notification`` in the audit record's ``handoff_failures``, and nothing about
the reply changes. Inside ``quiet_hours`` nothing is sent; the audit record
says ``quiet``, and a reminder (if configured) goes out once the quiet hours
end for anything still waiting.

``python -m inbox_core.notify --config client.toml --database-url URL`` runs
the reminders once against a SQL store and prints a report of counts; run it
from cron or a scheduler every few minutes. The Chatwoot service has its own
``python -m inbox_core.chatwoot remind``, which links to the conversation.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol, runtime_checkable

from inbox_core.config import ClientConfig, ConfigError, NotifyEvent, load_config
from inbox_core.store import Conversation, ConversationStore, as_naive_utc

__all__ = [
    "MAX_NOTIFIED_REASON",
    "LinkBuilder",
    "Notification",
    "NotificationTransport",
    "Notifications",
    "NotifyOutcome",
    "RecordingTransport",
    "ReminderReport",
    "build_notifications",
    "main",
    "resolve_urls",
    "run_reminders",
]

logger = logging.getLogger("inbox_core.notify")

NotifyOutcome = Literal["sent", "quiet", "off"]
"""What :meth:`Notifications.notify` did: sent it, held it for quiet hours, or not configured."""

LinkBuilder = Callable[[str, str, int | None], str]
"""``(channel, thread_key, conversation_id)`` to the URL a person opens."""

_PLACEHOLDER = re.compile(r"\$\{([A-Z][A-Z0-9_]{0,63})\}")

MAX_NOTIFIED_REASON = 120
"""Reasons are cut to this length, and to one line, before they are sent."""

_HEADLINES: dict[str, str] = {
    "hand_off": "a conversation was handed to a person",
    "draft_held": "a drafted reply is waiting for approval",
    "reminder": "still waiting for a person",
}


@dataclass(frozen=True)
class Notification:
    """One notification: fixed phrases, names from the config, numbers and a link."""

    event: NotifyEvent
    organisation: str
    category: str
    tier: str
    reason: str
    link: str
    waiting_minutes: int | None = None
    waiting_for: str = ""

    @property
    def title(self) -> str:
        """One line: who and what happened."""
        return f"{self.organisation}: {_HEADLINES[self.event]}"

    @property
    def body(self) -> str:
        """The event, category, tier, reason, how long it has waited, and the link."""
        lines = [f"Event: {self.event}"]
        if self.waiting_for:
            lines.append(f"Waiting: {self.waiting_for}")
        if self.waiting_minutes is not None:
            lines.append(f"Waiting for: {self.waiting_minutes} minutes")
        lines += [f"Category: {self.category}", f"Tier: {self.tier}"]
        if self.reason:
            lines.append(f"Reason: {self.reason}")
        if self.link:
            lines.append(f"Open: {self.link}")
        return "\n".join(lines)


@runtime_checkable
class NotificationTransport(Protocol):
    """Where notifications go. Raises if they could not be delivered."""

    def notify_staff(self, title: str, body: str) -> None:
        """Deliver one notification."""
        ...


@dataclass
class RecordingTransport:
    """A transport that records what it was given, or fails on demand. For tests."""

    sent: list[tuple[str, str]] = field(default_factory=list)
    fail: bool = False

    def notify_staff(self, title: str, body: str) -> None:
        """Record the notification, or raise ``ConnectionError`` when ``fail`` is set."""
        if self.fail:
            raise ConnectionError("notification transport unavailable")
        self.sent.append((title, body))


def _one_line(reason: str) -> str:
    flat = " ".join(reason.split())
    return flat[:MAX_NOTIFIED_REASON]


class Notifications:
    """Decides whether an event is notified, builds the notification and sends it.

    ``link`` turns a conversation into the URL a person opens; without one,
    the client's ``notifications.link`` template is used, and without that the
    notification has no link. ``clock`` is injectable for quiet-hours tests.
    """

    def __init__(
        self,
        config: ClientConfig,
        transport: NotificationTransport,
        *,
        link: LinkBuilder | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._config = config
        self._policy = config.notifications
        self._transport = transport
        self._link = link
        self._clock = clock

    def link_for(self, channel: str, thread_key: str, conversation_id: int | None) -> str:
        """The URL for this conversation, or an empty string."""
        if self._link is not None:
            return self._link(channel, thread_key, conversation_id)
        template = self._policy.link
        if not template:
            return ""
        return template.format(
            channel=channel,
            thread_key=thread_key,
            conversation_id="" if conversation_id is None else conversation_id,
        )

    def is_quiet(self) -> bool:
        """Whether it is inside the client's quiet hours now."""
        quiet = self._policy.quiet_hours
        if quiet is None:
            return False
        local = self._clock().astimezone(self._config.delivery.zone)
        return quiet.contains(local.hour, local.minute)

    def notify(
        self,
        event: NotifyEvent,
        *,
        channel: str,
        thread_key: str,
        conversation_id: int | None,
        category: str,
        tier: str,
        reason: str,
        waiting_minutes: int | None = None,
        waiting_for: str = "",
    ) -> NotifyOutcome:
        """Send one notification if ``event`` is configured and not quiet. Raises on failure."""
        if not self._policy.notifies(event):
            return "off"
        if self.is_quiet():
            return "quiet"
        notification = Notification(
            event=event,
            organisation=self._config.organisation.name,
            category=category,
            tier=tier,
            reason=_one_line(reason),
            link=self.link_for(channel, thread_key, conversation_id),
            waiting_minutes=waiting_minutes,
            waiting_for=waiting_for,
        )
        self._transport.notify_staff(notification.title, notification.body)
        return "sent"


def build_notifications(
    config: ClientConfig,
    *,
    env: Mapping[str, str] | None = None,
    link: LinkBuilder | None = None,
    transport: NotificationTransport | None = None,
) -> Notifications | None:
    """The client's notifier, or None when ``[notifications]`` names no URL.

    Without ``transport`` it is :class:`inbox_core.adapters.apprise.AppriseTransport`
    over the configured URLs, with every ``${VARIABLE}`` read from ``env``
    (the process environment by default). A variable that is not set is a
    :class:`inbox_core.config.ConfigError` naming the variable, never a value.
    """
    if not config.notifications.enabled:
        return None
    if transport is None:
        from inbox_core.adapters.apprise import AppriseTransport

        transport = AppriseTransport.from_policy(
            config.notifications, os.environ if env is None else env
        )
    return Notifications(config, transport, link=link)


@dataclass(frozen=True)
class ReminderReport:
    """What one :func:`run_reminders` run did. Counts only."""

    sent: int = 0
    quiet: int = 0
    failed: int = 0
    already_reminded: int = 0

    def to_dict(self) -> dict[str, int]:
        """A JSON-ready dictionary."""
        return {
            "sent": self.sent,
            "quiet": self.quiet,
            "failed": self.failed,
            "already_reminded": self.already_reminded,
        }


def _split_pause(reason: str | None) -> tuple[str, str]:
    tier, _, rest = (reason or "").partition(": ")
    if tier in ("needs_admin", "needs_executive", "auto_answer") and rest:
        return tier, rest
    return "needs_admin", reason or ""


def run_reminders(
    store: ConversationStore,
    notifications: Notifications,
    config: ClientConfig,
    *,
    now: datetime | None = None,
) -> ReminderReport:
    """Remind once about every hand-off and held draft waiting longer than configured.

    A hand-off is waiting while its conversation is still paused for a person
    (a person replying, or resuming the bot, ends it); a draft while it is
    still ``held``. Each is reminded about once: the store records the
    reminder (:meth:`inbox_core.store.ConversationStore.claim_reminder`)
    before it is sent, so two runs never both send it, and a failed send gives
    the claim back for the next run. Nothing is claimed inside quiet hours.
    Run it on a schedule, for example every few minutes.
    """
    policy = config.notifications
    if not policy.notifies("reminder") or policy.remind_after_minutes is None:
        return ReminderReport()
    if notifications.is_quiet():
        return ReminderReport(quiet=1)
    moment = as_naive_utc(now or datetime.now(UTC))
    cutoff = moment - timedelta(minutes=policy.remind_after_minutes)
    counts = {"sent": 0, "quiet": 0, "failed": 0, "already_reminded": 0}

    def remind(
        key: str,
        since: datetime,
        conversation: Conversation,
        *,
        category: str,
        tier: str,
        reason: str,
        waiting_for: str,
    ) -> None:
        if not store.claim_reminder(key):
            counts["already_reminded"] += 1
            return
        try:
            outcome = notifications.notify(
                "reminder",
                channel=conversation.channel,
                thread_key=conversation.thread_key,
                conversation_id=conversation.id,
                category=category,
                tier=tier,
                reason=reason,
                waiting_minutes=int((moment - since).total_seconds() // 60),
                waiting_for=waiting_for,
            )
        except Exception as exc:
            store.release_reminder(key)
            counts["failed"] += 1
            logger.warning("reminder %s failed: %s", key, type(exc).__name__)
            return
        if outcome != "sent":
            store.release_reminder(key)
            counts["quiet"] += 1
            return
        counts["sent"] += 1

    for draft in store.held_before(cutoff):
        conversation = store.get_conversation(draft.conversation_id)
        inbound = store.get_message(draft.reply_to_id) if draft.reply_to_id is not None else None
        if conversation is None:
            continue
        remind(
            f"draft:{draft.id}",
            draft.created_at,
            conversation,
            category=(inbound.category if inbound else None) or config.triage.fallback_category,
            tier=(inbound.tier if inbound else None) or "auto_answer",
            reason=draft.held_because or "",
            waiting_for="a drafted reply to approve",
        )
    for conversation in store.paused_before(cutoff):
        tier, reason = _split_pause(conversation.pause_reason)
        received = [m for m in store.messages_in(conversation.id) if m.direction == "inbound"]
        category = next((m.category for m in reversed(received) if m.category), None)
        remind(
            f"hand_off:{conversation.id}:{conversation.updated_at.isoformat()}",
            conversation.updated_at,
            conversation,
            category=category or config.triage.fallback_category,
            tier=tier,
            reason=reason,
            waiting_for="a handed-off conversation",
        )
    report = ReminderReport(**counts)
    logger.info("reminders: %s", report.to_dict())
    return report


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "")
    if not value.strip():
        raise ConfigError([f"{name} is not set; notifications.urls reads it"], "the environment")
    return value


def resolve_urls(urls: tuple[str, ...], env: Mapping[str, str]) -> tuple[str, ...]:
    """``urls`` with every ``${VARIABLE}`` replaced from ``env``. Used by the transports."""
    return tuple(_PLACEHOLDER.sub(lambda found: _require(env, found.group(1)), url) for url in urls)


def main(argv: Sequence[str] | None = None, *, env: Mapping[str, str] | None = None) -> int:
    """Run the reminders once against a SQL store and print the report."""
    parser = argparse.ArgumentParser(
        prog="python -m inbox_core.notify",
        description="Remind about hand-offs and held drafts still waiting for a person.",
    )
    parser.add_argument("--config", required=True, help="the client's configuration file")
    parser.add_argument("--database-url", required=True, help="a SQLAlchemy database URL")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    notifications = build_notifications(config, env=env)
    if notifications is None or not config.notifications.notifies("reminder"):
        parser.error("the configuration's [notifications] has no 'reminder' event")

    from sqlalchemy import create_engine

    from inbox_core.store.sqlalchemy import SqlAlchemyConversationStore, create_schema

    engine = create_engine(args.database_url)
    try:
        create_schema(engine)
        report = run_reminders(SqlAlchemyConversationStore(engine), notifications, config)
    finally:
        engine.dispose()
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())

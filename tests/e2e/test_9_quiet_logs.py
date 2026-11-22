"""Proof that visitor text reaches no container's log at the configured log level.

Known phrases go through every path a message can take (answered, handed
off, a staff reply, the service down), then every container's whole log is
searched for them. It runs last, so it also searches for what the rest of the
suite wrote.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from tests.e2e.stack import Agent, Visitor, compose, read_env, stack, unique, until

MODE = "auto"
pytestmark = pytest.mark.usefixtures("mode")

SERVICES = ("rails", "sidekiq", "postgres", "redis", "inbox-core", "widget-demo")
EARLIER = (
    "stopped working and the battery was burning hot",
    "reserve the hedge trimmer",
    "pressure washer this weekend",
    "complaint about how a volunteer spoke",
    "free on Saturday; I have put your name on it",
    "Wednesday evenings and Saturday mornings",
)


def every_log() -> dict[str, str]:
    return {name: compose("logs", "--no-color", name, timeout=180) for name in SERVICES}


def test_no_visitor_or_staff_text_in_any_container_log(
    visitor: Callable[[], Visitor], volunteer: Agent
) -> None:
    log_level = read_env("chatwoot.env")["LOG_LEVEL"]
    answered = unique("When does the library open on Saturday mornings?")
    handed = unique("A borrowed ladder broke and I hurt my wrist badly")
    staff = unique("So sorry, a volunteer will call you this afternoon")
    down = unique("Is anyone there to help with a sander rental")

    first = visitor()
    first.say(answered)
    until(first.replies, timeout=30)
    second = visitor()
    second.say(handed)
    until(second.replies, timeout=30)
    volunteer.reply(second.conversation_id or 0, staff)
    until(lambda: len(second.replies()) == 2, timeout=15)

    stack("stop-service")
    try:
        third = visitor()
        third.say(down)
        until(third.replies, timeout=60)
    finally:
        stack("start-service")

    secrets = read_env("secrets.env")
    logs = every_log()
    assert all(logs[name] for name in ("rails", "sidekiq", "inbox-core")), "a log was empty"
    found = {
        (name, phrase)
        for name, text in logs.items()
        for phrase in (answered, handed, staff, down, *EARLIER)
        if phrase.lower() in text.lower()
    }
    assert found == set(), f"message text in logs at LOG_LEVEL={log_level}: {sorted(found)}"
    # The service's own log never carries its webhook path token.
    token = secrets["INBOX_CORE_WEBHOOK_PATH_TOKEN"]
    assert token not in logs["inbox-core"]
    # Known residual, pinned so a Chatwoot upgrade that changes it is noticed:
    # when delivery to the bot fails, sidekiq logs the webhook URL, path token
    # included, at warn (lib/webhooks/trigger.rb, handle_failure). The
    # signature check still stands without it.
    assert token in logs["sidekiq"]

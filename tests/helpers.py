"""Shared builders for the test suite. Made-up data only."""

from __future__ import annotations

from typing import Any

from inbox_core.config import CategoryRule, ClientConfig, Organisation, TriagePolicy
from inbox_core.messages import IncomingMessage, make_sender_key

ADDRESS = "visitor@example.com"

OPEN_STORES: list[Any] = []
"""SQL stores a test built; tests/conftest.py closes them after each test."""


def track[T](store: T) -> T:
    """Close ``store`` (if it has ``close``) when the current test ends."""
    OPEN_STORES.append(store)
    return store


def bike_config(**triage: Any) -> ClientConfig:
    """A small made-up bicycle workshop with English and Spanish."""
    values: dict[str, Any] = {
        "categories": (
            CategoryRule("faq", "a general question about the workshop", auto_answer=True),
            CategoryRule("booking", "the sender wants to book or change a repair slot"),
            CategoryRule("refund", "the sender wants money back", escalates_to="needs_executive"),
            CategoryRule("other", "a person writing about anything else"),
            CategoryRule("automated", "not written by a person", escalates_to="skip"),
        ),
        "languages": {"en": "English", "es": "Spanish"},
        "confidence_threshold": 0.6,
        "fallback_category": "other",
    }
    values.update(triage)
    return ClientConfig(
        organisation=Organisation(
            name="Example Bike Workshop", summary="a made-up bicycle repair workshop"
        ),
        triage=TriagePolicy(**values),
    )


def message(
    text: str = "What time do you open on Saturday?",
    *,
    message_id: str = "msg-1",
    thread: str = "conv-1",
    channel: str = "web",
    subject: str = "",
    address: str = ADDRESS,
) -> IncomingMessage:
    return IncomingMessage(
        channel=channel,
        thread_key=thread,
        provider_message_id=message_id,
        sender_key=make_sender_key(address),
        sender_address=address,
        text=text,
        subject=subject,
    )

"""Fixtures for the Chatwoot connection: a fake Chatwoot and the real service over it."""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from inbox_core.chatwoot.app import ServiceParts, build_service
from inbox_core.chatwoot.service import create_app
from inbox_core.chatwoot.settings import ChatwootSettings
from inbox_core.chatwoot.webhook import signature_for
from inbox_core.crypto import generate_key_entry
from inbox_core.pipeline import InMemoryAuditSink
from tests.chatwoot.fake import ACCOUNT, BOT_TOKEN, FakeChatwoot
from tests.helpers import track

CHATWOOT_ORIGIN = "http://127.0.0.1:3910"
PUBLIC_ORIGIN = "http://127.0.0.1:3912"
BOT_SECRET = "example-bot-secret"
PATH_TOKEN = "p" * 32
TAB_SECRET = "t" * 40


def settings(tmp_path: Path, **changes: Any) -> ChatwootSettings:
    values: dict[str, Any] = {
        "chatwoot_url": "http://chatwoot.test",
        "chatwoot_origin": CHATWOOT_ORIGIN,
        "public_origin": PUBLIC_ORIGIN,
        "account_id": ACCOUNT,
        "bot_token": BOT_TOKEN,
        "bot_secret": BOT_SECRET,
        "webhook_path_token": PATH_TOKEN,
        "tab_secret": TAB_SECRET,
        "database_url": f"sqlite:///{tmp_path / 'service.db'}",
        "encryption_keys": generate_key_entry("k1"),
        "assignee_id": 5,
    }
    values.update(changes)
    return ChatwootSettings(**values)


class Clock:
    """Wall-clock seconds that a test can move forward."""

    def __init__(self) -> None:
        self.offset = 0.0

    def __call__(self) -> float:
        return time.time() + self.offset


@dataclass
class Stack:
    """The service under test, the fake Chatwoot behind it, and what it recorded."""

    chatwoot: FakeChatwoot
    parts: ServiceParts
    client: TestClient
    audit: InMemoryAuditSink
    clock: Clock
    slept: list[float] = field(default_factory=list)
    deliveries: int = 0

    def webhook(
        self,
        payload: dict[str, Any],
        *,
        secret: str = BOT_SECRET,
        timestamp: int | None = None,
        path_token: str = PATH_TOKEN,
        delivery: str | None = None,
        raw: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        body = raw if raw is not None else json.dumps(payload).encode()
        stamp = str(int(time.time()) if timestamp is None else timestamp)
        self.deliveries += 1
        sent = {
            "Content-Type": "application/json",
            "X-Chatwoot-Timestamp": stamp,
            "X-Chatwoot-Signature": signature_for(secret, stamp, body),
            "X-Chatwoot-Delivery": delivery or f"delivery-{self.deliveries}-{secrets.token_hex(4)}",
        }
        sent.update(headers or {})
        return self.client.post(f"/chatwoot/webhook/{path_token}", content=body, headers=sent)

    def visitor_says(self, conversation_id: int, message_id: int, text: str) -> Any:
        if conversation_id not in self.chatwoot.conversations:
            self.chatwoot.conversation(conversation_id)
        self.chatwoot.message(message_id, conversation_id, text)
        return self.webhook(message_payload(conversation_id, message_id, text))


def message_payload(
    conversation_id: int,
    message_id: int,
    text: str,
    *,
    message_type: str = "incoming",
    private: bool = False,
    sender_type: str | None = None,
    event: str = "message_created",
    account: int = ACCOUNT,
) -> dict[str, Any]:
    sender: dict[str, Any] = {"id": 50, "name": "Visitor"}
    if sender_type is not None:
        sender["type"] = sender_type
    return {
        "event": event,
        "id": message_id,
        "content": text,
        "message_type": message_type,
        "private": private,
        "account": {"id": account, "name": "Example"},
        "conversation": {"id": conversation_id, "inbox_id": 1, "status": "pending"},
        "sender": sender,
    }


def build_stack(
    tmp_path: Path, *, mode: str = "auto", env: dict[str, str] | None = None, **changes: Any
) -> Stack:
    chatwoot = FakeChatwoot()
    audit = InMemoryAuditSink()
    slept: list[float] = []
    clock = Clock()

    def submit(work: Callable[[], None]) -> None:
        work()

    parts = build_service(
        settings(tmp_path, **changes),
        env={"INBOX_CORE_CLASSIFIER": "example-keywords", "INBOX_CORE_MODE": mode, **(env or {})},
        audit=audit,
        transport=chatwoot.transport(),
        submit=submit,
        sleep=slept.append,
        clock=clock,
    )
    track(parts.store)
    client = TestClient(create_app(parts.service), base_url=PUBLIC_ORIGIN)
    return Stack(chatwoot, parts, client, audit, clock, slept)


@pytest.fixture
def stack(tmp_path: Path) -> Iterator[Stack]:
    built = build_stack(tmp_path)
    yield built
    built.parts.store.close()


@pytest.fixture
def draft_stack(tmp_path: Path) -> Iterator[Stack]:
    built = build_stack(tmp_path, mode="draft")
    yield built
    built.parts.store.close()

"""Talking to the local stack started by ``deploy/chatwoot/stack.sh up``.

The visitor side uses the website widget's own API (what the widget script
calls); the agent side uses Chatwoot's application API with the seeded
people's tokens, read from the stack's gitignored ``.local`` files.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "chatwoot"
LOCAL = DEPLOY / ".local"


def read_env(name: str) -> dict[str, str]:
    values = {}
    for line in (LOCAL / name).read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key] = value
    return values


def _layout() -> dict[str, str]:
    """The project and ports stack.sh brought the stack up with (``.local/stack.env``)."""
    return read_env("stack.env") if (LOCAL / "stack.env").exists() else {}


PROJECT = _layout().get("STACK_PROJECT", "inboxcore")
CHATWOOT = f"http://127.0.0.1:{_layout().get('CHATWOOT_PORT', '3910')}"
SERVICE = f"http://127.0.0.1:{_layout().get('SERVICE_PORT', '3912')}"


def stack(*args: str, timeout: float = 300) -> str:
    done = subprocess.run(  # noqa: S603 - our own script
        [str(DEPLOY / "stack.sh"), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    return done.stdout


def compose(*args: str, timeout: float = 120) -> str:
    done = subprocess.run(  # noqa: S603 - the stack's own project
        ["docker", "compose", "-p", PROJECT, "-f", str(DEPLOY / "compose.yaml"), *args],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    return done.stdout


def rails(ruby: str) -> str:
    return compose("exec", "-T", "rails", "bundle", "exec", "rails", "runner", ruby, timeout=180)


def until[T](check: Callable[[], T | None], *, timeout: float = 30, every: float = 0.5) -> T:
    deadline = time.monotonic() + timeout
    while True:
        found = check()
        if found:
            return found
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting")
        time.sleep(every)


def quiet_for(check: Callable[[], bool], seconds: float) -> None:
    """Assert ``check`` stays false for ``seconds``."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        assert not check()
        time.sleep(0.5)


def unique(phrase: str) -> str:
    """A phrase no one else will write, so it can be searched for in logs."""
    return f"{phrase} {uuid.uuid4().hex[:10]}"


@dataclass
class Visitor:
    """One visitor in the website widget, through the widget's own API."""

    website_token: str
    name: str = "Example Visitor"
    token: str = ""
    conversation_id: int | None = None
    said: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        config = httpx.post(
            f"{CHATWOOT}/api/v1/widget/config", params={"website_token": self.website_token}
        )
        config.raise_for_status()
        self.token = config.json()["website_channel_config"]["auth_token"]

    def _call(self, method: str, path: str, body: Any = None) -> Any:
        response = httpx.request(
            method,
            f"{CHATWOOT}{path}",
            params={"website_token": self.website_token},
            headers={"X-Auth-Token": self.token},
            json=body,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def say(self, text: str) -> None:
        self.said.append(text)
        stamp = time.strftime("%a %b %d %Y")
        if self.conversation_id is None:
            created = self._call(
                "POST",
                "/api/v1/widget/conversations",
                {"contact": {"name": self.name}, "message": {"content": text, "timestamp": stamp}},
            )
            self.conversation_id = int(created["id"])
        else:
            self._call(
                "POST",
                "/api/v1/widget/messages",
                {"message": {"content": text, "timestamp": stamp}},
            )

    def messages(self) -> list[dict[str, Any]]:
        found = self._call("GET", "/api/v1/widget/messages")
        payload: list[dict[str, Any]] = (
            found if isinstance(found, list) else found.get("payload", [])
        )
        return payload

    def replies(self) -> list[str]:
        """What the visitor sees from the organisation: outgoing, public messages."""
        return [
            str(m.get("content") or "")
            for m in self.messages()
            if m.get("message_type") == 1 and not m.get("private")
        ]


class Agent:
    """Chatwoot's application API with one person's token."""

    def __init__(self, token: str, account_id: int) -> None:
        self.token = token
        self.account = account_id

    def call(self, method: str, path: str, body: Any = None) -> httpx.Response:
        return httpx.request(
            method,
            f"{CHATWOOT}/api/v1/accounts/{self.account}{path}",
            headers={"api_access_token": self.token},
            json=body,
            timeout=20,
        )

    def conversation(self, conversation_id: int) -> dict[str, Any]:
        response = self.call("GET", f"/conversations/{conversation_id}")
        response.raise_for_status()
        found: dict[str, Any] = response.json()
        return found

    def messages(self, conversation_id: int) -> list[dict[str, Any]]:
        response = self.call("GET", f"/conversations/{conversation_id}/messages")
        response.raise_for_status()
        found: list[dict[str, Any]] = response.json()["payload"]
        return found

    def reply(self, conversation_id: int, text: str) -> None:
        response = self.call(
            "POST",
            f"/conversations/{conversation_id}/messages",
            {"content": text, "message_type": "outgoing", "private": False},
        )
        response.raise_for_status()


def audit_records() -> list[dict[str, Any]]:
    raw = compose("exec", "-T", "inbox-core", "cat", "/data/audit.jsonl")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def audit_for(conversation_id: int) -> list[dict[str, Any]]:
    return [r for r in audit_records() if r["thread_key"] == str(conversation_id)]


def tab(
    method: str,
    path: str,
    *,
    session: str | None = None,
    body: Any = None,
    origin: str | None = SERVICE,
) -> httpx.Response:
    headers = {}
    if origin:
        headers["Origin"] = origin
    if session:
        headers["Authorization"] = f"Bearer {session}"
    return httpx.request(method, f"{SERVICE}{path}", headers=headers, json=body, timeout=20)

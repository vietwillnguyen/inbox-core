"""Talking to the demo bundle started by ``deploy/demo/demo.sh up``.

Everything a visitor or the owner does goes through the bundle's reverse
proxy, at the origins demo.sh wrote to its gitignored ``.local/bundle.env``:
the widget's own API on the chat host, the draft tab on the bot host. Only the
checks of what is stored and logged reach inside, through ``docker compose``.
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
DEPLOY = ROOT / "deploy" / "demo"
LOCAL = DEPLOY / ".local"
PROJECT = "inboxcore-demo"


def read_env(name: str) -> dict[str, str]:
    values = {}
    for line in (LOCAL / name).read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key] = value
    return values


def compose(*args: str, timeout: float = 180) -> str:
    done = subprocess.run(  # noqa: S603 - fixed project name
        [  # noqa: S607
            "docker",
            "compose",
            "-p",
            PROJECT,
            "-f",
            str(DEPLOY / "compose.yaml"),
            "--env-file",
            str(LOCAL / "bundle.env"),
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    return done.stdout


def demo(*args: str, timeout: float = 300) -> str:
    done = subprocess.run(  # noqa: S603 - our own script
        [str(DEPLOY / "demo.sh"), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    return done.stdout


def refill_message_limit(bundle: dict[str, str]) -> None:
    """Wait until the proxy's per-address message bucket is full again.

    Every test posts from this one address, so a test that needs the whole
    burst (or must not be refused) waits for the bucket the earlier tests
    drained to refill, instead of depending on how fast they ran.
    """
    per_minute = int(bundle["DEMO_RATE_MESSAGES_PER_MINUTE"])
    burst = int(bundle["DEMO_RATE_MESSAGES_BURST"])
    time.sleep(burst * 60 / per_minute + 1)


def rails(ruby: str) -> str:
    return compose("exec", "-T", "rails", "bundle", "exec", "rails", "runner", ruby, timeout=240)


def until[T](check: Callable[[], T | None], *, timeout: float = 45, every: float = 0.5) -> T:
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
    """One visitor in the website widget, through the proxy and the widget's own API."""

    chat: str
    website_token: str
    token: str = ""
    conversation_id: int | None = None
    said: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        config = httpx.post(
            f"{self.chat}/api/v1/widget/config", params={"website_token": self.website_token}
        )
        config.raise_for_status()
        self.token = config.json()["website_channel_config"]["auth_token"]

    def post(self, text: str) -> httpx.Response:
        """Post one message and return the response, whatever its status."""
        self.said.append(text)
        stamp = time.strftime("%a %b %d %Y")
        params = {"website_token": self.website_token}
        headers = {"X-Auth-Token": self.token}
        if self.conversation_id is None:
            response = httpx.post(
                f"{self.chat}/api/v1/widget/conversations",
                params=params,
                headers=headers,
                json={"message": {"content": text, "timestamp": stamp}},
                timeout=20,
            )
            if response.status_code == 200:
                self.conversation_id = int(response.json()["id"])
            return response
        return httpx.post(
            f"{self.chat}/api/v1/widget/messages",
            params=params,
            headers=headers,
            json={"message": {"content": text, "timestamp": stamp}},
            timeout=20,
        )

    def say(self, text: str) -> None:
        self.post(text).raise_for_status()

    def _messages(self) -> list[dict[str, Any]]:
        response = httpx.get(
            f"{self.chat}/api/v1/widget/messages",
            params={"website_token": self.website_token},
            headers={"X-Auth-Token": self.token},
            timeout=20,
        )
        response.raise_for_status()
        found = response.json()
        messages: list[dict[str, Any]] = (
            found if isinstance(found, list) else found.get("payload", [])
        )
        return messages

    def everything(self) -> list[str]:
        """Every message the visitor's widget can read, whoever wrote it."""
        return [str(m.get("content") or "") for m in self._messages()]

    def replies(self) -> list[str]:
        """What the visitor sees from the shop: outgoing, public messages."""
        return [
            str(m.get("content") or "")
            for m in self._messages()
            if m.get("message_type") == 1 and not m.get("private")
        ]


class Owner:
    """Chatwoot's application API with the owner's (the administrator's) token."""

    def __init__(self, chat: str, token: str, account_id: int) -> None:
        self.base = f"{chat}/api/v1/accounts/{account_id}"
        self.token = token

    def call(self, method: str, path: str, body: Any = None) -> httpx.Response:
        return httpx.request(
            method,
            f"{self.base}{path}",
            headers={"api_access_token": self.token},
            json=body,
            timeout=20,
        )

    def conversation(self, conversation_id: int) -> dict[str, Any]:
        response = self.call("GET", f"/conversations/{conversation_id}")
        response.raise_for_status()
        found: dict[str, Any] = response.json()
        return found

    def notes(self, conversation_id: int) -> list[str]:
        response = self.call("GET", f"/conversations/{conversation_id}/messages")
        response.raise_for_status()
        return [str(m["content"]) for m in response.json()["payload"] if m["private"]]


def audit_for(conversation_id: int) -> list[dict[str, Any]]:
    """The service's audit records for one conversation, from its log."""
    records = []
    for line in compose("logs", "--no-color", "--no-log-prefix", "inbox-core").splitlines():
        if " inbox_core.audit " in line and "{" in line:
            record = json.loads(line[line.index("{") :])
            if record["thread_key"] == str(conversation_id):
                records.append(record)
    return records

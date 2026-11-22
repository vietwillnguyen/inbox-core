"""The Chatwoot service's settings, read from the environment.

Every secret is hidden from ``repr``. A missing or malformed setting raises
:class:`SettingsError` naming the variable, never its value.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from inbox_core.chatwoot.tab_auth import MAX_SESSION_SECONDS

__all__ = ["ChatwootSettings", "SettingsError"]


class SettingsError(ValueError):
    """A setting is missing or malformed. The message names the variable only."""


def _origin(name: str, value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.path not in ("", "/"):
        raise SettingsError(f"{name} must be an origin such as https://chat.example.com")
    return f"{parts.scheme}://{parts.netloc}"


@dataclass(frozen=True)
class ChatwootSettings:
    """Where Chatwoot is, who the bot is, and the service's own secrets.

    ``chatwoot_url`` is the API base the service calls (inside a compose
    network it is usually ``http://rails:3000``). ``chatwoot_origin`` is the
    origin agents' browsers load Chatwoot from, the only page allowed to frame
    the draft tab. ``public_origin`` is the origin browsers load this service
    from, which state-changing tab requests must come from.
    """

    chatwoot_url: str
    chatwoot_origin: str
    public_origin: str
    account_id: int
    bot_token: str = field(repr=False)
    bot_secret: str = field(repr=False)
    webhook_path_token: str = field(repr=False)
    tab_secret: str = field(repr=False)
    database_url: str = field(repr=False)
    encryption_keys: str = field(repr=False)
    assignee_id: int | None = None
    session_seconds: int = 1800

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ChatwootSettings:
        """Read ``INBOX_CORE_*`` and ``CHATWOOT_*`` variables."""
        source = os.environ if env is None else env

        def need(name: str) -> str:
            value = source.get(name, "").strip()
            if not value:
                raise SettingsError(f"{name} is not set")
            return value

        def number(name: str, default: str | None = None) -> int:
            raw = source.get(name, "").strip() or (default or "")
            if not raw:
                raise SettingsError(f"{name} is not set")
            if not raw.isdigit():
                raise SettingsError(f"{name} must be a whole number")
            return int(raw)

        path_token = need("INBOX_CORE_WEBHOOK_PATH_TOKEN")
        if len(path_token) < 24:
            raise SettingsError("INBOX_CORE_WEBHOOK_PATH_TOKEN must be at least 24 characters")
        tab_secret = need("INBOX_CORE_TAB_SECRET")
        if len(tab_secret) < 32:
            raise SettingsError("INBOX_CORE_TAB_SECRET must be at least 32 characters")
        session = number("INBOX_CORE_TAB_SESSION_SECONDS", "1800")
        if not 60 <= session <= MAX_SESSION_SECONDS:
            raise SettingsError("INBOX_CORE_TAB_SESSION_SECONDS must be between 60 and 28800")
        assignee = source.get("INBOX_CORE_ASSIGNEE_ID", "").strip()
        if assignee and not assignee.isdigit():
            raise SettingsError("INBOX_CORE_ASSIGNEE_ID must be a whole number")
        return cls(
            chatwoot_url=need("CHATWOOT_URL").rstrip("/"),
            chatwoot_origin=_origin("CHATWOOT_ORIGIN", need("CHATWOOT_ORIGIN")),
            public_origin=_origin("INBOX_CORE_PUBLIC_ORIGIN", need("INBOX_CORE_PUBLIC_ORIGIN")),
            account_id=number("CHATWOOT_ACCOUNT_ID"),
            bot_token=need("CHATWOOT_BOT_TOKEN"),
            bot_secret=need("CHATWOOT_BOT_SECRET"),
            webhook_path_token=path_token,
            tab_secret=tab_secret,
            database_url=need("INBOX_CORE_DATABASE_URL"),
            encryption_keys=need("INBOX_CORE_ENCRYPTION_KEYS"),
            assignee_id=int(assignee) if assignee else None,
            session_seconds=session,
        )

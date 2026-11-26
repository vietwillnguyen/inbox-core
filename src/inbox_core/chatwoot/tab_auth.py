"""Signing in to the draft tab, and binding every action to the signed-in agent.

Chatwoot frames the tab and posts it the conversation and the "current agent"
with ``postMessage(..., '*')``, unsigned (``Frame.vue`` at v4.19.1). Anything
running in the agent's browser, or any page that frames the tab, could post a
different identity. So the tab never trusts it. Instead:

1. **Sign-in.** The agent pastes their personal Chatwoot access token once.
   The service asks Chatwoot, with that token, who it belongs to
   (``GET /api/v1/profile``) and which inboxes they may see in this account
   (``GET /api/v1/accounts/{id}/inboxes``, which Chatwoot scopes to the
   agent's own inboxes). The token is used for those two calls and dropped;
   it is never stored or logged. The service then mints a **session token**:
   the agent's id, the account, those inbox ids, an expiry (default 30
   minutes, at most 8 hours) and a random id, signed with HMAC-SHA256 under
   a secret only the service holds.
2. **Every request** carries the session token as ``Authorization: Bearer``,
   so there is no cookie for a cross-site request to ride on. The service
   also refuses a state-changing request whose ``Origin`` is not the tab's
   own, and the page is served with ``frame-ancestors`` set to the Chatwoot
   origin only, so it cannot be framed elsewhere and clicked through.
3. **Every action** (send, discard) carries an **action token**, minted when
   the drafts are listed and bound to this session's id, this conversation and
   this draft, with a ten-minute expiry. A token for another draft or another
   session is refused. The service re-reads the conversation from Chatwoot to
   check its inbox is one this agent may see, and the draft itself moves from
   held to sent exactly once, so a replayed request finds nothing to do.

Tokens are ``<version>.<base64url JSON>.<base64url HMAC>``; the version is
part of what is signed. Verification is constant time and every failure is a
:class:`TabAuthError` with a fixed reason.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

__all__ = [
    "MAX_SESSION_SECONDS",
    "ActionClaims",
    "AttemptLimiter",
    "SessionClaims",
    "TabAuthError",
    "TabSigner",
    "same_origin",
]

VERSION = "v1"
MAX_SESSION_SECONDS = 8 * 3600
ACTION_SECONDS = 600


class TabAuthError(Exception):
    """A token or request failed a check. ``reason`` is a fixed phrase."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SessionClaims:
    """A verified session: who, in which account, which inboxes, until when."""

    agent_id: int
    account_id: int
    inbox_ids: frozenset[int]
    expires_at: int
    session_id: str

    @property
    def reviewer(self) -> str:
        """The identifier recorded on drafts this agent sends or discards."""
        return f"chatwoot-user:{self.agent_id}"


@dataclass(frozen=True)
class ActionClaims:
    """A verified action token: one draft, one conversation, one session."""

    session_id: str
    conversation_id: int
    draft_id: int
    expires_at: int


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class TabSigner:
    """Mints and verifies session and action tokens under one secret."""

    def __init__(self, secret: str, *, clock: Callable[[], float] = time.time) -> None:
        if len(secret) < 32:
            raise ValueError("the tab secret must be at least 32 characters")
        self._key = hashlib.sha256(b"inbox-core tab v1\0" + secret.encode()).digest()
        self._clock = clock

    def __repr__(self) -> str:
        return "TabSigner()"

    def _sign(self, kind: str, claims: dict[str, Any]) -> str:
        body = _b64(json.dumps({"k": kind, **claims}, sort_keys=True).encode())
        mac = hmac.new(self._key, f"{VERSION}.{body}".encode(), hashlib.sha256).digest()
        return f"{VERSION}.{body}.{_b64(mac)}"

    def _open(self, kind: str, token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != VERSION:
            raise TabAuthError("malformed token")
        expected = hmac.new(self._key, f"{VERSION}.{parts[1]}".encode(), hashlib.sha256).digest()
        try:
            given = _unb64(parts[2])
            claims = json.loads(_unb64(parts[1]))
        except (ValueError, UnicodeDecodeError):
            raise TabAuthError("malformed token") from None
        if not hmac.compare_digest(given, expected):
            raise TabAuthError("bad token signature")
        if not isinstance(claims, dict) or claims.get("k") != kind:
            raise TabAuthError("wrong kind of token")
        expires = claims.get("exp")
        if not isinstance(expires, int) or self._clock() >= expires:
            raise TabAuthError("expired token")
        return claims

    def mint_session(
        self, *, agent_id: int, account_id: int, inbox_ids: frozenset[int], ttl: int
    ) -> tuple[str, SessionClaims]:
        """A session token for a Chatwoot-verified agent."""
        if not 60 <= ttl <= MAX_SESSION_SECONDS:
            raise ValueError("a session lasts between one minute and eight hours")
        claims = SessionClaims(
            agent_id=agent_id,
            account_id=account_id,
            inbox_ids=frozenset(inbox_ids),
            expires_at=int(self._clock()) + ttl,
            session_id=secrets.token_urlsafe(16),
        )
        token = self._sign(
            "session",
            {
                "sub": agent_id,
                "acct": account_id,
                "inb": sorted(claims.inbox_ids),
                "exp": claims.expires_at,
                "sid": claims.session_id,
            },
        )
        return token, claims

    def verify_session(self, token: str, *, account_id: int) -> SessionClaims:
        """The session's claims, or :class:`TabAuthError`."""
        claims = self._open("session", token)
        try:
            agent, account = int(claims["sub"]), int(claims["acct"])
            inboxes = frozenset(int(i) for i in claims["inb"])
            session_id = str(claims["sid"])
        except (KeyError, TypeError, ValueError):
            raise TabAuthError("malformed token") from None
        if account != account_id:
            raise TabAuthError("token for another account")
        return SessionClaims(agent, account, inboxes, int(claims["exp"]), session_id)

    def mint_action(self, session: SessionClaims, *, conversation_id: int, draft_id: int) -> str:
        """An action token for one draft, valid for this session only."""
        expires = min(int(self._clock()) + ACTION_SECONDS, session.expires_at)
        return self._sign(
            "action",
            {"sid": session.session_id, "conv": conversation_id, "draft": draft_id, "exp": expires},
        )

    def verify_action(
        self, token: str, session: SessionClaims, *, conversation_id: int, draft_id: int
    ) -> ActionClaims:
        """The action's claims if they match this session, conversation and draft."""
        claims = self._open("action", token)
        try:
            found = ActionClaims(
                str(claims["sid"]), int(claims["conv"]), int(claims["draft"]), int(claims["exp"])
            )
        except (KeyError, TypeError, ValueError):
            raise TabAuthError("malformed token") from None
        if not hmac.compare_digest(found.session_id, session.session_id):
            raise TabAuthError("action token from another session")
        if found.conversation_id != conversation_id or found.draft_id != draft_id:
            raise TabAuthError("action token for another draft")
        return found


def same_origin(origin: str | None, expected: str) -> bool:
    """Whether a request's ``Origin`` header is exactly the tab's own origin."""
    return origin is not None and hmac.compare_digest(
        origin.rstrip("/").encode(), expected.rstrip("/").encode()
    )


class AttemptLimiter:
    """At most ``limit`` sign-in attempts per key in a sliding window, in memory."""

    def __init__(
        self, *, limit: int = 10, window: float = 60.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._limit = limit
        self._window = window
        self._clock = clock
        self._attempts: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Count an attempt for ``key``; False once the limit is reached."""
        now = self._clock()
        with self._lock:
            recent = [t for t in self._attempts.get(key, []) if now - t < self._window]
            if len(recent) >= self._limit:
                self._attempts[key] = recent
                return False
            recent.append(now)
            self._attempts[key] = recent
            if len(self._attempts) > 10_000:
                self._attempts = {
                    k: v for k, v in self._attempts.items() if v and now - v[-1] < self._window
                }
            return True

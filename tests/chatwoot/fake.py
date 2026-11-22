"""A small in-memory Chatwoot behind an httpx transport. Made-up data only.

It serves the endpoints the connection calls, with Chatwoot's response shapes
(as the generated client parses them) and its authorization rules: the bot
token may read conversations and post; an agent's token sees only the
agent's inboxes; deleting needs an administrator.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

ACCOUNT = 1
BOT_TOKEN = "bot-token-0123456789abcdef"
ADMIN_TOKEN = "admin-token-0123456789abcdef"
AGENT_TOKEN = "agent-token-0123456789abcdef"
OTHER_AGENT_TOKEN = "other-agent-token-0123456789"
OUTSIDER_TOKEN = "outsider-token-0123456789ab"


@dataclass
class User:
    id: int
    name: str
    roles: dict[int, str]
    inboxes: set[int]


@dataclass
class FakeChatwoot:
    """Conversations, messages, users and a record of every write."""

    conversations: dict[int, dict[str, Any]] = field(default_factory=dict)
    messages: dict[int, dict[str, Any]] = field(default_factory=dict)
    contacts: set[int] = field(default_factory=set)
    users: dict[str, User] = field(default_factory=dict)
    writes: list[tuple[str, int, Any]] = field(default_factory=list)
    fail_posts: bool = False
    down: bool = False
    failures: dict[str, int] = field(default_factory=dict)
    next_id: int = 100

    def __post_init__(self) -> None:
        self.users.setdefault(
            ADMIN_TOKEN, User(1, "Example Admin", {ACCOUNT: "administrator"}, {1, 2})
        )
        self.users.setdefault(AGENT_TOKEN, User(5, "Example Agent", {ACCOUNT: "agent"}, {1}))
        self.users.setdefault(OTHER_AGENT_TOKEN, User(6, "Second Agent", {ACCOUNT: "agent"}, {2}))
        self.users.setdefault(OUTSIDER_TOKEN, User(9, "Outsider", {7: "agent"}, {9}))

    # ---- arranging -------------------------------------------------------

    def conversation(
        self, conversation_id: int, *, inbox: int = 1, contact: int = 50, account: int = ACCOUNT
    ) -> None:
        self.conversations[conversation_id] = {
            "id": conversation_id,
            "account_id": account,
            "inbox_id": inbox,
            "status": "pending",
            "labels": [],
            "contact": contact,
            "last_activity_at": 1_700_000_000,
            "created_at": 1_700_000_000,
        }
        self.contacts.add(contact)

    def message(
        self,
        message_id: int,
        conversation_id: int,
        content: str,
        *,
        message_type: int = 0,
        private: bool = False,
        sender_type: str = "Contact",
    ) -> None:
        self.messages[message_id] = {
            "id": message_id,
            "conversation_id": conversation_id,
            "content": content,
            "message_type": message_type,
            "private": private,
            "sender_type": sender_type,
            "sender_id": 50,
            "created_at": 1_700_000_000,
        }

    def public_messages(self, conversation_id: int) -> list[str]:
        return [
            body["content"]
            for kind, cid, body in self.writes
            if kind == "message" and cid == conversation_id and not body.get("private")
        ]

    def notes(self, conversation_id: int) -> list[str]:
        return [
            body["content"]
            for kind, cid, body in self.writes
            if kind == "message" and cid == conversation_id and body.get("private")
        ]

    # ---- serving ---------------------------------------------------------

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("chatwoot is down", request=request)
        token = request.headers.get("api_access_token", "")
        path = request.url.path
        for suffix, remaining in self.failures.items():
            if remaining > 0 and path.endswith(suffix):
                self.failures[suffix] = remaining - 1
                return httpx.Response(500, json={})
        if path == "/api/v1/profile":
            user = self.users.get(token)
            if user is None:
                return httpx.Response(401, json={"error": "Invalid Access Token"})
            return httpx.Response(
                200,
                json={
                    "id": user.id,
                    "name": user.name,
                    "accounts": [
                        {"id": a, "name": "Example", "role": r} for a, r in user.roles.items()
                    ],
                },
            )
        match = re.fullmatch(r"/api/v1/accounts/(\d+)(/.*)", path)
        if not match:
            return httpx.Response(404, json={"error": "not found"})
        account, rest = int(match.group(1)), match.group(2)
        user = self.users.get(token)
        is_bot = token == BOT_TOKEN
        if not is_bot and (user is None or account not in user.roles):
            return httpx.Response(401, json={"error": "unauthorized"})
        if rest == "/inboxes":
            assert user is not None
            return httpx.Response(
                200,
                json={"payload": [{"id": i, "name": f"Inbox {i}"} for i in sorted(user.inboxes)]},
            )
        if rest == "/conversations" and request.method == "GET":
            return self._list(request)
        found = re.fullmatch(r"/conversations/(\d+)(/.*)?", rest)
        if found:
            return self._conversation(
                request, int(found.group(1)), found.group(2) or "", is_bot, user
            )
        found = re.fullmatch(r"/contacts/(\d+)(/conversations)?", rest)
        if found:
            contact = int(found.group(1))
            if found.group(2):
                left = [c for c in self.conversations.values() if c["contact"] == contact]
                return httpx.Response(200, json={"payload": [self._show(c) for c in left]})
            if request.method == "DELETE":
                if user is None or user.roles.get(account) != "administrator":
                    return httpx.Response(401, json={"error": "unauthorized"})
                self.contacts.discard(contact)
                self.writes.append(("delete contact", contact, None))
                return httpx.Response(200, json={})
        return httpx.Response(404, json={"error": "not found"})

    def _show(self, conversation: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": conversation["id"],
            "account_id": conversation["account_id"],
            "inbox_id": conversation["inbox_id"],
            "status": conversation["status"],
            "labels": list(conversation["labels"]),
            "last_activity_at": conversation["last_activity_at"],
            "created_at": conversation["created_at"],
            "meta": {"sender": {"id": conversation["contact"], "name": "Visitor"}},
        }

    def _list(self, request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        everything = sorted(self.conversations.values(), key=lambda c: c["id"])
        chunk = everything[(page - 1) * 25 : page * 25]
        return httpx.Response(
            200,
            json={
                "data": {
                    "meta": {"all_count": len(everything)},
                    "payload": [self._show(c) for c in chunk],
                }
            },
        )

    def _conversation(
        self,
        request: httpx.Request,
        conversation_id: int,
        rest: str,
        is_bot: bool,
        user: User | None,
    ) -> httpx.Response:
        conversation = self.conversations.get(conversation_id)
        if conversation is None:
            return httpx.Response(404, json={"error": "Resource could not be found"})
        outside = user is not None and conversation["inbox_id"] not in user.inboxes
        if not is_bot and outside and user.roles.get(ACCOUNT) != "administrator":  # type: ignore[union-attr]
            return httpx.Response(401, json={"error": "unauthorized"})
        body: dict[str, Any] = json.loads(request.content) if request.content else {}
        if rest == "" and request.method == "GET":
            return httpx.Response(200, json=self._show(conversation))
        if rest == "" and request.method == "DELETE":
            if user is None or user.roles.get(ACCOUNT) != "administrator":
                return httpx.Response(401, json={"error": "unauthorized"})
            del self.conversations[conversation_id]
            self.writes.append(("delete conversation", conversation_id, None))
            return httpx.Response(200)
        if rest == "/messages" and request.method == "GET":
            after = int(request.url.params.get("after", "0"))
            found = [
                m
                for m in sorted(self.messages.values(), key=lambda m: m["id"])
                if m["conversation_id"] == conversation_id and m["id"] > after
            ]
            return httpx.Response(200, json={"meta": {}, "payload": found})
        if rest == "/messages" and request.method == "POST":
            if self.fail_posts:
                return httpx.Response(422, json={"error": "could not create"})
            self.next_id += 1
            self.writes.append(("message", conversation_id, body))
            return httpx.Response(200, json={"id": self.next_id, "content": body["content"]})
        if rest == "/toggle_status":
            conversation["status"] = body["status"]
            self.writes.append(("status", conversation_id, body["status"]))
            return httpx.Response(
                200, json={"payload": {"success": True, "current_status": body["status"]}}
            )
        if rest == "/labels":
            conversation["labels"] = list(body["labels"])
            self.writes.append(("labels", conversation_id, list(body["labels"])))
            return httpx.Response(200, json={"payload": list(body["labels"])})
        if rest == "/assignments":
            self.writes.append(("assign", conversation_id, body["assignee_id"]))
            return httpx.Response(200, json={"id": body["assignee_id"]})
        return httpx.Response(404, json={"error": "not found"})

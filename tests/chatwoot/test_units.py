"""Small parts of the connection: tokens, the sink, the wiring."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import pytest

from inbox_core.chatwoot.app import build_service
from inbox_core.chatwoot.settings import SettingsError
from inbox_core.chatwoot.sink import ChatwootHandOff, ChatwootReplySink, conversation_id_of
from inbox_core.chatwoot.tab_auth import AttemptLimiter, TabAuthError, TabSigner, same_origin
from inbox_core.handoff import HandOffRequest
from inbox_core.messages import OutboundReply
from tests.chatwoot.conftest import Stack, build_stack, message_payload, settings
from tests.chatwoot.fake import FakeChatwoot

SECRET = "s" * 40


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def b64(data: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


class TestTokens:
    def test_a_session_round_trips(self) -> None:
        signer = TabSigner(SECRET, clock=Clock())
        token, minted = signer.mint_session(
            agent_id=5, account_id=1, inbox_ids=frozenset({1}), ttl=60
        )
        assert signer.verify_session(token, account_id=1) == minted
        assert minted.reviewer == "chatwoot-user:5"
        assert SECRET not in repr(signer)

    @pytest.mark.parametrize(
        "token",
        ["", "v1.a", "v2.a.b", "v1.!!!.???", "v1." + b64([1, 2]) + ".AAAA"],
    )
    def test_malformed_tokens(self, token: str) -> None:
        with pytest.raises(TabAuthError):
            TabSigner(SECRET).verify_session(token, account_id=1)

    def test_a_signed_token_with_missing_claims_is_malformed(self) -> None:
        signer = TabSigner(SECRET, clock=Clock())
        token = signer._sign("session", {"exp": 2_000_000})
        with pytest.raises(TabAuthError, match="malformed"):
            signer.verify_session(token, account_id=1)
        action = signer._sign("action", {"exp": 2_000_000})
        session = signer.mint_session(agent_id=5, account_id=1, inbox_ids=frozenset(), ttl=60)[1]
        with pytest.raises(TabAuthError, match="malformed"):
            signer.verify_action(action, session, conversation_id=1, draft_id=1)

    def test_an_action_token_is_not_a_session_and_the_reverse(self) -> None:
        signer = TabSigner(SECRET, clock=Clock())
        token, session = signer.mint_session(
            agent_id=5, account_id=1, inbox_ids=frozenset(), ttl=60
        )
        action = signer.mint_action(session, conversation_id=1, draft_id=2)
        with pytest.raises(TabAuthError, match="wrong kind"):
            signer.verify_session(action, account_id=1)
        with pytest.raises(TabAuthError, match="wrong kind"):
            signer.verify_action(token, session, conversation_id=1, draft_id=2)

    def test_a_session_for_another_account(self) -> None:
        signer = TabSigner(SECRET, clock=Clock())
        token, _ = signer.mint_session(agent_id=5, account_id=2, inbox_ids=frozenset(), ttl=60)
        with pytest.raises(TabAuthError, match="another account"):
            signer.verify_session(token, account_id=1)

    def test_an_action_never_outlives_its_session(self) -> None:
        clock = Clock()
        signer = TabSigner(SECRET, clock=clock)
        _, session = signer.mint_session(agent_id=5, account_id=1, inbox_ids=frozenset(), ttl=60)
        action = signer.mint_action(session, conversation_id=1, draft_id=2)
        clock.now += 61
        with pytest.raises(TabAuthError, match="expired"):
            signer.verify_action(action, session, conversation_id=1, draft_id=2)

    @pytest.mark.parametrize("ttl", [59, 8 * 3600 + 1])
    def test_session_length_is_bounded(self, ttl: int) -> None:
        with pytest.raises(ValueError, match="session"):
            TabSigner(SECRET).mint_session(agent_id=5, account_id=1, inbox_ids=frozenset(), ttl=ttl)

    def test_same_origin(self) -> None:
        assert same_origin("http://a.example/", "http://a.example")
        assert not same_origin("http://a.example:81", "http://a.example")
        assert not same_origin(None, "http://a.example")

    def test_the_limiter_window_slides_and_stays_bounded(self) -> None:
        now = [0.0]
        limiter = AttemptLimiter(limit=1, window=10, clock=lambda: now[0])
        assert limiter.allow("a")
        assert not limiter.allow("a")
        now[0] = 11
        assert limiter.allow("a")
        for n in range(10_001):
            limiter.allow(f"k{n}")
        now[0] = 30
        limiter.allow("fresh")
        assert len(limiter._attempts) <= 2


class TestSink:
    def test_a_thread_key_must_be_a_conversation_id(self) -> None:
        assert conversation_id_of("12") == 12
        with pytest.raises(ValueError, match="display id"):
            conversation_id_of("conv-1")

    def test_holding_sends_nothing(self) -> None:
        fake = FakeChatwoot()
        from inbox_core.chatwoot.api import ChatwootApi

        sink = ChatwootReplySink(ChatwootApi("http://c.test", 1, "t", transport=fake.transport()))
        reply = OutboundReply("4", "m", "x", "draft text", "en", "grounded_answer")
        assert sink.hold_for_review(reply) is None
        assert fake.writes == []

    def test_no_assignee_and_no_labels_do_nothing(self) -> None:
        fake = FakeChatwoot()
        fake.conversation(4)
        from inbox_core.chatwoot.api import ChatwootApi

        actions = ChatwootHandOff(ChatwootApi("http://c.test", 1, "t", transport=fake.transport()))
        request = HandOffRequest(
            "hand_off", "chatwoot", "4", "m", None, "x", "needs_admin", "r", (), "n"
        )
        actions.assign(request)
        actions.add_labels(request)
        assert fake.writes == []


class TestWiring:
    def test_an_unknown_classifier_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(SettingsError, match="INBOX_CORE_CLASSIFIER"):
            build_service(settings(tmp_path), env={"INBOX_CORE_CLASSIFIER": "magic"})

    def test_litellm_is_the_default_and_needs_its_extra(self, tmp_path: Path) -> None:
        with pytest.raises(ImportError, match="inbox-core\\[litellm\\]"):
            build_service(settings(tmp_path), env={})

    def test_a_client_config_and_knowledge_from_files(self, tmp_path: Path) -> None:
        from inbox_core.examples.demo import EXAMPLE_DIR

        knowledge = tmp_path / "knowledge.md"
        knowledge.write_text("## KB-1 Opening hours\nWe open at nine.\n")
        parts = build_service(
            settings(tmp_path),
            env={
                "INBOX_CORE_CLASSIFIER": "example-keywords",
                "INBOX_CORE_CONFIG": str(EXAMPLE_DIR / "client.toml"),
                "INBOX_CORE_KNOWLEDGE": str(knowledge),
                "INBOX_CORE_AUDIT_PATH": str(tmp_path / "audit.jsonl"),
                "INBOX_CORE_MODE": "off",
            },
        )
        assert parts.pipeline.drafts.mode.value == "off"
        assert parts.service._titles == {"KB-1": "Opening hours"}
        parts.store.close()


def test_a_failing_agent_reply_does_not_fall_back(tmp_path: Path) -> None:
    stack: Stack = build_stack(tmp_path)

    def down(*args: object, **kwargs: object) -> object:
        raise ConnectionError("database unavailable")

    stack.parts.store.conversation_for = down  # type: ignore[method-assign,assignment]
    stack.chatwoot.conversation(30)
    stack.chatwoot.message(1, 30, "On it", message_type=1, sender_type="User")
    stack.webhook(message_payload(30, 1, "x", message_type="outgoing", sender_type="user"))
    assert stack.chatwoot.writes == []
    stack.parts.store.close()


def test_an_unknown_asset_from_inside_is_a_404(tmp_path: Path) -> None:
    stack = build_stack(tmp_path)
    response = asyncio.run(stack.parts.service.draft_tab_asset(None, "x.js"))  # type: ignore[arg-type]
    assert response.status_code == 404
    stack.parts.store.close()

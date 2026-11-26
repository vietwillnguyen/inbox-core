"""The Chatwoot service: the agent-bot webhook and the draft tab, over the core.

:class:`ChatwootService` implements the generated
:class:`inbox_core.chatwoot._service_api.routes.ServiceApi`, so every route,
parameter and model comes from ``openapi.yaml``. :func:`create_app` wires it
into a FastAPI app with the API docs pages switched off and validation errors
answered with a fixed phrase, never an echo of the input.

**Webhook.** Verified (see :mod:`inbox_core.chatwoot.webhook`), answered at
once, and handled on a worker thread: the message is re-fetched from
Chatwoot's API, then a visitor message goes through ``Pipeline.process`` and a
staff reply through ``Pipeline.person_replied``. The handler never answers 429
or 500: Chatwoot retries those and logs the whole payload, visitor text
included, at ``warn`` (``app/jobs/agent_bots/webhook_job.rb``).

**When the core cannot finish.** A ``busy`` or ``incomplete`` message is
retried a few times. If it still did not deliver a holding message (because
the store, the classifier, a model or Chatwoot itself failed), the service
falls back: the client's holding text goes out through a
:class:`inbox_core.delivery.Delivery` under the same mode and language gates,
at most once per conversation per process, and the conversation is opened
for a person with a note saying why. Nothing in the fallback carries message
content.

**Draft tab.** See :mod:`inbox_core.chatwoot.tab_auth` for how an agent signs
in. Every action is checked against the session, the action token, the
request's origin, the conversation's inbox as Chatwoot reports it, and the
draft's own state; each refusal is counted by reason.
"""

from __future__ import annotations

import html
import json
import logging
import threading
import time
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from importlib import resources
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from inbox_core.chatwoot._service_api.routes import build_router
from inbox_core.chatwoot.api import ChatwootApi, ChatwootError, MessageFacts
from inbox_core.chatwoot.settings import ChatwootSettings
from inbox_core.chatwoot.tab_auth import (
    AttemptLimiter,
    SessionClaims,
    TabAuthError,
    TabSigner,
    same_origin,
)
from inbox_core.chatwoot.webhook import DeliveryLog, WebhookEvent, check_webhook, classify_event
from inbox_core.config import ClientConfig
from inbox_core.delivery import Delivery, ReleaseRefusedError
from inbox_core.handoff import REVIEW_LABEL, HandOffActions, HandOffRequest
from inbox_core.messages import IncomingMessage, OutboundReply, make_sender_key
from inbox_core.pipeline import AuditRecord, Pipeline
from inbox_core.review import (
    DraftContentUnavailableError,
    DraftNotFoundError,
    DraftNotPendingError,
    DraftSendFailedError,
    HeldDraft,
)
from inbox_core.store import ConversationStore

__all__ = ["CHANNEL", "ChatwootService", "Submit", "create_app", "thread_submit"]

logger = logging.getLogger("inbox_core.chatwoot")

CHANNEL = "chatwoot"
SEEN_LABEL = "inbox-core"
"""Put on every conversation the service processes; see ``deploy/chatwoot/seed.rb``."""
RETRY_DELAYS = (0.5, 1.0, 2.0, 4.0)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
ASSET_TYPES = {"tab.js": "text/javascript; charset=utf-8", "tab.css": "text/css; charset=utf-8"}

Submit = Callable[[Callable[[], None]], None]


def thread_submit(work: Callable[[], None]) -> None:
    """Run ``work`` on its own daemon thread, so the webhook can answer at once."""
    threading.Thread(target=work, daemon=True, name="inbox-core-webhook").start()


def _problem(status: int, error: str) -> JSONResponse:
    return JSONResponse({"error": error}, status_code=status, headers=SECURITY_HEADERS)


class _Refused(Exception):  # noqa: N818 - private control flow, not an error type
    def __init__(self, status: int, error: str, reason: str) -> None:
        super().__init__(reason)
        self.status, self.error, self.reason = status, error, reason


class ChatwootService:
    """Implements every operation in ``openapi.yaml``."""

    def __init__(
        self,
        *,
        settings: ChatwootSettings,
        config: ClientConfig,
        pipeline: Pipeline,
        store: ConversationStore,
        api: ChatwootApi,
        handoff: HandOffActions,
        fallback_delivery: Delivery,
        source_titles: Mapping[str, str] | None = None,
        submit: Submit = thread_submit,
        sleep: Callable[[float], object] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._settings = settings
        self._config = config
        self._pipeline = pipeline
        self._store = store
        self._api = api
        self._handoff = handoff
        self._fallback = fallback_delivery
        self._titles = dict(source_titles or {})
        self._submit = submit
        self._sleep = sleep
        self._clock = clock
        self._signer = TabSigner(settings.tab_secret, clock=clock)
        self._limiter = AttemptLimiter()
        self._deliveries = DeliveryLog()
        self._fell_back: set[int] = set()
        self._lock = threading.Lock()
        self.counts: dict[str, Counter[str]] = {
            "accepted": Counter(),
            "ignored": Counter(),
            "rejected": Counter(),
            "tab_rejected": Counter(),
            "processed": Counter(),
        }

    def _count(self, kind: str, reason: str) -> None:
        with self._lock:
            self.counts[kind][reason] += 1

    # ---- operations -------------------------------------------------------

    async def health(self, request: Request) -> Any:
        """Liveness and the delivery mode."""
        return {"status": "ok", "mode": self._pipeline.drafts.mode.value}

    async def metrics(self, request: Request) -> Any:
        """Counters by reason. Numbers only."""
        with self._lock:
            return {
                "webhooks_accepted": sum(self.counts["accepted"].values()),
                "webhooks_ignored": dict(self.counts["ignored"]),
                "webhooks_rejected": dict(self.counts["rejected"]),
                "tab_rejected": dict(self.counts["tab_rejected"]),
                "processed": dict(self.counts["processed"]),
            }

    async def receive_webhook(
        self,
        request: Request,
        path_token: str,
        x__chatwoot__signature: str | None,
        x__chatwoot__timestamp: str | None,
        x__chatwoot__delivery: str | None,
        body: Any,
    ) -> Any:
        """Verify, sort and hand a webhook to a worker. Never 429 or 500."""
        try:
            raw = await request.body()
            reason = check_webhook(
                path_token=path_token,
                expected_path_token=self._settings.webhook_path_token,
                secret=self._settings.bot_secret,
                raw_body=raw,
                timestamp=x__chatwoot__timestamp,
                signature=x__chatwoot__signature,
                delivery_id=x__chatwoot__delivery,
                deliveries=self._deliveries,
                now=self._clock,
            )
            if reason is not None:
                self._count("rejected", reason)
                logger.warning("webhook rejected: %s", reason)
                return _problem(401, "not verified")
            payload = json.loads(raw)
            event = classify_event(payload if isinstance(payload, dict) else {})
            if event.account_id is not None and event.account_id != self._settings.account_id:
                self._count("ignored", "another account")
                return {"status": "ignored"}
            if event.kind == "ignored":
                self._count("ignored", event.why_ignored)
                return {"status": "ignored"}
            self._count("accepted", event.kind)
            content = payload.get("content")
            text = content if isinstance(content, str) else ""
            self._submit(lambda: self._handle(event, text))
            return {"status": "accepted"}
        except Exception as exc:
            # Answer 200 whatever happened: a 500 makes Chatwoot log the payload.
            self._count("ignored", f"internal error ({type(exc).__name__})")
            logger.error("webhook handling failed: %s", type(exc).__name__)
            return {"status": "ignored"}

    # ---- the worker -------------------------------------------------------

    def _handle(self, event: WebhookEvent, text: str) -> None:
        conversation_id = event.conversation_id or 0
        record: AuditRecord | None = None
        failure = ""
        for attempt, delay in enumerate((*RETRY_DELAYS, None)):
            try:
                record = self._handle_once(event, text)
            except _Refused as refused:
                self._count("rejected", refused.reason)
                logger.warning(
                    "webhook for conversation %s refused after re-fetch: %s",
                    conversation_id,
                    refused.reason,
                )
                return
            except Exception as exc:
                failure = f"internal error ({type(exc).__name__})"
                logger.warning(
                    "conversation %s attempt %d failed: %s",
                    conversation_id,
                    attempt + 1,
                    type(exc).__name__,
                )
            else:
                if record.decision not in ("busy", "incomplete"):
                    self._count("processed", record.decision)
                    return
                failure = record.reason
            if delay is not None:
                self._sleep(delay)
        self._count("processed", "fallback")
        if event.kind == "visitor_message":
            delivered = record.delivery if record is not None else ""
            self._fall_back(
                conversation_id, failure, holding_delivered=delivered in ("sent", "held")
            )

    def _handle_once(self, event: WebhookEvent, text: str) -> AuditRecord:
        conversation_id, message_id = event.conversation_id or 0, event.message_id or 0
        # The signature already proved Chatwoot sent this. Re-reading the
        # conversation (the one read a bot token may make) confirms it is in
        # this account and that the message is not newer than Chatwoot's
        # latest; when it is the latest, Chatwoot's own copy must agree on
        # who sent it and its text is what the core reads.
        conversation = self._api.get_conversation(conversation_id)
        if conversation.account_id != self._settings.account_id:
            raise _Refused(0, "", "another account")
        latest = conversation.latest
        if latest is None or message_id > latest.id:
            raise _Refused(0, "", "message not found in Chatwoot")
        if latest.id == message_id:
            self._check_facts(event, latest)
            text = latest.content
        if SEEN_LABEL not in conversation.labels:
            # Marks the conversation as one this service has seen, which is
            # what keeps Chatwoot's service-down rule (opened with no labels)
            # from firing when a person takes it over. Best effort.
            try:
                self._api.add_labels(conversation_id, (SEEN_LABEL,))
            except ChatwootError as exc:
                logger.warning("could not label conversation %s: %s", conversation_id, exc.status)
        contact = conversation.contact_id if conversation.contact_id is not None else "unknown"
        sender_key = make_sender_key(f"chatwoot-contact:{conversation.account_id}:{contact}")
        thread_key = str(conversation_id)
        if event.kind == "agent_reply":
            return self._pipeline.person_replied(
                CHANNEL, thread_key, sender_key, message_id=str(message_id)
            )
        return self._pipeline.process(
            IncomingMessage(
                channel=CHANNEL,
                thread_key=thread_key,
                provider_message_id=str(message_id),
                sender_key=sender_key,
                sender_address=f"chatwoot-conversation:{conversation_id}",
                text=text,
                received_at=datetime.fromtimestamp(self._clock(), tz=UTC),
            )
        )

    @staticmethod
    def _check_facts(event: WebhookEvent, facts: MessageFacts) -> None:
        if facts.private:
            raise _Refused(0, "", "re-fetched message is private")
        if event.kind == "visitor_message":
            if facts.message_type != "incoming" or facts.sender_type != "Contact":
                raise _Refused(0, "", "re-fetched message is not from the visitor")
        elif facts.message_type != "outgoing" or facts.sender_type != "User":
            raise _Refused(0, "", "re-fetched message is not from a person")

    def _fall_back(self, conversation_id: int, failure: str, *, holding_delivered: bool) -> None:
        """Tell the visitor a person will reply, and open the conversation. Best effort."""
        with self._lock:
            if conversation_id in self._fell_back:
                return
            self._fell_back.add(conversation_id)
        language = self._config.triage.default_language
        text = self._config.holding_text(language)
        if text and not holding_delivered:
            reply = OutboundReply(
                thread_key=str(conversation_id),
                in_reply_to="fallback",
                to_address=f"chatwoot-conversation:{conversation_id}",
                text=text,
                language=language,
                kind="holding",
            )
            try:
                self._fallback.deliver(reply, sender_key=f"fallback-{conversation_id}")
            except Exception as exc:
                logger.error("fallback holding message failed: %s", type(exc).__name__)
        request = HandOffRequest(
            purpose="hand_off",
            channel=CHANNEL,
            thread_key=str(conversation_id),
            message_id="fallback",
            conversation_id=None,
            category=self._config.triage.fallback_category,
            tier="needs_admin",
            reason="the assistant could not process this message",
            labels=("handoff", "inbox-core-unavailable"),
            note=(
                "inbox-core could not process the latest message, so it was not answered.\n"
                f"Reason: {failure[:120] or 'unknown'}."
            ),
        )
        # The same order as the pipeline's hand-off: open, then assign, so
        # Chatwoot notifies the assignee.
        for step in (
            self._handoff.add_internal_note,
            self._handoff.add_labels,
            self._handoff.open_for_person,
            self._handoff.assign,
        ):
            try:
                step(request)
            except Exception as exc:
                logger.error("fallback hand-off step failed: %s", type(exc).__name__)

    # ---- the draft tab ----------------------------------------------------

    async def draft_tab_page(self, request: Request) -> Any:
        """The tab page, framable only by Chatwoot."""
        page = resources.files("inbox_core.chatwoot").joinpath("static/tab.html").read_text()
        page = page.replace("{{CHATWOOT_ORIGIN}}", html.escape(self._settings.chatwoot_origin))
        return HTMLResponse(page, headers=self._page_headers())

    async def draft_tab_asset(self, request: Request, asset: str) -> Any:
        """The tab's script or stylesheet."""
        media = ASSET_TYPES.get(str(asset))
        if media is None:
            return _problem(404, "no such asset")
        text = resources.files("inbox_core.chatwoot").joinpath(f"static/{asset}").read_text()
        return Response(text, media_type=media, headers=self._page_headers())

    def _page_headers(self) -> dict[str, str]:
        policy = (
            "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "img-src 'self' data:; base-uri 'none'; form-action 'none'; "
            f"frame-ancestors {self._settings.chatwoot_origin}"
        )
        return {**SECURITY_HEADERS, "Content-Security-Policy": policy}

    def _refuse(self, refused: _Refused) -> JSONResponse:
        self._count("tab_rejected", refused.reason)
        logger.warning("draft tab refused: %s", refused.reason)
        return _problem(refused.status, refused.error)

    def _origin(self, request: Request) -> None:
        if not same_origin(request.headers.get("origin"), self._settings.public_origin):
            raise _Refused(403, "cross-origin request", "bad origin")

    def _session(self, request: Request) -> SessionClaims:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise _Refused(401, "sign in first", "no session")
        try:
            return self._signer.verify_session(token.strip(), account_id=self._settings.account_id)
        except TabAuthError as exc:
            raise _Refused(401, "sign in again", exc.reason) from None

    def _may_see(self, session: SessionClaims, conversation_id: int) -> None:
        """Chatwoot, asked with the bot's token, says which inbox this conversation is in."""
        try:
            conversation = self._api.get_conversation(conversation_id)
        except ChatwootError as exc:
            if exc.status == 404:
                raise _Refused(403, "not your conversation", "unknown conversation") from None
            raise _Refused(502, "Chatwoot is unavailable", "chatwoot unavailable") from None
        if conversation.account_id != session.account_id:
            raise _Refused(403, "not your conversation", "another account")
        if conversation.inbox_id not in session.inbox_ids:
            raise _Refused(403, "not your conversation", "inbox not allowed")

    def _draft_in(self, conversation_id: int, draft_id: int) -> HeldDraft:
        try:
            draft = self._pipeline.drafts.get(draft_id)
        except DraftNotFoundError:
            raise _Refused(404, "no such draft", "unknown draft") from None
        except DraftNotPendingError:
            raise _Refused(409, "this draft was already dealt with", "draft not pending") from None
        except DraftContentUnavailableError:
            raise _Refused(409, "this draft's text is gone", "draft content gone") from None
        if draft.channel != CHANNEL or draft.thread_key != str(conversation_id):
            raise _Refused(404, "no such draft", "draft in another conversation")
        return draft

    async def create_tab_session(self, request: Request, body: Any) -> Any:
        """Exchange the agent's Chatwoot token, checked with Chatwoot, for a session."""
        try:
            self._origin(request)
            client = request.client.host if request.client else "unknown"
            if not self._limiter.allow(client):
                raise _Refused(429, "too many attempts, wait a minute", "rate limited")
            token = str(body.chatwoot_token)
            return await run_in_threadpool(self._exchange, token)
        except _Refused as refused:
            return self._refuse(refused)

    def _exchange(self, token: str) -> Any:
        account = self._settings.account_id
        try:
            profile = self._api.profile(token)
            if account not in profile.roles:
                raise _Refused(403, "not a member of this account", "not in account")
            inboxes = self._api.inbox_ids(token)
        except ChatwootError as exc:
            if exc.status in (401, 403):
                raise _Refused(401, "Chatwoot did not accept that token", "token refused") from None
            raise _Refused(502, "Chatwoot is unavailable", "chatwoot unavailable") from None
        session_token, claims = self._signer.mint_session(
            agent_id=profile.id,
            account_id=account,
            inbox_ids=inboxes,
            ttl=self._settings.session_seconds,
        )
        logger.info("draft tab sign-in: agent %s", profile.id)
        return {
            "session_token": session_token,
            "agent_id": profile.id,
            "agent_name": profile.name,
            "expires_at": datetime.fromtimestamp(claims.expires_at, tz=UTC).isoformat(),
        }

    async def list_drafts(self, request: Request, conversation_id: int) -> Any:
        """Held drafts in a conversation this agent may see."""
        try:
            session = self._session(request)
            return await run_in_threadpool(self._list, session, int(conversation_id))
        except _Refused as refused:
            return self._refuse(refused)

    def _list(self, session: SessionClaims, conversation_id: int) -> Any:
        self._may_see(session, conversation_id)
        found = self._store.find_conversation(CHANNEL, str(conversation_id))
        drafts = self._pipeline.drafts.pending(found.id) if found is not None else ()
        return {
            "conversation_id": conversation_id,
            "mode": self._pipeline.drafts.mode.value,
            "drafts": [
                {
                    "id": d.id,
                    "kind": d.kind,
                    "language": d.language,
                    "text": d.text,
                    "sources": [{"id": s, "title": self._titles.get(s, "")} for s in d.sources],
                    "held_because": d.held_because,
                    "created_at": d.created_at.replace(tzinfo=UTC).isoformat(),
                    "category": d.category,
                    "tier": d.tier,
                    "confidence": d.confidence,
                    "classifier": d.classifier,
                    "action_token": self._signer.mint_action(
                        session, conversation_id=conversation_id, draft_id=d.id
                    ),
                }
                for d in drafts
            ],
        }

    def _authorise_action(
        self, request: Request, conversation_id: int, draft_id: int, action_token: str
    ) -> SessionClaims:
        self._origin(request)
        session = self._session(request)
        try:
            self._signer.verify_action(
                action_token, session, conversation_id=conversation_id, draft_id=draft_id
            )
        except TabAuthError as exc:
            status = 401 if exc.reason in ("expired token", "malformed token") else 403
            raise _Refused(status, "this action is not allowed", exc.reason) from None
        return session

    async def send_draft(
        self, request: Request, conversation_id: int, draft_id: int, body: Any
    ) -> Any:
        """Send a draft as the signed-in agent's decision."""
        try:
            session = self._authorise_action(
                request, int(conversation_id), int(draft_id), str(body.action_token)
            )
            return await run_in_threadpool(
                self._send, session, int(conversation_id), int(draft_id), str(body.text)
            )
        except _Refused as refused:
            return self._refuse(refused)

    def _send(self, session: SessionClaims, conversation_id: int, draft_id: int, text: str) -> Any:
        self._may_see(session, conversation_id)
        self._draft_in(conversation_id, draft_id)
        try:
            result = self._pipeline.drafts.send(draft_id, reviewer=session.reviewer, text=text)
        except DraftNotPendingError:
            raise _Refused(409, "this draft was already dealt with", "draft not pending") from None
        except ReleaseRefusedError:
            raise _Refused(409, "delivery is off", "delivery off") from None
        except DraftSendFailedError:
            raise _Refused(502, "Chatwoot refused the message", "send failed") from None
        except ValueError:
            raise _Refused(400, "a reply cannot be empty", "empty text") from None
        how = "edited" if result.outcome == "sent_edited" else "as written"
        self._after_review(
            conversation_id, f"inbox-core draft {draft_id} sent {how} by agent {session.agent_id}."
        )
        return {"draft_id": draft_id, "outcome": result.outcome, "reviewer": result.reviewer}

    async def discard_draft(
        self, request: Request, conversation_id: int, draft_id: int, body: Any
    ) -> Any:
        """Discard a draft."""
        try:
            session = self._authorise_action(
                request, int(conversation_id), int(draft_id), str(body.action_token)
            )
            return await run_in_threadpool(
                self._discard, session, int(conversation_id), int(draft_id)
            )
        except _Refused as refused:
            return self._refuse(refused)

    def _discard(self, session: SessionClaims, conversation_id: int, draft_id: int) -> Any:
        self._may_see(session, conversation_id)
        self._draft_in(conversation_id, draft_id)
        try:
            result = self._pipeline.drafts.discard(draft_id, reviewer=session.reviewer)
        except DraftNotPendingError:
            raise _Refused(409, "this draft was already dealt with", "draft not pending") from None
        self._after_review(
            conversation_id, f"inbox-core draft {draft_id} discarded by agent {session.agent_id}."
        )
        return {"draft_id": draft_id, "outcome": result.outcome, "reviewer": result.reviewer}

    def _after_review(self, conversation_id: int, text: str) -> None:
        """A staff note saying who did what, and the pending label off once nothing waits."""
        self._note(conversation_id, text)
        found = self._store.find_conversation(CHANNEL, str(conversation_id))
        if found is not None and not self._store.held_for_review(found.id):
            try:
                self._api.remove_labels(conversation_id, (REVIEW_LABEL,))
            except ChatwootError as exc:
                logger.warning("could not clear the review label: %s", exc.status)

    def _note(self, conversation_id: int, text: str) -> None:
        try:
            self._api.add_private_note(conversation_id, text)
        except ChatwootError as exc:
            logger.warning("review note failed: %s", exc.status)


def create_app(service: ChatwootService) -> FastAPI:
    """The FastAPI app: the generated router over ``service``, docs pages off."""
    app = FastAPI(
        title="inbox-core Chatwoot connection", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.include_router(build_router(service))

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default 422 echoes the input back, which could be a draft's
        # text or a token. Answer with a fixed phrase instead. A malformed
        # webhook is an unverified one.
        if request.url.path.startswith("/chatwoot/webhook/"):
            service._count("rejected", "malformed")
            return _problem(401, "not verified")
        return _problem(422, "invalid request")

    return app

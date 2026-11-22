"""The pipeline: guard, triage, handle, deliver, hand off, and one audit record.

Every message takes the same steps, in this order:

1. **Dedupe.** A message already handled is a ``duplicate`` and nothing happens.
2. **Record.** The conversation and the inbound row are written before any
   side effect. A conversation a person owns is ``left_for_person``.
3. **Guard.** A guard may drop the message or send it straight to a person.
4. **Triage.** The classifier reports signals (with bounded retries; if it
   stays unavailable, the message goes to a person) and ``derive_tier`` decides.
5. **Handle and deliver.** Only an ``auto_answer`` message reaches a handler,
   and only within the per-conversation reply cap. Its reply goes through
   :class:`inbox_core.delivery.Delivery`, which applies the mode, the language
   gate and the caps.
6. **Hand off.** Everything else - an escalating tier, a handler that declined
   or failed, a failed delivery, delivery being off - is handed to a person: a
   holding message (through the same delivery rules), a notification, and the
   conversation paused.

It fails closed. If a person cannot be told, the message is left unhandled
(``incomplete``) so it is retried, and the conversation is not paused. Any
unexpected error is reported the same way.

Exactly one :class:`AuditRecord` is emitted per call to :meth:`Pipeline.process`.
It holds ids, the category, tier, decision, handler, mode and delivery outcome,
and never any message content. Log lines carry ids, decisions and exception
type names only.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from inbox_core.config import ClientConfig
from inbox_core.delivery import Delivery, DeliveryMode, DeliveryResult, ReplySink, Route, SendCaps
from inbox_core.guards import Guard, default_guards, run_guards
from inbox_core.handlers import HandlerRegistry, HandlerRequest
from inbox_core.handoff import (
    HandOffActions,
    HandOffPurpose,
    HandOffRequest,
    NoHandOffActions,
    handoff_labels,
    handoff_note,
)
from inbox_core.messages import IncomingMessage, OutboundReply
from inbox_core.store import (
    Conversation,
    ConversationStore,
    StoredMessage,
    StoreSendCaps,
    as_naive_utc,
)
from inbox_core.triage import (
    RetryingClassifier,
    Tier,
    TriageClassifier,
    TriageDecision,
    TriageSignals,
    TriageUnavailable,
    decide,
    escalation_reason,
)

__all__ = [
    "AuditRecord",
    "AuditSink",
    "Decision",
    "Escalation",
    "InMemoryAuditSink",
    "JsonlAuditSink",
    "LoggingAuditSink",
    "Notifier",
    "Pipeline",
]

logger = logging.getLogger("inbox_core.pipeline")

Decision = Literal[
    "duplicate",
    "left_for_person",
    "dropped",
    "skipped",
    "answered",
    "answer_held",
    "handed_off",
    "incomplete",
    "person_replied",
]
"""What the pipeline did with a message; ``person_replied`` comes from ``person_replied``."""

UNAVAILABLE = "unavailable"
HOLDING_KIND = "holding"


@dataclass(frozen=True)
class Escalation:
    """What a person is told when a message is handed to them. Ids and reasons only."""

    channel: str
    thread_key: str
    message_id: str
    conversation_id: int | None
    category: str
    tier: str
    reason: str


@runtime_checkable
class Notifier(Protocol):
    """Tells a person about a hand-off. Raises if they could not be told."""

    def notify(self, escalation: Escalation) -> None:
        """Deliver ``escalation`` to whoever handles this inbox."""
        ...


@dataclass(frozen=True)
class AuditRecord:
    """One message's outcome. Holds no message content, by construction.

    ``at`` is naive UTC in ISO format. ``delivery`` is ``none``, ``held``,
    ``sent``, ``failed`` or empty when nothing was attempted.
    ``handoff_failures`` names the best-effort hand-off steps that failed
    (see :mod:`inbox_core.handoff`).
    """

    at: str
    channel: str
    thread_key: str
    message_id: str
    conversation_id: int | None
    category: str
    tier: str
    confidence: float | None
    classifier: str
    decision: Decision
    reason: str
    handler: str
    mode: str
    delivery: str
    held_because: str
    sources: tuple[str, ...]
    guard: str
    tags: tuple[str, ...]
    handoff_failures: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """A JSON-ready dictionary."""
        data = asdict(self)
        data["sources"] = list(self.sources)
        data["tags"] = list(self.tags)
        data["handoff_failures"] = list(self.handoff_failures)
        return data


@runtime_checkable
class AuditSink(Protocol):
    """Where audit records go."""

    def emit(self, record: AuditRecord) -> None:
        """Keep ``record``."""
        ...


@dataclass
class InMemoryAuditSink:
    """Keeps records in a list. For tests and demos."""

    records: list[AuditRecord] = field(default_factory=list)

    def emit(self, record: AuditRecord) -> None:
        """Append ``record``."""
        self.records.append(record)


class JsonlAuditSink:
    """Appends one JSON line per record to a file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def emit(self, record: AuditRecord) -> None:
        """Append ``record`` as one line."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")


class LoggingAuditSink:
    """Writes each record as JSON to a logger (``inbox_core.audit`` by default)."""

    def __init__(self, logger_name: str = "inbox_core.audit", level: int = logging.INFO) -> None:
        self._logger = logging.getLogger(logger_name)
        self._level = level

    def emit(self, record: AuditRecord) -> None:
        """Log ``record``."""
        self._logger.log(self._level, "audit %s", json.dumps(record.to_dict(), sort_keys=True))


class _Incomplete(Exception):  # noqa: N818 - private control flow, not an error type
    """A person could not be told. The message stays unhandled for a retry."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _Unfinished(Exception):  # noqa: N818 - private control flow, not an error type
    """An earlier attempt to deliver this reply did not finish; do not repeat it."""


class _PersonTookOver(Exception):  # noqa: N818 - private control flow, not an error type
    """A person replied while this message was being processed; stay silent."""


PERSON_REPLIED = "a person replied in this conversation"


@dataclass
class _Draft:
    """The audit record being built while one message is processed."""

    message: IncomingMessage
    mode: str
    conversation_id: int | None = None
    category: str = ""
    tier: str = ""
    confidence: float | None = None
    classifier: str = ""
    decision: Decision = "incomplete"
    reason: str = ""
    handler: str = ""
    delivery: str = ""
    held_because: str = ""
    sources: tuple[str, ...] = ()
    guard: str = ""
    tags: tuple[str, ...] = ()
    handoff_failures: list[str] = field(default_factory=list)

    def take(self, decision: TriageDecision) -> None:
        self.category = decision.category
        self.tier = decision.tier
        self.confidence = round(float(decision.confidence), 4)
        self.classifier = decision.classifier

    def freeze(self, at: datetime) -> AuditRecord:
        return AuditRecord(
            at=as_naive_utc(at).isoformat(),
            channel=self.message.channel,
            thread_key=self.message.thread_key,
            message_id=self.message.provider_message_id,
            conversation_id=self.conversation_id,
            category=self.category,
            tier=self.tier,
            confidence=self.confidence,
            classifier=self.classifier,
            decision=self.decision,
            reason=self.reason,
            handler=self.handler,
            mode=self.mode,
            delivery=self.delivery,
            held_because=self.held_because,
            sources=self.sources,
            guard=self.guard,
            tags=self.tags,
            handoff_failures=tuple(self.handoff_failures),
        )


class Pipeline:
    """Processes one message at a time through the steps in the module docstring.

    ``caps`` defaults to :class:`inbox_core.store.StoreSendCaps` over ``store``
    with the limits from the configuration. ``guards`` defaults to
    :func:`inbox_core.guards.default_guards`; pass your own list (usually the
    defaults plus channel guards) to change it. ``mode_override`` replaces the
    configured mode, for a runtime switch read with
    :func:`inbox_core.delivery.parse_mode`. ``handoff_actions`` is the
    channel's shared-inbox side of a hand-off (see :mod:`inbox_core.handoff`);
    without it nothing beyond the holding message and the notifier happens.
    """

    def __init__(
        self,
        *,
        config: ClientConfig,
        classifier: TriageClassifier,
        handlers: HandlerRegistry,
        sink: ReplySink,
        store: ConversationStore,
        notifier: Notifier,
        audit: AuditSink,
        caps: SendCaps | None = None,
        guards: Iterable[Guard] | None = None,
        mode_override: DeliveryMode | None = None,
        handoff_actions: HandOffActions | None = None,
        classifier_attempts: int = 3,
        backoff: tuple[float, ...] = (0.5, 2.0),
        sleep: Callable[[float], object] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        handlers.validate(config)
        policy = config.delivery
        self._config = config
        self._classifier = classifier
        self._retrying = RetryingClassifier(
            classifier, attempts=classifier_attempts, backoff=backoff, sleep=sleep
        )
        self._handlers = handlers
        self._store = store
        self._notifier = notifier
        self._audit = audit
        self._guards = tuple(guards) if guards is not None else default_guards()
        self._actions = handoff_actions if handoff_actions is not None else NoHandOffActions()
        self._clock = clock
        self._mode = mode_override if mode_override is not None else policy.mode
        self._delivery = Delivery(
            sink,
            mode=self._mode,
            auto_languages=policy.auto_languages,
            caps=caps
            if caps is not None
            else StoreSendCaps(
                store,
                daily_cap=policy.daily_send_cap,
                per_sender_cap=policy.per_sender_daily_cap,
                timezone=policy.zone,
                clock=clock,
            ),
        )

    def process(self, message: IncomingMessage) -> AuditRecord:
        """Take one message through every step. Always returns its audit record."""
        draft = _Draft(message, self._mode.value)
        try:
            self._run(message, draft)
        except _Incomplete as exc:
            draft.decision = "incomplete"
            draft.reason = exc.reason
            logger.error("message %s: %s", message.provider_message_id, exc.reason)
        except Exception as exc:
            draft.decision = "incomplete"
            draft.reason = f"internal error ({type(exc).__name__})"
            logger.error(
                "message %s: internal error %s", message.provider_message_id, type(exc).__name__
            )
            self._try_notify(message, draft)

        record = draft.freeze(self._clock())
        try:
            self._audit.emit(record)
        except Exception as exc:
            logger.error(
                "audit sink failed for %s: %s", message.provider_message_id, type(exc).__name__
            )
        logger.info(
            "message %s on %s: %s", message.provider_message_id, message.channel, record.decision
        )
        return record

    def _run(self, message: IncomingMessage, draft: _Draft) -> None:
        store = self._store
        if store.is_handled(message.channel, message.provider_message_id):
            draft.decision = "duplicate"
            return

        conversation = store.conversation_for(
            message.channel, message.thread_key, message.sender_key
        )
        draft.conversation_id = conversation.id
        row = store.record_inbound(conversation.id, message)

        if conversation.status != "bot":
            store.mark_handled(row.id, "left_for_person")
            draft.decision = "left_for_person"
            draft.reason = "a person owns this conversation"
            return

        try:
            self._decide_and_act(message, conversation, row, draft)
        except _PersonTookOver:
            store.mark_handled(row.id, "left_for_person")
            draft.decision = "left_for_person"
            draft.reason = "a person replied while this message was processed"
            draft.delivery = ""

    def _decide_and_act(
        self,
        message: IncomingMessage,
        conversation: Conversation,
        row: StoredMessage,
        draft: _Draft,
    ) -> None:
        store = self._store
        guarded = run_guards(self._guards, message)
        if guarded is not None:
            draft.guard = guarded.guard
            draft.reason = guarded.reason
            if guarded.action == "drop":
                store.mark_handled(row.id, "dropped")
                draft.decision = "dropped"
                return
            unclassified = self._fallback(classifier="")
            draft.take(unclassified)
            self._hand_off(message, conversation, row, unclassified, draft)
            return

        decision, shadow = self._triage(message)
        store.record_triage(row.id, decision, shadow)
        draft.take(decision)

        if decision.tier == "skip":
            store.mark_handled(row.id, "skipped")
            draft.decision = "skipped"
            return

        if decision.tier == "auto_answer":
            reason = self._answer(message, conversation, row, decision, draft)
            if reason is None:
                return
            draft.reason = reason
        elif decision.classifier == UNAVAILABLE:
            draft.reason = "classifier unavailable"
        else:
            draft.reason = escalation_reason(decision.signals(), self._config.triage)
        self._hand_off(message, conversation, row, decision, draft)

    def _fallback(self, *, classifier: str) -> TriageDecision:
        policy = self._config.triage
        return TriageDecision(
            category=policy.fallback_category,
            language="other",
            confidence=0.0,
            asks_for_human=False,
            mentions_money_or_commitment=False,
            classifier=classifier,
            tier="needs_admin",
        )

    def _triage(self, message: IncomingMessage) -> tuple[TriageDecision, TriageSignals | None]:
        try:
            found = self._retrying.classify(message)
        except TriageUnavailable as exc:
            logger.warning("message %s: %s", message.provider_message_id, type(exc).__name__)
            return self._fallback(classifier=UNAVAILABLE), None
        shadow = getattr(self._classifier, "last_shadow", None)
        return decide(found, self._config.triage), shadow

    def _answer(
        self,
        message: IncomingMessage,
        conversation: Conversation,
        row: StoredMessage,
        decision: TriageDecision,
        draft: _Draft,
    ) -> str | None:
        """Answer the message, or return why a person must instead."""
        if self._mode is DeliveryMode.OFF:
            return "delivery is off"
        cap = self._config.delivery.max_bot_replies_per_conversation
        # A retry of this same message resumes its own earlier reply (which
        # _deliver_once reports rather than repeats), so that reply must not
        # count against the cap it already passed.
        resuming = any(m.kind != HOLDING_KIND for m in self._store.outbound_for(row.id))
        if conversation.bot_reply_count >= cap and not resuming:
            return f"bot reply cap reached ({cap} per conversation)"

        handler = self._handlers.for_category(decision.category)
        draft.handler = handler.name
        try:
            result = handler.handle(HandlerRequest(message, decision, self._config))
        except Exception as exc:
            logger.warning(
                "handler %s failed for %s: %s",
                handler.name,
                message.provider_message_id,
                type(exc).__name__,
            )
            return f"handler {handler.name} failed ({type(exc).__name__})"
        draft.tags = result.tags
        if result.outcome == "hand_off":
            return result.reason

        reply = OutboundReply(
            thread_key=message.thread_key,
            in_reply_to=message.provider_message_id,
            to_address=message.sender_address,
            text=result.text,
            language=decision.language,
            kind=result.kind,
            sources=tuple(source.id for source in result.sources),
        )
        draft.sources = reply.sources
        try:
            delivered = self._deliver_once(
                conversation, row, reply, requires_approval=result.requires_approval
            )
        except _Unfinished:
            return "an earlier delivery attempt did not finish"
        except _PersonTookOver:
            raise
        except Exception as exc:
            logger.warning(
                "delivery failed for %s: %s", message.provider_message_id, type(exc).__name__
            )
            return f"delivery failed ({type(exc).__name__})"

        draft.delivery = delivered.action
        draft.held_because = delivered.held_because
        if delivered.action == "held":
            self._bring_in_a_person("review", message, decision.tier, delivered.held_because, draft)
        draft.decision = "answered" if delivered.action == "sent" else "answer_held"
        self._store.mark_handled(row.id, draft.decision)
        return None

    def _deliver_once(
        self,
        conversation: Conversation,
        row: StoredMessage,
        reply: OutboundReply,
        *,
        requires_approval: bool = False,
    ) -> DeliveryResult:
        """Deliver ``reply`` unless an earlier attempt for this message already did.

        The outbound row is written as ``pending`` before delivery. On a retry,
        a finished earlier attempt is reported instead of repeated, and an
        unfinished or failed one raises :class:`_Unfinished`: it may or may not
        have reached the public, and the safe reading is "do not send again".
        """
        self._ensure_bot_owns(conversation.id)
        earlier = [m for m in self._store.outbound_for(row.id) if m.kind == reply.kind]
        if earlier:
            last = earlier[-1]
            if last.action in ("pending", "failed"):
                raise _Unfinished
            if last.action == "sent":
                return DeliveryResult(Route.SEND, "sent", last.provider_ref, "")
            if last.action == "held":
                return DeliveryResult(
                    Route.HOLD, "held", last.provider_ref, "held on an earlier attempt"
                )
            return DeliveryResult(Route.NONE, "none", None, "delivery is off")

        outbound = self._store.begin_outbound(
            conversation.id,
            reply_to_id=row.id,
            kind=reply.kind,
            language=reply.language,
            text=reply.text,
            sources=reply.sources,
        )
        try:
            result = self._delivery.deliver(
                reply, sender_key=conversation.sender_key, requires_approval=requires_approval
            )
        except Exception:
            self._store.finish_outbound(outbound.id, action="failed", provider_ref=None)
            raise
        self._store.finish_outbound(
            outbound.id, action=result.action, provider_ref=result.provider_ref
        )
        return result

    def _hand_off(
        self,
        message: IncomingMessage,
        conversation: Conversation,
        row: StoredMessage,
        decision: TriageDecision,
        draft: _Draft,
    ) -> None:
        """Holding message, notification, pause, in that order; then handled."""
        policy = self._config.triage
        language = (
            decision.language
            if decision.language in policy.languages
            else (policy.default_language)
        )
        text = self._config.holding_text(language)
        draft.delivery = "none"
        if text:
            holding = OutboundReply(
                thread_key=message.thread_key,
                in_reply_to=message.provider_message_id,
                to_address=message.sender_address,
                text=text,
                language=language,
                kind=HOLDING_KIND,
            )
            try:
                delivered = self._deliver_once(conversation, row, holding)
                draft.delivery = delivered.action
                draft.held_because = delivered.held_because
            except _Unfinished:
                draft.delivery = "none"
            except _PersonTookOver:
                raise
            except Exception as exc:
                # A failed holding message must not stop the hand-off itself.
                draft.delivery = "failed"
                logger.warning(
                    "holding message failed for %s: %s",
                    message.provider_message_id,
                    type(exc).__name__,
                )

        tier: Tier = decision.tier
        self._ensure_bot_owns(conversation.id)
        self._bring_in_a_person("hand_off", message, tier, draft.reason, draft)
        try:
            self._notifier.notify(self._escalation(message, draft, tier))
        except Exception as exc:
            raise _Incomplete(f"could not notify a person ({type(exc).__name__})") from None
        self._store.pause(conversation.id, f"{tier}: {draft.reason}"[:256])
        self._store.mark_handled(row.id, "handed_off")
        draft.decision = "handed_off"

    def _ensure_bot_owns(self, conversation_id: int) -> None:
        """Raise :class:`_PersonTookOver` if a person replied since processing began."""
        current = self._store.get_conversation(conversation_id)
        if current is not None and current.status == "paused_manual":
            raise _PersonTookOver

    def person_replied(
        self, channel: str, thread_key: str, sender_key: str, *, message_id: str
    ) -> AuditRecord:
        """Record that a person replied in this conversation; the bot stays silent there.

        Every later message in the conversation is ``left_for_person`` until
        :meth:`resume`. A message already being processed checks again right
        before it delivers anything, so the bot does not answer over the
        person. ``sender_key`` is the visitor's, used only if the conversation
        is new to the store. ``message_id`` is the person's message, for the
        audit record. Returns that record, with decision ``person_replied``.
        """
        incoming = IncomingMessage(
            channel=channel,
            thread_key=thread_key,
            provider_message_id=message_id,
            sender_key=sender_key,
            sender_address="",
            text="",
        )
        draft = _Draft(incoming, self._mode.value)
        try:
            conversation = self._store.conversation_for(channel, thread_key, sender_key)
            draft.conversation_id = conversation.id
            self._store.pause_manual(conversation.id)
            draft.decision = "person_replied"
            draft.reason = PERSON_REPLIED
        except Exception as exc:
            draft.decision = "incomplete"
            draft.reason = f"internal error ({type(exc).__name__})"
            logger.error("person reply %s: internal error %s", message_id, type(exc).__name__)
        record = draft.freeze(self._clock())
        try:
            self._audit.emit(record)
        except Exception as exc:
            logger.error("audit sink failed for %s: %s", message_id, type(exc).__name__)
        return record

    def resume(self, channel: str, thread_key: str) -> bool:
        """Give a conversation back to the bot. A person's decision; False if it is unknown.

        The bot reply count is kept, so resuming does not reset the
        per-conversation cap.
        """
        found = self._store.find_conversation(channel, thread_key)
        if found is None:
            return False
        self._store.resume(found.id)
        return True

    def _bring_in_a_person(
        self,
        purpose: HandOffPurpose,
        message: IncomingMessage,
        tier: str,
        reason: str,
        draft: _Draft,
    ) -> None:
        """Run the channel's hand-off steps in order; only failing to open is fatal."""
        category = draft.category or self._config.triage.fallback_category
        request = HandOffRequest(
            purpose=purpose,
            channel=message.channel,
            thread_key=message.thread_key,
            message_id=message.provider_message_id,
            conversation_id=draft.conversation_id,
            category=category,
            tier=tier or "needs_admin",
            reason=reason,
            labels=handoff_labels(
                purpose, category, classifier_unavailable=draft.classifier == UNAVAILABLE
            ),
            note=handoff_note(
                purpose,
                category=category,
                tier=tier or "needs_admin",
                reason=reason,
                sources=draft.sources,
            ),
        )
        actions = self._actions
        for name, step in (
            ("add_internal_note", actions.add_internal_note),
            ("add_labels", actions.add_labels),
            ("assign", actions.assign),
        ):
            try:
                step(request)
            except Exception as exc:
                draft.handoff_failures.append(name)
                logger.warning(
                    "hand-off step %s failed for %s: %s",
                    name,
                    message.provider_message_id,
                    type(exc).__name__,
                )
        try:
            actions.open_for_person(request)
        except Exception as exc:
            raise _Incomplete(
                f"could not open the conversation for a person ({type(exc).__name__})"
            ) from None

    def _escalation(self, message: IncomingMessage, draft: _Draft, tier: str) -> Escalation:
        return Escalation(
            channel=message.channel,
            thread_key=message.thread_key,
            message_id=message.provider_message_id,
            conversation_id=draft.conversation_id,
            category=draft.category or self._config.triage.fallback_category,
            tier=tier or "needs_admin",
            reason=draft.reason,
        )

    def _try_notify(self, message: IncomingMessage, draft: _Draft) -> None:
        try:
            self._notifier.notify(self._escalation(message, draft, draft.tier))
        except Exception as exc:
            logger.error(
                "could not notify a person about %s: %s",
                message.provider_message_id,
                type(exc).__name__,
            )

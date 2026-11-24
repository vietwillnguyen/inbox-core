"""Building the Chatwoot service from its settings.

:func:`build_service` assembles the parts: the SQL store (encryption is
required, because the store is the draft review queue), the Chatwoot API with
the bot's token, the sink and hand-off actions, the classifier, the handlers
and the pipeline. Everything is a parameter, so a deployment with its own
classifier or handlers calls it with them.

Classifiers by ``INBOX_CORE_CLASSIFIER``:

- ``litellm`` (default): :class:`inbox_core.adapters.litellm.LiteLLMClassifier`,
  with a LiteLLM generator for grounded answers. Needs ``inbox-core[litellm]``
  and a provider key in the environment. ``INBOX_CORE_MODEL`` names the model
  (Gemini Flash-Lite by default); ``INBOX_CORE_MODEL_API_BASE`` and
  ``INBOX_CORE_MODEL_API_KEY`` point both at a LiteLLM gateway instead of the
  provider, for example ``litellm_proxy/<model group>`` behind
  ``http://litellm:4000`` with the gateway's key.
- ``example-keywords``: the worked example's deterministic keyword stand-in
  and an extractive generator. Not a model and not accurate; for local runs
  and the end-to-end suite, which need no network beyond Chatwoot.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import create_engine

from inbox_core.chatwoot.api import ChatwootApi
from inbox_core.chatwoot.service import ChatwootService, Submit, thread_submit
from inbox_core.chatwoot.settings import ChatwootSettings, SettingsError
from inbox_core.chatwoot.sink import ChatwootHandOff, ChatwootReplySink
from inbox_core.config import ClientConfig, load_config
from inbox_core.crypto import parse_keys
from inbox_core.delivery import Delivery, DeliveryMode, InMemorySendCaps, parse_mode
from inbox_core.handlers import (
    ExtractiveGenerator,
    Generator,
    GroundedAnswer,
    Handler,
    HandlerRegistry,
    Template,
)
from inbox_core.knowledge import InMemoryRetriever, KnowledgeEntry, load_markdown_knowledge
from inbox_core.pipeline import AuditSink, Escalation, JsonlAuditSink, LoggingAuditSink, Pipeline
from inbox_core.store.sqlalchemy import SqlAlchemyConversationStore, create_schema
from inbox_core.triage import TriageClassifier

__all__ = ["LoggingNotifier", "ServiceParts", "build_service", "default_handlers"]

logger = logging.getLogger("inbox_core.chatwoot")


class LoggingNotifier:
    """Logs each hand-off by ids. In Chatwoot, opening the conversation is what tells a person."""

    def notify(self, escalation: Escalation) -> None:
        """Log ``escalation``'s ids, category, tier and reason."""
        logger.info(
            "hand-off conversation %s message %s: %s %s (%s)",
            escalation.thread_key,
            escalation.message_id,
            escalation.category,
            escalation.tier,
            escalation.reason,
        )


@dataclass(frozen=True)
class ServiceParts:
    """What :func:`build_service` built, for tests and for operators' own wiring."""

    service: ChatwootService
    pipeline: Pipeline
    store: SqlAlchemyConversationStore
    api: ChatwootApi


def default_handlers(
    config: ClientConfig,
    retriever: InMemoryRetriever,
    generator: Generator,
    *,
    min_score: float = 2.0,
) -> HandlerRegistry:
    """A template for each auto-answered category that has one, else a grounded answer.

    The extractive stand-in answers from the best passage alone, so it is given
    only that one: the sources a reply cites must be the ones it was written from.
    """
    limit = 1 if isinstance(generator, ExtractiveGenerator) else 3
    handlers: dict[str, Handler] = {}
    for name in sorted(config.triage.auto_answer_categories):
        if name in config.templates:
            handlers[name] = Template.from_config(config, name)
        else:
            handlers[name] = GroundedAnswer(
                retriever, generator, min_score=min_score, limit=limit, cite=True
            )
    return HandlerRegistry(handlers)


def build_service(
    settings: ChatwootSettings,
    *,
    env: Mapping[str, str] | None = None,
    config: ClientConfig | None = None,
    classifier: TriageClassifier | None = None,
    handlers: HandlerRegistry | None = None,
    audit: AuditSink | None = None,
    transport: httpx.BaseTransport | None = None,
    submit: Submit | None = None,
    sleep: Callable[[float], object] | None = None,
    clock: Callable[[], float] | None = None,
) -> ServiceParts:
    """Every part of the service, from settings and the ``INBOX_CORE_*`` environment."""
    source = os.environ if env is None else env
    cipher = parse_keys(settings.encryption_keys, setting="INBOX_CORE_ENCRYPTION_KEYS")
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    create_schema(engine)
    store = SqlAlchemyConversationStore(engine, cipher=cipher)
    try:
        api = ChatwootApi(
            settings.chatwoot_url, settings.account_id, settings.bot_token, transport=transport
        )

        entries: tuple[KnowledgeEntry, ...] = ()
        retriever = InMemoryRetriever(())
        if config is None or handlers is None:
            from inbox_core.examples.demo import EXAMPLE_DIR, example_retriever

            config_path = source.get("INBOX_CORE_CONFIG", "").strip()
            knowledge_path = source.get("INBOX_CORE_KNOWLEDGE", "").strip()
            config = config or load_config(Path(config_path or EXAMPLE_DIR / "client.toml"))
            if knowledge_path:
                entries = load_markdown_knowledge(Path(knowledge_path))
                retriever = InMemoryRetriever(entries)
            else:
                retriever = example_retriever()
                entries = load_markdown_knowledge(EXAMPLE_DIR / "knowledge.md")
        kind = source.get("INBOX_CORE_CLASSIFIER", "litellm").strip()
        generator: Generator
        if kind == "example-keywords":
            from inbox_core.examples.demo import KeywordClassifier

            classifier = classifier or KeywordClassifier()
            generator = ExtractiveGenerator()
        elif kind == "litellm":
            from inbox_core.adapters.litellm import (
                DEFAULT_MODEL,
                LiteLLMClassifier,
                LiteLLMGenerator,
            )

            model = source.get("INBOX_CORE_MODEL", "").strip() or DEFAULT_MODEL
            api_base = source.get("INBOX_CORE_MODEL_API_BASE", "").strip() or None
            api_key = source.get("INBOX_CORE_MODEL_API_KEY", "").strip() or None
            classifier = classifier or LiteLLMClassifier(
                config, model=model, api_base=api_base, api_key=api_key
            )
            generator = LiteLLMGenerator(model=model, api_base=api_base, api_key=api_key)
        else:
            raise SettingsError("INBOX_CORE_CLASSIFIER must be litellm or example-keywords")
        handlers = handlers or default_handlers(config, retriever, generator)
        raw_mode = source.get("INBOX_CORE_MODE", "").strip()
        mode = parse_mode(raw_mode) if raw_mode else None
        audit_path = source.get("INBOX_CORE_AUDIT_PATH", "").strip()
        audit = audit or (JsonlAuditSink(audit_path) if audit_path else LoggingAuditSink())

        sink = ChatwootReplySink(api)
        handoff = ChatwootHandOff(api, assignee_id=settings.assignee_id)
        pipeline = Pipeline(
            config=config,
            classifier=classifier,
            handlers=handlers,
            sink=sink,
            store=store,
            notifier=LoggingNotifier(),
            audit=audit,
            handoff_actions=handoff,
            mode_override=mode,
        )
        effective = mode if mode is not None else config.delivery.mode
        fallback = Delivery(
            sink,
            mode=effective,
            auto_languages=config.delivery.auto_languages,
            caps=InMemorySendCaps.from_policy(config.delivery),
        )
        service = ChatwootService(
            settings=settings,
            config=config,
            pipeline=pipeline,
            store=store,
            api=api,
            handoff=handoff,
            fallback_delivery=fallback,
            source_titles={entry.id: entry.title for entry in entries},
            submit=submit or thread_submit,
            sleep=sleep or time.sleep,
            clock=clock or time.time,
        )
        if effective is DeliveryMode.OFF:
            logger.warning("delivery mode is off: nothing will be sent or drafted")
    except BaseException:
        # Nothing else holds the engine yet; do not leak its connections.
        engine.dispose()
        raise
    return ServiceParts(service, pipeline, store, api)

"""inbox-core: the fail-closed triage and delivery core of an inbox assistant.

A message arrives from any channel, is guarded, triaged into a tier that is
decided in code, handled by a pluggable handler, delivered under an off, draft
or auto mode with caps, and recorded for audit.

The names here are the everyday surface. Everything else is in its module:
:mod:`inbox_core.guards`, :mod:`inbox_core.knowledge`,
:mod:`inbox_core.adapters`, :mod:`inbox_core.store`, :mod:`inbox_core.crypto`,
:mod:`inbox_core.testing` and :mod:`inbox_core.evals`.

The package is pre-release and its interface may change between minor versions.
"""

import logging
from importlib.metadata import PackageNotFoundError, version

from inbox_core.config import (
    CategoryRule,
    ClientConfig,
    ConfigError,
    DeliveryPolicy,
    Organisation,
    TriagePolicy,
    load_config,
)
from inbox_core.delivery import Delivery, DeliveryMode, ReplySink
from inbox_core.handlers import (
    GroundedAnswer,
    Handler,
    HandlerRegistry,
    HandlerRequest,
    HandlerResult,
    HandOff,
    Template,
)
from inbox_core.messages import IncomingMessage, OutboundReply, make_sender_key
from inbox_core.pipeline import AuditRecord, Escalation, Notifier, Pipeline
from inbox_core.store import ConversationStore
from inbox_core.triage import (
    TriageClassifier,
    TriageDecision,
    TriageSignals,
    TriageUnavailable,
    decide,
    derive_tier,
)

try:
    __version__ = version("inbox-core")
except PackageNotFoundError:  # pragma: no cover - only when run from a bare source tree
    __version__ = "0.0.0"

# A library attaches a NullHandler and nothing else: where log records go is
# the host application's decision.
_root = logging.getLogger("inbox_core")
if not any(isinstance(handler, logging.NullHandler) for handler in _root.handlers):
    _root.addHandler(logging.NullHandler())

__all__ = [
    "AuditRecord",
    "CategoryRule",
    "ClientConfig",
    "ConfigError",
    "ConversationStore",
    "Delivery",
    "DeliveryMode",
    "DeliveryPolicy",
    "Escalation",
    "GroundedAnswer",
    "HandOff",
    "Handler",
    "HandlerRegistry",
    "HandlerRequest",
    "HandlerResult",
    "IncomingMessage",
    "Notifier",
    "Organisation",
    "OutboundReply",
    "Pipeline",
    "ReplySink",
    "Template",
    "TriageClassifier",
    "TriageDecision",
    "TriagePolicy",
    "TriageSignals",
    "TriageUnavailable",
    "__version__",
    "decide",
    "derive_tier",
    "load_config",
    "make_sender_key",
]

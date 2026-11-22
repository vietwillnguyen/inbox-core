"""The public surface: small, typed, and documented."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Any

import inbox_core

TOP_LEVEL = {
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
}


GENERATED = ("inbox_core.chatwoot._chatwoot_api", "inbox_core.chatwoot._service_api")
"""Packages written by scripts/generate.py, held to their generator's standard, not this one."""


def modules() -> list[Any]:
    found = [inbox_core]
    for info in pkgutil.walk_packages(inbox_core.__path__, "inbox_core."):
        if info.name.startswith(GENERATED):
            continue
        found.append(importlib.import_module(info.name))
    return found


def test_the_top_level_api_is_the_curated_set() -> None:
    assert set(inbox_core.__all__) == TOP_LEVEL
    for name in TOP_LEVEL:
        assert hasattr(inbox_core, name), name


def test_every_module_declares_all_and_every_name_in_it_exists() -> None:
    for module in modules():
        assert module.__doc__, f"{module.__name__} has no docstring"
        exported = getattr(module, "__all__", None)
        if module.__name__.endswith(("channels", "adapters", "testing", "examples")):
            continue
        assert exported is not None, f"{module.__name__} has no __all__"
        for name in exported:
            assert hasattr(module, name), f"{module.__name__}.{name}"


def test_every_public_class_function_and_method_has_a_docstring() -> None:
    missing = []
    for module in modules():
        for name in getattr(module, "__all__", ()):
            obj = getattr(module, name)
            if not (inspect.isclass(obj) or inspect.isfunction(obj)):
                continue
            if getattr(obj, "__module__", "") != module.__name__:
                continue
            if not inspect.getdoc(obj):
                missing.append(f"{module.__name__}.{name}")
            if inspect.isclass(obj):
                for member, value in vars(obj).items():
                    if member.startswith("_"):
                        continue
                    target = value.fget if isinstance(value, property) else value
                    if isinstance(target, staticmethod | classmethod):
                        target = target.__func__
                    if inspect.isfunction(target) and not target.__doc__:
                        missing.append(f"{module.__name__}.{name}.{member}")
    assert missing == []

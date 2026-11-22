"""The Chatwoot connection adds no way to the public that bypasses the delivery module."""

from __future__ import annotations

import ast
from pathlib import Path

import inbox_core
from tests.test_delivery import enclosing

PACKAGE = Path(inbox_core.__file__).parent


def calls_of(attribute: str) -> list[tuple[str, str]]:
    found = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == attribute
            ):
                found.append((path.relative_to(PACKAGE).as_posix(), enclosing(tree, node)))
    return found


def test_the_public_transport_is_called_only_by_the_sink() -> None:
    assert calls_of("send_message") == [("chatwoot/sink.py", "ChatwootReplySink.send_to_public")]


def test_public_messages_are_created_only_by_send_message_and_notes_are_private() -> None:
    assert sorted(calls_of("_create_message")) == [
        ("chatwoot/api.py", "ChatwootApi.add_private_note"),
        ("chatwoot/api.py", "ChatwootApi.send_message"),
    ]
    source = (PACKAGE / "chatwoot" / "api.py").read_text()
    assert "return self._create_message(conversation_id, text, private=True)" in source
    assert "return self._create_message(conversation_id, text, private=False)" in source


def test_the_generated_create_message_call_has_one_caller() -> None:
    callers = [
        site
        for site in calls_of("sync_detailed")
        if site[0] == "chatwoot/api.py" and site[1] == "ChatwootApi._create_message"
    ]
    assert len(callers) == 1


def test_the_tab_send_reaches_the_public_only_through_draft_review() -> None:
    sends = [site for site in calls_of("send") if site[0] == "chatwoot/service.py"]
    assert sends == [("chatwoot/service.py", "ChatwootService._send")]
    service = (PACKAGE / "chatwoot" / "service.py").read_text()
    assert "self._pipeline.drafts.send(" in service
    assert "send_to_public" not in service
    assert ".send_message(" not in service


def test_the_fallback_holding_message_goes_through_delivery() -> None:
    delivers = [site for site in calls_of("deliver") if site[0] == "chatwoot/service.py"]
    assert delivers == [("chatwoot/service.py", "ChatwootService._fall_back")]

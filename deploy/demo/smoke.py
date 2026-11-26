"""Smoke test for a running demo bundle: every public route, and one answered question.

    ./deploy/demo/demo.sh smoke

Standard library only, so it runs on the server without installing anything.
It asks one question as a new visitor through the widget's own API and waits
for the grounded answer, checks that the answer names no knowledge source to
the visitor and that the service's audit record (read from its container log)
keeps the sources, then checks that what must not be public is not.
Exit code 0 means every check passed. It prints no message text but its own.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
QUESTION = "What are your opening hours?"


_getaddrinfo = socket.getaddrinfo


def _loopback_for_localhost(host: Any, *args: Any, **kwargs: Any) -> Any:
    """Resolve every ``*.localhost`` name to this machine (RFC 6761), as browsers do.

    The local bundle serves ``demo.localhost`` and its subdomains; not every
    system resolver answers for subdomains of ``localhost``.
    """
    if isinstance(host, str) and (host == "localhost" or host.endswith(".localhost")):
        host = "127.0.0.1"
    return _getaddrinfo(host, *args, **kwargs)


socket.getaddrinfo = _loopback_for_localhost


def fetch(method: str, url: str, body: Any = None, headers: dict[str, str] | None = None) -> Any:
    """The status and the parsed JSON (or text) of one request."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 - our own URLs
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
            raw = response.read().decode()
            status = response.status
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(errors="replace")
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def check(name: str, ok: bool) -> bool:
    """Print one result line."""
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
    return ok


def ask(chat: str, website_token: str, timeout: float) -> tuple[int | None, str]:
    """Ask the question as a new visitor: the conversation id and first reply, or ''."""
    query = f"?website_token={website_token}"
    status, config = fetch("POST", f"{chat}/api/v1/widget/config{query}")
    if status != 200:
        return None, ""
    auth = {"X-Auth-Token": config["website_channel_config"]["auth_token"]}
    stamp = time.strftime("%a %b %d %Y")
    status, created = fetch(
        "POST",
        f"{chat}/api/v1/widget/conversations{query}",
        {"contact": {"name": "Smoke test"}, "message": {"content": QUESTION, "timestamp": stamp}},
        auth,
    )
    if status != 200:
        return None, ""
    conversation_id = created.get("id") if isinstance(created, dict) else None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, found = fetch("GET", f"{chat}/api/v1/widget/messages{query}", headers=auth)
        messages = found if isinstance(found, list) else (found or {}).get("payload", [])
        replies = [m.get("content") or "" for m in messages if m.get("message_type") == 1]
        if replies:
            return conversation_id, str(replies[0])
        time.sleep(1)
    return conversation_id, ""


def audit_sources(project: str, env_file: str, conversation_id: int | None) -> list[str]:
    """The sources in the service's audit records for one conversation, from its log."""
    if conversation_id is None:
        return []
    logs = subprocess.run(  # noqa: S603 - fixed arguments
        [  # noqa: S607
            "docker",
            "compose",
            "-p",
            project,
            "-f",
            str(HERE / "compose.yaml"),
            "--env-file",
            env_file,
            "logs",
            "--no-color",
            "--no-log-prefix",
            "inbox-core",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    ).stdout
    sources: list[str] = []
    for line in logs.splitlines():
        if " inbox_core.audit " in line and "{" in line:
            record = json.loads(line[line.index("{") :])
            if record.get("thread_key") == str(conversation_id):
                sources.extend(record.get("sources") or [])
    return sources


def main() -> int:
    """Run every check; exit 1 if any failed."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", required=True)
    parser.add_argument("--chat", required=True)
    parser.add_argument("--bot", required=True)
    parser.add_argument("--website-token", required=True)
    parser.add_argument("--compose-project", required=True)
    parser.add_argument("--compose-env-file", required=True)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()

    results = []
    status, page = fetch("GET", args.page)
    results.append(check("the visitor's page loads", status == 200 and "This is a demo" in page))
    results.append(check("Chatwoot answers", fetch("GET", f"{args.chat}/api")[0] == 200))
    results.append(check("the draft tab is served", fetch("GET", f"{args.bot}/tab")[0] == 200))
    for path in ("/healthz", "/metrics", "/chatwoot/webhook/anything"):
        results.append(
            check(f"inbox-core {path} is not public", fetch("GET", f"{args.bot}{path}")[0] == 404)
        )
    admin = fetch("GET", f"{args.chat}/super_admin")[0]
    results.append(check("Chatwoot's super admin is not public", admin == 404))
    conversation_id, reply = ask(args.chat, args.website_token, args.timeout)
    results.append(check("a visitor's question gets an answer", bool(reply)))
    results.append(
        check(
            "the answer names no source to the visitor",
            bool(reply) and "Source" not in reply and "QCW-" not in reply,
        )
    )
    sources = audit_sources(args.compose_project, args.compose_env_file, conversation_id)
    results.append(
        check(
            "the audit record keeps the answer's sources",
            any(source.startswith("QCW-") for source in sources),
        )
    )
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())

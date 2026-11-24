"""Smoke test for a running demo bundle: every public route, and one answered question.

    ./deploy/demo/demo.sh smoke

Standard library only, so it runs on the server without installing anything.
It asks one question as a new visitor through the widget's own API and waits
for the grounded answer, then checks that what must not be public is not.
Exit code 0 means every check passed. It prints no message text but its own.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Any

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


def ask(chat: str, website_token: str, timeout: float) -> str:
    """Ask the question as a new visitor and return the first reply, or ''."""
    query = f"?website_token={website_token}"
    status, config = fetch("POST", f"{chat}/api/v1/widget/config{query}")
    if status != 200:
        return ""
    auth = {"X-Auth-Token": config["website_channel_config"]["auth_token"]}
    stamp = time.strftime("%a %b %d %Y")
    status, _ = fetch(
        "POST",
        f"{chat}/api/v1/widget/conversations{query}",
        {"contact": {"name": "Smoke test"}, "message": {"content": QUESTION, "timestamp": stamp}},
        auth,
    )
    if status != 200:
        return ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, found = fetch("GET", f"{chat}/api/v1/widget/messages{query}", headers=auth)
        messages = found if isinstance(found, list) else (found or {}).get("payload", [])
        replies = [m.get("content") or "" for m in messages if m.get("message_type") == 1]
        if replies:
            return str(replies[0])
        time.sleep(1)
    return ""


def main() -> int:
    """Run every check; exit 1 if any failed."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", required=True)
    parser.add_argument("--chat", required=True)
    parser.add_argument("--bot", required=True)
    parser.add_argument("--website-token", required=True)
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
    reply = ask(args.chat, args.website_token, args.timeout)
    results.append(check("a visitor's question gets a grounded answer", "Source: QCW-" in reply))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())

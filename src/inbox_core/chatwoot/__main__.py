"""``python -m inbox_core.chatwoot serve`` and ``python -m inbox_core.chatwoot retention``.

``serve`` runs the service with uvicorn. Its access log is off: a webhook's
URL carries the unguessable path token, which must not reach a log.

``retention --days N`` deletes Chatwoot conversations inactive for N days and
their orphaned contacts (with ``CHATWOOT_ADMIN_TOKEN``, an administrator's
token), then erases the core store's content older than N days. It prints a
JSON report of counts.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Sequence

__all__ = ["main"]


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the command line and run it."""
    parser = argparse.ArgumentParser(prog="python -m inbox_core.chatwoot")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="run the webhook and draft tab service")
    serve.add_argument("--host", default="0.0.0.0")  # noqa: S104 - inside a container
    serve.add_argument("--port", type=int, default=8000)
    retention = commands.add_parser("retention", help="delete old transcripts and content")
    retention.add_argument("--days", type=int, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    from inbox_core.chatwoot.settings import ChatwootSettings

    settings = ChatwootSettings.from_env()
    if args.command == "retention":
        if args.days < 1:
            parser.error("--days must be at least 1")
        from sqlalchemy import create_engine

        from inbox_core.chatwoot.api import ChatwootApi
        from inbox_core.chatwoot.retention import run_chatwoot_retention
        from inbox_core.retention import run_retention
        from inbox_core.store.sqlalchemy import SqlAlchemyConversationStore, create_schema

        admin_token = os.environ.get("CHATWOOT_ADMIN_TOKEN", "").strip()
        if not admin_token:
            parser.error("CHATWOOT_ADMIN_TOKEN is not set")
        admin = ChatwootApi(settings.chatwoot_url, settings.account_id, admin_token)
        chatwoot = run_chatwoot_retention(admin, days=args.days)
        engine = create_engine(settings.database_url)
        create_schema(engine)
        core = run_retention(SqlAlchemyConversationStore(engine), days=args.days)
        engine.dispose()
        print(json.dumps({"chatwoot": chatwoot.to_dict(), "core": core.to_dict()}, sort_keys=True))
        return 0

    import uvicorn

    from inbox_core.chatwoot.app import build_service
    from inbox_core.chatwoot.service import create_app

    parts = build_service(settings)
    try:
        uvicorn.run(create_app(parts.service), host=args.host, port=args.port, access_log=False)
    finally:
        parts.store.close()
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())

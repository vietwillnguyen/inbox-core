"""``python -m inbox_core.chatwoot serve`` and ``python -m inbox_core.chatwoot retention``.

``serve`` runs the service with uvicorn. Its access log is off: a webhook's
URL carries the unguessable path token, which must not reach a log.

``retention --days N`` deletes Chatwoot conversations inactive for N days and
their orphaned contacts (with ``CHATWOOT_ADMIN_TOKEN``, an administrator's
token), then erases the core store's content older than N days. It prints a
JSON report of counts.

``remind`` sends the client's reminders (``[notifications]`` with the
``reminder`` event) for hand-offs and held drafts still waiting, once, with a
link to the conversation in Chatwoot, and prints a JSON report of counts. Run
it every few minutes from cron or a scheduler.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inbox_core.chatwoot.settings import ChatwootSettings

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
    commands.add_parser("remind", help="remind about hand-offs and drafts still waiting")
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

    if args.command == "remind":
        return _remind(settings, parser)

    import uvicorn

    from inbox_core.chatwoot.app import build_service
    from inbox_core.chatwoot.service import create_app

    parts = build_service(settings)
    try:
        uvicorn.run(create_app(parts.service), host=args.host, port=args.port, access_log=False)
    finally:
        parts.store.close()
    return 0


def _remind(settings: ChatwootSettings, parser: argparse.ArgumentParser) -> int:
    from pathlib import Path

    from sqlalchemy import create_engine

    from inbox_core.chatwoot.app import chatwoot_notifications
    from inbox_core.config import load_config
    from inbox_core.examples.demo import EXAMPLE_DIR
    from inbox_core.notify import run_reminders
    from inbox_core.store.sqlalchemy import SqlAlchemyConversationStore, create_schema

    config_path = os.environ.get("INBOX_CORE_CONFIG", "").strip()
    config = load_config(Path(config_path or EXAMPLE_DIR / "client.toml"))
    notifications = chatwoot_notifications(settings, config, os.environ)
    if notifications is None or not config.notifications.notifies("reminder"):
        parser.error("the configuration's [notifications] has no 'reminder' event")
    engine = create_engine(settings.database_url)
    try:
        create_schema(engine)
        report = run_reminders(SqlAlchemyConversationStore(engine), notifications, config)
    finally:
        engine.dispose()
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())

"""Notifications through Apprise: one config line per service, for 100+ services.

Apprise (https://github.com/caronc/apprise, BSD licence) turns a URL such as
``ntfy://...``, ``tgram://...``, ``discord://...`` or ``mailtos://...`` into a
notification on that service, so a client picks where hand-offs and held
drafts are announced without the core knowing any of them.

Install it with ``pip install 'inbox-core[notify]'``. ``apprise`` is imported
only when a transport is built, so the core installs and imports without it.

The URLs come from the client's ``notifications.urls``, with every secret in a
``${VARIABLE}`` placeholder that :meth:`AppriseTransport.from_policy` fills
from the environment. The filled-in URLs live only in this object; they are
never logged, and errors name a URL by its position, never by its value.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from typing import Any

from inbox_core.config import ConfigError, NotificationPolicy
from inbox_core.notify import resolve_urls

__all__ = ["AppriseTransport", "NotificationFailedError", "load_apprise"]


class NotificationFailedError(RuntimeError):
    """Apprise could not deliver a notification to every URL."""


def load_apprise() -> Any:
    """The ``apprise`` module, or an ImportError that names the extra to install."""
    try:
        return importlib.import_module("apprise")
    except ImportError:
        raise ImportError("notifications need: pip install 'inbox-core[notify]'") from None


class AppriseTransport:
    """A :class:`inbox_core.notify.NotificationTransport` over one ``apprise.Apprise``."""

    def __init__(self, urls: Sequence[str], *, apprise: Any = None) -> None:
        module = apprise if apprise is not None else load_apprise()
        if not urls:
            raise ConfigError(["notifications.urls names no URL"])
        self._apprise = module.Apprise()
        self._text = module.NotifyFormat.TEXT
        problems = [
            f"notifications.urls[{index}] is not a URL Apprise accepts"
            for index, url in enumerate(urls)
            if not self._apprise.add(url)
        ]
        if problems:
            raise ConfigError(problems)

    @classmethod
    def from_policy(
        cls, policy: NotificationPolicy, env: Mapping[str, str], *, apprise: Any = None
    ) -> AppriseTransport:
        """The transport for a client's ``[notifications]``, with secrets from ``env``."""
        return cls(resolve_urls(policy.urls, env), apprise=apprise)

    def __repr__(self) -> str:
        return f"AppriseTransport({len(self._apprise)} url(s))"

    def notify_staff(self, title: str, body: str) -> None:
        """Send to every URL. Raises :class:`NotificationFailedError` unless all succeed."""
        if not self._apprise.notify(title=title, body=body, body_format=self._text):
            raise NotificationFailedError("apprise could not deliver to every notification URL")

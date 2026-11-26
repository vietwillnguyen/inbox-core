"""The Chatwoot connection: inbox-core as a Chatwoot agent bot, with a draft tab.

Installed with ``inbox-core[chatwoot]``; the core never imports it. The parts:

- :mod:`inbox_core.chatwoot.webhook`: verifying and sorting agent-bot webhooks.
- :mod:`inbox_core.chatwoot.api`: the Chatwoot calls, over a client generated
  from Chatwoot's own OpenAPI spec (``scripts/generate.py``).
- :mod:`inbox_core.chatwoot.sink`: the reply sink and hand-off actions.
- :mod:`inbox_core.chatwoot.tab_auth`: signing an agent in to the draft tab.
- :mod:`inbox_core.chatwoot.service`: the service, implementing the routes
  generated from ``openapi.yaml``.
- :mod:`inbox_core.chatwoot.app`: building it from settings.
- :mod:`inbox_core.chatwoot.retention`: deleting old transcripts in Chatwoot.

See ``docs/chatwoot.md`` for running it.
"""

__all__: list[str] = []

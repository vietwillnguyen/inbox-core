"""A client library for accessing Chatwoot (subset used by inbox-core)"""

from .client import AuthenticatedClient, Client

__all__ = (
    "AuthenticatedClient",
    "Client",
)

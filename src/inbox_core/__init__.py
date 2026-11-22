"""inbox-core: the fail-closed triage and delivery core of an inbox assistant.

A message arrives from any channel, is guarded, triaged into a tier that is
decided in code, handled by a pluggable handler, delivered under an off, draft
or auto mode with caps, and recorded for audit.

The package is pre-release and its interface may change between minor versions.
"""

import logging
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("inbox-core")
except PackageNotFoundError:  # pragma: no cover - only when run from a bare source tree
    __version__ = "0.0.0"

# A library attaches a NullHandler and nothing else: where log records go is
# the host application's decision.
_root = logging.getLogger("inbox_core")
if not any(isinstance(handler, logging.NullHandler) for handler in _root.handlers):
    _root.addHandler(logging.NullHandler())

__all__ = ["__version__"]

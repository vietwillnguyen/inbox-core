"""Channel-specific extensions to the core message shapes.

The core never imports from here. A channel adapter attaches one of these to
:attr:`inbox_core.messages.IncomingMessage.extension` for its own guards and
sinks to read.
"""

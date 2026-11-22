"""Entry point for ``python -m inbox_core.evals``."""

import sys

from inbox_core.evals.cli import main

__all__: list[str] = []

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

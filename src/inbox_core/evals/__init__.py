"""Evaluation: may the classifier decide, are answers grounded, where should thresholds sit.

Three runners, run on demand with ``python -m inbox_core.evals``, never in CI,
because they spend real model calls. What runs in CI is the part that can be
wrong for free: :mod:`inbox_core.evals.golden` validates a golden set
(including that every expected tier is what :func:`inbox_core.triage.derive_tier`
returns for that case) and :mod:`inbox_core.evals.metrics` is the arithmetic.

Output written to disk is numbers and case ids only: no case text, no model
responses.
"""

__all__: list[str] = []

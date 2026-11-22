"""The origin engine's hard-coded tier policy, kept verbatim as a test oracle.

Copyright (c) 2025 Vietnam Hearts. MIT licence (see LICENSE and NOTICE).

The constants and ``derive_tier`` below are the origin's ``triage/policy.py``
unchanged except for the imports and the ``Category``/``Tier`` aliases, which
are widened to ``str`` so the oracle can be fed values outside the original
enums. ``tests/test_triage_equivalence.py`` checks the configurable policy
against it over the whole input space. Do not edit the rules here: the point is
that this is the code that was deployed.
"""

from __future__ import annotations

from typing import Protocol

Category = str
Tier = str


class _Signals(Protocol):
    @property
    def category(self) -> str: ...
    @property
    def language(self) -> str: ...
    @property
    def confidence(self) -> float: ...
    @property
    def asks_for_human(self) -> bool: ...
    @property
    def mentions_money_or_commitment(self) -> bool: ...


CATEGORIES: tuple[Category, ...] = (
    "signup",
    "faq",
    "volunteer_ops",
    "sponsorship",
    "donation",
    "partnership",
    "press",
    "safeguarding_legal",
    "acceptance",
    "human_other",
    "automated",
)

LANGUAGES: tuple[str, ...] = ("en", "vi", "other")

EXECUTIVE_CATEGORIES: frozenset[Category] = frozenset(
    {
        "sponsorship",
        "donation",
        "partnership",
        "press",
        "safeguarding_legal",
        "acceptance",
    }
)

CATEGORY_TIERS: dict[Category, Tier] = {
    "signup": "auto_answer",
    "faq": "auto_answer",
    "volunteer_ops": "needs_admin",
    "sponsorship": "needs_executive",
    "donation": "needs_executive",
    "partnership": "needs_executive",
    "press": "needs_executive",
    "safeguarding_legal": "needs_executive",
    "acceptance": "needs_executive",
    "human_other": "needs_admin",
    "automated": "skip",
}


def derive_tier(signals: _Signals, confidence_threshold: float) -> Tier:
    """Which tier handles this mail. Never chosen by a model."""
    if signals.category in EXECUTIVE_CATEGORIES or signals.mentions_money_or_commitment:
        return "needs_executive"

    if signals.category == "automated":
        return "skip"

    if (
        signals.language not in ("en", "vi")
        or signals.asks_for_human
        or signals.confidence < confidence_threshold
    ):
        return "needs_admin"

    return CATEGORY_TIERS.get(signals.category, "needs_admin")

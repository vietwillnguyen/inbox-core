"""Proof: the configurable policy, given the origin's table, decides exactly as the origin did.

The input space is derived here rather than taken on trust. ``derive_tier``
reads five signal fields and one threshold, so the space is their product:

- category: every category in the origin's table, plus one it does not list
  (the origin falls back to ``needs_admin`` for that, and so must we);
- language: both supported codes, the origin's ``other``, and an arbitrary
  unsupported code (the origin tests ``not in ("en", "vi")``, not the enum);
- confidence: a grid from 0 to 1 in steps of 0.05, plus, for each threshold,
  the threshold itself and the nearest floats on either side of it, because
  the only place confidence matters is the comparison with the threshold;
- asks_for_human and mentions_money_or_commitment: both values each;
- threshold: several, because the origin takes it as an argument.

Non-finite confidences are excluded on purpose and tested separately: there the
new policy is deliberately stricter (see ``test_nan_is_a_deliberate_difference``).
"""

from __future__ import annotations

import itertools
import math
from pathlib import Path

from inbox_core.config import load_config
from inbox_core.triage import TriageSignals, derive_tier
from tests.reference import origin_policy

CONFIG = load_config(Path(__file__).parent / "fixtures" / "origin_table.toml")

CATEGORIES = (*origin_policy.CATEGORIES, "not_in_the_table")
LANGUAGES = (*origin_policy.LANGUAGES, "fr")
THRESHOLDS = (0.3, 0.55, 0.6, 0.7, 0.9, 1.0)
GRID = tuple(round(step * 0.05, 2) for step in range(21))
BOOLEANS = (False, True)


def confidences_for(threshold: float) -> tuple[float, ...]:
    near = {threshold, math.nextafter(threshold, 0.0), math.nextafter(threshold, 2.0)}
    return tuple(sorted({*GRID, *(value for value in near if 0.0 <= value <= 1.0)}))


def test_the_fixture_is_the_origin_table() -> None:
    policy = CONFIG.triage
    assert tuple(rule.name for rule in policy.categories) == origin_policy.CATEGORIES
    assert policy.executive_categories == origin_policy.EXECUTIVE_CATEGORIES
    for rule in policy.categories:
        origin_tier = origin_policy.CATEGORY_TIERS[rule.name]
        expected = "auto_answer" if rule.auto_answer else rule.escalates_to
        assert expected == origin_tier, rule.name
    assert set(policy.languages) == {"en", "vi"}


def test_identical_tiers_for_every_combination_of_inputs() -> None:
    compared = 0
    expected_total = 0
    for threshold in THRESHOLDS:
        policy = CONFIG.triage.with_threshold(threshold)
        confidences = confidences_for(threshold)
        expected_total += (
            len(CATEGORIES) * len(LANGUAGES) * len(confidences) * len(BOOLEANS) * len(BOOLEANS)
        )
        for category, language, confidence, human, money in itertools.product(
            CATEGORIES, LANGUAGES, confidences, BOOLEANS, BOOLEANS
        ):
            given = TriageSignals(category, language, confidence, human, money, "proof")
            new = derive_tier(given, policy)
            old = origin_policy.derive_tier(given, threshold)
            assert new == old, (given, threshold)
            compared += 1

    assert compared == expected_total
    # Recorded in docs/design.md; a change to the input space must update both.
    assert compared == 26_304


def test_every_tier_is_reached_so_the_proof_is_not_vacuous() -> None:
    reached = set()
    for category, language, human, money in itertools.product(
        CATEGORIES, LANGUAGES, BOOLEANS, BOOLEANS
    ):
        given = TriageSignals(category, language, 0.95, human, money, "proof")
        reached.add(derive_tier(given, CONFIG.triage))
    assert reached == {"auto_answer", "needs_admin", "needs_executive", "skip"}


def test_nan_is_a_deliberate_difference() -> None:
    # The origin compares ``confidence < threshold``, which is False for NaN, so
    # a NaN confidence on an FAQ was auto-answered. The configurable policy
    # treats any non-finite confidence as not confident.
    given = TriageSignals("faq", "en", float("nan"), False, False, "proof")
    assert origin_policy.derive_tier(given, 0.6) == "auto_answer"
    assert derive_tier(given, CONFIG.triage) == "needs_admin"

"""Typed loading and validation of a golden set.

A golden set is a TOML (or YAML) file with a ``[[cases]]`` list. Each case is
validated against the client's configuration, and ``expected_tier`` is never
trusted as written: it is recomputed from the case's expected signals with the
real :func:`inbox_core.triage.derive_tier` and must match. A golden set
therefore cannot drift from the policy it measures, and a policy change shows
up as a failing validation rather than as a mysteriously better score.

Every problem in the file is reported at once.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from inbox_core.config import ClientConfig
from inbox_core.messages import IncomingMessage, make_sender_key
from inbox_core.triage import TriageSignals, derive_tier

__all__ = [
    "GOLDEN_CONFIDENCE",
    "GoldenCase",
    "GoldenSetInvalid",
    "answerable_cases",
    "as_incoming",
    "executive_cases",
    "load_golden_set",
]

GOLDEN_CONFIDENCE = 1.0
"""The confidence a correct classifier would report on an unambiguous case."""

GOLDEN_SENDER = "golden@example.com"

_KEYS = {
    "id",
    "language",
    "subject",
    "text",
    "expected_category",
    "expected_tier",
    "expected_asks_for_human",
    "expected_mentions_money",
    "must_mention",
    "must_not_answer",
    "note",
}


class GoldenSetInvalid(ValueError):  # noqa: N818 - the established name
    """The golden set does not satisfy its own contract."""


@dataclass(frozen=True)
class GoldenCase:
    """One validated case. ``language`` is a configured code or ``other``."""

    id: str
    language: str
    subject: str
    text: str
    expected_category: str
    expected_tier: str
    expected_asks_for_human: bool = False
    expected_mentions_money: bool = False
    must_mention: tuple[str, ...] = ()
    must_not_answer: tuple[str, ...] = ()
    note: str = ""

    def expected_signals(self) -> TriageSignals:
        """What a perfect classifier would report for this case."""
        return TriageSignals(
            category=self.expected_category,
            language=self.language,
            confidence=GOLDEN_CONFIDENCE,
            asks_for_human=self.expected_asks_for_human,
            mentions_money_or_commitment=self.expected_mentions_money,
            classifier="golden",
        )

    @property
    def is_executive(self) -> bool:
        """Whether the 100 percent recall gate is measured on this case."""
        return self.expected_tier == "needs_executive"

    @property
    def is_answerable(self) -> bool:
        """Whether the groundedness judge is measured on this case."""
        return self.expected_tier == "auto_answer"


def load_golden_set(
    path: str | Path, config: ClientConfig, *, require_every_language: bool = False
) -> tuple[GoldenCase, ...]:
    """Every case, validated against ``config``. Raises :class:`GoldenSetInvalid`.

    With ``require_every_language``, every category that is not skipped needs
    a case in every configured language.
    """
    source = Path(path)
    raw = _read(source)
    cases: list[GoldenCase] = []
    problems: list[str] = []
    for index, entry in enumerate(raw):
        try:
            cases.append(_build(entry, index, config))
        except GoldenSetInvalid as exc:
            problems.append(str(exc))
    problems.extend(_collective(cases, config, require_every_language))
    if problems:
        raise GoldenSetInvalid(
            f"{len(problems)} problem(s) in {source.name}:\n  - " + "\n  - ".join(problems)
        )
    return tuple(cases)


def _read(source: Path) -> Sequence[object]:
    if not source.is_file():
        raise GoldenSetInvalid(f"no golden set at {source.name}")
    text = source.read_text(encoding="utf-8")
    suffix = source.suffix.lower()
    loaded: object
    if suffix == ".toml":
        loaded = tomllib.loads(text)
    elif suffix in (".yaml", ".yml"):
        import yaml

        loaded = yaml.safe_load(text)
    else:
        raise GoldenSetInvalid(f"unsupported golden set type {suffix!r}; use .toml or .yaml")
    cases = loaded.get("cases") if isinstance(loaded, Mapping) else None
    if not isinstance(cases, list) or not cases:
        raise GoldenSetInvalid(f"{source.name} contains no list of cases")
    return cases


def _flag(entry: Mapping[str, Any], name: str, where: str) -> bool:
    value = entry.get(name, False)
    if not isinstance(value, bool):
        raise GoldenSetInvalid(f"{where}: {name} must be true or false")
    return value


def _strings(entry: Mapping[str, Any], name: str, where: str) -> tuple[str, ...]:
    value = entry.get(name) or []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise GoldenSetInvalid(f"{where}: {name} must be a list of strings")
    return tuple(value)


def _build(entry: object, index: int, config: ClientConfig) -> GoldenCase:
    if not isinstance(entry, Mapping):
        raise GoldenSetInvalid(f"case #{index} must be a table")
    data = cast("Mapping[str, Any]", entry)
    where = str(data.get("id") or f"case #{index}")
    unknown = sorted(set(data) - _KEYS)
    if unknown:
        raise GoldenSetInvalid(f"{where}: unknown key {unknown[0]!r}")
    for required in ("id", "language", "text", "expected_category", "expected_tier"):
        if not isinstance(data.get(required), str) or not data[required].strip():
            raise GoldenSetInvalid(f"{where}: missing {required}")

    policy = config.triage
    category = data["expected_category"]
    if policy.category(category) is None:
        raise GoldenSetInvalid(f"{where}: unknown category {category!r}")
    language = data["language"]
    if language not in policy.languages and language != "other":
        raise GoldenSetInvalid(f"{where}: language {language!r} is not configured (or 'other')")

    case = GoldenCase(
        id=data["id"],
        language=language,
        subject=str(data.get("subject", "")),
        text=data["text"],
        expected_category=category,
        expected_tier=data["expected_tier"],
        expected_asks_for_human=_flag(data, "expected_asks_for_human", where),
        expected_mentions_money=_flag(data, "expected_mentions_money", where),
        must_mention=_strings(data, "must_mention", where),
        must_not_answer=_strings(data, "must_not_answer", where),
        note=str(data.get("note", "")),
    )
    derived = derive_tier(case.expected_signals(), policy)
    if derived != case.expected_tier:
        raise GoldenSetInvalid(
            f"{where}: expected_tier is {case.expected_tier!r} but derive_tier gives "
            f"{derived!r} for category {category!r}, language {language!r}, "
            f"asks_for_human={case.expected_asks_for_human}, "
            f"mentions_money={case.expected_mentions_money}"
        )
    if case.is_answerable and not case.must_mention:
        raise GoldenSetInvalid(
            f"{where}: an auto_answer case needs must_mention, or the judge has nothing to check"
        )
    return case


def _collective(
    cases: Sequence[GoldenCase], config: ClientConfig, require_every_language: bool
) -> Iterator[str]:
    seen: dict[str, int] = {}
    for case in cases:
        seen[case.id] = seen.get(case.id, 0) + 1
    for case_id, count in seen.items():
        if count > 1:
            yield f"duplicate id {case_id!r} ({count} times)"
    languages_by_category: dict[str, set[str]] = {}
    for case in cases:
        languages_by_category.setdefault(case.expected_category, set()).add(case.language)
    for rule in config.triage.categories:
        found = languages_by_category.get(rule.name, set())
        if not found:
            yield f"category {rule.name!r} has no cases"
            continue
        if require_every_language and rule.escalates_to != "skip":
            for code in config.triage.languages:
                if code not in found:
                    yield f"category {rule.name!r} has no {code} case"


def executive_cases(cases: Sequence[GoldenCase]) -> tuple[GoldenCase, ...]:
    """The cases the executive recall gate is measured on."""
    return tuple(case for case in cases if case.is_executive)


def answerable_cases(cases: Sequence[GoldenCase]) -> tuple[GoldenCase, ...]:
    """The cases the groundedness judge is measured on."""
    return tuple(case for case in cases if case.is_answerable)


def as_incoming(case: GoldenCase, *, channel: str = "eval") -> IncomingMessage:
    """One case as the message a classifier or handler would be given.

    A fixed fictional sender: the classifier is never shown the address, and a
    per-case one would only invite a runner to start reading it.
    """
    return IncomingMessage(
        channel=channel,
        thread_key=f"golden-{case.id}",
        provider_message_id=f"golden-{case.id}",
        sender_key=make_sender_key(GOLDEN_SENDER),
        sender_address=GOLDEN_SENDER,
        subject=case.subject,
        text=case.text,
    )

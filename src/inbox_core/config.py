"""Per-client configuration: typed, validated, loadable from TOML or YAML.

The category table is data, not code. Each client names its categories, says
which of them may ever be answered automatically and where the rest escalate,
and sets the confidence threshold and the supported languages. The tier rules
that read the table live in :mod:`inbox_core.triage` and are the same for every
client.

Validation runs whenever a config object is built, from a file or in Python,
and reports every problem at once. It refuses anything that could auto-answer
without a confidence threshold, any unknown tier, duplicate categories, and a
fallback category that would not reach a person.
"""

from __future__ import annotations

import dataclasses
import math
import re
import tomllib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from inbox_core.delivery import DeliveryMode

__all__ = [
    "ESCALATION_TIERS",
    "CategoryRule",
    "ClientConfig",
    "ConfigError",
    "DeliveryPolicy",
    "EscalationTier",
    "Organisation",
    "TriagePolicy",
    "load_config",
]

EscalationTier = Literal["needs_admin", "needs_executive", "skip"]
"""Where a category goes when it is not answered automatically."""

ESCALATION_TIERS: tuple[EscalationTier, ...] = ("needs_admin", "needs_executive", "skip")

RESERVED_LANGUAGE = "other"
"""The language code a classifier reports for anything unsupported."""

_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_LANGUAGE = re.compile(r"^[a-z]{2,3}(-[a-z0-9]{2,8})?$")


class ConfigError(ValueError):
    """A configuration does not satisfy its contract. Lists every problem found."""

    def __init__(self, problems: Iterable[str], source: str = "configuration") -> None:
        self.problems = tuple(problems)
        self.source = source
        super().__init__(
            f"{len(self.problems)} problem(s) in {source}:\n  - " + "\n  - ".join(self.problems)
        )


@dataclass(frozen=True)
class Organisation:
    """Who the assistant answers for. Rendered into the classifier prompts.

    ``summary`` is one phrase a model can use to understand what the inbox is
    for, such as "a volunteer-run lending library for tools".
    """

    name: str
    summary: str

    def __post_init__(self) -> None:
        problems = [
            f"organisation.{name} must be a non-empty string"
            for name in ("name", "summary")
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip()
        ]
        if problems:
            raise ConfigError(problems)


@dataclass(frozen=True)
class CategoryRule:
    """One row of the category table.

    ``auto_answer`` says whether a message in this category may ever be
    answered without a person; even then the tier rules can still escalate it.
    ``escalates_to`` is where it goes otherwise. The defaults are the safe
    ones: not auto-answered, and handled by a person.
    """

    name: str
    description: str
    auto_answer: bool = False
    escalates_to: EscalationTier = "needs_admin"


def _threshold_problem(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return "confidence_threshold must be a number"
    if not math.isfinite(value) or not 0.0 < value <= 1.0:
        return "confidence_threshold must be greater than 0 and at most 1"
    return None


@dataclass(frozen=True)
class TriagePolicy:
    """The category table, languages and confidence threshold for one client.

    ``languages`` maps a language code to its English name, in order; the
    first is the default, used for a holding message when the language is
    unknown. ``fallback_category`` is what the audit records when the
    classifier is unavailable, and must be a category a person handles.
    """

    categories: tuple[CategoryRule, ...]
    languages: Mapping[str, str]
    confidence_threshold: float | None
    fallback_category: str
    _by_name: Mapping[str, CategoryRule] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "categories", tuple(self.categories))
        object.__setattr__(self, "languages", MappingProxyType(dict(self.languages)))
        problems = list(self._problems())
        if problems:
            raise ConfigError(problems)
        by_name = {rule.name: rule for rule in self.categories}
        object.__setattr__(self, "_by_name", MappingProxyType(by_name))

    def _problems(self) -> Iterable[str]:
        if not self.categories:
            yield "triage needs at least one category"
        seen: set[str] = set()
        for rule in self.categories:
            yield from _rule_problems(rule)
            if rule.name in seen:
                yield f"duplicate category {rule.name!r}"
            seen.add(rule.name)

        threshold_problem = _threshold_problem(self.confidence_threshold)
        if threshold_problem:
            yield threshold_problem
        auto = [rule.name for rule in self.categories if rule.auto_answer]
        if auto and self.confidence_threshold is None:
            yield (
                "confidence_threshold is required because these categories may be "
                f"auto-answered: {', '.join(auto)}"
            )

        if not self.languages:
            yield "triage needs at least one supported language"
        for code, name in self.languages.items():
            if code == RESERVED_LANGUAGE:
                yield f"language code {code!r} is reserved for unsupported languages"
            elif not isinstance(code, str) or not _LANGUAGE.match(code):
                yield f"language code {code!r} must be a lower-case code such as 'en' or 'pt-br'"
            if not isinstance(name, str) or not name.strip():
                yield f"language {code!r} needs a name"

        fallback = next((r for r in self.categories if r.name == self.fallback_category), None)
        if fallback is None:
            yield f"fallback_category {self.fallback_category!r} is not a listed category"
        elif fallback.auto_answer or fallback.escalates_to == "skip":
            yield (
                f"fallback_category {self.fallback_category!r} must be a category a "
                "person handles (not auto-answered and not skipped)"
            )

    def category(self, name: str) -> CategoryRule | None:
        """The rule for ``name``, or None if the table does not list it."""
        return self._by_name.get(name)

    @property
    def default_language(self) -> str:
        """The first configured language."""
        return next(iter(self.languages))

    @property
    def executive_categories(self) -> frozenset[str]:
        """Categories that always go to ``needs_executive``."""
        return frozenset(r.name for r in self.categories if r.escalates_to == "needs_executive")

    @property
    def skip_categories(self) -> frozenset[str]:
        """Categories that are never answered or escalated."""
        return frozenset(r.name for r in self.categories if r.escalates_to == "skip")

    @property
    def auto_answer_categories(self) -> frozenset[str]:
        """Categories that may be answered without a person."""
        return frozenset(r.name for r in self.categories if r.auto_answer)

    def seriousness_order(self) -> tuple[str, ...]:
        """Categories from most to least serious, for the multi-topic prompt rule.

        Executive categories first, then those a person handles, then those
        that may be auto-answered, each group in declaration order. Skipped
        categories are not ranked: a message written by a person is never
        "automated" because it also mentions a newsletter.
        """
        groups: list[list[str]] = [[], [], []]
        for rule in self.categories:
            if rule.escalates_to == "skip":
                continue
            if rule.escalates_to == "needs_executive":
                groups[0].append(rule.name)
            elif rule.auto_answer:
                groups[2].append(rule.name)
            else:
                groups[1].append(rule.name)
        return tuple(name for group in groups for name in group)

    def with_threshold(self, threshold: float) -> TriagePolicy:
        """A copy at another confidence threshold, validated like any other."""
        return dataclasses.replace(self, confidence_threshold=threshold)


def _rule_problems(rule: CategoryRule) -> Iterable[str]:
    if not isinstance(rule.name, str) or not _NAME.match(rule.name):
        yield (
            f"category name {rule.name!r} must start with a lower-case letter and use "
            "only lower-case letters, digits and underscores (at most 64)"
        )
    if not isinstance(rule.description, str) or not rule.description.strip():
        yield f"category {rule.name!r} needs a description; it is what the classifier is shown"
    # Read as plain objects: a rule built from parsed data or by an untyped
    # caller can hold anything, and that is exactly what this checks.
    auto: object = rule.auto_answer
    tier: object = rule.escalates_to
    if not isinstance(auto, bool):
        yield f"category {rule.name!r}: auto_answer must be true or false"
    if tier == "auto_answer":
        yield (
            f"category {rule.name!r}: escalates_to cannot be auto_answer; set "
            "auto_answer = true and escalates_to = 'needs_admin' instead"
        )
    elif tier not in ESCALATION_TIERS:
        yield (
            f"category {rule.name!r}: unknown tier {tier!r}; expected one of "
            f"{', '.join(ESCALATION_TIERS)}"
        )
    elif auto is True and tier != "needs_admin":
        yield (
            f"category {rule.name!r} may be auto-answered, so it must escalate to "
            f"needs_admin when unsure, not {tier}"
        )


def _template_problems(
    templates: Mapping[str, Mapping[str, str]], policy: TriagePolicy
) -> list[str]:
    problems: list[str] = []
    for name, texts in templates.items():
        if not isinstance(name, str) or not _NAME.match(name):
            problems.append(f"template name {name!r} must be a lower-case identifier")
        if not isinstance(texts, Mapping) or not texts:
            problems.append(f"template {name!r} needs at least one language = text entry")
            continue
        for code, text in texts.items():
            if code not in policy.languages:
                problems.append(f"template {name!r} has text for unconfigured language {code!r}")
            if not isinstance(text, str) or not text.strip():
                problems.append(f"template {name!r} has an empty text for {code!r}")
    return problems


def _positive_int_problem(name: str, value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return f"{name} must be a whole number of at least 1"
    return None


@dataclass(frozen=True)
class DeliveryPolicy:
    """How replies are delivered, and the bounds on them.

    The defaults are the safe ones: ``off``, no language signed off for
    automatic sending, one bot reply per conversation. ``holding`` is the
    message sent (or held) when a conversation is handed to a person, by
    language; :meth:`ClientConfig.holding_text` falls back to the default
    language. ``timezone`` is the organisation's, for when a day starts.
    """

    mode: DeliveryMode = DeliveryMode.OFF
    auto_languages: frozenset[str] = frozenset()
    daily_send_cap: int = 30
    per_sender_daily_cap: int = 2
    max_bot_replies_per_conversation: int = 1
    timezone: str = "UTC"
    holding: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "holding", MappingProxyType(dict(self.holding)))
        problems = []
        mode: object = self.mode
        auto_languages: object = self.auto_languages
        if not isinstance(mode, DeliveryMode):
            problems.append("delivery.mode must be one of off, draft, auto")
        if not isinstance(auto_languages, frozenset):
            problems.append("delivery.auto_languages must be a set of language codes")
        for name in ("daily_send_cap", "per_sender_daily_cap", "max_bot_replies_per_conversation"):
            problem = _positive_int_problem(f"delivery.{name}", getattr(self, name))
            if problem:
                problems.append(problem)
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            problems.append(f"delivery.timezone {self.timezone!r} is not a known IANA timezone")
        for code, text in self.holding.items():
            if not isinstance(text, str) or not text.strip():
                problems.append(f"delivery.holding has an empty text for {code!r}")
        if problems:
            raise ConfigError(problems)

    @property
    def zone(self) -> ZoneInfo:
        """The organisation's timezone."""
        return ZoneInfo(self.timezone)


@dataclass(frozen=True)
class ClientConfig:
    """Everything a client configures about the core, as one validated object.

    ``templates`` holds fixed replies the client wrote, by template name and
    then by language code, for the :class:`inbox_core.handlers.Template`
    handler.
    """

    organisation: Organisation
    triage: TriagePolicy
    templates: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    delivery: DeliveryPolicy = field(default_factory=DeliveryPolicy)

    def __post_init__(self) -> None:
        frozen = {
            name: MappingProxyType(dict(texts)) if isinstance(texts, Mapping) else texts
            for name, texts in dict(self.templates).items()
        }
        object.__setattr__(self, "templates", MappingProxyType(frozen))
        problems = _template_problems(self.templates, self.triage)
        languages = self.triage.languages
        for code in sorted(self.delivery.auto_languages - set(languages)):
            problems.append(f"delivery.auto_languages names unconfigured language {code!r}")
        for code in sorted(set(self.delivery.holding) - set(languages)):
            problems.append(f"delivery.holding has text for unconfigured language {code!r}")
        if problems:
            raise ConfigError(problems)

    def holding_text(self, language: str) -> str | None:
        """The holding message for ``language``, else the default language's, else None."""
        holding = self.delivery.holding
        return holding.get(language) or holding.get(self.triage.default_language)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], source: str = "configuration") -> ClientConfig:
        """Build and validate from parsed TOML or YAML. Raises :class:`ConfigError`."""
        reader = _Reader(source)
        config = reader.client(data)
        if reader.problems or config is None:
            raise ConfigError(reader.problems, source)
        return config


def load_config(path: str | Path) -> ClientConfig:
    """Read a ``.toml``, ``.yaml`` or ``.yml`` file into a :class:`ClientConfig`."""
    source = Path(path)
    if not source.is_file():
        raise ConfigError([f"no configuration file at {source.name}"], source.name)
    return ClientConfig.from_mapping(_parse_file(source), source.name)


def _parse_file(source: Path) -> Mapping[str, Any]:
    text = source.read_text(encoding="utf-8")
    suffix = source.suffix.lower()
    if suffix == ".toml":
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError([f"not valid TOML: {exc}"], source.name) from None
    if suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            raise ConfigError(
                ["YAML needs the optional extra: pip install 'inbox-core[yaml]'"], source.name
            ) from None
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ConfigError([f"not valid YAML: {exc}"], source.name) from None
        if not isinstance(loaded, Mapping):
            raise ConfigError(["the file must contain a mapping at the top level"], source.name)
        return cast("Mapping[str, Any]", loaded)
    raise ConfigError([f"unsupported file type {suffix!r}; use .toml, .yaml or .yml"], source.name)


class _Reader:
    """Strict reading of parsed data: unknown keys and wrong types are problems."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.problems: list[str] = []

    def table(self, data: object, where: str, allowed: Iterable[str]) -> Mapping[str, Any] | None:
        if not isinstance(data, Mapping):
            self.problems.append(f"{where} must be a table")
            return None
        unknown = sorted(set(data) - set(allowed))
        for key in unknown:
            self.problems.append(f"{where}: unknown key {key!r}")
        return cast("Mapping[str, Any]", data)

    def client(self, data: Mapping[str, Any]) -> ClientConfig | None:
        sections = ("organisation", "triage", "templates", "delivery")
        root = self.table(data, "the configuration", sections)
        if root is None:
            return None
        organisation = self.organisation(root.get("organisation"))
        triage = self.triage(root.get("triage"))
        delivery = self.delivery(root.get("delivery", {}))
        templates = root.get("templates", {})
        if not isinstance(templates, Mapping):
            self.problems.append("templates must be a table of template tables")
            return None
        if organisation is None or triage is None or delivery is None:
            return None
        return self._build(
            lambda: ClientConfig(
                organisation=organisation, triage=triage, templates=templates, delivery=delivery
            )
        )

    def delivery(self, data: object) -> DeliveryPolicy | None:
        allowed = (
            "mode",
            "auto_languages",
            "daily_send_cap",
            "per_sender_daily_cap",
            "max_bot_replies_per_conversation",
            "timezone",
            "holding",
        )
        table = self.table(data, "delivery", allowed)
        if table is None:
            return None
        values: dict[str, Any] = {key: value for key, value in table.items() if key in allowed}
        mode = values.get("mode", "off")
        if mode not in {m.value for m in DeliveryMode}:
            self.problems.append("delivery.mode must be one of off, draft, auto")
            return None
        values["mode"] = DeliveryMode(mode)
        languages = values.get("auto_languages", [])
        if not isinstance(languages, list) or not all(isinstance(c, str) for c in languages):
            self.problems.append("delivery.auto_languages must be a list of language codes")
            return None
        values["auto_languages"] = frozenset(languages)
        if not isinstance(values.get("holding", {}), Mapping):
            self.problems.append("delivery.holding must be a table of language = text")
            return None
        return self._build(lambda: DeliveryPolicy(**values))

    def organisation(self, data: object) -> Organisation | None:
        table = self.table(data, "organisation", ("name", "summary"))
        if table is None:
            return None
        return self._build(
            lambda: Organisation(name=table.get("name", ""), summary=table.get("summary", ""))
        )

    def triage(self, data: object) -> TriagePolicy | None:
        allowed = ("categories", "languages", "confidence_threshold", "fallback_category")
        table = self.table(data, "triage", allowed)
        if table is None:
            return None
        raw_categories = table.get("categories")
        if not isinstance(raw_categories, list):
            self.problems.append("triage.categories must be a list of tables")
            return None
        rules = [self.rule(entry, index) for index, entry in enumerate(raw_categories)]
        languages = table.get("languages", {})
        if not isinstance(languages, Mapping):
            self.problems.append("triage.languages must be a table of code = name")
            return None
        if any(rule is None for rule in rules):
            return None
        return self._build(
            lambda: TriagePolicy(
                categories=tuple(rule for rule in rules if rule is not None),
                languages=languages,
                confidence_threshold=table.get("confidence_threshold"),
                fallback_category=table.get("fallback_category", ""),
            )
        )

    def rule(self, data: object, index: int) -> CategoryRule | None:
        where = f"triage.categories[{index}]"
        table = self.table(data, where, ("name", "description", "auto_answer", "escalates_to"))
        if table is None:
            return None
        auto = table.get("auto_answer", False)
        if not isinstance(auto, bool):
            self.problems.append(f"{where}: auto_answer must be true or false")
            return None
        return CategoryRule(
            name=table.get("name", ""),
            description=table.get("description", ""),
            auto_answer=auto,
            escalates_to=table.get("escalates_to", "needs_admin"),
        )

    def _build[T](self, factory: Callable[[], T]) -> T | None:
        try:
            return factory()
        except ConfigError as exc:
            self.problems.extend(exc.problems)
            return None

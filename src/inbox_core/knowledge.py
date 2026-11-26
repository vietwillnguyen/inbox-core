"""Knowledge entries, the retriever protocol, and a small in-memory retriever.

:class:`InMemoryRetriever` is BM25 over the entries' titles, keywords and
text, with no embeddings and no network. It is for tests, demos and small
knowledge bases; a deployment with a vector store implements :class:`Retriever`
over it instead.

Scores are BM25 units, not probabilities. A score of zero means no query term
appears in the entry, and such entries are never returned.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

__all__ = [
    "DEFAULT_STOPWORDS",
    "MAX_URL_LENGTH",
    "InMemoryRetriever",
    "KnowledgeEntry",
    "Passage",
    "Retriever",
    "is_public_url",
    "load_markdown_knowledge",
]

_WORD = re.compile(r"\w+", re.UNICODE)

_ENGLISH_STOPWORDS = (
    "a",
    "an",
    "the",
    "is",
    "are",
    "am",
    "was",
    "were",
    "be",
    "been",
    "do",
    "does",
    "did",
    "you",
    "your",
    "we",
    "our",
    "us",
    "i",
    "me",
    "my",
    "to",
    "of",
    "in",
    "on",
    "at",
    "for",
    "and",
    "or",
    "can",
    "could",
    "would",
    "what",
    "how",
    "it",
    "its",
    "this",
    "that",
    "there",
    "if",
    "any",
    "with",
    "by",
    "from",
    "as",
    "have",
    "has",
    "will",
)
_SPANISH_STOPWORDS = (
    "el",
    "la",
    "los",
    "las",
    "un",
    "una",
    "unos",
    "unas",
    "de",
    "del",
    "en",
    "y",
    "o",
    "que",
    "es",
    "son",
    "por",
    "para",
    "con",
    "se",
    "su",
    "sus",
    "mi",
    "mis",
    "me",
    "te",
    "lo",
    "al",
)
DEFAULT_STOPWORDS = frozenset((*_ENGLISH_STOPWORDS, *_SPANISH_STOPWORDS))
"""A small English and Spanish stop list. Pass your own for other languages.

"when" and "where" are deliberately kept as search terms: in an inbox they carry
the intent of the question (opening hours, location).
"""


MAX_URL_LENGTH = 2048
"""The longest public URL an entry may carry."""

_URL_UNSAFE = re.compile(r"[\s\x00-\x1f\x7f<>\"`]")


def is_public_url(value: object) -> bool:
    """Whether ``value`` is an absolute https URL fit to show the public.

    It needs the ``https`` scheme and a host, and may not carry a user name or
    password, white space, control characters, or more than
    :data:`MAX_URL_LENGTH` characters.
    """
    if not isinstance(value, str) or not value or len(value) > MAX_URL_LENGTH:
        return False
    if _URL_UNSAFE.search(value):
        return False
    try:
        parts = urlsplit(value)
        port_ok = parts.port is None or parts.port > 0
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and bool(parts.hostname)
        and parts.username is None
        and parts.password is None
        and port_ok
    )


@dataclass(frozen=True)
class KnowledgeEntry:
    """One entry in a client's knowledge base.

    ``keywords`` are extra search terms, such as the same idea in another
    language, indexed but never shown to the sender. ``url`` is the optional
    public page the entry is about (an absolute https URL, see
    :func:`is_public_url`). It is the only part of an entry a reply may show
    the public, and only when the client sets ``delivery.show_sources``; the
    id and title are for staff.
    """

    id: str
    title: str
    text: str = field(repr=False)
    keywords: tuple[str, ...] = ()
    url: str | None = None

    def __post_init__(self) -> None:
        if self.url is not None and not is_public_url(self.url):
            raise ValueError(
                f"knowledge entry {self.id!r}: url must be an absolute https URL "
                "with a host and no user name or password"
            )


@dataclass(frozen=True)
class Passage:
    """An entry a retriever found, with its score."""

    entry: KnowledgeEntry
    score: float


@runtime_checkable
class Retriever(Protocol):
    """Finds the knowledge entries most relevant to a query."""

    def search(self, query: str, *, limit: int) -> Sequence[Passage]:
        """Up to ``limit`` passages, best first, each with a positive score."""
        ...


def _tokens(text: str, stopwords: frozenset[str]) -> list[str]:
    words = (word for word in _WORD.findall(text.lower()) if word not in stopwords)
    return [word[:-1] if len(word) > 3 and word.endswith("s") else word for word in words]


class InMemoryRetriever:
    """BM25 over a fixed set of entries. Deterministic: ties keep corpus order."""

    def __init__(
        self,
        entries: Iterable[KnowledgeEntry],
        *,
        k1: float = 1.5,
        b: float = 0.75,
        stopwords: frozenset[str] = DEFAULT_STOPWORDS,
    ) -> None:
        self.entries = tuple(entries)
        ids = [entry.id for entry in self.entries]
        duplicates = sorted({entry_id for entry_id in ids if ids.count(entry_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate knowledge entry id(s): {', '.join(duplicates)}")
        self._stopwords = stopwords
        self._k1 = k1
        self._b = b
        self._docs = [
            Counter(
                _tokens(
                    " ".join((entry.title, entry.title, *entry.keywords, entry.text)), stopwords
                )
            )
            for entry in self.entries
        ]
        lengths = [sum(doc.values()) for doc in self._docs]
        self._lengths = lengths
        self._average = (sum(lengths) / len(lengths)) if lengths else 0.0
        frequency = Counter(term for doc in self._docs for term in doc)
        count = len(self._docs)
        self._idf = {
            term: math.log(1 + (count - df + 0.5) / (df + 0.5)) for term, df in frequency.items()
        }

    def search(self, query: str, *, limit: int) -> list[Passage]:
        """The best ``limit`` entries with a positive score."""
        terms = _tokens(query, self._stopwords)
        scored: list[Passage] = []
        for entry, doc, length in zip(self.entries, self._docs, self._lengths, strict=True):
            score = 0.0
            for term in terms:
                tf = doc.get(term, 0)
                if not tf:
                    continue
                norm = self._k1 * (1 - self._b + self._b * length / (self._average or 1.0))
                score += self._idf[term] * tf * (self._k1 + 1) / (tf + norm)
            if score > 0:
                scored.append(Passage(entry, round(score, 6)))
        scored.sort(key=lambda passage: passage.score, reverse=True)
        return scored[:limit]


_KEYWORDS = re.compile(r"^keywords:\s*(.*)$", re.IGNORECASE)
_URL = re.compile(r"^url:\s*(.*)$", re.IGNORECASE)


def load_markdown_knowledge(path: str | Path) -> tuple[KnowledgeEntry, ...]:
    """Entries from a Markdown file of ``## <id> <title>`` sections.

    Text before the first ``##`` heading is ignored. A section may start with a
    ``Keywords: a, b`` line and a ``URL: https://...`` line, in either order:
    the URL is the entry's public page. Raises ValueError for a missing title,
    an empty section, a duplicate id, a URL that is not an absolute https URL,
    or a file with no entries.
    """
    source = Path(path)
    entries: list[KnowledgeEntry] = []
    blocks = re.split(r"^## ", source.read_text(encoding="utf-8"), flags=re.MULTILINE)[1:]
    for block in blocks:
        head, _, body = block.partition("\n")
        entry_id, _, title = head.strip().partition(" ")
        if not title.strip():
            raise ValueError(f"{source.name}: entry {entry_id!r} has no title")
        lines = body.strip().splitlines()
        keywords: tuple[str, ...] = ()
        url: str | None = None
        for _ in range(2):
            head_line = lines[0].strip() if lines else ""
            if not keywords and (match := _KEYWORDS.match(head_line)):
                keywords = tuple(word.strip() for word in match.group(1).split(",") if word.strip())
            elif url is None and (match := _URL.match(head_line)):
                url = match.group(1).strip()
            else:
                break
            lines = lines[1:]
        text = "\n".join(lines).strip()
        if not text:
            raise ValueError(f"{source.name}: entry {entry_id!r} is empty")
        if any(entry.id == entry_id for entry in entries):
            raise ValueError(f"{source.name}: duplicate entry id {entry_id!r}")
        try:
            entries.append(KnowledgeEntry(entry_id, title.strip(), text, keywords, url))
        except ValueError as exc:
            raise ValueError(f"{source.name}: {exc}") from None
    if not entries:
        raise ValueError(f"{source.name}: no entries (expected '## <id> <title>' sections)")
    return tuple(entries)

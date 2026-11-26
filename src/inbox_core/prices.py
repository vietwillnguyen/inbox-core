"""The published-price check: a price in a reply must be stated in a passage it cites.

A client that lets the assistant answer price questions
(``triage.prices = "published_prices_only"``) is trusting the knowledge base,
not the model, with the figure. :func:`check_prices` is how the pipeline holds
it to that, in code, after the reply is written and before it is delivered.

What counts as a price in a reply:

- A **figure**: an amount (digits, with ``,`` or ``.`` separators) with a
  currency marker right before it (``£45``, ``$1,200.50``, ``USD 30``,
  ``A$12``) or right after it (``45 euros``, ``45 EUR``, ``50.000đ``,
  ``50p``). One space between the marker and the amount is allowed.
- A **lone marker**: a currency symbol, code or word that is not part of a
  figure, such as "pounds" in "forty-five pounds". A model can write a price
  in words; the marker is how that is caught.
- In a reply to a price question only, a **bare number**: digits with no
  marker, such as "45" in "a basic service is 45".

What "stated in a cited passage" means, exactly:

- A figure is stated when the same figure appears in the title or text of a
  passage the reply cites. Same means the same marker (case aside, a plural
  word read as singular) on the same side of the same amount, written the
  same way. ``£45`` matches ``£45`` and ``£ 45``; it does not match ``£45.00``,
  ``45 pounds``, ``$45`` or the ``£45`` inside ``£450``. Anything else is
  unstated, which is the fail-closed reading: a person checks it.
- A lone marker is stated when the same word or symbol appears in a cited
  passage.
- A bare number is stated when the same number appears in a cited passage,
  on its own or as the amount of a figure.

Only passages the reply cites count. A price that is in the knowledge base but
in an entry the reply was not written from is unstated.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

__all__ = ["PriceCheck", "check_prices", "price_mentions"]

_AMOUNT = r"\d+(?:[.,]\d+)*"

_SYMBOLS = "£€¥₫₹₩₱฿₺₽₪₴₦₡₲₵₭₮"
_DOLLAR = r"(?<![A-Za-z])(?:US|AU|CA|NZ|HK|A|C|S|R)?\$"
_CODES = (
    "USD|EUR|GBP|VND|AUD|CAD|NZD|JPY|CNY|RMB|INR|SGD|HKD|CHF|THB|PHP|MYR|IDR|KRW|BRL|MXN|ZAR|"
    "SEK|NOK|DKK|PLN"
)
_WORDS = r"dollars?|euros?|pounds?|pence|cents?|quid|bucks?|yen|yuan|rupees?|dong|đồng"
_SINGULAR = {"dollars", "euros", "pounds", "cents", "rupees", "bucks"}

_PREFIX = rf"{_DOLLAR}|[{_SYMBOLS}]|\b(?:{_CODES})\b"
_SUFFIX = rf"\$|[{_SYMBOLS}]|\b(?:{_CODES})\b|\b(?:{_WORDS})\b|(?:đ|p)(?!\w)"

_FIGURE = re.compile(
    rf"(?P<pre>{_PREFIX})\s?(?P<pre_amount>{_AMOUNT})|(?P<amount>{_AMOUNT})\s?(?P<suf>{_SUFFIX})",
    re.IGNORECASE,
)
_LONE = re.compile(
    rf"{_DOLLAR}|[{_SYMBOLS}]|\b(?:{_CODES})\b|\b(?:{_WORDS})\b",
    re.IGNORECASE,
)
_NUMBER = re.compile(rf"(?<![\w.,]){_AMOUNT}")


def _marker(raw: str) -> str:
    marker = raw.lower()
    return marker[:-1] if marker in _SINGULAR else marker


def _figures(text: str) -> tuple[list[str], list[str], str]:
    """The figures in ``text``, their amounts, and the text with each figure blanked."""
    figures: list[str] = []
    amounts: list[str] = []
    rest = list(text)
    for found in _FIGURE.finditer(text):
        if found.group("pre") is not None:
            amount = found.group("pre_amount")
            figures.append(f"{_marker(found.group('pre'))}{amount}")
        else:
            amount = found.group("amount")
            figures.append(f"{amount} {_marker(found.group('suf'))}")
        amounts.append(amount)
        rest[found.start() : found.end()] = " " * (found.end() - found.start())
    return figures, amounts, "".join(rest)


def price_mentions(text: str) -> tuple[str, ...]:
    """Every figure in ``text``, in order, in the normalised form the check compares."""
    return tuple(_figures(text)[0])


@dataclass(frozen=True)
class PriceCheck:
    """What :func:`check_prices` found.

    ``prices`` are the reply's figures and lone markers; ``unstated`` the ones
    (and, for a price question, the bare numbers) no cited passage states.
    Both hold normalised figures, markers and numbers only, never other text.
    """

    prices: tuple[str, ...]
    unstated: tuple[str, ...]

    @property
    def states_prices(self) -> bool:
        """Whether the reply states any price at all."""
        return bool(self.prices) or bool(self.unstated)


def check_prices(reply: str, passages: Iterable[str], *, price_question: bool) -> PriceCheck:
    """Which prices in ``reply`` no passage in ``passages`` states. See the module docstring.

    ``passages`` are the texts (titles included) of the passages the reply
    cites. ``price_question`` turns on the bare-number rule, for a reply to a
    message that asks what something costs.
    """
    cited = list(passages)
    stated: set[str] = set()
    cited_numbers: set[str] = set()
    for passage in cited:
        figures, amounts, rest = _figures(passage)
        stated.update(figures)
        cited_numbers.update(amounts)
        cited_numbers.update(_NUMBER.findall(rest))
    cited_text = "\n".join(cited)

    figures, _, rest = _figures(reply)
    lone = [found.group(0).lower() for found in _LONE.finditer(rest)]
    unstated = [figure for figure in figures if figure not in stated]
    for marker in lone:
        if not re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", cited_text, re.IGNORECASE):
            unstated.append(marker)
    if price_question:
        unstated.extend(n for n in _NUMBER.findall(rest) if n not in cited_numbers)
    return PriceCheck(
        prices=tuple(dict.fromkeys([*figures, *lone])),
        unstated=tuple(dict.fromkeys(unstated)),
    )

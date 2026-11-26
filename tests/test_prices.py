"""The published-price check: every price a reply states must be in a cited passage."""

from __future__ import annotations

import pytest

from inbox_core.prices import check_prices, price_mentions

PRICES = "A basic service costs £45. A full service costs £120. City bikes rent for £20 a day."


class TestFindingPrices:
    @pytest.mark.parametrize(
        ("text", "found"),
        [
            ("It costs £45.", ("£45",)),
            ("It costs £ 45.", ("£45",)),
            ("It costs $1,200.50 in total", ("$1,200.50",)),
            ("About 45 euros", ("45 euro",)),
            ("About 45 EUR", ("45 eur",)),
            ("USD 30 or 25 dollars", ("usd30", "25 dollar")),
            ("50.000đ một giờ", ("50.000 đ",)),
            ("50p a go", ("50 p",)),
            ("A$12 and NZ$ 9", ("a$12", "nz$9")),
        ],
    )
    def test_figures_with_a_currency_are_found(self, text: str, found: tuple[str, ...]) -> None:
        assert price_mentions(text) == found

    @pytest.mark.parametrize(
        "text",
        [
            "We open at 5pm on Saturdays.",
            "It takes two working days.",
            "The shop is at 12 Lantern Row.",
            "Riders aged 16 or over can rent on their own.",
        ],
    )
    def test_times_addresses_and_counts_are_not_prices(self, text: str) -> None:
        assert price_mentions(text) == ()


class TestPublishedPrices:
    def test_a_price_copied_from_a_cited_passage_is_stated(self) -> None:
        check = check_prices("A basic service is £45.", (PRICES,), price_question=True)
        assert check.prices == ("£45",)
        assert check.unstated == ()
        assert check.states_prices

    def test_an_invented_price_is_unstated(self) -> None:
        check = check_prices("A basic service is £40.", (PRICES,), price_question=True)
        assert check.unstated == ("£40",)

    def test_a_figure_inside_a_larger_one_does_not_count(self) -> None:
        # "£12" is a substring of "£120", but it is not stated.
        check = check_prices("A puncture repair is £12.", (PRICES,), price_question=False)
        assert check.unstated == ("£12",)

    def test_the_same_amount_in_another_currency_is_unstated(self) -> None:
        check = check_prices("A basic service is $45.", (PRICES,), price_question=False)
        assert check.unstated == ("$45",)

    def test_a_price_from_an_uncited_passage_is_unstated(self) -> None:
        check = check_prices(
            "A basic service is £45.", ("The shop opens at 8am.",), price_question=False
        )
        assert check.unstated == ("£45",)

    def test_a_spelled_out_price_is_unstated(self) -> None:
        check = check_prices("It is forty-five pounds.", (PRICES,), price_question=True)
        assert check.unstated == ("pounds",)

    def test_a_bare_number_in_an_answer_to_a_price_question_must_be_cited(self) -> None:
        invented = check_prices("A basic service is 40.", (PRICES,), price_question=True)
        assert invented.unstated == ("40",)
        cited = check_prices("A basic service is 45.", (PRICES,), price_question=True)
        assert cited.unstated == ()

    def test_bare_numbers_are_not_checked_outside_a_price_question(self) -> None:
        check = check_prices("It takes 3 days.", ("It takes two days.",), price_question=False)
        assert check.unstated == ()
        assert not check.states_prices

    def test_a_reply_with_no_price_states_none(self) -> None:
        check = check_prices("Please ask at the counter.", (PRICES,), price_question=True)
        assert check.prices == ()
        assert check.unstated == ()
        assert not check.states_prices

    def test_a_reply_with_one_stated_and_one_invented_price_is_unstated(self) -> None:
        check = check_prices("Basic £45, full £150.", (PRICES,), price_question=True)
        assert check.prices == ("£45", "£150")
        assert check.unstated == ("£150",)

"""expression_v1 language: safe parsing and evaluation on a frame."""

import polars as pl
import pytest

from factor_investor.components.expression import parse_expression

FRAME = pl.DataFrame(
    {
        "instrument_id": [1, 2, 3, 4],
        "roic": [0.20, 0.05, None, 0.30],
        "pe_ratio": [10.0, 30.0, 12.0, -5.0],
        "fcf_yield": [0.08, 0.01, 0.07, None],
    }
)


def selected(source: str) -> list[int]:
    expression = parse_expression(source)
    return FRAME.filter(expression.to_polars().fill_null(False))["instrument_id"].to_list()


def test_comparisons_and_boolean_logic() -> None:
    assert selected("roic >= 0.15 and pe_ratio < 15") == [1, 4]
    assert selected("roic >= 0.15 and (pe_ratio < 0 or fcf_yield > 0.06)") == [1, 4]
    assert selected("not roic > 0.1") == [2]


def test_missing_values_never_pass() -> None:
    """Instrument 3 has no ROIC: a condition on it is unknown, so it is not selected."""
    assert 3 not in selected("roic >= 0")
    assert 3 not in selected("not roic >= 0")
    assert 3 in selected("roic >= 0 or pe_ratio > 0")


def test_arithmetic_and_chained_comparisons() -> None:
    assert selected("0 < pe_ratio <= 12") == [1, 3]
    assert selected("1 / pe_ratio > 0.09") == [1]
    assert selected("abs(pe_ratio) <= 5") == [4]
    assert selected("-pe_ratio > 0") == [4]


def test_names_are_collected() -> None:
    assert parse_expression("roic >= 0.15 and (pe_ratio < 15 or abs(fcf_yield) > 0)").names == {
        "roic",
        "pe_ratio",
        "fcf_yield",
    }


@pytest.mark.parametrize(
    "source",
    [
        "__import__('os').system('ls')",
        "roic.real > 0",
        "open('x')",
        "[roic]",
        "roic if pe_ratio else fcf_yield",
        "lambda: 1",
        "roic ** 2 > 0",
        "'text' == roic",
        "roic in (1, 2)",
        "",
    ],
)
def test_anything_else_is_refused(source: str) -> None:
    with pytest.raises(ValueError):
        parse_expression(source)


def test_unknown_names_are_refused_when_names_are_given() -> None:
    with pytest.raises(ValueError, match="roci"):
        parse_expression("roci > 0", known_names={"roic"})
    assert parse_expression("roic > 0", known_names={"roic"}).names == {"roic"}

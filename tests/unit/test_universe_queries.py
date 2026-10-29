"""Converting universe snapshot columns."""

from decimal import Decimal

from factor_investor.universe.queries import _to_float


def test_zero_stays_zero() -> None:
    """A median turnover of 0 (no trades) is information, not a missing value."""
    assert _to_float(Decimal("0.00")) == 0.0
    assert _to_float(None) is None
    assert _to_float(Decimal("12.5")) == 12.5

"""Pipeline strategy pieces that need no database."""

import hashlib
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from factor_investor.pipeline.strategy import combine_scores, rebalancing_dates
from factor_investor.strategy.registry import RegisteredStrategy


def scores(rows: list[tuple[int, float | None]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema={"instrument_id": pl.Int32, "score": pl.Float64}, orient="row")


def test_weighted_mean_over_available_blocks_with_minimum_coverage() -> None:
    quality = scores([(1, 0.9), (2, 0.1), (3, None)])
    value = scores([(1, 0.5), (2, None), (3, 0.8)])
    result = dict(combine_scores([(quality, 3.0), (value, 1.0)], min_coverage=0.5).rows())
    assert result[1] == pytest.approx((0.9 * 3 + 0.5) / 4)
    assert result[2] == pytest.approx(0.1)  # 75% of the weight has a score
    assert result[3] is None  # 25% < 50%


def test_full_coverage_required_by_default() -> None:
    result = dict(
        combine_scores(
            [(scores([(1, 0.9), (2, 0.1)]), 1.0), (scores([(1, 0.5), (2, None)]), 1.0)],
            min_coverage=1.0,
        ).rows()
    )
    assert result == {1: pytest.approx(0.7), 2: None}


def test_rebalancing_dates() -> None:
    year = (date(2024, 1, 1), date(2024, 12, 31))
    assert len(rebalancing_dates("monthly", *year)) == 12
    assert [d.month for d in rebalancing_dates("quarterly", *year)] == [3, 6, 9, 12]
    assert [d.month for d in rebalancing_dates("semiannual", *year)] == [6, 12]
    assert [d.month for d in rebalancing_dates("annual", *year)] == [12]


def test_single_source_file_hash_is_unchanged(tmp_path: Path) -> None:
    """Trials logged before multi-file hashes must still match."""
    source = tmp_path / "a.py"
    source.write_text("x = 1\n")
    registered = RegisteredStrategy("a_v1", lambda _p: None, (source,))  # type: ignore[arg-type, return-value]
    assert registered.source_hash() == hashlib.sha256(b"x = 1\n").hexdigest()

    other = tmp_path / "b.yaml"
    other.write_text("id: b\n")
    both = RegisteredStrategy("a_v1", lambda _p: None, (source, other))  # type: ignore[arg-type, return-value]
    before = both.source_hash()
    assert before != registered.source_hash()
    other.write_text("id: c\n")  # editing any file changes the hash
    assert both.source_hash() != before

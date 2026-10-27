"""get_factor must normalize over the full cross-section, regardless of the
instrument_ids filter, and the cache must hold the full cross-section."""

from datetime import date

import polars as pl
import pytest

from factor_investor.factors import queries

AS_OF = date(2024, 1, 31)
BASE = pl.DataFrame(
    {
        "instrument_id": [1, 2, 3, 4],
        "date": [AS_OF] * 4,
        "value": [10.0, 20.0, 30.0, 40.0],
    }
)


@pytest.fixture(autouse=True)
def fake_base_metric(monkeypatch, tmp_path):
    def fake(metric, as_of_date, instrument_ids=None):
        df = BASE
        if instrument_ids:
            df = df.filter(pl.col("instrument_id").is_in(instrument_ids))
        return df

    monkeypatch.setattr(queries, "_get_base_metric", fake)
    monkeypatch.setattr(queries, "CACHE_DIR", tmp_path)


def test_subset_request_uses_full_cross_section_percentiles() -> None:
    full = queries.get_factor("roe_level_pct", AS_OF, use_cache=False)
    subset = queries.get_factor("roe_level_pct", AS_OF, instrument_ids=[2], use_cache=False)

    expected = full.filter(pl.col("instrument_id") == 2)["value"].to_list()
    assert subset["value"].to_list() == expected


def test_cache_written_by_subset_request_holds_everyone() -> None:
    queries.get_factor("roe_level_pct", AS_OF, instrument_ids=[1])

    cached_full = queries.get_factor("roe_level_pct", AS_OF)

    assert sorted(cached_full["instrument_id"].to_list()) == [1, 2, 3, 4]

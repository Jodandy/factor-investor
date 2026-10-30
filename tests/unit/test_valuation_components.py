"""H11 components: relative value (own multiple history) and owner-earnings IRR."""

from datetime import date

import pytest

from factor_investor.components.base import build_component
from factor_investor.components.valuation import DcfParams, dcf_value
from tests.unit.test_components import FakeView, ids, scores

T = date(2024, 1, 31)
MONTHS = [date(2022 + (m + 1) // 12, (m + 1) % 12 + 1, 28) for m in range(23)]  # 2022-02..2023-12


def history(values: dict[int, float]) -> list[tuple[int, date, float]]:
    """Each instrument's multiple constant at `value` over the past 23 months."""
    return [(i, d, v) for i, v in values.items() for d in MONTHS]


# P/E: 1 trades at half its usual multiple, 2 at its usual, 3 is a loss now.
# P/S: 1 and 2 both at their usual multiple; 3 cheap.
VIEW = FakeView(
    {"pe_ratio": {1: 10.0, 2: 20.0, 3: -5.0}, "ps_ratio": {1: 2.0, 2: 2.0, 3: 1.0}},
    history={
        "pe_ratio": history({1: 20.0, 2: 20.0, 3: 15.0}),
        "ps_ratio": history({1: 2.0, 2: 2.0, 3: 2.0}),
    },
)
REL = {"metrics": ["pe_ratio", "ps_ratio"], "years": 2, "min_observations": 12, "min_metrics": 1}


def kept(
    component: str, params: dict[str, object], view: FakeView, instruments: list[int]
) -> list[int]:
    result = build_component(component, params).run(view, ids(*instruments))  # type: ignore[attr-defined]
    return sorted(result["instrument_id"].to_list())


def test_relative_upside_is_the_mean_over_valid_metrics() -> None:
    # 1: P/E +100%, P/S 0% -> +50%; 2: 0%; 3: P/E invalid, P/S +100% -> +100%
    assert kept(
        "relative_value_filter_v1", {**REL, "band": "mid", "min_upside": 0.4}, VIEW, [1, 2, 3]
    ) == [1, 3]
    assert kept(
        "relative_value_filter_v1", {**REL, "band": "mid", "min_upside": 0.6}, VIEW, [1, 2, 3]
    ) == [3]


def test_min_metrics_requires_enough_valid_multiples() -> None:
    params = {**REL, "min_metrics": 2, "band": "mid", "min_upside": 0.0}
    assert kept("relative_value_filter_v1", params, VIEW, [1, 2, 3]) == [
        1,
        2,
    ]  # 3 has one valid multiple


def test_relative_score_ranks_by_upside() -> None:
    result = scores(build_component("relative_value_score_v1", REL).run(VIEW, ids(1, 2, 3)))  # type: ignore[attr-defined]
    assert result[3] > result[1] > result[2]


ANNUAL = {
    # 10 and 11: same price 100; 10 earns 10/share, 11 earns 2/share; 12 has a loss
    "earnings_per_share": [(10, date(y, 12, 31), 10.0) for y in (2021, 2022, 2023)]
    + [(11, date(y, 12, 31), 2.0) for y in (2021, 2022, 2023)]
    + [(12, date(2023, 12, 31), -1.0)],
    "dividend": [(10, date(2023, 12, 31), 5.0), (11, date(2023, 12, 31), 1.0)],
    "roe": [
        (10, date(2023, 12, 31), 0.20),
        (11, date(2023, 12, 31), 0.20),
        (12, date(2023, 12, 31), -0.1),
    ],
}
IRR_VIEW = FakeView({}, universe={"price": {10: 100.0, 11: 100.0, 12: 100.0}}, annual=ANNUAL)
IRR = {"years_avg": 3, "growth_cap": 0.10, "growth_fallback": 0.06}


def test_owner_earnings_irr_filter() -> None:
    # growth = min(10%, ROE 20% x retention 50%) = 10%: value of 10/share at 100 is very cheap
    p = DcfParams()
    assert dcf_value(10.0, 0.10, 0.15, p) > 100 > dcf_value(2.0, 0.10, 0.15, p)
    assert kept(
        "owner_earnings_irr_filter_v1", {**IRR, "min_irr": 0.15}, IRR_VIEW, [10, 11, 12]
    ) == [10]
    assert kept(
        "owner_earnings_irr_filter_v1", {**IRR, "min_irr": -0.2}, IRR_VIEW, [10, 11, 12]
    ) == [10, 11]


def test_owner_earnings_irr_score() -> None:
    result = scores(
        build_component("owner_earnings_irr_score_v1", IRR).run(IRR_VIEW, ids(10, 11, 12))
    )  # type: ignore[attr-defined]
    assert result[10] > result[11]
    assert result[12] is None


def test_invalid_band() -> None:
    with pytest.raises(ValueError):
        build_component("relative_value_filter_v1", {**REL, "band": "low", "min_upside": 0.1})

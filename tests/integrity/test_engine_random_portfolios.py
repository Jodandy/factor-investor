"""Random portfolios average out to the equal-weighted universe (WORK_ORDER fas 6).

Each period, an equal-weighted random pick of k names returns the mean of its
names' returns, whose expectation over all picks is the mean of all names: the
equal-weighted universe. With independent picks per period, the expected final
value of a random portfolio equals the equal-weighted universe's final value
exactly (zero costs). With costs, random portfolios trade far more and fall
behind.

No database, but ~90 s, so not part of the fast suite run after every edit.
"""

import random
import statistics

import pytest

from tests.integrity.synthetic import (
    InMemoryEngine,
    ScheduledStrategy,
    equal_weight,
    random_walk_prices,
    run,
    trading_days,
)

N_NAMES, PICK, EVERY, N_DAYS = 40, 5, 10, 121
DAYS = trading_days(N_DAYS)
SIGNAL_DAYS = DAYS[: -1 : EVERY]
PRICES = random_walk_prices(N_NAMES, N_DAYS, seed=3)
ENGINE = InMemoryEngine(PRICES)


def random_schedule(run_id: int) -> dict:
    return {
        d: equal_weight(random.Random(run_id * 1_000_003 + d.toordinal()).sample(range(N_NAMES), PICK))
        for d in SIGNAL_DAYS
    }


def final_values(n_runs: int, cost_bps: int) -> list[float]:
    return [
        run(ENGINE, ScheduledStrategy(random_schedule(r), cost_bps=cost_bps), DAYS).metadata["final_value"]
        for r in range(n_runs)
    ]


def equal_weighted_universe(cost_bps: int) -> float:
    schedule = {d: equal_weight(list(range(N_NAMES))) for d in SIGNAL_DAYS}
    return run(ENGINE, ScheduledStrategy(schedule, cost_bps=cost_bps), DAYS).metadata["final_value"]


@pytest.mark.integrity
@pytest.mark.slow
def test_random_portfolios_average_to_equal_weight_without_costs() -> None:
    values = final_values(500, cost_bps=0)
    mean = statistics.fmean(values)
    standard_error = statistics.stdev(values) / len(values) ** 0.5

    assert abs(mean - equal_weighted_universe(cost_bps=0)) < 4 * standard_error


@pytest.mark.integrity
@pytest.mark.slow
def test_random_portfolios_trail_equal_weight_by_their_costs() -> None:
    free = statistics.fmean(final_values(100, cost_bps=0))
    costly = statistics.fmean(final_values(100, cost_bps=10))
    benchmark = equal_weighted_universe(cost_bps=10)

    # Same picks, so the gap is the cost drag: ~12 rebalances turning over most of
    # the portfolio at 10 bps each way is about 2%
    assert 0.01 < 1 - costly / free < 0.03
    assert costly < benchmark

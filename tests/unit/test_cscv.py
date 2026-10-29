"""CSCV/PBO, deflated Sharpe and block stability on synthetic returns."""

import itertools
import math

import numpy as np
import pytest

from factor_investor.validation.cscv import (
    block_bounds,
    block_stability,
    cscv,
    deflated_sharpe,
    expected_max_sharpe,
    probabilistic_sharpe,
)


def noise(months: int, configs: int, seed: int, mean: float = 0.0) -> np.ndarray:
    return np.random.default_rng(seed).normal(mean, 0.04, (months, configs))


def test_blocks_cover_every_month_once() -> None:
    bounds = block_bounds(226, 8)
    assert len(bounds) == 8
    assert bounds[0][0] == 0 and bounds[-1][1] == 226
    assert all(a[1] == b[0] for a, b in itertools.pairwise(bounds))
    assert max(e - s for s, e in bounds) - min(e - s for s, e in bounds) <= 1


def test_every_block_is_out_of_sample_equally_often() -> None:
    result = cscv(noise(160, 10, seed=1), n_blocks=8, purge=0)
    assert result.combinations == math.comb(8, 4) == 70
    assert set(result.oos_block_counts) == {35}


def test_pure_noise_gives_pbo_near_one_half() -> None:
    """With no skill, the in-sample winner is a coin flip out of sample."""
    pbos = [cscv(noise(240, 50, seed=s), n_blocks=8, purge=0).pbo for s in range(20)]
    assert 0.35 < float(np.mean(pbos)) < 0.65


def test_a_real_edge_gives_pbo_near_zero() -> None:
    returns = noise(240, 20, seed=2)
    returns[:, 7] += 0.03  # one configuration with a large, persistent edge
    result = cscv(returns, n_blocks=8, purge=0)
    assert result.pbo < 0.05
    assert result.best_is_counts[7] == result.combinations


def test_purge_removes_months_next_to_training_blocks() -> None:
    returns = noise(80, 3, seed=3)
    assert (
        cscv(returns, n_blocks=4, purge=2).oos_months_mean
        < cscv(returns, n_blocks=4, purge=0).oos_months_mean
    )


def test_probabilistic_sharpe_basics() -> None:
    assert probabilistic_sharpe(0.0, 0.0, 120, 0.0, 3.0) == pytest.approx(0.5)
    assert probabilistic_sharpe(0.2, 0.0, 120, 0.0, 3.0) > 0.95
    # fat tails and negative skew make a Sharpe ratio less certain
    assert probabilistic_sharpe(0.2, 0.0, 120, -1.0, 8.0) < probabilistic_sharpe(
        0.2, 0.0, 120, 0.0, 3.0
    )


def test_expected_max_sharpe_grows_with_trials() -> None:
    assert expected_max_sharpe(1, 0.01) == 0.0
    values = [expected_max_sharpe(n, 0.01) for n in (2, 10, 100, 1000)]
    assert values == sorted(values) and values[0] > 0


def test_deflated_sharpe_falls_with_more_trials() -> None:
    returns = noise(226, 1, seed=4, mean=0.01)[:, 0]
    one = deflated_sharpe(returns, n_trials=1, sharpe_variance=0.002)
    many = deflated_sharpe(returns, n_trials=100, sharpe_variance=0.002)
    assert one.dsr > many.dsr
    assert one.expected_max_sharpe == 0.0


def test_block_stability() -> None:
    benchmark = np.zeros(80)
    returns = np.zeros((80, 2))
    returns[:, 0] = 0.01  # beats the benchmark in every block
    returns[:40, 1] = 0.01  # only in the first half
    returns[40:, 1] = -0.01
    result = block_stability(returns, benchmark, n_blocks=4)
    assert result.share_of_blocks_beaten.tolist() == [1.0, 0.5]
    assert result.excess_by_block.shape == (4, 2)

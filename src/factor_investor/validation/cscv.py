"""Overfitting statistics over an experiment's configurations.

- `cscv`: combinatorially symmetric cross-validation (Bailey, Borwein, López
  de Prado and Zhu, "The Probability of Backtest Overfitting", 2017). The
  history is split into blocks; for every choice of half the blocks as
  in-sample, the configuration with the best in-sample Sharpe ratio is ranked
  out-of-sample on the other half. PBO is the share of splits where it ranks
  at or below the median. Every block is out-of-sample in half the splits, so
  all periods weigh equally. Months next to an in-sample block can be purged
  from the out-of-sample set (holding periods straddle the boundary).
- `deflated_sharpe`: probability that the true Sharpe ratio exceeds what the
  best of n_trials unskilled configurations would show (Bailey and López de
  Prado, "The Deflated Sharpe Ratio", 2014), adjusted for skew and fat tails.
- `block_stability`: excess return over a benchmark per block.

Inputs are monthly returns, shape (months, configurations). Sharpe ratios are
per month (not annualized), as the formulas expect.
"""

import itertools
import math
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

EULER_GAMMA = 0.5772156649015329
_NORMAL = NormalDist()


def block_bounds(months: int, n_blocks: int) -> list[tuple[int, int]]:
    """[start, end) of n_blocks consecutive blocks of (nearly) equal length."""
    edges = np.linspace(0, months, n_blocks + 1).round().astype(int)
    return [(int(a), int(b)) for a, b in itertools.pairwise(edges)]


def _sharpe(returns: np.ndarray) -> np.ndarray:
    std = returns.std(axis=0, ddof=1)
    return np.where(std > 0, returns.mean(axis=0) / np.where(std > 0, std, 1.0), 0.0)


@dataclass(frozen=True)
class CscvResult:
    combinations: int
    pbo: float
    logits: np.ndarray  # one per split; <= 0 means the IS winner ranked at or below the OOS median
    best_is_counts: np.ndarray  # per configuration: splits in which it was the IS winner
    oos_block_counts: list[int]  # per block: splits in which it was out-of-sample
    oos_months_mean: float
    oos_sharpe_of_is_best: np.ndarray  # per split
    oos_sharpe_median: np.ndarray  # per split, median over configurations

    @property
    def prob_oos_loss(self) -> float:
        """Share of splits where the IS winner has a negative OOS Sharpe ratio."""
        return float(np.mean(self.oos_sharpe_of_is_best < 0))


def cscv(returns: np.ndarray, n_blocks: int = 8, purge: int = 1) -> CscvResult:
    """PBO over the configurations (columns) of `returns`.

    Args:
        returns: monthly returns, shape (months, configurations)
        n_blocks: even number of blocks
        purge: months dropped from the out-of-sample set on each side of an
            in-sample block
    """
    months, n_configs = returns.shape
    if n_blocks % 2 or n_blocks < 2:
        raise ValueError("n_blocks must be even")
    if n_configs < 2:
        raise ValueError("CSCV needs at least two configurations")
    bounds = block_bounds(months, n_blocks)
    logits, best_counts, oos_counts = [], np.zeros(n_configs, dtype=int), [0] * n_blocks
    oos_lengths, oos_best, oos_median = [], [], []

    for is_blocks in itertools.combinations(range(n_blocks), n_blocks // 2):
        in_sample = np.zeros(months, dtype=bool)
        for b in is_blocks:
            in_sample[bounds[b][0] : bounds[b][1]] = True
        near_is = in_sample.copy()
        for shift in range(1, purge + 1):
            near_is[shift:] |= in_sample[:-shift]
            near_is[:-shift] |= in_sample[shift:]
        out_of_sample = ~near_is
        for b in set(range(n_blocks)) - set(is_blocks):
            oos_counts[b] += 1

        is_sharpe = _sharpe(returns[in_sample])
        oos_sharpe = _sharpe(returns[out_of_sample])
        best = int(np.argmax(is_sharpe))
        best_counts[best] += 1
        # rank 1 = worst ... n_configs = best; relative rank strictly inside (0, 1)
        rank = 1 + int(np.sum(oos_sharpe < oos_sharpe[best]))
        omega = rank / (n_configs + 1)
        logits.append(math.log(omega / (1 - omega)))
        oos_lengths.append(int(out_of_sample.sum()))
        oos_best.append(float(oos_sharpe[best]))
        oos_median.append(float(np.median(oos_sharpe)))

    logit_array = np.array(logits)
    return CscvResult(
        combinations=len(logits),
        pbo=float(np.mean(logit_array <= 0)),
        logits=logit_array,
        best_is_counts=best_counts,
        oos_block_counts=oos_counts,
        oos_months_mean=float(np.mean(oos_lengths)),
        oos_sharpe_of_is_best=np.array(oos_best),
        oos_sharpe_median=np.array(oos_median),
    )


def probabilistic_sharpe(
    sharpe: float, benchmark_sharpe: float, observations: int, skew: float, kurtosis: float
) -> float:
    """P(true Sharpe > benchmark_sharpe) given an observed per-period Sharpe
    ratio, its sample size, skewness and (non-excess) kurtosis."""
    variance = 1 - skew * sharpe + (kurtosis - 1) / 4 * sharpe**2
    z = (sharpe - benchmark_sharpe) * math.sqrt(observations - 1) / math.sqrt(max(variance, 1e-12))
    return _NORMAL.cdf(z)


def expected_max_sharpe(n_trials: int, sharpe_variance: float) -> float:
    """Expected highest Sharpe ratio among n_trials unskilled configurations
    whose Sharpe ratios vary with sharpe_variance."""
    if n_trials <= 1:
        return 0.0
    return math.sqrt(sharpe_variance) * (
        (1 - EULER_GAMMA) * _NORMAL.inv_cdf(1 - 1 / n_trials)
        + EULER_GAMMA * _NORMAL.inv_cdf(1 - 1 / (n_trials * math.e))
    )


@dataclass(frozen=True)
class DeflatedSharpe:
    sharpe: float  # per period
    expected_max_sharpe: float
    dsr: float
    observations: int
    skew: float
    kurtosis: float


def deflated_sharpe(returns: np.ndarray, n_trials: int, sharpe_variance: float) -> DeflatedSharpe:
    """Deflated Sharpe ratio of one return series selected among n_trials."""
    observations = len(returns)
    centered = returns - returns.mean()
    std = returns.std(ddof=1)
    sharpe = float(returns.mean() / std)
    skew = float(np.mean(centered**3) / returns.std() ** 3)
    kurtosis = float(np.mean(centered**4) / returns.std() ** 4)
    threshold = expected_max_sharpe(n_trials, sharpe_variance)
    return DeflatedSharpe(
        sharpe=sharpe,
        expected_max_sharpe=threshold,
        dsr=probabilistic_sharpe(sharpe, threshold, observations, skew, kurtosis),
        observations=observations,
        skew=skew,
        kurtosis=kurtosis,
    )


@dataclass(frozen=True)
class BlockStability:
    excess_by_block: np.ndarray  # (blocks, configurations), compounded return minus benchmark's
    share_of_blocks_beaten: np.ndarray  # per configuration


def block_stability(
    returns: np.ndarray, benchmark: np.ndarray, n_blocks: int = 8
) -> BlockStability:
    """Compounded excess return over the benchmark in each block."""
    rows = []
    for start, end in block_bounds(len(returns), n_blocks):
        strategy = np.prod(1 + returns[start:end], axis=0) - 1
        bench = np.prod(1 + benchmark[start:end]) - 1
        rows.append(strategy - bench)
    excess = np.array(rows)
    return BlockStability(excess, (excess > 0).mean(axis=0))

"""Benchmark run files: one per benchmark and area, random seeds grouped."""

from pathlib import Path

from factor_investor.benchmarks.run import AREAS, BenchmarkRun


def test_paths() -> None:
    out = Path("out")
    assert BenchmarkRun("SE", "cap").path(out) == out / "cap_weight_v1_SE.parquet"
    assert BenchmarkRun("EU", "equal").path(out) == out / "equal_weight_v1_EU.parquet"
    assert BenchmarkRun("SE", "random", 30, 7).path(out) == (
        out / "random_pick_v1_SE_k30" / "seed_007.parquet"
    )


def test_areas() -> None:
    assert set(AREAS) == {"SE", "NO", "FI", "DK", "US", "EU"}

# Strategy system architecture

Status: **draft for review** (2026-10-28). Replaces the strategy-schema parts of WORK_ORDER fas 5 once agreed. Invariants in `CLAUDE.md` take precedence over everything here.

## 1. Goal

Systematically find out *which kinds of approaches work*, not just tune one. The owner's own thesis — good companies, cheap in relative and absolute terms, intact fundamentals, under accumulation, bought when they start moving up, held hard — is one configuration among many. "Pure trend following", "just cheap", "quality at any price" are others. The final result may be an ensemble.

Therefore:

- A strategy is a **pipeline of independent stages**. Each stage is made of **components** that can be switched on/off, configured, swapped, or searched over.
- Simple things are **declared in YAML**; complex things (DCF, Monte Carlo, accumulation detectors, ML, custom entry tactics) are **code**. Both look identical from the outside: one interface, one config format, one search syntax, one registry.
- Every component and named configuration is **versioned** and **immutable once used**.
- Components can only see data through a **point-in-time view**. Lookahead is impossible by construction, not just tested for.

## 2. Pipeline stages

```
                 ┌──────────────────────── rebalance clock (e.g. monthly) ────────────────────────┐
 all instruments │ 1.1 Universe filters → 1.2 Selection pools → 2 Valuation & quality scoring     │ → candidates
                 └─────────────────────────────────────────────────────────────────────────────────┘     (scored)
                 ┌──────────────────────── daily clock ───────────────────────────────────────────┐
 candidates +    │ 3 Technical timing → 4 Entry / trade management / exit → 5 Portfolio & sizing  │ → orders
 positions       └─────────────────────────────────────────────────────────────────────────────────┘     (T+1)
```

| Stage | Purpose | Examples |
|---|---|---|
| **1.1 Universe filters** | Cheap screens on simple data. May be empty ("no filters"). | min price, min turnover, min market cap, exclude sectors |
| **1.2 Selection pools** | One or more pools of companies matching metric combinations; pools are combined with AND/OR. | `top_growth_quality_v1`: ROIC ≥ x AND (A > u OR B > t) |
| **2.1 Relative valuation** | Attractive vs. the company's own history. | P/E percentile vs. own 10y, price vs. historical relation to FCF |
| **2.2 Absolute valuation** | Attractive in absolute terms. | `dcf_fcf_v1`, `dcf_owner_earnings_v1`, `dcf_monte_carlo_v1`, EV/EBIT thresholds |
| **2.3 Business quality** | Stability, durability; metric proxies first, AI later (see §6.3). | Piotroski, margin stability, ROIC consistency |
| **2.4 Cross-sectional** | Everything above relative to other companies. | percentiles, z-scores within universe or sector |
| **3.1 Price action** | Trend, momentum, mean reversion, ML. | MA distance, RSI, 12-1 momentum |
| **3.2 Volume action** | Accumulation/distribution; support and resistance from past volume. | `accumulation_obv_v1`, volume trend, `volume_profile_v1` (later, see §10.2) |
| **4 Entry / management / exit** | When and how to enter, add, trim, exit; positions can have several tranches. | `breakout_entry_v1`, `pyramid_on_strength_v1`, `trailing_stop_v1` |
| **5 Portfolio & sizing** | How much per position, limits, cash policy. | equal weight, inverse volatility, max per sector |
| **Ensemble** | Combine complete systems. | 50% thesis system + 50% trend system |

Stages 1–2 run on the **rebalance clock** (fundamentals change slowly; expensive computations). Stages 3–5 run on the **daily clock** over the current candidates and open positions, because entry timing and exits need daily resolution. Any stage may be empty or disabled.

## 3. Components

### 3.1 Kinds and outputs

| Kind | Input | Output |
|---|---|---|
| `filter` | instruments, date | subset of instruments |
| `score` | instruments, date | score per instrument (higher = better), NaN allowed |
| `signal` | instruments, date | per-instrument signal strength in [−1, 1] or boolean |
| `entry` | candidates + signals, date | order intents to open/add (with tranche info) |
| `management` | open positions, date | intents to add/trim (pyramiding, scaling out) |
| `exit` | open positions, date | intents to close, with a reason |
| `sizing` | intents + portfolio state | target size per intent |
| `portfolio` | all intents + state | final orders (limits, sector caps, cash policy) |

Every order and trade carries the id of the component that caused it (the "reason"), so the trade log shows *why* each trade happened.

### 3.2 Interface (sketch)

```python
class Component(ABC):
    id: ClassVar[str]               # e.g. "dcf_monte_carlo_v1" — must end in _v<N>
    kind: ClassVar[ComponentKind]
    Params: ClassVar[type[BaseModel]]   # pydantic schema; defines what can be searched

    def __init__(self, params: BaseModel) -> None: ...

    @abstractmethod
    def run(self, view: PointInTimeView, instruments: list[int]) -> ComponentResult: ...
```

- Components are pure functions of `(params, view, instruments)`; any randomness takes a seed from params (invariant 7).
- Components declare their **data needs** (metrics, price history length) so the pipeline can preload and cache efficiently.
- Code components live in `src/factor_investor/components/<kind>/<id>.py` and register via a decorator. The registry rejects duplicate ids and ids without a version suffix.

### 3.3 The generic expression component

Most of 1.1, 1.2, 2.4 and simple 2.x needs no code. A built-in `expression_v1` evaluates boolean or arithmetic expressions over any registered factor:

```yaml
expression: "roic_mean_5y >= 0.15 and (pe_ratio < 15 or fcf_yield > 0.06)"
```

Factors are the existing generative factors (`<base>_<transformation>_<window>_<normalization>`) plus any `score` component output, referenced by id. Expressions are parsed into a safe AST (no `eval`), and the parser validates that every referenced factor exists.

## 4. Versioning

**Rule: everything that can affect a result has an explicit version, and a version never changes behavior once used in a logged run.**

- **Code components:** id ends in `_v<N>` (`dcf_monte_carlo_v1`, `my_own_entry_tactic_v1`). Any change to behavior → new file, new id (`_v2`). Pure refactors that provably keep results identical may keep the version; when in doubt, bump.
- **Named configurations:** selection criteria, scoring blocks, strategies, systems and ensembles defined in YAML are versioned the same way (`top_growth_quality_v1`, `thesis_value_accumulation_v1`). Changing any parameter or structure → new version. Search spaces count as structure (WORK_ORDER fas 10).
- **Enforcement:**
  - The registry refuses unversioned or duplicate ids.
  - Each component version stores a hash of its source file (code) or canonical YAML (config). The trial registry records ids, versions and hashes for every run.
  - If an id that already appears in the trial registry is found with a different hash, the run is refused: "`top_growth_quality_v1` changed after use — create `_v2`".
- Old versions are kept, never deleted, so any logged result can be reproduced.

## 5. Configuration format

### 5.1 Named building blocks (reusable)

```yaml
# config/selection/top_growth_quality_v1.yaml
id: top_growth_quality_v1
kind: selection
description: Profitable growers with consistent returns on capital
pools:
  - name: compounders
    expression: "roic_pretax_mean_5y >= 0.15 and revenue_growth_1y > 0.10"
  - name: improving
    expression: "roic_pretax_trend_3y > 0 and gross_margin_level > 0.4"
combine: "compounders or improving"
```

### 5.2 Strategy

```yaml
# config/strategies/thesis_value_accumulation_v1.yaml
id: thesis_value_accumulation_v1
hypothesis: H2
rebalance: monthly

universe:
  - component: expression_v1
    params: { expression: "turnover_median_60d >= 100000 and price >= 5" }

selection: top_growth_quality_v1

scoring:
  combine: weighted_rank
  blocks:
    - component: relative_valuation_v1
      weight: 0.4
    - component: dcf_monte_carlo_v1
      weight: { search: [0.0, 0.3, 0.6] }   # 0.0 = effectively off
      params: { discount_rate: { search: [0.08, 0.10] }, simulations: 1000, seed: 7 }
    - component: quality_stability_v1
      weight: 0.3
  keep_top: { search: [10, 20, 50] }   # watchlist concentration (see §10.4)

timing:
  - component: accumulation_obv_v1
    enabled: { search: [true, false] }        # ablation
  - component: price_above_ma_v1
    params: { days: 200 }

entry:     { component: breakout_entry_v1, params: { tranches: [0.5, 0.5] } }
management:
  - component: pyramid_on_strength_v1
    enabled: false
exit:
  - component: trailing_stop_v1
    params: { pct: { search: [0.20, 0.30] } }
  - component: fundamentals_broken_v1

sizing:    { component: equal_weight_v1 }
portfolio: { component: standard_portfolio_v1, params: { max_positions: 25, max_weight: 0.08 } }
costs: costs.yaml
```

Any numeric or boolean field accepts `{search: [...]}` or `{search: {low, high, step}}`; the same file serves single runs and searches. `enabled: false` turns a component off without deleting it.

### 5.3 Ensemble (system of systems)

```yaml
id: core_ensemble_v1
members:
  - strategy: thesis_value_accumulation_v1
    weight: 0.5
  - strategy: trend_following_v1
    weight: 0.5
rebalance_members: quarterly
```

## 6. Point-in-time view

### 6.1 Guarantees

Components never touch the database. They receive a `PointInTimeView` bound to a date *T*:

- `view.fundamentals(metrics, history_years)` → only values with `known_from <= T` (latest known version).
- `view.prices(instruments, lookback_days)` → only prices on or before *T* (closing price of *T* included, since the signal is computed after the close; execution is T+1 by the engine).
- `view.factor(factor_id)` → generative factors computed through the same view.
- `view.universe()`, `view.calendar()`.
- No method accepts a date argument. Creating a view for another date is only possible through the pipeline.

Integrity tests (CLAUDE.md invariant 8) run every registered component twice — on full data and on data truncated at *T* — and require identical outputs. A new component cannot be used in a logged run until it passes.

### 6.2 Models that learn (ML)

A learning component gets `view.training_window(...)` that only yields data before *T*, minus an embargo covering its label horizon (e.g. if the label is the 6-month forward return, training samples must end ≥ 6 months before *T*). Retraining cadence is a parameter. Same truncation test applies.

### 6.3 AI / language models (stage 2.3)

A language model has read about how companies turned out. Asking a 2026 model whether a company looked good in 2012 leaks the future. Allowed uses, in order of safety:

1. Classification of facts that do not depend on later events, using only text available at *T* (e.g. business description → "recurring revenue: yes/no"), with outputs cached and frozen per (document, model version).
2. Models whose training cutoff is before the backtest period being evaluated (evaluation restricted to after the cutoff).

Never: asking a model to judge quality, prospects or reputation of a company *as of a past date*. AI components must declare their model and cutoff; the run is labeled accordingly.

## 7. Engine changes

The current engine takes target weights on rebalance dates. The pipeline needs:

- **Two clocks:** rebalance clock for stages 1–2, daily clock for stages 3–5.
- **Order intents** instead of only target weights: open, add (tranche), trim, close — each with size rule and reason. Executed T+1 per instrument, as today.
- **Position state:** entry date and price, tranches, highs since entry (for trailing stops), the component that opened it.
- **Watchlist:** candidates from stage 2 that are not yet bought wait for a timing/entry signal until the next rebalance drops or keeps them.

The existing `LongOnlyFactorStrategy` becomes a degenerate configuration: no timing, entry = "buy at rebalance", exit = "not in top N at rebalance". It stays as the baseline and for regression tests.

## 8. Experiments

- **Ablation:** `enabled: {search: [true, false]}` on any component answers "does this part add anything?"
- **Consistency across systems:** a component earns its place only if it improves *most* systems it is added to, not just one. A filter or rule that helps one strategy and hurts the others is more likely noise than signal.
- **Variants:** swapping `dcf_v1` for `dcf_monte_carlo_v1` in one field.
- **Staged search** (WORK_ORDER fas 10): selection/scoring first with a standard portfolio, then portfolio parameters, then trade management, then timing/regime overlays. Limits the number of combinations and therefore overfitting.
- **Logging:** every run writes to the trial registry: strategy id + version + hash, all component ids + versions + hashes, resolved parameters, data period, metrics, and stage. Trial counts feed deflated Sharpe and PBO.
- **Evaluation:** walk-forward and CPCV over the full history (no fixed holdout), plus forward paper trading of final candidates.

## 9. Mapping to existing code

| Existing | Becomes |
|---|---|
| `factors/` (base metrics, transformations, normalizations, composites) | Factor library used by `view.factor()` and `expression_v1`; composites become score components |
| `pit.as_of`, `universe.queries` | Backends of `PointInTimeView` (not called by components directly) |
| `backtest/engine.py`, `portfolio.py` | Execution layer; extended with order intents, position state, two clocks |
| `backtest/strategy.py` `LongOnlyFactorStrategy` | Baseline configuration + regression test |
| `analytics/` | Unchanged; fed by engine results |
| empty `strategy/`, `search/`, `validation/` packages | Config schema + loader, search runner + trial registry, validation |

## 10. Decisions on design questions (2026-10-28)

1. **DCF inputs:** projections from point-in-time history only (no analyst forecasts). Expect several variants as separate components, differing in the cash flow measure, e.g. `dcf_fcf_v1`, `dcf_owner_earnings_v1`, plus Monte Carlo versions.
2. **Support and resistance (stage 3.2):** daily data only; intraday is too short-term anyway. Approach: a **volume profile** — how much volume has traded around the current price level in the past. For a stock that has fallen: is there support (heavy past volume) near the current price? On the way up: is there resistance overhead? Considered advanced; build after simpler volume analysis (accumulation/distribution, volume trend).
3. **Ensemble weighting:** deferred. Depends on how systems behave across market regimes, and on whether regimes can be detected reliably at all.
4. **Watchlist concentration:** a searchable parameter (`keep_top`), tested like portfolio concentration — on both return and risk. Owner's prior: favor concentration ("why track 100 ideas when we know which 20 look best"), but whether the scoring can actually rank that well is an empirical question.

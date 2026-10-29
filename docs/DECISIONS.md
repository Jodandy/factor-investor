# Design Decisions

Log of non-trivial design decisions for factor-investor.

Format: Date | Decision | Rationale | Alternatives considered

---

## 2026-10-06 | Project naming: factor-investor

**Decision:** Use `factor-investor` as project name and `factor_investor` as Python module name.

**Rationale:** Repository was already created with this name.

**Alternatives:** `factor-lab` was the original spec name.

---

## 2026-10-06 | Accept survivorship bias from Börsdata

**Decision:** Proceed with Börsdata as sole data source despite missing delisted companies.

**Rationale:** External data sources (Bloomberg, Datastream) would add significant cost and complexity. User accepted the limitation.

**Impact:**
- All backtest results will have survivorship bias (overstated returns)
- H4 (deep value in distressed companies) results are especially suspect
- All reports must clearly state this limitation

**Mitigations:**
- Document bias prominently in all outputs
- Be extra conservative interpreting results
- Consider robustness tests that simulate random delistings

**Alternatives considered:**
- External data source for delisted companies (rejected: cost/complexity)
- Limit scope to H1/H2/H3 only (rejected: user wants full scope)
- Use index constituent history (rejected: incomplete coverage)

---

## 2026-10-06 | Calculate metrics from reports, skip KPI sync

**Decision:** Calculate all financial metrics (ROE, ROIC, FCF margin, etc.) from raw report data instead of syncing Börsdata's pre-calculated KPIs.

**Rationale:**
1. The reports API includes all necessary data fields including FCF (verified)
2. ROIC can be approximated using effective tax rate derived from data
3. EBITDA is the only metric truly missing, but net_debt/EBIT is a suitable substitute
4. Calculating ourselves gives full transparency into the formulas
5. Reduces API calls and sync complexity

**Metrics verified calculable:**
- ROE = profit_to_equity_holders / total_equity
- ROIC ≈ operating_income × (1 - effective_tax) / (equity + net_debt)
- All margins from income statement items
- FCF directly available in reports
- All valuation ratios with price data

**Alternative considered:**
- Sync KPIs (EBITDA=54, ROIC, etc.) - rejected: unnecessary complexity, less transparency

---

## 2026-10-06 | Filter OHLC data quality violations

**Decision:** Filter out price records with OHLC logic violations in the universe builder (Fas 3).

**Rationale:**
- Data audit found 35,980 rows (1.27% of 28.3M) with impossible OHLC combinations
- Examples: high < low (10,597 cases), close > high (5,043 cases), close < low (3,704 cases)
- These are data quality errors from Börsdata that would corrupt analysis
- Better to exclude bad days than to use nonsensical data

**Filter criteria:**
```python
# Exclude if any of these are true:
- high < low (impossible)
- close > high × 1.01 (with 1% tolerance for rounding)
- close < low × 0.99
- open > high × 1.01
- open < low × 0.99
- Any price ≤ 0
```

**Implementation:** Apply filter in universe builder when constructing daily investable universe.

**Impact:** ~1.3% of price records excluded. Since violations appear clustered in specific instruments/dates, some instruments may have many missing days.

**Alternative considered:**
- Fix data at ingestion (rejected: don't want to modify raw data)
- Flag and warn but allow (rejected: breaks downstream calculations)
- Just use close price and ignore OHLC (rejected: need high/low for some metrics)

---

## 2026-10-06 | Point-in-time fundamentals layer - Metric definitions

**Decision:** Document all derived metric formulas explicitly for transparency and reproducibility.

**Implementation:** All metrics are calculated during `build-pit` and stored in `fundamentals_pit` table with `known_from` dates to prevent lookahead bias.

### Profitability Metrics

**Return on Equity (ROE)**
```
ROE = profit_to_equity_holders / total_equity
```
- Returns None if equity ≤ 0 or either input is NULL
- Measures profit per unit of shareholder equity

**Return on Assets (ROA)**
```
ROA = profit_to_equity_holders / total_assets
```
- Returns None if assets ≤ 0 or either input is NULL
- Measures profit per unit of total assets

**Return on Invested Capital (ROIC)**
```
effective_tax_rate = 1 - (profit_to_equity_holders / profit_before_tax)
NOPAT = operating_income * (1 - effective_tax_rate)
invested_capital = total_equity + net_debt
ROIC = NOPAT / invested_capital
```
- *Superseded 2026-10-27 (see "ROIC in loss years"):* unusable tax rates fall back to 22%, operating losses give negative ROIC; None only if operating income or invested capital is missing, or invested capital ≤ 0. Pre-tax variant `roic_pretax` added.

**Gross Margin**
```
gross_margin = gross_income / revenues
```
- Returns None if revenues ≤ 0 or either input is NULL

**Operating Margin (EBIT Margin)**
```
operating_margin = operating_income / revenues
```
- Returns None if revenues ≤ 0 or either input is NULL

**Net Margin**
```
net_margin = profit_to_equity_holders / revenues
```
- Returns None if revenues ≤ 0 or either input is NULL

**Free Cash Flow Margin**
```
fcf_margin = free_cash_flow / revenues
```
- Returns None if revenues ≤ 0 or either input is NULL
- Note: `free_cash_flow` is directly available from Börsdata reports

### Leverage Metrics

**Net Debt to Equity**
```
net_debt_to_equity = net_debt / total_equity
```
- Returns None if equity ≤ 0 or either input is NULL
- Measures financial leverage

**Net Debt to EBIT**
```
net_debt_to_ebit = net_debt / operating_income
```
- Returns None if operating_income ≤ 0 or either input is NULL
- Note: Using `operating_income` as proxy for EBIT since EBITDA not available
- Measures debt servicing capacity

**Solvency (Equity Ratio)**
```
solvency = total_equity / total_assets
```
- Returns None if assets ≤ 0 or either input is NULL
- Measures financial stability (% of assets financed by equity)

**Current Ratio**
```
current_ratio = current_assets / current_liabilities
```
- Returns None if current_liabilities ≤ 0 or either input is NULL
- Measures short-term liquidity

### Efficiency Metrics

**Asset Turnover**
```
asset_turnover = revenues / total_assets
```
- Returns None if assets ≤ 0 or either input is NULL
- Measures how efficiently assets generate revenue

**Interest Coverage**
```
interest_expense = operating_income - profit_before_tax
interest_coverage = operating_income / interest_expense
```
- Returns None if:
  - Either input is NULL
  - interest_expense ≤ 0 (no interest or net financial income)
- Estimates interest expense as difference between EBIT and EBT
- Measures ability to service debt

### Shareholder Metrics

**Book Value Per Share**
```
book_value_per_share = total_equity / number_of_shares
```
- Returns None if shares ≤ 0 or either input is NULL
- Note: `number_of_shares` in millions from reports

### NULL Handling Philosophy

**All derived metrics follow these principles:**
1. Return `None` (NULL) if any required input is missing
2. Return `None` if denominator is zero or negative
3. Return `None` if calculation produces unreasonable values (e.g., tax rate > 1)
4. Never substitute zeros or defaults - let NULLs propagate naturally

**Rationale:** NULLs are honest - they indicate "not calculable" rather than hiding data quality issues behind zero values. Downstream analysis can then explicitly handle missing data.

### Trading Day Buffer

**Decision:** Use **calendar days**, not trading days, for the trading day buffer.

**Rationale:**
- Simpler implementation (no external trading calendar dependency)
- Conservative approach (adds 1-2 extra days compared to trading days)
- Acceptable for Fas 2 (can optimize later if needed)

**Configuration:**
```toml
[report_delays]
quarterly = 60      # Days after period end
annual = 90         # Days after period end
trading_day_buffer = 1  # Additional calendar days
```

### Known_from Calculation

**Algorithm:**
```python
if report_date exists and year != 1899:
    known_from = report_date + trading_day_buffer
else:
    delay = annual (90) if period_type == 'year' else quarterly (60)
    known_from = period_end + delay + trading_day_buffer
```

**Notes:**
- Börsdata uses `1899-12-30/31` as "missing date" indicator → filtered out
- Fallback is conservative: assumes reports published later than typical
- Trading buffer prevents same-day trading on publication

**Observed Statistics (from build):**
- ~94-95% of reports have actual publication dates
- Median delay: 38 days for all report types
- Fallback used for ~5% of reports

---

## 2026-10-06 | Universe granularity - Monthly snapshots

**Decision:** Build investable universe snapshots at end-of-month only, not daily.

**Rationale:**
- Sufficient granularity for monthly/quarterly rebalancing strategies
- ~500k rows for 10 years vs ~10M for daily snapshots (20x smaller dataset)
- Simplifies initial implementation
- Can add daily builds later if needed for specific high-frequency strategies

**Implementation:** `UniverseService.build_universe_monthly()` finds last trading day of each month (searches backward up to 7 days from calendar month-end to find date with price data).

**Alternative considered:**
- Daily snapshots (rejected: 20x larger dataset, not needed for initial hypotheses)

---

## 2026-10-06 | Skip FX conversion, keep native currencies

**Decision:** Store total returns in each instrument's native currency. Do not convert to base currency (SEK).

**Rationale:**
- Simplifies implementation significantly (no need for Riksbanken/ECB FX API integration)
- Portfolio-level aggregation can handle multiple currencies when needed
- Most Nordic instruments already in SEK/NOK/DKK (similar currencies)
- Avoids potential FX data quality issues and missing rate gaps

**Impact:**
- `total_returns` table has `total_return_index` in local currency
- Universe constituents have metrics in local currency (`market_cap_local`, `median_turnover_60d`)
- Portfolio engine (Fas 6) will need to handle currency conversion at aggregation time if needed

**Alternative considered:**
- Convert all to SEK using Riksbanken API (rejected: unnecessary complexity for initial implementation)

---

## 2026-10-06 | Optimistic delisting recovery (100%)

**Decision:** Assume 100% recovery rate for all delistings (final traded price).

**Rationale:**
- Consistent with survivorship bias from using Börsdata (no delisted companies in dataset)
- Most Nordic delistings are acquisitions at premium to trading price
- Transparent and simple assumption
- Conservative given we're missing delisting data entirely

**Configuration:**
```toml
[corporate_events]
default_delisting_recovery = 1.0  # 100% recovery at final price
```

**Sensitivity Analysis Plan:**
- Run validation (Fas 9) with 0% recovery assumption to bound the impact
- Document range of results in final reports

**Alternative considered:**
- 0% recovery (pessimistic, rejected: too conservative)
- Variable recovery by detection method (rejected: insufficient data to calibrate)

---

## 2026-10-06 | Include First North markets by default

**Decision:** Include First North and other small-cap markets in default universe configuration.

**Rationale:**
- Captures small-cap growth opportunities critical for H1/H2 hypotheses
- First North companies still subject to same quality filters (liquidity, market cap, history)
- More complete Nordic universe
- Can be excluded via config for conservative strategies

**Configuration:**
```toml
[universe]
include_first_north = true  # Default
```

**Filters still apply:**
- Min market cap: 100M in local currency
- Min median turnover: 100k per day
- Min price: 10 in local currency
- Min history: 2 years

**Alternative considered:**
- Exclude First North by default (rejected: limits small-cap coverage for H1/H2)

---

## 2026-10-06 | Dividend ex-date estimation (simplified)

**Decision:** Extract dividends directly from annual reports and estimate all ex-dates as `report_date + 30 days`.

**Rationale:**
- Dividends already available in reports (no need for separate API call)
- Typical Nordic pattern: Annual general meeting (AGM) held ~4-6 weeks after annual report
- Dividend ex-date usually occurs day after AGM
- 30 days is reasonable middle estimate
- Conservative (later than immediate reinvestment)
- Estimation accuracy sufficient for total return calculation with T+1 execution lag

**Implementation:**
```python
# From dividend_service.py
ex_date = report_date + timedelta(days=30)
is_estimated = True  # All ex-dates are estimated
source = "report_estimated"
```

**Simplification from initial design:**
- Initially planned to use Börsdata calendar API for precise ex-dates
- Decided to skip calendar sync - estimation is sufficient for backtesting
- Reduces API calls and simplifies data flow
- All dividends now extracted during `build-returns` command

**Alternative considered:**
- Use calendar API for precise ex-dates (rejected: unnecessary complexity, estimation sufficient)
- Use report_date directly (rejected: too aggressive, dividends paid later)
- Use period_end + 60 days (rejected: less accurate than report_date + 30)

---

## 2026-10-06 | Total return index calculation

**Decision:** Calculate total return index with dividend reinvestment using standard formula, base 100 on first date.

**Formula:**
```python
TR_index[0] = 100.0  # Base on first available date

for t in dates[1:]:
    price_return = (price[t] / price[t-1]) - 1
    dividend_return = dividend[t] / price[t-1]  # Dividend on ex-date
    total_return = price_return + dividend_return
    TR_index[t] = TR_index[t-1] * (1 + total_return)
```

**Key details:**
- Dividends are reinvested on estimated ex-date (report_date + 30 days)
- Per-share dividend amount from annual reports in local currency
- Assumes reinvestment at close price on ex-date
- Base 100 is instrument-specific (each starts at 100 on its first date with data)
- ±few days precision on ex-date is acceptable given T+1 execution lag

**Validation:**
- Spot-check against known dividend-paying stocks (e.g., Investor AB, H&M)
- Verify TR index > price index on ex-dates
- Compare to external TR indices where available (OMX GI for large caps)

**Alternative considered:**
- Base 1000 (rejected: 100 is more intuitive)
- Accumulate dividends separately (rejected: TR index is standard format for backtesting)

---

## 2026-10-06 | Liquidity bucket classification

**Decision:** Classify instruments into 5 liquidity buckets based on fixed thresholds of median daily turnover.

**Thresholds (in local currency):**
```toml
[universe]
liquidity_bucket_thresholds = [
    10_000_000.0,  # Bucket 1: >= 10M daily turnover (most liquid)
    1_000_000.0,   # Bucket 2: >= 1M
    100_000.0,     # Bucket 3: >= 100k
    10_000.0,      # Bucket 4: >= 10k
    # Bucket 5: < 10k (least liquid)
]
```

**Rationale:**
- Fixed thresholds are simple and explainable
- Thresholds roughly align with market cap tiers
- Enables realistic transaction cost modeling in backtest engine (Fas 6)
- Turnover = close_price * volume (daily)
- Median over 60 trading days (rolling window)

**Usage in Fas 6:**
- Bucket 1-2: Low spread costs, high capacity
- Bucket 3-4: Medium spread costs, limited capacity
- Bucket 5: High spread costs, very limited capacity (may exclude from strategies)

**Alternative considered:**
- Dynamic percentile-based buckets (rejected: less stable, harder to interpret)
- Market-cap based buckets (rejected: turnover is better proxy for liquidity)

---

## 2026-10-06 | Minimal universe philosophy - strategies choose their own criteria

**Decision:** Universe includes ALL instruments with sufficient data quality, regardless of geography, size, or liquidity. Strategies apply their own selection criteria at backtest time.

**Rationale:**
- Different hypotheses target different segments (H1: small caps, H2: large stable, H4: distressed)
- Hard-coding filters would prevent hypotheses from running
- Global scope: All geographies with data are interesting to analyze
- Flexibility: Strategies can test sensitivity to different criteria
- Transparency: We see the full opportunity set, strategies document what they exclude

**Universe Configuration:**
```toml
[universe]
# PHILOSOPHY: Universe = all instruments with sufficient data quality
# NO geographic filters, NO market cap cutoffs, NO liquidity requirements

# Data quality filter (minimal - exclude pennystocks)
min_price = 5.0  # Filter out pennystocks (< 5 in local currency)

# Liquidity bucket thresholds (for cost modeling - informational, not exclusionary)
liquidity_bucket_thresholds = [10_000_000, 1_000_000, 100_000, 10_000]
```

**What Universe Provides:**
- **Inclusion:** All instruments with price data and fundamental data (reports)
- **Exclusion:** Only pennystocks (price < 5.0 in local currency) for data quality
- **Metrics calculated for all** (stored, not used for exclusion):
  - `market_cap_local`: Price × PIT shares (for strategy filtering)
  - `median_turnover_60d`: 60-day median daily turnover (for strategy filtering)
  - `years_of_history`: Years of price data available (for strategy filtering)
  - `liquidity_bucket`: 1-5 classification (for transaction cost modeling)
  - `is_eligible`: TRUE for almost everything (except data quality issues)
  - `exclusion_reason`: NULL for most, only set for extreme cases

**Strategy Selection Criteria (applied at backtest time):**
```python
# Example: H1 (Small cap momentum)
selection_criteria:
  market_cap_range: [10_000_000, 500_000_000]  # 10M-500M
  min_median_turnover_60d: 50_000
  min_history_years: 1  # Accept newer companies
  exclude_sectors: []  # No sector exclusions

# Example: H2 (Stable dividends)
selection_criteria:
  market_cap_range: [500_000_000, null]  # 500M+
  min_median_turnover_60d: 1_000_000
  min_history_years: 5  # Require established companies
  exclude_sectors: ["Banks", "Real Estate"]
```

**Temporal Integrity (maintained):**
- Market cap uses PIT share count from `as_of(as_of_date)` query
- Turnover calculated from past 60 trading days relative to as_of_date
- Listing date checked to prevent including not-yet-listed instruments
- All metrics use only data available as of universe construction date

**Benefits:**
1. **Global universe:** All geographies with data, not just Nordics
2. **Hypothesis flexibility:** Each strategy defines its own filters
3. **Sensitivity testing:** Easy to test impact of different criteria
4. **Transparency:** Full opportunity set visible, strategies document exclusions
5. **Cost modeling:** Liquidity buckets enable realistic transaction costs

**Alternatives considered:**
- Hard-coded Nordic filters (rejected: too restrictive, misses global opportunities)
- Hard-coded market cap/turnover cutoffs (rejected: prevents testing different strategies)
- Default "investable universe" with soft filters (rejected: still imposes arbitrary choices)

---

---

## 2026-10-27 | Backtest engine: T+1 execution and accounting fixes

**Decisions:**
- **Execution delay:** signals are generated on the rebalancing date and executed `execution_delay_days` trading days later (settings.toml, must be >= 1) at that day's price. Trades record both `date` (execution) and `signal_date`. `BacktestEngine(execution_delay_days=0)` exists only for the integrity test that proves the delay changes results.
- **Per-instrument execution:** the engine's calendar is the union of all markets (some trade on weekends), so a stock may not trade on the due day. Each instrument's order waits for that stock's own next price; it never executes at a stale (signal-day) price. A new signal cancels unfilled orders from the previous one. Buy orders that get no price within 30 days are dropped.
- **Positions that stop trading:** a holding with no price for `STALE_PRICE_DAYS` (30 calendar days) is sold at its last known price. Rationale (user): in acquisitions the buyer pays roughly the last price. Börsdata contains no delisted companies (see DATA_AUDIT), so this mostly covers trading halts; bankruptcy recovery cannot be modelled from this data.
- **No leverage:** buys are capped at available cash. If a sell is waiting for a price, buys funded by it are partially filled and the cash stays uninvested until the next signal.
- **Daily returns** are computed from end-of-day portfolio value, so transaction costs now show up in the returns series.

**Bug fixed:** `Portfolio.rebalance` used a polars outer join without `coalesce=True`. Fully exited positions got a null `instrument_id`, so the sale credited cash but the position stayed in holdings — every rebalance created money. All backtest results before this date are invalid and were deleted.

**Not filtered in the engine (user decision):** liquidity and universe membership. Both must be available as strategy-level filters instead. Flat-bps costs remain on by default; `costs.yaml`-based costs are still TODO.

**Corrupted-instrument list:** kept as a manual list despite being identified partly from backtest outcomes (mild hindsight). Accepted because the list is short relative to the universe.

---

## 2026-10-27 | Drop the fixed holdout period

**Decision:** Remove `HOLDOUT_START` and the locked holdout (old CLAUDE.md invariant 4). All ~20 years of data (2006–today) are used for research.

**Rationale (user):** A fixed holdout at the end of the data is a single, short (2–3 year), regime-specific window. Using it as a pass/fail gate puts a premium on what happened to work in the last few years, which may not reflect long-run behaviour. Strategies should be judged across all periods equally.

**Overfitting is handled instead by:**
- Walk-forward and CPCV over the full history, so every sub-period takes a turn as out-of-sample
- Deflated Sharpe and PBO using the trial count from the trial registry (invariant 5 still applies)
- Forward paper trading of final candidates — data that did not exist when the strategy was built

**Unchanged:** lookahead protection (PIT `known_from` for fundamentals, T+1 execution for prices) is the top priority and is independent of this decision.

**Alternatives considered:**
- Keep holdout at 2022-07-01 (rejected: already viewed, and recent-regime bias)
- Move holdout to 2024-01-01 (rejected: same recent-regime bias, just shorter)

---

## 2026-10-27 | Accepted residual lookahead risks

The user accepted these known, minor risks rather than mitigating them now:

1. **Restated reports:** if Börsdata overwrites historical reports with restated figures, we only see the final version, not what was originally published. Unverified.
2. **Split-adjusted price levels:** historical prices are back-adjusted for splits, so filters on absolute price level (e.g. `min_price = 5`) or turnover in currency use levels not seen at the time. Returns are unaffected.
3. **Corrupted-instrument list:** partly identified from backtest outcomes (see entry above).

---

## 2026-10-27 | Implausible publication dates fall back to conservative delay

**Decision:** `known_from` uses `report_date` only if it is at least `min_publication_days` (10, settings.toml) after `period_end`. Otherwise (and for the 1899 placeholder) the fallback delay applies: period_end + 60 days (quarter/r12) or + 90 days (year), + 1 day buffer. Applies to all report types.

**Rationale:** Börsdata has `report_date == report_end_date` on ~8.7% of annual reports (~15,700), ~6,400 quarterly and ~10,900 r12 reports, plus a few hundred dated before the period ended. These are not real publication dates; trusting them made reports known 1–3 months (sometimes up to a year) early — lookahead.

**Threshold (user, 10 days):** quarterly publication delay has p1 = 14 days, median 38. Spot checks of reports dated 1–7 days after period end (Admicom H1 2020 on 2020-07-01, Waystream Q2 2022 on 2022-07-07, a Swiss cantonal bank in 3 days) are clearly wrong; ~1,400 reports fall within 1–11 days. Days 12–14 (~5,500, e.g. US banks) are plausible and kept. Erring late only delays a report; erring early is lookahead.

---

## 2026-10-27 | Remove 2020-06 fundamentals cutoff; default start 2006

**Decision:** Removed the `period_end >= 2020-06-01` filter in `factors.queries._get_base_metric`. Default start for universe and base-metric builds changed from 2016 to 2006 (20 years of prices now available).

**Rationale:** The filter was added on the theory that older values were stored as percentages, based on one instrument (Quinsam Capital). Derived metrics like ROIC are computed by our own code from raw report totals, so their format cannot depend on the period. The filter discarded all fundamentals before mid-2020. To be verified on the rebuilt PIT table.

---

## 2026-10-27 | Report types: factors use r12 and year only

**Verified against data (AAK, Kallebäck Property):**
- **r12** flow items = sum of the last four quarters; balance sheet items = latest quarter; r12 at Q4 equals the year report. Year reports share the Q4 report date.
- **Semi-annual reporters (~4,000 instruments, 26%)** have only Q2 and Q4 rows, holding H1 and H2 (6-month) figures. Their r12 is still correct (H1 + H2).
- **`dividend`** in all report types is the latest announced annual DPS, carried forward; it first appears in the report that announces it, so no lookahead.
- **r12 history** starts later than year history for some instruments (~72k year rows without r12, mostly 2005–2014), but the newest r12 is never older than the newest year report.
- **Broken fiscal years** (25% of year rows) are handled via `report_end_date`.

**Decision:** Factors use only r12 and year values (r12 preferred on ties): `factors.queries.select_latest_ttm` and `base_metrics`. Quarter rows are never used directly, since they mix 3-month and 6-month periods. Previously `_get_base_metric` picked the newest row of any type, which for 347 instruments today was a quarter row.

---

## 2026-10-27 | Valuation ratio units fixed

**Bug:** `base_metrics` multiplied `number_of_shares` (millions) by 1,000,000 while totals (revenues, FCF, net debt, operating income) are also in millions. P/S and P/FCF were 10⁶ too large, FCF yield 10⁶ too small, EV/EBIT effectively ignored net debt, and dividend yield divided the per-share dividend by the share count again. The `< 1,000,000` sanity filter then dropped every stock with true P/S > 1. P/E and P/B were correct.

**Decision:** All ratios computed in `factors.base_metrics.valuation_ratios` with market cap in millions = price × number_of_shares. Verified with AAK 2024 figures in unit tests.
- P/E, P/B, P/S, P/FCF, EV/EBIT only for positive denominators (a negative multiple sorts as "cheapest", which is misleading).
- FCF yield and dividend yield keep negative/zero values; non-payers get dividend yield 0 (previously missing).

---

## 2026-10-27 | Dividends in total returns (supersedes 2026-10-06 entry)

**Bugs fixed:**
- Dividends were only applied if the estimated ex-date was an exact trading day: 41% (32,600 of 80,452) fell on weekends and were silently dropped.
- Dividends before 2015 were excluded (prices now go back to 2006).
- Reports without a publication date were skipped; reports with a placeholder date (on/just after period end) put the dividend weeks too early.

**Decision:**
- Ex-date = PIT `known_from` + 30 days, using the same plausibility rules as the PIT layer (no dividend before the announcing report was known).
- Applied on the first trading day on or after the estimated ex-date; same-day dividends summed (`compute_total_return_index`).
- Extraction deletes and re-creates all `report_estimated` dividends, so it is idempotent.

**Known limitation:** one dividend per fiscal year from the annual report. Quarterly/semi-annual payers (common in the US/UK) get the year's dividends lumped on one date, shifted later. Börsdata's dividend calendar endpoint could improve this; not yet evaluated.

---

## 2026-10-27 | Performance metrics annualize by date span

**Bug:** metrics assumed 252 rows per year, but the backtest calendar is the union of all markets (~365 rows/year when some market trades on weekends). A 5-year backtest counted as 7.25 years: CAGR 4.2% instead of 6.2% in the old report.

**Decision:** `n_years` = calendar span / 365.25; `periods_per_year` = rows / n_years, used for annualized return, volatility, downside volatility, Omega threshold and all benchmark metrics. Zero-return rows on non-trading days dilute daily variance by the same factor, so annualized volatility stays consistent (tested with business-day vs calendar-day series).

---

## 2026-10-27 | Price metric lookbacks

**Bugs:** `momentum_12_1m` was the plain 12-month return (used the last value instead of the value one month back). All lookbacks were one day short (21 rows back = 20 trading days), and 12-month metrics needed 250 rows from a 365-day query window, which often had fewer.

**Decision:** `price_metrics_from_series`: lookbacks in the instrument's own trading days (1m = 21, 3m = 63, 6m = 126, 12m = 252), a return over N days compares tr[-1] with tr[-(N+1)]; 12-1 momentum = tr[-22] / tr[-253] − 1. Query window 400 calendar days.

---

## 2026-10-27 | Windowed transformations require full window coverage

**Bug:** mean/median/min/max/stability_cv/percentile_history required only N data points for an N-year window (trend required 3). With monthly samples, a "5-year mean" was computed from 5 months.

**Decision:** the earliest value in the window must be within 45 days of the window start (monthly grid tolerance); otherwise no value (NaN) for that date, as WORK_ORDER fas 4 allows. CAGR already required the full span. Strategies targeting young companies should use shorter windows explicitly.

---

## 2026-10-27 | Factor cache holds the full cross-section

**Bug:** `get_factor(..., instrument_ids=subset)` computed and normalized over the subset only, then cached that as the factor for the date. Percentiles were relative to the subset, and later full requests got the subset.

**Decision:** always compute over all instruments, cache the full result, filter on return. Cache path is versioned (`data/factors/cache/v2`) so values from earlier logic are never read; the cache must be cleared after rebuilding base data.

---

## 2026-10-27 | ROIC in loss years; add pre-tax ROIC

**Problem:** ROIC was None whenever profit before tax ≤ 0 or the effective tax rate fell outside [0, 1]. Loss years disappeared, so multi-year ROIC averages only included good years and flattered unstable companies.

**Decision (user: keep both as separate metrics):**
- `roic` (after-tax): effective tax rate when computable, otherwise `DEFAULT_TAX_RATE` = 22%. Operating losses: NOPAT = operating income (no tax shield) → negative ROIC.
- `roic_pretax`: operating income / (equity + net debt). No tax-rate noise, comparable across tax regimes (close to Greenblatt's return on capital).
- Both None only when operating income or invested capital is missing, or invested capital ≤ 0 (undefined).

**Alternatives considered:** pre-tax only; after-tax only with default rate; keep None (rejected: survivorship-like bias within the factor).

---

## 2026-10-28 | Survivorship bias: scope research realistically

**Context:** Börsdata has no delisted companies (DATA_AUDIT). Extending prices to 2006 makes the bias larger in early years: the further back, the more failed companies are missing. The bias is uneven — strongest for cheap, small and distressed companies, weaker for quality.

**Decision (user):** accept the data source, but be realistic in what conclusions are drawn:
- Focus research on quality-oriented approaches, where the bias exists but is smaller.
- Distressed/deep-value strategies (incl. net-nets) are flagged as high-bias; their results need extra skepticism and robustness checks.
- Absolute returns from backtests are treated as upper bounds, never as expected returns.

---

## 2026-10-28 | Exclude German listings

**Finding:** 6,094 of 17,894 instruments are listed in Germany; 4,326 of these report in non-EUR currencies, i.e. mostly secondary listings of US, Canadian and Chinese companies. 3,657 company names appear more than once overall. Duplicates distort cross-sectional rankings, allow holding the same company twice, and secondary quotes are often illiquid with stale prices.

**Decision (user):** exclude all German listings (`[universe] exclude_country_ids = [8]`), since primary and secondary listings cannot be told apart reliably. Accepts losing genuine German primaries.

**Also:** factor normalization (percentiles, z-scores, ranks) is computed only over instruments eligible in the universe on that date, so excluded listings cannot affect other companies' scores (`factors.queries._eligible_instruments`). Factor cache version bumped to 3.

**Open:** remaining duplicates (share classes, other cross-listings) still to be handled.

---

## 2026-10-28 | Cap dividend yield at 15%

**Finding:** report dividends and prices are scaled inconsistently for some instruments after restructurings (DATA_AUDIT "Report Dividends vs Prices"). 297 dividends exceed 100% of the share price; reinvesting them made total-return indices explode (Atos overflowed `Numeric(24, 6)`, i.e. > 10^18), and the same values would top the `dividend_yield` factor.

**Decision (user):** treat any dividend above 15% of the price as a data error (`MAX_DIVIDEND_YIELD` in `universe/dividend_service.py`):
- Total returns: a trading day's summed dividends above 15% of the previous close are not reinvested.
- `dividend_yield` factor: omitted (None) when DPS / price > 15%.

The previous close is known before the ex-date, so the check adds no lookahead.

Every skipped dividend is logged per instrument (name, count, max yield) during `build-returns` and written to `data/logs/implausible_dividends.csv` for auditing. First run: 2,373 dividends in 1,387 instruments (468 of them German, already outside the universe).

**Trade-off:** genuine special dividends above 15% are lost too, understating returns for those companies. Accepted: such dividends are rare and the bad data is common enough (2,419 dividends above 15%) that a looser cutoff lets milder scaling errors through.

**Alternatives considered:** 50% cutoff (rejected by user as too loose); detecting the scaling mismatch per instrument (more complex, not needed yet); dropping affected instruments entirely (loses their valid price history).

Total returns and base metrics rebuilt with `--force`; factor cache version bumped to 4.

---

## 2026-10-28 | Stocks only; indices and FX for prices only

**Finding:** the universe contained 1,188 non-stock instruments at some point (indices, currencies, commodities, crypto, preference shares, SPACs, units). Börsdata's instrument type codes are undocumented; meanings inferred from names (DATA_AUDIT "Instrument Types").

**Decision (user):** `[instruments]` in settings:
- `stock_types = [0, 3, 9]` (ordinary shares, second share classes, ADRs): synced with prices and reports, eligible for the universe. Second share classes are kept and deduplicated later (one class per company); ADRs are often the only listing of the company in Börsdata.
- `price_only_types = [2, 4, 5, 6, 11, 13]` (indices, FX): prices synced for benchmarks and currency conversion, never eligible.
- All other types (preference shares, commodities, SPACs, units, crypto) are not synced.

Existing rows for dropped types remain in the database but are never eligible.

---

## 2026-10-28 | Snapshot dates: last weekday, per-instrument last price

**Finding:** month-end dates were the last calendar day with any price. Crypto and FX trade on weekends, so 66 of 241 snapshots fell on a weekend and held 1–98 instruments instead of ~8,000 (same for base metrics). Prices were also matched on the exact date, so markets closed that day dropped out entirely: on Dec 31 all Swedish, Finnish and Danish stocks were missing.

**Decision (user):** `factor_investor.dates.month_end_dates` returns the last weekday (Mon–Fri) of each month; used by the universe, base metrics, factor history and strategy rebalancing. Each instrument uses its last close on or before the snapshot date, at most `max_price_age_days = 7` calendar days old (`universe.queries.get_latest_prices`). Only prices on or before the date are used, so no lookahead.

**Alternatives considered:** taking dates from the data (the original bug); requiring a price on the exact date (drops closed markets); one calendar per market (more complex, not needed with the per-instrument lookup).

Factor cache version bumped to 5.

---

## 2026-10-28 | Price glitches: keep for now, exclude later

**Finding:** placeholder prices such as 0.0002 followed by a jump back (Investar Holding 2014-07-01: 0.0002 → 14.20) create fake returns; total-return indices up to 1.8 × 10^7. 2,276 one-day rises above 3× and 2,076 falls below 1/3 in 1,594 stocks (mix of real penny-stock moves and errors).

**Decision (user):** keep the raw data; handle glitches later in a dedicated exclusion/cleaning step. Until then, price metrics and backtests can be distorted for the affected stocks.

---

## 2026-10-28 | One listing per company (`dedupe_listings_v1`)

**Finding:** after excluding Germany, 248 company names still had more than one eligible listing on 2026-09-30 (Apple in the US, Warsaw and Milan; Canadian companies also listed in the US; ADRs next to home listings; share classes). Holding several of them doubles the position in one company.

**Decision (user):** a universe filter applied at read time, no rebuild (`universe/listings.py`):
- **Grouping** from instrument metadata only: same ISIN, same name, or same name apart from a share class suffix (A, B, C, D, R, K, SDR, SDB) in the same country; groups chain. ISINs alone are not enough (missing for most secondary listings and ADRs, and exchange-specific for some, e.g. Stora Enso). Name matching was checked against reports: 56 of 57 share class pairs have identical annual reports; most same-name pairs have matching net margins. Truncated names shared by different companies are kept apart by an exception list (`NOT_SAME_COMPANY_V1`: Caisse Regionale de Credit).
- **Selection** per snapshot date: the listing with the highest 60-day median turnover in USD (USD/XXX pairs from Börsdata, last quote on or before the date), then the listing trading in the reporting currency, then the lowest instrument id.
- Removes 49–349 listings per snapshot (330 on 2026-09-30).

**Known cost:** the chosen listing switches in 2.1% of company-months (738 times over 2007–2026), mostly companies with home and US listings of similar liquidity (AB InBev, Logitech, BP, Aegon, Santander) and Lindt's two share classes. A strategy holding such a company would sell one listing and buy the other. Accepted for v1; if backtests show it matters, v2 keeps the current listing unless another is clearly more liquid.

**Alternatives considered:** home listing by ISIN country (stable, but ISINs are missing for many listings); keep the type-0 listing (arbitrary for share classes); a deduplicated universe table (needs a rebuild whenever the rule changes).

---

## 2026-10-29 | In-memory price panel for the backtest engine

**Finding:** the engine queried `total_returns` once per trading day (about 50 ms with row conversion), about 15 s for a 2-year monthly backtest and several minutes for 20 years. Too slow for random-portfolio baselines (WORK_ORDER fas 6: 500 runs).

**Decision:** `backtest/prices.py` exports `total_returns` (instrument_id, date, total_return_index) to `data/cache/prices/total_returns.parquet` via `COPY` (42M rows, 36 s, 410 MB) and the engine reads prices from memory (`PricePanel`, loaded once per process, 1.4 s). The Parquet file stores the table's row count and newest `created_at`; on load they are compared with the database and the file is rebuilt if they differ, so prices from before a `build-returns` are never used. Strategies never see the panel; the engine only asks for the current day's prices, as before.

**Verified:** identical prices on 6 dates, identical trading days, and an identical backtest (trades, daily returns, final value) against the old per-day queries; 1.1 s vs 15 s for 2022–2023.

**Alternatives considered:** keep per-day queries (too slow); one query per backtest (still re-reads 42M rows per run); a manual `build-price-panel` step (easy to forget after a rebuild).

---

## 2026-10-29 | Index-like benchmarks per market (`benchmarks/universe.py`)

**Decision:** benchmarks are ordinary strategies run through the same engine (same T+1 execution, 10 bps costs, monthly rebalancing on `month_end_dates`), over one market's investable universe: eligible on T, one country and trading currency (no FX conversion yet), one listing per company (`dedupe_listings_v1`).

- `equal_weight_v1`: all names, equal weight. Primary benchmark (HYPOTHESES).
- `cap_weight_v1`: weight by `market_cap_local` (point-in-time share count × price on T), with guards from DATA_AUDIT "Market Cap and Share Counts": drop a name whose implied share count (market cap / price) is more than 10× away from its median over the snapshots in the 370 days before T (about four quarterly reports); drop a name whose 60-day median daily turnover exceeds its market cap; cap each weight at 10%, redistributing the excess in proportion until no name is above the cap. Names without share history are kept.
- `random_pick_v1`: k names drawn uniformly per rebalance, seeded by (seed, date), equal weight.

Benchmarks are not strategy trials: they are not selected by a search, so they are not logged in the trial registry and do not count towards deflated Sharpe or PBO.

**Verified:** weighting rules unit-tested; inputs and weights for 2026-06-30 are identical when all universe snapshots and prices after that date are deleted (in a rolled-back transaction), and the test fails if the share-history query reads past T. Engine replication: an equal-weighted universe matches the closed-form value on every day (synthetic prices, no costs). Sweden 2023-12-29: 592 investable names; cap weights drop 3 (no market cap; QLife's 28× share issue, a false positive; Vetted Assets, ~4,000×); largest weights AstraZeneca (capped at 10%), Atlas Copco A, ABB, Investor B, Volvo B.

**Known limitations:** single-country only until a daily FX series is used; D shares are still in the universe until the planned universe rule; instrument country and currency are current metadata, not point-in-time.

**Amendment 2026-10-29 (user):** a market means its domestic companies: ISIN country code equal to the market code, in addition to country and trading currency. Foreign companies' local listings (Nokia, AstraZeneca, ABB in Stockholm) carry the whole company's market cap; at the end of 2008 they were 9 names but 37% of the Swedish universe's market cap, and Nokia alone cost about 7 points against OMX Stockholm GI in 2009. With the rule: CAGR 9.91% vs 10.05% for the index (was 9.61%), tracking error 3.4% (was 4.2%). Applies to benchmarks only; strategies choose their own universe. No benchmark run had been logged, so `_v1` is amended rather than versioned.

**Alternatives considered:** a vectorized benchmark separate from the engine (two implementations of execution and costs to keep in sync; the engine is instead checked against a closed form); capping in the engine via `max_position_weight` (caps once and renormalizes, so names can end up above the cap).

---

## 2026-10-29 | No minimum price in the universe; D shares excluded

**Finding:** `min_price = 5` was applied to split-adjusted prices, so whether a stock was eligible depended on splits made later. At the end of 2008, 47 Swedish stocks were ineligible for "price too low", including Hexagon (4.75 SEK adjusted, about 60 SEK actual).

**Decision (user):** `min_price` is opt-in (`UniverseConfig.min_price = None` by default, unset in `settings.toml`), as planned in ARCHITECTURE §10.5; strategies that want a price filter apply their own. Names ending in " D" are excluded with reason `d_share` (`exclude_name_suffixes`): Swedish property companies' D shares (Corem, Fastpartner, Intea, Sagax, Samhällsbyggnadsbolaget) are preference-like with capped upside, and Börsdata types them as ordinary or second-class shares (0 or 3), so the type filter misses them. No other names end in " D" in any country (checked 2026-10-29).

**Consequence:** junk placeholder prices (e.g. 0.0002 followed by a jump back) that the price threshold happened to exclude are now eligible; read-time glitch handling (DECISIONS "Price glitches") becomes necessary before equal-weighted results are trusted. Takes effect at the next `build-universe`.

**Alternatives considered:** a threshold on unadjusted prices (not available: Börsdata gives only adjusted prices and one year of splits); keeping 5 SEK (biased by later splits).

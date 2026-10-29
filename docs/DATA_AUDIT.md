# Data Audit

Documentation of Börsdata API behavior, data quality, and known issues.

**Audit date:** 2026-10-06
**API access level:** Pro+ (global access)

---

## Critical Finding: Delisted Companies

### Status: ⚠️ DELISTED COMPANIES NOT INCLUDED

Tested by searching for well-known Swedish companies that were acquired/delisted:

| Company | Delisted | Reason | In API? |
|---------|----------|--------|---------|
| Gambro | 2006 | Acquired by Baxter | **NO** |
| Meda | 2016 | Acquired by Mylan | **NO** |
| Capio | 2018 | Acquired by Ramsay | **NO** |
| Acando | 2019 | Acquired by CGI | **NO** |
| Tradedoubler | - | (actually still listed?) | Not found |

**Verification method:**
1. Fetched all 17,917 instruments (global access)
2. Searched for known delisted company names
3. Checked that all Swedish instruments (1,033) have recent price data (2026-10-05)
4. No instruments found with last trade date older than yesterday

**Impact:**
- Survivorship bias will affect all backtests
- H4 (deep value in distressed companies) cannot be tested correctly without bankruptcy data
- Historical universe reconstruction is incomplete

**Possible mitigations:**
1. External data source for delisted Nordic companies (e.g., Datastream, Bloomberg)
2. Accept limitation and document survivorship bias in all results
3. Use index constituent history as partial proxy for universe

---

## API Endpoints Verified

### Authentication
- Method: Query parameter `authKey` (case-sensitive)
- Rate limits: 100 calls/10 seconds, target <10,000/24h
- HTTP 429 returned with `Retry-After` header when exceeded

### Instruments
- **Endpoint:** `/v1/instruments` (Nordic), `/v1/instruments/global` (Global)
- **Total instruments:** 17,917 (with global access)
- **Fields:** insId, name, ticker, ISIN, sectorId, marketId, branchId, countryId, listingDate, stockPriceCurrency, reportCurrency

**Distribution by country:**
| Country | Count |
|---------|-------|
| Germany | 6,074 |
| USA | 5,813 |
| Canada | 2,011 |
| Sweden | 1,033 |
| France | 575 |
| UK | 448 |
| Poland | 421 |
| Norway | 305 |
| Finland | 209 |
| Switzerland | 206 |
| Denmark | 164 |

### Stock Prices
- **Endpoint:** `/v1/instruments/{id}/stockprices`
- **Fields:** d (date), o (open), h (high), l (low), c (close), v (volume)
- **History:** Up to 20 years with `maxCount` parameter
- **Split adjustment:** ✅ **YES** - prices are split-adjusted (verified with 4:1 split on 2025-11-18, prices continuous)

### Reports
- **Endpoint:** `/v1/instruments/{id}/reports`
- **Types:** year, quarter, r12 (rolling 12 months)
- **Key fields:**
  - `report_End_Date`: Fiscal period end
  - `report_Date`: **Publication date** ✅ (critical for point-in-time)
  - Full income statement, balance sheet, cash flow
  - `number_Of_Shares`: Share count at period end

**Publication date coverage:**
- **Year reports:** 93.7% (235,433 / 251,177)
- **Quarter reports:** 94.7% (513,413 / 542,330)
- **R12 reports:** 94.8% (529,413 / 558,232)

**Publication delay (report_date - report_end_date):**
| Percentil | Year | Quarter/R12 |
|-----------|------|-------------|
| Median | 38 days | 38 days |
| p75 | 52 days | 49 days |
| p90 | 60 days | 58 days |

**Data quality issues:**
- 362 reports have `report_date = 1899-12-30/31` (Börsdata's "missing" indicator)
- 55 reports have extreme delays (>365 days), likely legitimate special cases

### Stock Splits
- **Endpoint:** `/v1/instruments/StockSplits`
- **Limitation:** Maximum 1 year of history
- **Fields:** instrumentId, splitType, ratio, splitDate

### Dividends
- **Endpoint:** `/v1/instruments/dividend/calendar`
- **Fields (checked 2026-10-29):** `insId`, `values[]` with `amountPaid`, `currencyShortName`, `excludingDate` (ex-date), `dividendType` (0 ordinary; 1 and 4 seen for extra and instalment payments, meaning not verified), `distributionFrequency` (null so far)
- **Coverage (full sync 2026-10-29):** 168,601 rows for 8,381 of 17,059 stock instruments; Nordic countries from 2010, all others from 2015 (Sweden 925 of 947 stocks, USA 2,148 of 5,214, Germany 2,701 of 6,085). Includes announced future ex-dates (up to 2027-11-25). Types: 0 = 163,327 rows, 3 = 2,147, 4 = 1,927, 1 = 856, 2 = 311, 5 = 27, 6 = 6.
- **Lag from report publication (PIT known_from) to the first ex-date** (median days): Canada 22, USA 32, Denmark 38, Finland 50, England 57, Switzerland 60, Norway 71, Netherlands 75, Sweden 77, Germany/Belgium/Italy 97, Spain 104, France 111, Poland 139; all 63.
- **Amounts are not split-adjusted:** Investor B 2010-04-15 is 4.00 SEK, but the split-adjusted price fell 0.93 SEK that day (4:1 split in 2022). Report dividends are adjusted (1.00 for 2009), consistent with prices.

### Indices Available
Many indices available including:
- OMXS30, OMXS30GI
- OMXSPI, OMXSGI (Stockholm GI)
- Sector indices (Financials, Technology, etc.)
- First North All index

---

## Data Quality Questions

### ✅ Report publication date available?
**YES.** The `report_Date` field contains the publication date. Example:
- AAK fiscal year 2025: `report_End_Date` = 2025-12-31, `report_Date` = 2026-02-05

### ⚠️ Are delisted companies included?
**NO.** See critical finding above.

### ✅ Are prices split-adjusted?
**YES.** Verified with Byggmästare AJ Ahlström 4:1 split on 2025-11-18. Prices are continuous across split:
- Before: 61-62 SEK
- After: 60-62 SEK

Historical prices are adjusted to current share basis. No manual split adjustment needed.

### ❓ Is there a total return series?
**TBD.** Need to check if dividends are incorporated or must be calculated.

### ❌ Historical report revisions (restatements)?
**NO.** Analysis shows:
- No duplicates of (ins_id, year, period) in any report table
- Börsdata stores only the latest version of each report
- The `original` parameter exists but we did not fetch historical revisions
- **Impact:** Point-in-time layer cannot handle restatements; all reports treated as "always known with these values"

### ✅ Distribution of (publication date - period end)?
**ANALYZED.** See publication date coverage above. Median delay is 38 days for all report types.

---

## Financial Metrics Analysis

### Available directly in reports

The reports endpoint includes comprehensive financial data (verified 2026-10-06):

**Income Statement:**
- revenues, net_sales, gross_income
- operating_income (EBIT)
- profit_before_tax, profit_to_equity_holders
- earnings_per_share

**Balance Sheet:**
- total_assets, total_equity, total_liabilities_and_equity
- current_assets, current_liabilities, non_current_assets, non_current_liabilities
- intangible_assets, tangible_assets, financial_assets
- cash_and_equivalents, net_debt

**Cash Flow:**
- cash_flow_from_operating_activities
- cash_flow_from_investing_activities
- cash_flow_from_financing_activities
- cash_flow_for_the_year
- **free_cash_flow** ✅ (directly available!)

**Share Data:**
- number_of_shares (in millions)
- dividend
- stock_price_average/high/low (at report time)

### Calculable from report data

| Metric | Formula | Status |
|--------|---------|--------|
| ROE | profit_to_equity_holders / total_equity | ✅ |
| ROA | profit_to_equity_holders / total_assets | ✅ |
| Operating margin | operating_income / revenues | ✅ |
| Gross margin | gross_income / revenues | ✅ |
| Net margin | profit_to_equity_holders / revenues | ✅ |
| FCF margin | free_cash_flow / revenues | ✅ |
| Current ratio | current_assets / current_liabilities | ✅ |
| Debt/Equity | net_debt / total_equity | ✅ |
| Net debt/EBIT | net_debt / operating_income | ✅ |
| ROIC | NOPAT / invested_capital (approx) | ✅ See note |
| EV/EBIT | (market_cap + net_debt) / operating_income | ✅ With prices |
| P/B, P/E | With prices + shares | ✅ With prices |

**ROIC approximation:**
```
effective_tax_rate ≈ 1 - (profit_to_equity_holders / profit_before_tax)
NOPAT = operating_income × (1 - effective_tax_rate)
invested_capital = total_equity + net_debt
ROIC = NOPAT / invested_capital
```

### NOT available (would need KPI sync)

| Metric | Why missing | Alternative |
|--------|-------------|-------------|
| EBITDA | D&A not separate | Use net_debt/EBIT instead |
| Interest expense | Not in reports | Estimate as operating_income - profit_before_tax |

### Conclusion

**For hypotheses H1-H4, we can calculate all required metrics from report data:**
- H1 (Talent): ROIC, revenue CAGR, margins ✅
- H2 (Quality ranking): ROIC, FCF margin, EV/EBIT ✅ (use net_debt/EBIT instead of net_debt/EBITDA)
- H3 (Stable cash flows): FCF directly available ✅
- H4 (Deep value): P/B, P/S, EV/S all calculable ✅

**No KPI sync required for core functionality.** KPIs can be added later for convenience or additional factors.

---

## Sync Statistics (2026-10-06)

Initial sync completed:
- **Countries:** 43 (including placeholder countries for markets)
- **Sectors:** 10
- **Branches:** 94
- **Markets:** 73
- **Instruments:** 17,917

## Price History Coverage

### Historical depth per instrument

| Percentil | Years of data |
|-----------|--------------|
| p10 | 0.9 |
| p25 | 3.3 |
| **Median** | **8.4** |
| p75 | 10.0 |
| p90 | 10.0 |
| **Max** | **10.0** |
| Mean | 6.7 |

**Observations:**
- Maximum history is **10 years** — but only because the sync did not pass `maxCount`. Verified 2026-10-27: without parameters (or with only `from`) the endpoint returns 10 years; with `maxCount` it returns 20 years (capped at 20 even with `maxCount=20000`). Sync now requests full history; the figures in this section predate that fix and need re-running.
- 25% of instruments have <3.3 years of data
- 10% have <1 year of data

### Instruments with price data by year

| Year | Instruments |
|------|------------|
| 2016 | 8,120 |
| 2017 | 8,745 |
| 2018 | 9,339 |
| 2019 | 9,840 |
| 2020 | 10,653 |
| 2021 | 12,272 |
| 2022 | 13,117 |
| 2023 | 13,881 |
| 2024 | 14,723 |
| 2025 | 16,360 |
| 2026 | 17,917 |

**Trend:** Growing coverage from 8,120 (2016) to 17,917 (2026).

---

## Data Quality Issues

### Stock Prices

**Duplicates:** ✅ None found (ins_id, date is unique)

**NULL values:**
| Field | NULL count | % of 28.3M rows |
|-------|-----------|-----------------|
| close | 0 | 0.00% |
| open | 12 | 0.00% |
| high | 13 | 0.00% |
| low | 13 | 0.00% |
| volume | 40,060 | 0.14% |

**Invalid prices:** 46 rows with zero/negative prices (0.0002%)

**OHLC logic violations:** ❌ **35,980 rows (1.27%)** with issues:
- `high < low`: 10,597 cases (impossible)
- `close > 1.01 × high`: 5,043 cases
- `close < 0.99 × low`: 3,704 cases

**Examples:**
```
ins_id=587, 2017-12-13: open=7.00, high=7.00, low=7.00, close=9.00
ins_id=491, 2024-01-19: open=0.40, high=0.34, low=0.31, close=0.34
```

**Recommendation:** Filter out days with OHLC violations in universe builder.

### Instrument Types (checked 2026-10-28)

The `instrument` field of the instruments endpoint is not documented. Meanings inferred from example names:

| Type | Count | Inferred meaning | Examples |
|------|-------|------------------|----------|
| 0 | 16,624 | Ordinary shares | AAK, ABB |
| 1 | 19 | Preference shares | Heimstaden Pref |
| 2 | 8 | Nordic indices | OMX Stockholm 30 |
| 3 | 56 | Second share class | Handelsbanken B, Industrivärden A, Maersk A |
| 4 | 34 | Sector indices | OMXS Energy |
| 5 | 41 | Industry indices | Food & Beverage |
| 6 | 94 | Currency pairs | USD/EUR |
| 7 | 7 | Commodities | Gold |
| 8 | 570 | SPACs (mostly US) | "... Acquisition Corp" |
| 9 | 379 | ADRs (US) | iQIYI, Harmony Gold |
| 10 | 9 | US units / equity units | NextEra NEEpS |
| 11 | 23 | US indices | S&P 500, Nasdaq 100 |
| 12 | 7 | Crypto | Bitcoin |
| 13 | 23 | Gross (total return) indices | OMX Stockholm 30 GI |

Crypto and currency pairs have prices on weekends, so the union of all price dates includes Saturdays and Sundays. Handling: DECISIONS 2026-10-28 "Stocks only" and "Snapshot dates".

### Report Dividends vs Prices (checked 2026-10-28)

Report dividends (DPS) and stock prices are not always scaled consistently. After large restructurings (rights issues, reverse splits, reverse mergers) the price history is adjusted but report per-share values are not, or are adjusted differently.

- Atos (ins_id 18217): prices €0.0016–61 over 2006–2026, report dividends €30–126 per share (actual payouts were about €0.4–1.7).
- Mechanics Bancorp (ins_id 72838): dividends $1,648–3,659 per share, price never above $17.

Dividend / last close on or before the estimated ex-date, over all 79,662 report dividends:

| Yield | Dividends | Instruments |
|-------|-----------|-------------|
| > 15% | 2,419 | |
| > 50% | 527 | 369 |
| > 100% | 297 | 203 |
| max | 580,934× | |

Before the fix, 78 instruments had a final total-return index above 10,000 (base 100), and two overflowed `Numeric(24, 6)`. Normal names (Ericsson, H&M) match. Handling: DECISIONS 2026-10-28 "Cap dividend yield at 15%". Earnings and book value per share have the same scaling problem; see the next section.

### Market Cap and Share Counts (checked 2026-10-28)

Price history is adjusted backwards for later corporate actions; report share counts and per-share values are not, or not consistently. Returns are unaffected (the adjusted series gives correct percentage changes), but levels (market cap, P/E, P/B, price) can be wrong.

- Atos (ins_id 18217): price €0.67 at end of 2017 (actually traded around €120), €0.003 at end of 2024, €50 at end of 2025. On 2024-01-31, P/B = 0.000014.
- Corem Property D (ins_id 2218): price 187 SEK is right, but P/B = 0.000007 (book value per share about 27 million SEK): the D-share report share count is wrong.

Implied share count (`market_cap_local / price`) in `universe_constituents`, jumps of more than 10× between consecutive snapshots:

| | Count |
|---|---|
| Jumps | 957 |
| Instruments with a jump | 636 of 16,988 (3.7%) |
| Reverting spikes (opposite jump within 13 months) | 242 |
| Persistent shifts | 599 (556 up, 43 down) |
| Rows where 60-day median daily turnover > market cap | 3,619 (2,538 eligible) |

- **Spikes:** one report has the share count in the wrong unit and market cap collapses until the next report (2–13 months). Example: Airtel Africa (22733), 4.9 billion → 2,862 for Feb–Apr 2024. Market cap is too small, so the instrument gets almost no weight.
- **Early-history unit errors:** Lloyds (36563) market cap is about 150,000× too small before 2008-02.
- **Dangerous direction (market cap inflated):** the share count later drops more than 10×, typically a reverse split applied backwards to prices. 111 instruments have such a drop; at the snapshot before it, 32 were in the top 10% of their country by market cap and 12 in the top 1%. This is not detectable at T (the data looks consistent until the event).

Extreme but arithmetically real ratios also occur (Karnov P/E 20,852 from near-zero earnings) and are kept.

Handling (planned, in the cap-weighting component, no rebuild): skip market cap when a report's share count differs more than 10× from the median of the last four reports; exclude when daily turnover > market cap; cap single-name weights. Equal-weight and rank-based components are unaffected by level errors.

### Extreme Moves and Zero Volume (checked 2026-10-29)

- 24,569 one-day moves above 3× or below 1/3 in 2,830 instruments (12,569 up, 12,000 down). 8,588 are back within 2× of the level before the move after 5 days.
- 9,248,067 of 42,027,005 price rows (22%) have volume 0; 49,260 have no stock_prices row (volume null). Zero-volume days repeat a quote, which can be a bad print (Kvix 2024-10-25..11-07: 0.70 for 9 days between 4.67 and 10.1).
- Persistent wrong levels exist: Transferator B 2010-04-12 ×12.2 (volume from about 100,000 to about 1,500 a day), back ×1/11.5 on 2013-05-08. Looks like a reverse split missing from the adjustment; cannot be verified (one year of splits).

### Benchmark vs OMX Stockholm GI (checked 2026-10-29)

`cap_weight_v1` for Sweden over 2008-01-02..2026-10-27 vs OMX Stockholm GI (ins_id 639): CAGR 9.61% vs 10.05%, monthly correlation 0.969, tracking error 4.2% a year. Causes found:

- **Foreign companies at full global market cap:** Nokia's SEK listing (ins_id 249, 484 bn SEK) was the largest name in the Swedish universe at the end of 2008 (capped at 10%); foreign-ISIN listings (Nokia and other Finnish companies, AstraZeneca, ABB) were 9 names but 37% of market cap. Restricting to SE ISINs: CAGR 9.91%, tracking error 3.4%, and 2009–2010 go from −13.5 and −7.0 points to +4.4 and +4.6.
- **`min_price = 5` on split-adjusted prices:** 47 Swedish stocks ineligible at the end of 2008, including Hexagon (4.75 SEK adjusted, about 60 SEK actual). Exclusion depends on later splits. Small effect on cap weighting (+0.03 points a year).
- **Dividend timing:** mean monthly difference to the index is +0.6% in February and +1.7% in March, −1.5% in April and −0.8% in May, and within ±0.15% in other months. Estimated ex-dates (`known_from + 30`) fall about two months before the real ones (Investor B 2009 dividend: 2010-02-21 estimated, 2010-04-15 actual). Nets out over a year, but moves about 3% of return between months for dividend payers.
- **Total return index precision:** `Numeric(24, 6)` with base 100 rounds the index of stocks that fell more than 99.9999% to zero (9,641 rows, 26 instruments); 108 instruments fall below 0.0001, where returns move in steps of 1% or more. The engine treats non-positive prices as missing.

**After the fixes (partial rebuild 2026-10-29: dividend calendar ex-dates, double-precision index, domestic companies only, no minimum price, D shares excluded):** `cap_weight_v1` Sweden CAGR 9.92% vs 10.05% for OMX Stockholm GI, monthly correlation 0.996, tracking error 1.6% a year (was 4.2%). Mean monthly difference within ±0.2% in every calendar month (the February–May dividend pattern is gone). Largest yearly gaps: 2010 +4.5, 2021 −3.2, 2022 −3.0, 2018 −2.9 points. 151,169 of 183,965 report dividends are on calendar ex-dates; no total return index is zero or negative (minimum 2.4e-16).

**Equal-weighted Sweden:** CAGR rose from 6.5% to 10.1% once stocks below 5 SEK became eligible. Held positions had 157 one-day moves above 3× or below 1/3 (Transferator B ×12.2 on 2010-04-12, Kvix ×14.6 on 2024-11-08). With extreme moves withheld until confirmed (`price_filter_v1`, DECISIONS 2026-10-29) the CAGR is 10.02%, so glitches explain little of the rise. Most of it is the minimum price itself: on split-adjusted prices, a 5 SEK threshold excluded stocks that later split, which are mostly past winners. Year by year, equal weighting follows OMX Stockholm Small Cap PI closely (2015 +48% vs +50%, 2023 −9% vs −6%); 10.0% against the index's 7.45% price return (about 9.5% with dividends) fits an equal-weighted universe that includes First North.

### Benchmarks vs Indices (checked 2026-10-29)

Saved in `data/benchmarks/` (`factor-investor benchmarks run`). Period 2008-01-02..2026-10-27, monthly statistics, 10 bps costs, `price_filter_v2`, `cap_weight_v1` with the zero-turnover and 10-trillion-USD guards. "Price only" is a diagnostic run on prices without dividends, for indices that exclude dividends.

| Area | Index | Index CAGR | `cap_weight_v1` | corr | TE | `equal_weight_v1` |
|---|---|---|---|---|---|---|
| SE | OMX Stockholm GI (total return) | 10.05% | 9.92% | 0.996 | 1.6% | 9.63% |
| NO | OSEBX (total return) | 8.09% | 9.50% | 0.963 | 4.8% | 5.73% |
| FI | OMX Helsinki GI (total return) | 5.35% | 7.58% | 0.979 | 3.5% | 4.06% |
| DK | OMX Copenhagen GI (total return) | 8.44% | 9.24% | 0.912 | 7.5% | 5.72% |
| US | S&P 500 (price) | 9.27% | 11.80%; price only 9.82% (corr 0.995, TE 1.6%) | 0.993 | 1.8% | 13.66% |
| EU | Stoxx Europe 600 (price) | 3.13% | 6.70%; price only 3.30% (corr 0.987, TE 2.3%) | 0.985 | 2.5% | 8.07% |
| DE (check) | DAX (total return) | 6.37% | 5.84% | 0.978 | 3.7% | |

- **Finland, Denmark:** the 10% cap explains the gaps (Nokia over 30% of Helsinki in 2008, Novo Nordisk about half of Copenhagen). Uncapped: Finland 5.08% (TE 2.8%), Denmark 9.23% (correlation 0.986).
- **Norway:** about 0.7 points a year remain uncapped (8.77%); foreign ISINs do not explain it (8.51% with them). OSEBX weights by free float and holds about 70 stocks; the state owns large stakes in Equinor (67%), Telenor, Hydro and DNB.
- **US and Europe:** price-only versions track the price indices within 0.2–0.6 points a year; dividends add 2.0 (US) and 3.4 (Europe) points. The US excess (0.55 points) fits a universe broader than the 500 largest plus survivorship.
- **US equal weight is not usable:** Börsdata has only US companies listed today. The US universe holds 1,625 companies at the end of 2008 (about 5,000 were listed), rising to 3,021 in 2025, so equal weighting is a portfolio of survivors (13.7% vs Russell 2000 at 7.2% price).
- **Börsdata lacks delisted companies everywhere**, so all backtest returns are upper bounds; the effect is largest for equal weighting and small companies.

**Data errors found on the way:**
- **Reverse splits missing from the price adjustment** (confirmed one-day rises: Atos 2025-04-30 ×10,217, Dolfines ×3,535, Curatis ×2,709, Ming Le Sports ×1,200, SA Commerciale de Brasserie ×586). Before `price_filter_v2`, `equal_weight_v1` Europe had a CAGR of 27.5% with 69% volatility.
- **Market caps from adjusted prices and unadjusted share counts** (Wheeler REIT 2017-05-31: price 5.2e11 USD, market cap 4.5e18 USD, median turnover 0; Sunshine Biopharma 3.3e17; Jaguar Health 7.7e15). Ratios of turnover to market cap overlap with real thinly traded A shares, so they cannot be separated that way.
- **Calendar effect:** the engine uses the union of all markets' trading days. A month end that is a holiday in Sweden but not elsewhere is still a trading day, so signals and trades come one day earlier than on a Swedish calendar (Sweden equal weight: 6.39M vs 6.45M final value over 20 years, about 0.05 points a year). Both respect the execution delay.

**`random_pick_v1` Sweden, k = 30, redrawn monthly, 500 seeds:**

| | mean | p5 | p25 | median | p75 | p95 | sd |
|---|---|---|---|---|---|---|---|
| CAGR | 6.52% | 1.87% | 4.66% | 6.63% | 8.35% | 11.37% | 2.82% |
| volatility | 21.4% | 19.9% | 20.7% | 21.4% | 22.0% | 23.2% | 1.0% |
| max drawdown | −60.6% | −71.9% | −65.5% | −60.2% | −55.6% | −49.7% | 6.7% |

`equal_weight_v1` Sweden: CAGR 9.63%, volatility 18.0%, max drawdown −52.1%. The gap to the random mean is costs and volatility (checked with `price_filter_v1`: arithmetic annual return 8.70% vs 10.64%, of which 2.24 points are costs, since a full redraw each month is about 200% turnover a month; volatility drag σ²/2 2.15% vs 1.03%; gross, random portfolios average the same as equal weight within about 1.3 standard errors). Runs are deterministic: parallel runs reproduce single-process results exactly.

---

## Remaining Questions

- [ ] Is there a total return series, or must dividends be added manually? (Likely manual - dividend field exists in reports)
- [ ] Can we fetch delisted companies from alternative data source?
- [ ] Should we implement OHLC validation filters at ingestion or universe level?

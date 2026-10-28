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
- **Fields:** Amount, currency, ex-date
- **Coverage:** TBD

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

Before the fix, 78 instruments had a final total-return index above 10,000 (base 100), and two overflowed `Numeric(24, 6)`. Normal names (Ericsson, H&M) match. Handling: DECISIONS 2026-10-28 "Cap dividend yield at 15%". Earnings and book value per share may have the same scaling problem; not yet checked.

---

## Remaining Questions

- [ ] Is there a total return series, or must dividends be added manually? (Likely manual - dividend field exists in reports)
- [ ] Can we fetch delisted companies from alternative data source?
- [ ] Should we implement OHLC validation filters at ingestion or universe level?

# Incremental Factor Sync

## Översikt

Systemet stöder **inkrementell uppdatering** av enskilda faktorer utan att behöva bygga om hela datasetet. Detta gör det snabbt och enkelt att:
- Lägga till nya faktorer när de utvecklas
- Backfilla saknade faktorer för äldre datum
- Testa nya faktorer på senaste data först
- Experimentera med faktorvarianter

## Varför Incremental Sync?

**Problemet:** Full rebuild tar ~90 minuter för 120 månader × 17,800 instrument
**Lösningen:** Bygg bara de faktorer du behöver → ~2 minuter

**Säkerhet:** `ON CONFLICT DO NOTHING` betyder att dubbletter ignoreras - helt säkert att köra flera gånger.

## Användning

### 1. Bygg Enskilda Faktorer

```bash
# Lägg till en faktor
uv run factor-investor build-base-metrics --metrics pe_ratio

# Lägg till flera faktorer (komma-separerad lista)
uv run factor-investor build-base-metrics --metrics pe_ratio,pb_ratio,ps_ratio

# Faktorer för Piotroski F-score
uv run factor-investor build-base-metrics \
  --metrics cash_flow_from_operating_activities,total_equity
```

### 2. Backfill för Specifika Datum

```bash
# De första 31 datumen (2016-10 till 2019-04) saknar vissa faktorer
# Backfill bara dessa datum:
uv run factor-investor build-base-metrics \
  --metrics cash_flow_from_operating_activities,total_equity \
  --from-date 2016-01-01 \
  --to-date 2019-04-30
```

### 3. Testa Nya Faktorer på Senaste Data

```bash
# Utveckla och testa en ny faktor på senaste året först
uv run factor-investor build-base-metrics \
  --metrics ev_ebitda \
  --from-date 2025-01-01

# När den fungerar bra, backfill full historik:
uv run factor-investor build-base-metrics \
  --metrics ev_ebitda \
  --from-date 2016-01-01
```

### 4. Full Rebuild (Standard)

```bash
# Ingen --metrics parameter = bygg ALLA faktorer
uv run factor-investor build-base-metrics --from-date 2016-01-01
```

## Tillgängliga Faktorer

### Fundamental Metrics

**Valuation Ratios:**
- `pe_ratio` - Price/Earnings
- `pb_ratio` - Price/Book
- `ps_ratio` - Price/Sales
- `ev_ebit` - Enterprise Value/EBIT
- `p_fcf` - Price/Free Cash Flow
- `fcf_yield` - Free Cash Flow Yield
- `dividend_yield` - Dividend Yield

**Profitability:**
- `roe` - Return on Equity
- `roic` - Return on Invested Capital
- `roa` - Return on Assets
- `gross_margin` - Gross Profit Margin
- `operating_margin` - Operating Profit Margin
- `net_margin` - Net Profit Margin
- `fcf_margin` - Free Cash Flow Margin

**Quality/Stability:**
- `asset_turnover` - Asset Turnover Ratio
- `current_ratio` - Current Ratio (liquidity)
- `net_debt_to_ebit` - Net Debt to EBIT
- `solvency` - Equity Ratio

**Piotroski F-Score Components:**
- `cash_flow_from_operating_activities` - Operating Cash Flow
- `total_equity` - Total Equity (for leverage change)

**Growth (1-Year):**
- `revenue_growth_1y` - Revenue Growth YoY
- `profit_growth_1y` - Profit Growth YoY
- `fcf_growth_1y` - Free Cash Flow Growth YoY

### Price Metrics

**Returns:**
- `return_1m` - 1-month total return
- `return_3m` - 3-month total return
- `return_6m` - 6-month total return
- `return_12m` - 12-month total return
- `momentum_12_1m` - 12-1 month momentum (skip recent month)

**Volatility:**
- `volatility_60d` - 60-day annualized volatility
- `volatility_250d` - 250-day annualized volatility
- `max_drawdown_1y` - Maximum drawdown over 1 year

**Technical:**
- `distance_ma_50d` - Distance to 50-day moving average
- `distance_ma_200d` - Distance to 200-day moving average
- `distance_52w_high` - Distance to 52-week high

## Vanliga Användningsfall

### Scenario 1: Piotroski F-Score Saknar Komponenter

**Problem:** De första 31 datumen (2016-10 till 2019-04) saknar `cash_flow_from_operating_activities` och `total_equity`

**Lösning:**
```bash
uv run factor-investor build-base-metrics \
  --metrics cash_flow_from_operating_activities,total_equity \
  --from-date 2016-01-01 \
  --to-date 2019-04-30
```

**Tidsåtgång:** ~2 minuter (vs ~90 minuter för full rebuild)

### Scenario 2: Ny Faktor (EV/EBITDA) Läggs Till

**Steg 1 - Implementera i kod:**
```python
# I base_metrics.py, lägg till i valuation-sektionen:
if should_calculate("ev_ebitda"):
    ebitda = row.get("ebitda")  # När denna data finns
    if market_cap and net_debt is not None and ebitda and abs(float(ebitda)) > MIN_DENOMINATOR:
        ev = market_cap + float(net_debt)
        ev_ebitda = ev / float(ebitda)
        if abs(ev_ebitda) < MAX_RATIO:
            metrics.append({...})
```

**Steg 2 - Testa på senaste data:**
```bash
uv run factor-investor build-base-metrics \
  --metrics ev_ebitda \
  --from-date 2025-01-01
```

**Steg 3 - Verifiera och backfill:**
```bash
# Kolla resultatet
SELECT COUNT(*), AVG(value), MIN(value), MAX(value)
FROM fundamental_metrics
WHERE metric = 'ev_ebitda';

# Om OK, bygg full historik:
uv run factor-investor build-base-metrics \
  --metrics ev_ebitda \
  --from-date 2016-01-01
```

### Scenario 3: Experimentera med Faktorvariant

```bash
# Testa en ny variant av ROE (t.ex. median över 3 år istället för senaste)
# 1. Implementera som ny faktor: roe_median_3y
# 2. Testa på senaste 12 månader:
uv run factor-investor build-base-metrics \
  --metrics roe_median_3y \
  --from-date 2025-01-01

# 3. Jämför med original ROE i backtest
# 4. Om bättre, bygg full historik
```

## Tekniska Detaljer

### Hur Det Fungerar

1. **Metrics Filter:** `--metrics` parameter skapar en lista av faktorer att beräkna
2. **Should Calculate:** Varje faktor wrappas i `if should_calculate("metric_name"):`
3. **Upsert:** `ON CONFLICT DO NOTHING` betyder dubbletter ignoreras
4. **Performance:** Hoppar över alla faktorer inte i filtret → mycket snabbare

### Implementation

```python
# I base_metrics.py
def calculate_fundamental_metrics(
    session: Session,
    rebal_date: date,
    instrument_ids: list[int] | None = None,
    metrics_filter: list[str] | None = None,  # <-- Ny parameter
) -> list[dict]:

    def should_calculate(metric_name: str) -> bool:
        if metrics_filter is None:
            return True  # Bygg alla
        return metric_name in metrics_filter

    # Exempel:
    if should_calculate("pe_ratio"):
        eps = row.get("earnings_per_share")
        if eps and eps > MIN_DENOMINATOR:
            pe_ratio = float(price) / float(eps)
            metrics.append({...})
```

### Database Constraint

```sql
-- Unique constraint gör upsert säkert
CONSTRAINT uq_fundamental_metrics
UNIQUE (instrument_id, metric, date)

-- Insertar ignoreras om (instrument_id, metric, date) redan finns
INSERT INTO fundamental_metrics (...)
VALUES (...)
ON CONFLICT ON CONSTRAINT uq_fundamental_metrics DO NOTHING;
```

## Verifiering

### Kontrollera Vad Som Finns

```bash
# Python one-liner
uv run python -c "
from factor_investor.db import get_session
from sqlalchemy import text

with get_session() as session:
    # Visa alla fundamental metrics
    result = session.execute(text('''
        SELECT metric, COUNT(*) as count
        FROM fundamental_metrics
        GROUP BY metric
        ORDER BY count DESC
    '''))

    print('Fundamental Metrics:')
    print('-' * 50)
    for row in result:
        print(f'{row[0]:35s} {row[1]:>12,} rows')

    # Visa alla price metrics
    result = session.execute(text('''
        SELECT metric, COUNT(*) as count
        FROM price_metrics
        GROUP BY metric
        ORDER BY count DESC
    '''))

    print('\nPrice Metrics:')
    print('-' * 50)
    for row in result:
        print(f'{row[0]:35s} {row[1]:>12,} rows')
"
```

### Hitta Saknade Faktorer

```sql
-- Vilka datum har cash_flow_from_operating_activities?
SELECT
    MIN(date) as first_date,
    MAX(date) as last_date,
    COUNT(DISTINCT date) as num_dates
FROM fundamental_metrics
WHERE metric = 'cash_flow_from_operating_activities';

-- Saknas den för vissa datum?
SELECT DISTINCT date
FROM fundamental_metrics
WHERE metric = 'roe'  -- En faktor som finns överallt
EXCEPT
SELECT DISTINCT date
FROM fundamental_metrics
WHERE metric = 'cash_flow_from_operating_activities';
```

## Best Practices

### 1. Testa Lokalt Först
```bash
# Testa ny faktor på senaste månad först
uv run factor-investor build-base-metrics \
  --metrics my_new_metric \
  --from-date 2026-09-01 \
  --to-date 2026-09-30
```

### 2. Verifiera Före Full Backfill
```sql
-- Kolla fördelning
SELECT
    AVG(value) as mean,
    STDDEV(value) as std,
    MIN(value) as min,
    MAX(value) as max,
    COUNT(*) as count
FROM fundamental_metrics
WHERE metric = 'my_new_metric';

-- Kolla extremvärden
SELECT instrument_id, date, value
FROM fundamental_metrics
WHERE metric = 'my_new_metric'
ORDER BY ABS(value) DESC
LIMIT 20;
```

### 3. Använd Logs För Debugging
```bash
# Verbose logging för att se vad som händer
uv run factor-investor build-base-metrics \
  --metrics ev_ebitda \
  --from-date 2025-01-01 \
  --verbose
```

### 4. Kombinera Med Date Filtering
```bash
# Bygg flera faktorer för specifik period
uv run factor-investor build-base-metrics \
  --metrics pe_ratio,pb_ratio,ps_ratio,ev_ebit \
  --from-date 2024-01-01 \
  --to-date 2024-12-31
```

## Felsökning

### Problem: "Metric not found in filter"
**Orsak:** Faktorn finns inte i koden ännu
**Lösning:** Implementera faktorn i `base_metrics.py` först

### Problem: Saknade Värden
**Orsak:** PIT-data saknas för underliggande metrics
**Lösning:** Kolla att PIT-table har nödvändiga inputs:
```sql
SELECT COUNT(*)
FROM fundamentals_pit
WHERE metric = 'earnings_per_share'
AND instrument_id = 12345;
```

### Problem: Extremvärden
**Orsak:** Outliers i data (division med nära-noll)
**Lösning:** Bounds checking är redan på plats (`MAX_RATIO = 1,000,000`)

## Framtida Utökningar

### 1. EV/EBITDA
När EBITDA-data finns tillgänglig:
```bash
uv run factor-investor build-base-metrics --metrics ev_ebitda
```

### 2. Composite Scores
Piotroski F-score, Altman Z-score, etc. kommer vara **transformerade faktorer** (Parquet cache), inte base metrics.

### 3. Industry-Adjusted Metrics
```python
# Exempel: Industry-adjusted P/E
# Kommer som transformation: pe_ratio_industry_adj
```

## Se Också

- [Fas 4 Implementation Plan](../plan.md) - Full arkitektur
- [PIT System Documentation](./pit-system.md) - Temporal correctness
- [Factor Transformations](./factor-transformations.md) - Lazy calculations med Parquet cache

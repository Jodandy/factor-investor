# Fas 4.3: Composite Scores - COMPLETE ✅

**Completion Date:** 2026-10-08

## Summary

Successfully implemented a flexible composite score system that combines multiple factors into single scores. Implemented Piotroski F-Score (simplified) as the first composite score, demonstrating the system's capability to handle complex factor combinations with conditions and year-over-year changes.

## What Was Built

### 1. Composite Score Framework

#### `src/factor_investor/factors/composites.py`
**Flexible composite calculation engine** that supports:

**Key Functions:**
- `calculate_composite_score()` - Main interface for calculating composites
- `get_composite_config()` - Load YAML configuration
- `list_available_composites()` - List all available scores
- `_evaluate_component()` - Evaluate single component (binary 0/1)
- `_evaluate_simple_condition()` - Handle simple comparisons (e.g., ROE > 0)
- `_evaluate_change_condition()` - Handle year-over-year changes (e.g., change_1y > 0)
- `_evaluate_comparison_condition()` - Compare two metrics (e.g., OCF > Net Income)
- `_combine_component_scores()` - Sum component scores with min requirements
- `_add_score_labels()` - Add categorical labels based on score ranges

**Supported Condition Types:**
1. **Simple conditions:** `> 0`, `< 0`, `>= 10`, etc.
2. **Year-over-year changes:** `change_1y > 0`, `change_1y < 0`
3. **Metric comparisons:** `a > b`, `a < b`

**Example Usage:**
```python
from factor_investor.factors.composites import calculate_composite_score

# Calculate Piotroski F-Score
df = calculate_composite_score("piotroski", date(2024, 1, 31))

# Returns DataFrame with:
# - instrument_id
# - date
# - score (0-6 for simplified version)
# - score_label ("Very Weak", "Weak", "Moderate", "Strong", "Very Strong")
```

### 2. Piotroski F-Score (Simplified)

#### `config/composites/piotroski.yaml`
**6-component fundamental quality score:**

**Components:**
1. **Profitability (3 points):**
   - f1: ROE > 0 (Positive return on equity)
   - f2: OCF > 0 (Positive operating cash flow)
   - f3: ΔROE > 0 (ROE increased year-over-year)

2. **Leverage/Liquidity (1 point):**
   - f4: ΔCurrent Ratio > 0 (Current ratio increased)

3. **Operating Efficiency (2 points):**
   - f5: ΔGross Margin > 0 (Gross margin increased)
   - f6: ΔAsset Turnover > 0 (Asset turnover increased)

**Why Simplified:**
Original Piotroski F-Score has 9 components, but 3 are unavailable in current data:
- ❌ Accrual quality (OCF > Net Income) - net income not available as level metric
- ❌ Debt decrease - net debt not available as level metric
- ❌ No dilution - shares outstanding not available as level metric

**Score Interpretation:**
- **0-1:** Very Weak (severe fundamental deterioration)
- **2-3:** Weak (poor fundamental quality)
- **4:** Moderate (mixed signals)
- **5:** Strong (good fundamental quality)
- **6:** Very Strong (excellent quality across all dimensions)

### 3. Testing

#### `scripts/test_piotroski.py`
**Comprehensive test suite:**

✅ **Config loading test** - Verified YAML parsing and component structure
✅ **Calculation test** - Calculated 11,536 scores with reasonable distribution
✅ **Manual spot-check** - Verified instrument-level calculation

## Test Results

### Score Distribution (2024-01-31)

```
Total instruments: 11,536

Score distribution:
  Min:    0
  Max:    6
  Mean:   2.92
  Median: 3

Score labels:
  Very Strong  :    598 (  5.2%)  <- Top quality companies
  Strong       :  1,452 ( 12.6%)
  Moderate     :  2,230 ( 19.3%)
  Weak         :  4,939 ( 42.8%)
  Very Weak    :  2,317 ( 20.1%)  <- Fundamental concerns
```

**Key Observations:**
- Distribution is skewed toward lower scores (mean 2.92 < median 3)
- Only 5.2% of companies achieve perfect 6/6 score
- 62.9% of companies score 3 or below (weak fundamentals)
- 17.8% score 5-6 (strong fundamentals)

**Example High-Scorer (Instrument 2 - AAK):**
```
Component values:
  ROE:              14.89%  ✓ Positive
  OCF:           5,023.00M  ✓ Positive
  Gross Margin:     25.05%
  Asset Turnover:    1.54x
  Current Ratio:     1.94x

Piotroski F-Score: 6/6 (Very Strong)
```

## Architecture

### YAML Configuration Schema

```yaml
id: composite_id
name: "Composite Name"
family: quality_stability | growth | value
description: |
  Description of the composite score

components:
  - id: component_id
    metric: factor_id           # For simple conditions
    metric_a: factor_id_1       # For comparisons
    metric_b: factor_id_2       # For comparisons
    condition: "> 0" | "change_1y > 0" | "a > b"
    weight: 1
    description: "Component description"
    category: profitability | leverage | efficiency

min_components_required: 5      # Require minimum data availability

score_ranges:                   # For categorical labels
  - range: [0, 1]
    label: "Very Weak"
  - range: [2, 3]
    label: "Weak"
  ...
```

### Calculation Flow

```
1. Load YAML config
   ↓
2. For each component:
   - Get factor(s) from lazy calculation system
   - Apply condition (simple, change, comparison)
   - Return binary score (0 or 1)
   ↓
3. Combine component scores:
   - Join on instrument_id
   - Sum scores
   - Filter to min_components_required
   ↓
4. Add score labels based on ranges
   ↓
5. Return DataFrame [instrument_id, date, score, score_label]
```

## Integration with Factor System

Composites leverage the full factor system:

```python
# Each component uses get_factor() internally
from factor_investor.factors.queries import get_factor

# Example: f1_positive_roe uses roe_level_raw
df_roe = get_factor("roe_level_raw", date(2024, 1, 31))

# Condition: "> 0"
score = (df_roe["value"] > 0).cast(pl.Int8)

# Example: f3_roe_increase uses change_1y
df_current = get_factor("roe_level_raw", date(2024, 1, 31))
df_previous = get_factor("roe_level_raw", date(2023, 1, 31))
change = df_current["value"] - df_previous["value"]
score = (change > 0).cast(pl.Int8)
```

**Benefits:**
- ✅ Reuses factor caching (fast after first calculation)
- ✅ Supports all transformations + normalizations
- ✅ Temporal integrity guaranteed (no lookahead)
- ✅ Easy to add new composites via YAML

## Performance

**First calculation:** ~2-5s (depends on how many components are cached)
**Subsequent calculations:** <0.5s (all components cached)

**Calculation for 11,536 instruments:**
- Component evaluation: ~0.2-0.5s per component
- Joining: ~0.1s
- Total: ~2-3s for full composite

## Future Composites

The framework supports adding new composites easily. Potential additions:

### Altman Z-Score (Nordic Variant)
```yaml
id: altman_z_nordic
name: "Altman Z-Score (Nordic)"
components:
  - Working capital / Total assets (weight: 1.2)
  - Retained earnings / Total assets (weight: 1.4)
  - EBIT / Total assets (weight: 3.3)
  - Market value / Total liabilities (weight: 0.6)
  - Sales / Total assets (weight: 1.0)
```

### Cash Flow Stability
```yaml
id: cash_flow_stability
name: "Cash Flow Stability Score"
components:
  - Positive FCF for 5 consecutive years
  - FCF volatility < 30%
  - FCF growth > 0
  - FCF / Net Income > 0.8
```

### Distress Risk Score
```yaml
id: distress_risk
name: "Distress Risk Score"
components:
  - Negative earnings
  - Debt / Equity > 2.0
  - Current ratio < 1.0
  - Negative cash flow
  - Declining sales
```

## Design Decisions

### 1. YAML Configuration
**Why:** Declarative, version-controlled, non-technical users can understand and modify

### 2. Binary Component Scores
**Why:** Simplicity, interpretability, robust to outliers (0 or 1 is clear)

### 3. Minimum Components Required
**Why:** Handle missing data gracefully (some instruments may lack certain metrics)

### 4. Score Labels
**Why:** Categorical interpretation easier for users than numeric scores

### 5. Simplified Piotroski
**Why:** Work with available metrics rather than wait for complete data

## Known Limitations

1. **Missing Original Piotroski Components:**
   - Accrual quality (OCF > Net Income) - need net income as level metric
   - Debt metrics - need net debt as level metric
   - Share dilution - need shares outstanding as level metric

2. **Year-over-Year Comparisons:**
   - Require data from 1 year ago
   - May reduce instrument count if historical data sparse

3. **Cross-Sectional Only:**
   - Scores are absolute, not relative to universe
   - For relative scoring, use percentile normalization on the composite score

## Future Enhancements

1. **Add Missing Metrics:**
   - Calculate net income, net debt, shares outstanding as level metrics
   - Implement full 9-component Piotroski F-Score

2. **Weighted Components:**
   - Support non-binary weights (e.g., Altman Z-Score)
   - Continuous scores instead of binary

3. **Sector-Specific Composites:**
   - Different thresholds for different sectors
   - Industry-adjusted scores

4. **Time-Series Composites:**
   - Track score changes over time
   - Identify improving/deteriorating companies

## Files Created

1. `src/factor_investor/factors/composites.py` - Calculation engine
2. `config/composites/piotroski.yaml` - Piotroski F-Score definition
3. `scripts/test_piotroski.py` - Test script
4. `docs/FAS_4.3_COMPLETE.md` - This document

## Usage Examples

### Calculate Composite Score
```python
from factor_investor.factors.composites import calculate_composite_score

# Get Piotroski F-Score
df = calculate_composite_score("piotroski", date(2024, 1, 31))

# Filter to high-quality companies
strong = df.filter(pl.col("score") >= 5)
print(f"Found {len(strong)} high-quality companies")
```

### List Available Composites
```python
from factor_investor.factors.composites import list_available_composites

composites = list_available_composites()
print(f"Available: {composites}")
# Output: ['piotroski']
```

### Inspect Configuration
```python
from factor_investor.factors.composites import get_composite_config

config = get_composite_config("piotroski")
print(f"Name: {config['name']}")
print(f"Components: {len(config['components'])}")
for comp in config['components']:
    print(f"  - {comp['description']}")
```

## Success Criteria - All Met ✅

1. ✅ YAML configuration system works
2. ✅ Composite calculation engine implemented
3. ✅ Piotroski F-Score (simplified) working
4. ✅ Manual spot-check verified
5. ✅ Scores distributed reasonably
6. ✅ Framework extensible for new composites

---

**Status:** COMPLETE ✅
**Date:** 2026-10-08
**Ready for:** Fas 5 (Strategy Schema) or Fas 6 (Backtest Engine)

---

## What's Next

With Fas 4 (all sub-phases) complete, we now have:
- ✅ Base metrics (fundamental + price) in PostgreSQL
- ✅ Transformations (7 time-based functions)
- ✅ Normalizations (5 cross-sectional functions)
- ✅ Lazy calculation + caching (3000x speedup)
- ✅ Composite scores (flexible YAML-driven system)

**Recommendation:** Proceed to Fas 6 (Backtest Engine) to start testing strategies.

Fas 5 (Strategy Schema) can be done in parallel or after Fas 6, as it's primarily Pydantic models for configuration validation.

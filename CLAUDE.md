# factor-investor — instructions for Claude Code

## Purpose

A research framework for backtesting equity strategies on global data from Börsdata, without lookahead bias and with strict protection against overfitting. The goal is not to find the strategy with the highest historical return, but the most robust one: stable excess return against a relevant benchmark, across many parameter choices, sub-periods and market segments.

The framework must be able to express and test very different strategy types with the same machinery (e.g. growing quality companies with short history, stable cash flows with timing, deep value). It must never be hard-coded to one specific strategy.

Key documents:
- `docs/ARCHITECTURE.md` — strategy system design (pipeline, versioned components, point-in-time view)
- `docs/DECISIONS.md` — design decisions log (read before changing anything it covers)
- `docs/WORK_ORDER.md`, `docs/HYPOTHESES.md` — phases and hypotheses (Swedish)
- `docs/DATA_AUDIT.md` — what is known and verified about Börsdata's data

## Non-negotiable invariants

These apply to all code. Never break them, not even temporarily or "to test". If a task seems to require it, stop and ask.

1. **Point-in-time.** All fundamental data is looked up via its `known_from` date, never via period end. A report may not be used before the day it was published. Missing or implausible publication dates (on or less than `min_publication_days` after period end) use the conservative fallback delay.
2. **Execution delay.** A signal computed with data as of day T may be executed on day T+1 at the earliest, on the instrument's own next trading day. Never trade at the price the signal was computed from.
3. **No survivorship filters.** Delisted companies (acquisitions, bankruptcies, delistings) belong in the universe for the dates they were listed. No code may filter on "exists today". (Börsdata itself lacks delisted companies — see DECISIONS; treat backtest returns as upper bounds.)
4. **No fixed holdout; all periods weigh equally.** The full history is used for research. Overfitting is controlled by walk-forward and CPCV over the whole period (each sub-period takes a turn as out-of-sample), deflated Sharpe and PBO based on the number of trials, and forward paper trading of final candidates. No single period, especially not the most recent years, may be the sole gate for accepting or rejecting a strategy.
5. **Every run is registered.** Every backtest run within a search or experiment is logged in the trial registry (configuration, config hash, component versions, hypothesis id, metrics). No research run "on the side". Trial counts feed deflated Sharpe and PBO.
6. **Costs are always on.** Transaction costs are on by default. Turning them off requires an explicit flag and the result is labeled "gross".
7. **Determinism.** The same configuration and data give exactly the same result. All randomness is seeded.
8. **Lookahead tests always pass.** The integrity tests under `tests/integrity/` run on every change to the data, factor or engine layer. A PostToolUse hook runs the fast database-free suite automatically after Python edits.
9. **Everything is versioned.** Strategy components and named configurations have ids ending in `_v<N>` (e.g. `dcf_monte_carlo_v1`, `top_growth_quality_v1`). A version never changes behavior once used in a logged run — make `_v2` instead. See `docs/ARCHITECTURE.md` §4.

## Technical stack

- Python 3.12 (`.python-version`), dependencies via `uv`
- PostgreSQL 16 in Docker Desktop (`docker compose`, port 5434), migrations with Alembic
- Parquet + DuckDB/Polars for factor panels and analysis
- numpy, Numba where the backtest loop needs it (profile first)
- pydantic v2 for all configuration, YAML as file format
- Optuna for parameter search
- pytest, ruff, mypy (strict on `core`, `engine`, `pit`)
- typer for the CLI, Plotly for reports (static HTML)

## Working with the data

- **Sync:** `uv run factor-investor ingest sync --metadata --instruments`, then `uv run factor-investor ingest sync-all` (resumable; logs in `data/logs/`). The Makefile's `sync-*` targets reference commands that no longer exist.
- **Builds, in order:** `build-pit`, `build-returns`, `build-universe --from-date 2006-01-01`, `build-base-metrics --from-date 2006-01-01`.
- **Units in Börsdata reports:** totals and `number_of_shares` are in millions; `earnings_per_share` and `dividend` are per share; all values are already converted to the trading currency at historical year-end rates. Quarter rows of semi-annual reporters hold 6-month figures — factors use only r12 and year data.
- **German listings are excluded** (`[universe] exclude_country_ids`): mostly secondary listings.

## Ways of working

- Work one phase or component at a time. State acceptance criteria and verify them with tests before moving on; stop for review after each phase. Do not mark anything "complete" without evidence.
- Write tests together with the code, not afterwards — preferably test first, and confirm the test fails before the fix. Every new factor or component needs a test showing it only uses data known at the calculation date.
- Log every non-trivial design decision in `docs/DECISIONS.md` (date, decision, rationale, rejected alternatives).
- Do not invent details about Börsdata's API. Verify endpoints, fields and limits against the documentation and actual responses, and record them in `docs/DATA_AUDIT.md`.
- **Database migrations:** every unique constraint and composite index must be declared in the model's `__table_args__`, otherwise `alembic revision --autogenerate` drops it. Always review generated migrations before running them, and run `uv run alembic check` afterwards.
- Prefer simple, readable code over clever code. Optimize only when profiling shows a need.
- Respond to the user in English. Code, identifiers and comments in English.

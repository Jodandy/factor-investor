# factor-investor

Research framework for backtesting equity strategies on global data from Börsdata.

## Quick Start

```bash
# Install dependencies
make dev

# Start database
make db-up

# Run checks
make check
```

## Documentation

- **[SYNC_GUIDE.md](docs/SYNC_GUIDE.md)** - **Data sync commands (START HERE!)** ⭐
- **[Incremental Factor Sync](docs/incremental-factor-sync.md)** - Add individual factors without full rebuild ⚡
- [CLAUDE.md](docs/CLAUDE.md) - Project instructions
- [WORK_ORDER.md](docs/WORK_ORDER.md) - Implementation phases
- [HYPOTHESES.md](docs/HYPOTHESES.md) - Strategy hypotheses
- [DECISIONS.md](docs/DECISIONS.md) - Design decisions log
- [DATA_AUDIT.md](docs/DATA_AUDIT.md) - Data quality documentation

## Data Sync

After initial setup, sync data from Börsdata:

```bash
# Initial setup (one-time, ~2-3 hours)
uv run factor-investor sync-instruments
uv run factor-investor sync-prices
uv run factor-investor sync-reports
uv run factor-investor build-pit
uv run factor-investor build-returns
uv run factor-investor build-universe --from-date 2016-01-01

# Regular updates (monthly, ~1 hour)
# See docs/SYNC_GUIDE.md for details
```

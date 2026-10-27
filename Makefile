.PHONY: check lint format test typecheck install dev db-up db-down db-migrate clean help
.PHONY: sync-all sync-raw sync-derived sync-update

# Default target
help:
	@echo "Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  make install    - Install dependencies with uv"
	@echo "  make dev        - Install with dev dependencies"
	@echo "  make check      - Run all checks (lint, typecheck, test)"
	@echo "  make lint       - Run ruff linter"
	@echo "  make format     - Format code with ruff"
	@echo "  make typecheck  - Run mypy type checker"
	@echo "  make test       - Run pytest"
	@echo ""
	@echo "Database:"
	@echo "  make db-up      - Start PostgreSQL container"
	@echo "  make db-down    - Stop PostgreSQL container"
	@echo "  make db-migrate - Run database migrations"
	@echo ""
	@echo "Data Sync (see docs/SYNC_GUIDE.md):"
	@echo "  make sync-all     - Full sync + build (SLOW ~2-3h, one-time setup)"
	@echo "  make sync-raw     - Sync instruments, prices, reports (~40 min)"
	@echo "  make sync-derived - Build PIT, returns, universe (~2h)"
	@echo "  make sync-update  - Quick monthly update (~1h)"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean      - Remove cache files"

install:
	uv sync

dev:
	uv sync --all-extras

check: lint typecheck test
	@echo "All checks passed!"

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

format:
	uv run ruff check --fix src tests
	uv run ruff format src tests

typecheck:
	uv run mypy src

test:
	uv run pytest

db-up:
	docker compose up -d
	@echo "Waiting for database to be ready..."
	@sleep 2
	@docker compose exec db pg_isready -U factor -d factor_investor || (echo "Database not ready" && exit 1)
	@echo "Database is ready!"

db-down:
	docker compose down

db-migrate:
	uv run alembic upgrade head

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Data sync commands (see docs/SYNC_GUIDE.md for details)

sync-all: sync-raw sync-derived
	@echo "✓ Full sync complete! Data is ready for backtesting."

sync-raw:
	@echo "Syncing raw data from Börsdata API..."
	uv run factor-investor sync-instruments
	uv run factor-investor sync-prices
	uv run factor-investor sync-reports
	@echo "✓ Raw data sync complete"

sync-derived:
	@echo "Building derived data tables..."
	uv run factor-investor build-pit
	uv run factor-investor build-returns
	uv run factor-investor build-universe --from-date 2006-01-01
	@echo "✓ Derived data build complete"

sync-update:
	@echo "Running incremental monthly update..."
	uv run factor-investor sync-instruments
	uv run factor-investor sync-prices
	uv run factor-investor sync-reports
	uv run factor-investor build-pit
	uv run factor-investor build-returns
	uv run factor-investor build-universe --from-date $$(date -v-3m +%Y-%m-%d)
	@echo "✓ Data updated successfully"

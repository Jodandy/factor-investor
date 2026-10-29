"""Data synchronization service for Börsdata."""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from factor_investor.db import get_session
from factor_investor.ingest.client import BorsdataClient, create_client_from_env
from factor_investor.ingest.models import (
    Branch,
    Country,
    DividendCalendarEntry,
    Instrument,
    InstrumentSyncStatus,
    Market,
    ReportQuarter,
    ReportR12,
    ReportYear,
    Sector,
    StockPrice,
    StockSplit,
    SyncLog,
)
from factor_investor.settings import price_only_instrument_types, stock_instrument_types

logger = logging.getLogger(__name__)

# Börsdata returns only 10 years of prices unless maxCount is given; the API
# caps history at 20 years, so this requests everything available.
PRICE_HISTORY_MAX_COUNT = 20 * 365

# The dividend calendar endpoint takes at most 50 instruments per request.
DIVIDEND_CALENDAR_BATCH = 50


def _price_instrument_types() -> list[int]:
    """Instrument types synced for prices: stocks plus indices and FX."""
    return stock_instrument_types() + price_only_instrument_types()


def parse_date(date_str: str | None) -> date | None:
    """Parse date string from API response."""
    if not date_str:
        return None
    try:
        # Handle both "2024-01-15" and "2024-01-15T00:00:00" formats
        if "T" in date_str:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
        return date.fromisoformat(date_str)
    except ValueError:
        logger.warning(f"Could not parse date: {date_str}")
        return None


def parse_dividend_calendar(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Rows for dividend_calendar from a /v1/instruments/dividend/calendar response.

    Rows with the same instrument, ex-date and type are summed (one row per
    unique key); rows without an ex-date are skipped.
    """
    rows: dict[tuple[int, date, int], dict[str, Any]] = {}
    for item in data.get("list") or []:
        for value in item.get("values") or []:
            ex_date = parse_date(value.get("excludingDate"))
            if ex_date is None:
                continue
            key = (item["insId"], ex_date, int(value.get("dividendType") or 0))
            amount = value.get("amountPaid")
            if key in rows:
                previous = rows[key]["amount_paid"]
                if amount is not None:
                    rows[key]["amount_paid"] = (previous or 0) + amount
                continue
            rows[key] = {
                "ins_id": key[0],
                "ex_date": key[1],
                "dividend_type": key[2],
                "amount_paid": amount,
                "currency": value.get("currencyShortName"),
                "distribution_frequency": value.get("distributionFrequency"),
            }
    return list(rows.values())


def save_raw_json(data: dict[str, Any], name: str, raw_dir: Path) -> None:
    """Save raw API response to JSON file for traceability."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = raw_dir / f"{name}_{timestamp}.json"
    with filepath.open("w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.debug(f"Saved raw JSON to {filepath}")


class SyncService:
    """Service for synchronizing data from Börsdata to local database."""

    def __init__(
        self,
        client: BorsdataClient | None = None,
        raw_dir: Path | None = None,
        save_raw: bool = True,
    ):
        self.client = client or create_client_from_env()
        self.raw_dir = raw_dir or Path("data/raw")
        self.save_raw = save_raw

    def _start_sync(self, session: Session, sync_type: str) -> SyncLog:
        """Start a sync operation and log it."""
        sync_log = SyncLog(
            sync_type=sync_type,
            started_at=datetime.utcnow(),
            status="running",
        )
        session.add(sync_log)
        session.flush()
        return sync_log

    def _complete_sync(
        self,
        _session: Session,
        sync_log: SyncLog,
        records: int,
        error: str | None = None,
    ) -> None:
        """Complete a sync operation."""
        sync_log.completed_at = datetime.utcnow()
        sync_log.records_processed = records
        if error:
            sync_log.status = "failed"
            sync_log.error_message = error
        else:
            sync_log.status = "completed"

    def sync_metadata(self) -> dict[str, int]:
        """Sync all metadata tables (countries, markets, sectors, branches)."""
        counts: dict[str, int] = {}

        with get_session() as session:
            # Countries - fetch first
            countries_data = self.client.get_countries()
            if self.save_raw:
                save_raw_json(countries_data, "countries", self.raw_dir)

            country_ids = {item["id"] for item in countries_data.get("countries", [])}

            # Markets - fetch to find any missing country references
            markets_data = self.client.get_markets()
            if self.save_raw:
                save_raw_json(markets_data, "markets", self.raw_dir)

            # Find country IDs referenced by markets but not in countries API
            market_country_ids = {item["countryId"] for item in markets_data.get("markets", [])}
            missing_country_ids = market_country_ids - country_ids

            # Insert known countries
            for item in countries_data.get("countries", []):
                stmt = insert(Country).values(
                    id=item["id"],
                    name=item["name"],
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={"name": stmt.excluded.name},
                )
                session.execute(stmt)

            # Insert placeholder countries for missing IDs
            for country_id in missing_country_ids:
                stmt = insert(Country).values(
                    id=country_id,
                    name=f"Unknown Country {country_id}",
                )
                stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
                session.execute(stmt)

            counts["countries"] = len(countries_data.get("countries", [])) + len(
                missing_country_ids
            )

            # Sectors
            data = self.client.get_sectors()
            if self.save_raw:
                save_raw_json(data, "sectors", self.raw_dir)

            for item in data.get("sectors", []):
                stmt = insert(Sector).values(
                    id=item["id"],
                    name=item["name"],
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={"name": stmt.excluded.name},
                )
                session.execute(stmt)
            counts["sectors"] = len(data.get("sectors", []))

            # Branches
            data = self.client.get_branches()
            if self.save_raw:
                save_raw_json(data, "branches", self.raw_dir)

            for item in data.get("branches", []):
                stmt = insert(Branch).values(
                    id=item["id"],
                    name=item["name"],
                    sector_id=item["sectorId"],
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "name": stmt.excluded.name,
                        "sector_id": stmt.excluded.sector_id,
                    },
                )
                session.execute(stmt)
            counts["branches"] = len(data.get("branches", []))

            # Markets - now insert with all country FKs satisfied
            for item in markets_data.get("markets", []):
                stmt = insert(Market).values(
                    id=item["id"],
                    name=item["name"],
                    country_id=item["countryId"],
                    exchange_name=item.get("exchangeName"),
                    is_index=item.get("isIndex", False),
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "name": stmt.excluded.name,
                        "country_id": stmt.excluded.country_id,
                        "exchange_name": stmt.excluded.exchange_name,
                        "is_index": stmt.excluded.is_index,
                    },
                )
                session.execute(stmt)
            counts["markets"] = len(markets_data.get("markets", []))

        logger.info(f"Synced metadata: {counts}")
        return counts

    def sync_instruments(self, include_global: bool = True) -> int:
        """Sync all instruments."""
        with get_session() as session:
            sync_log = self._start_sync(session, "instruments")

            try:
                data = self.client.get_instruments(include_global=include_global)
                if self.save_raw:
                    save_raw_json(data, "instruments", self.raw_dir)

                instruments = data.get("instruments", [])
                for item in instruments:
                    stmt = insert(Instrument).values(
                        ins_id=item["insId"],
                        name=item["name"],
                        ticker=item.get("ticker"),
                        isin=item.get("isin"),
                        yahoo=item.get("yahoo"),
                        url_name=item.get("urlName"),
                        instrument_type=item.get("instrument", 0),
                        country_id=item["countryId"],
                        market_id=item["marketId"],
                        sector_id=item.get("sectorId"),
                        branch_id=item.get("branchId"),
                        listing_date=parse_date(item.get("listingDate")),
                        stock_price_currency=item.get("stockPriceCurrency"),
                        report_currency=item.get("reportCurrency"),
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["ins_id"],
                        set_={
                            "name": stmt.excluded.name,
                            "ticker": stmt.excluded.ticker,
                            "isin": stmt.excluded.isin,
                            "yahoo": stmt.excluded.yahoo,
                            "url_name": stmt.excluded.url_name,
                            "instrument_type": stmt.excluded.instrument_type,
                            "country_id": stmt.excluded.country_id,
                            "market_id": stmt.excluded.market_id,
                            "sector_id": stmt.excluded.sector_id,
                            "branch_id": stmt.excluded.branch_id,
                            "listing_date": stmt.excluded.listing_date,
                            "stock_price_currency": stmt.excluded.stock_price_currency,
                            "report_currency": stmt.excluded.report_currency,
                            "updated_at": datetime.utcnow(),
                        },
                    )
                    session.execute(stmt)

                count = len(instruments)
                self._complete_sync(session, sync_log, count)
                logger.info(f"Synced {count} instruments")
                return count

            except Exception as e:
                self._complete_sync(session, sync_log, 0, str(e))
                raise

    def sync_prices_for_instrument(
        self,
        session: Session,
        ins_id: int,
        from_date: str | None = None,
        max_count: int | None = None,
    ) -> int:
        """Sync prices for a single instrument using bulk insert."""
        if from_date is None and max_count is None:
            max_count = PRICE_HISTORY_MAX_COUNT
        data = self.client.get_stock_prices(ins_id, from_date=from_date, max_count=max_count)
        prices = data.get("stockPricesList", [])

        if not prices:
            return 0

        # Build list of values for bulk insert
        values = [
            {
                "ins_id": ins_id,
                "date": parse_date(item["d"]),
                "open": item.get("o"),
                "high": item.get("h"),
                "low": item.get("l"),
                "close": item.get("c"),
                "volume": item.get("v"),
            }
            for item in prices
        ]

        # Bulk insert with ON CONFLICT
        stmt = insert(StockPrice).values(values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_stock_prices_ins_date",
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
            },
        )
        session.execute(stmt)

        return len(prices)

    def sync_prices(
        self,
        instrument_ids: list[int] | None = None,
        from_date: str | None = None,
        max_count: int | None = None,
        batch_size: int = 100,
    ) -> int:
        """Sync prices for multiple instruments."""
        with get_session() as session:
            sync_log = self._start_sync(session, "prices")

            try:
                # Get instrument IDs if not provided
                if instrument_ids is None:
                    result = session.execute(
                        select(Instrument.ins_id).where(
                            Instrument.instrument_type.in_(_price_instrument_types())
                        )
                    )
                    instrument_ids = [row[0] for row in result]

                total = 0
                for i, ins_id in enumerate(instrument_ids):
                    count = self.sync_prices_for_instrument(
                        session, ins_id, from_date=from_date, max_count=max_count
                    )
                    total += count

                    if (i + 1) % batch_size == 0:
                        session.commit()
                        logger.info(f"Processed {i + 1}/{len(instrument_ids)} instruments")

                self._complete_sync(session, sync_log, total)
                logger.info(f"Synced {total} price records for {len(instrument_ids)} instruments")
                return total

            except Exception as e:
                self._complete_sync(session, sync_log, 0, str(e))
                raise

    def sync_reports_for_instrument(self, session: Session, ins_id: int) -> dict[str, int]:
        """Sync all reports for a single instrument."""
        data = self.client.get_reports(ins_id, max_year_count=50, max_r12q_count=100)
        counts: dict[str, int] = {"year": 0, "quarter": 0, "r12": 0}

        # Year reports
        for item in data.get("reportsYear", []):
            stmt = insert(ReportYear).values(
                ins_id=ins_id,
                year=item["year"],
                period=item.get("period"),
                report_start_date=parse_date(item.get("report_Start_Date")),
                report_end_date=parse_date(item.get("report_End_Date")),
                report_date=parse_date(item.get("report_Date")),
                broken_fiscal_year=item.get("broken_Fiscal_Year", False),
                currency=item.get("currency"),
                currency_ratio=item.get("currency_Ratio"),
                revenues=item.get("revenues"),
                net_sales=item.get("net_Sales"),
                gross_income=item.get("gross_Income"),
                operating_income=item.get("operating_Income"),
                profit_before_tax=item.get("profit_Before_Tax"),
                profit_to_equity_holders=item.get("profit_To_Equity_Holders"),
                earnings_per_share=item.get("earnings_Per_Share"),
                intangible_assets=item.get("intangible_Assets"),
                tangible_assets=item.get("tangible_Assets"),
                financial_assets=item.get("financial_Assets"),
                non_current_assets=item.get("non_Current_Assets"),
                cash_and_equivalents=item.get("cash_And_Equivalents"),
                current_assets=item.get("current_Assets"),
                total_assets=item.get("total_Assets"),
                total_equity=item.get("total_Equity"),
                non_current_liabilities=item.get("non_Current_Liabilities"),
                current_liabilities=item.get("current_Liabilities"),
                total_liabilities_and_equity=item.get("total_Liabilities_And_Equity"),
                net_debt=item.get("net_Debt"),
                cash_flow_from_operating_activities=item.get("cash_Flow_From_Operating_Activities"),
                cash_flow_from_investing_activities=item.get("cash_Flow_From_Investing_Activities"),
                cash_flow_from_financing_activities=item.get("cash_Flow_From_Financing_Activities"),
                cash_flow_for_the_year=item.get("cash_Flow_For_The_Year"),
                free_cash_flow=item.get("free_Cash_Flow"),
                number_of_shares=item.get("number_Of_Shares"),
                dividend=item.get("dividend"),
                stock_price_average=item.get("stock_Price_Average"),
                stock_price_high=item.get("stock_Price_High"),
                stock_price_low=item.get("stock_Price_Low"),
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_reports_year_ins_year",
                set_={
                    col: getattr(stmt.excluded, col)
                    for col in [
                        "report_start_date",
                        "report_end_date",
                        "report_date",
                        "revenues",
                        "net_sales",
                        "gross_income",
                        "operating_income",
                        "profit_before_tax",
                        "profit_to_equity_holders",
                        "earnings_per_share",
                        "total_assets",
                        "total_equity",
                        "net_debt",
                        "free_cash_flow",
                        "number_of_shares",
                        "dividend",
                    ]
                },
            )
            session.execute(stmt)
            counts["year"] += 1

        # Quarter reports
        for item in data.get("reportsQuarter", []):
            stmt = insert(ReportQuarter).values(
                ins_id=ins_id,
                year=item["year"],
                period=item["period"],
                report_start_date=parse_date(item.get("report_Start_Date")),
                report_end_date=parse_date(item.get("report_End_Date")),
                report_date=parse_date(item.get("report_Date")),
                currency=item.get("currency"),
                currency_ratio=item.get("currency_Ratio"),
                revenues=item.get("revenues"),
                net_sales=item.get("net_Sales"),
                gross_income=item.get("gross_Income"),
                operating_income=item.get("operating_Income"),
                profit_before_tax=item.get("profit_Before_Tax"),
                profit_to_equity_holders=item.get("profit_To_Equity_Holders"),
                earnings_per_share=item.get("earnings_Per_Share"),
                intangible_assets=item.get("intangible_Assets"),
                tangible_assets=item.get("tangible_Assets"),
                financial_assets=item.get("financial_Assets"),
                non_current_assets=item.get("non_Current_Assets"),
                cash_and_equivalents=item.get("cash_And_Equivalents"),
                current_assets=item.get("current_Assets"),
                total_assets=item.get("total_Assets"),
                total_equity=item.get("total_Equity"),
                non_current_liabilities=item.get("non_Current_Liabilities"),
                current_liabilities=item.get("current_Liabilities"),
                total_liabilities_and_equity=item.get("total_Liabilities_And_Equity"),
                net_debt=item.get("net_Debt"),
                cash_flow_from_operating_activities=item.get("cash_Flow_From_Operating_Activities"),
                cash_flow_from_investing_activities=item.get("cash_Flow_From_Investing_Activities"),
                cash_flow_from_financing_activities=item.get("cash_Flow_From_Financing_Activities"),
                cash_flow_for_the_year=item.get("cash_Flow_For_The_Year"),
                free_cash_flow=item.get("free_Cash_Flow"),
                number_of_shares=item.get("number_Of_Shares"),
                dividend=item.get("dividend"),
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_reports_quarter_ins_year_period",
                set_={
                    col: getattr(stmt.excluded, col)
                    for col in [
                        "report_start_date",
                        "report_end_date",
                        "report_date",
                        "revenues",
                        "operating_income",
                        "profit_to_equity_holders",
                        "total_assets",
                        "total_equity",
                        "net_debt",
                        "free_cash_flow",
                        "number_of_shares",
                    ]
                },
            )
            session.execute(stmt)
            counts["quarter"] += 1

        # R12 reports
        for item in data.get("reportsR12", []):
            stmt = insert(ReportR12).values(
                ins_id=ins_id,
                year=item["year"],
                period=item["period"],
                report_start_date=parse_date(item.get("report_Start_Date")),
                report_end_date=parse_date(item.get("report_End_Date")),
                report_date=parse_date(item.get("report_Date")),
                currency=item.get("currency"),
                currency_ratio=item.get("currency_Ratio"),
                revenues=item.get("revenues"),
                net_sales=item.get("net_Sales"),
                gross_income=item.get("gross_Income"),
                operating_income=item.get("operating_Income"),
                profit_before_tax=item.get("profit_Before_Tax"),
                profit_to_equity_holders=item.get("profit_To_Equity_Holders"),
                earnings_per_share=item.get("earnings_Per_Share"),
                intangible_assets=item.get("intangible_Assets"),
                tangible_assets=item.get("tangible_Assets"),
                financial_assets=item.get("financial_Assets"),
                non_current_assets=item.get("non_Current_Assets"),
                cash_and_equivalents=item.get("cash_And_Equivalents"),
                current_assets=item.get("current_Assets"),
                total_assets=item.get("total_Assets"),
                total_equity=item.get("total_Equity"),
                non_current_liabilities=item.get("non_Current_Liabilities"),
                current_liabilities=item.get("current_Liabilities"),
                total_liabilities_and_equity=item.get("total_Liabilities_And_Equity"),
                net_debt=item.get("net_Debt"),
                cash_flow_from_operating_activities=item.get("cash_Flow_From_Operating_Activities"),
                cash_flow_from_investing_activities=item.get("cash_Flow_From_Investing_Activities"),
                cash_flow_from_financing_activities=item.get("cash_Flow_From_Financing_Activities"),
                cash_flow_for_the_year=item.get("cash_Flow_For_The_Year"),
                free_cash_flow=item.get("free_Cash_Flow"),
                number_of_shares=item.get("number_Of_Shares"),
                dividend=item.get("dividend"),
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_reports_r12_ins_year_period",
                set_={
                    col: getattr(stmt.excluded, col)
                    for col in [
                        "report_start_date",
                        "report_end_date",
                        "report_date",
                        "revenues",
                        "operating_income",
                        "profit_to_equity_holders",
                        "total_assets",
                        "total_equity",
                        "net_debt",
                        "free_cash_flow",
                        "number_of_shares",
                    ]
                },
            )
            session.execute(stmt)
            counts["r12"] += 1

        return counts

    def sync_reports(
        self,
        instrument_ids: list[int] | None = None,
        batch_size: int = 50,
    ) -> dict[str, int]:
        """Sync reports for multiple instruments."""
        with get_session() as session:
            sync_log = self._start_sync(session, "reports")

            try:
                if instrument_ids is None:
                    result = session.execute(
                        select(Instrument.ins_id).where(
                            Instrument.instrument_type.in_(stock_instrument_types())
                        )
                    )
                    instrument_ids = [row[0] for row in result]

                totals: dict[str, int] = {"year": 0, "quarter": 0, "r12": 0}
                for i, ins_id in enumerate(instrument_ids):
                    counts = self.sync_reports_for_instrument(session, ins_id)
                    for k, v in counts.items():
                        totals[k] += v

                    if (i + 1) % batch_size == 0:
                        session.commit()
                        logger.info(
                            f"Processed reports for {i + 1}/{len(instrument_ids)} instruments"
                        )

                total_records = sum(totals.values())
                self._complete_sync(session, sync_log, total_records)
                logger.info(f"Synced reports: {totals}")
                return totals

            except Exception as e:
                self._complete_sync(session, sync_log, 0, str(e))
                raise

    def sync_reports_resumable(
        self,
        include_global: bool = True,
        batch_size: int = 50,
        skip_completed: bool = True,
    ) -> dict[str, int]:
        """Sync reports with per-instrument tracking for resume capability.

        This method tracks which instruments have been synced successfully,
        allowing the sync to be resumed if interrupted.
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        with get_session() as session:
            sync_log = self._start_sync(session, "reports_resumable")

            try:
                # Stocks only: indices and FX have no reports
                query = (
                    select(Instrument.ins_id)
                    .join(Market)
                    .where(Market.is_index == False)  # noqa: E712
                    .where(Instrument.instrument_type.in_(stock_instrument_types()))
                )
                if not include_global:
                    query = query.where(Instrument.country_id.in_([1, 2, 3, 4]))

                result = session.execute(query)
                all_ids = [row[0] for row in result]

                # Filter out already completed if resuming
                if skip_completed:
                    completed = session.execute(
                        select(InstrumentSyncStatus.ins_id).where(
                            InstrumentSyncStatus.sync_type == "reports",
                            InstrumentSyncStatus.status == "completed",
                        )
                    )
                    completed_ids = {row[0] for row in completed}
                    instrument_ids = [i for i in all_ids if i not in completed_ids]
                    logger.info(
                        f"Resuming: {len(completed_ids)} already done, "
                        f"{len(instrument_ids)} remaining out of {len(all_ids)}"
                    )
                else:
                    instrument_ids = all_ids

                totals: dict[str, int] = {"year": 0, "quarter": 0, "r12": 0}
                failed: list[int] = []

                for i, ins_id in enumerate(instrument_ids):
                    try:
                        counts = self.sync_reports_for_instrument(session, ins_id)
                        for k, v in counts.items():
                            totals[k] += v

                        # Mark as completed
                        stmt = pg_insert(InstrumentSyncStatus).values(
                            ins_id=ins_id,
                            sync_type="reports",
                            last_synced_at=datetime.utcnow(),
                            status="completed",
                            records_synced=sum(counts.values()),
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["ins_id", "sync_type"],
                            set_={
                                "last_synced_at": stmt.excluded.last_synced_at,
                                "status": stmt.excluded.status,
                                "records_synced": stmt.excluded.records_synced,
                                "error_message": None,
                            },
                        )
                        session.execute(stmt)

                    except Exception as e:
                        # Mark as failed but continue with others
                        failed.append(ins_id)
                        stmt = pg_insert(InstrumentSyncStatus).values(
                            ins_id=ins_id,
                            sync_type="reports",
                            last_synced_at=datetime.utcnow(),
                            status="failed",
                            error_message=str(e)[:500],
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["ins_id", "sync_type"],
                            set_={
                                "last_synced_at": stmt.excluded.last_synced_at,
                                "status": stmt.excluded.status,
                                "error_message": stmt.excluded.error_message,
                            },
                        )
                        session.execute(stmt)
                        logger.warning(f"Failed to sync reports for {ins_id}: {e}")

                    if (i + 1) % batch_size == 0:
                        session.commit()
                        logger.info(
                            f"Progress: {i + 1}/{len(instrument_ids)} "
                            f"({len(failed)} failed) - reports: {totals}"
                        )

                # Final commit
                session.commit()
                total_records = sum(totals.values())
                self._complete_sync(session, sync_log, total_records)

                logger.info(f"Sync completed: {totals}, {len(failed)} instruments failed")
                if failed:
                    logger.warning(f"Failed instrument IDs: {failed[:20]}...")

                return totals

            except Exception as e:
                self._complete_sync(session, sync_log, 0, str(e))
                raise

    def sync_prices_resumable(
        self,
        include_global: bool = True,
        from_date: str | None = None,
        max_count: int | None = None,
        batch_size: int = 100,
        skip_completed: bool = True,
    ) -> int:
        """Sync prices with per-instrument tracking for resume capability."""
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        with get_session() as session:
            sync_log = self._start_sync(session, "prices_resumable")

            try:
                # Stocks plus indices and FX (benchmarks, currency conversion)
                query = select(Instrument.ins_id).where(
                    Instrument.instrument_type.in_(_price_instrument_types())
                )
                if not include_global:
                    query = query.where(Instrument.country_id.in_([1, 2, 3, 4]))

                result = session.execute(query)
                all_ids = [row[0] for row in result]

                # Filter out already completed if resuming
                if skip_completed:
                    completed = session.execute(
                        select(InstrumentSyncStatus.ins_id).where(
                            InstrumentSyncStatus.sync_type == "prices",
                            InstrumentSyncStatus.status == "completed",
                        )
                    )
                    completed_ids = {row[0] for row in completed}
                    instrument_ids = [i for i in all_ids if i not in completed_ids]
                    logger.info(
                        f"Resuming: {len(completed_ids)} already done, "
                        f"{len(instrument_ids)} remaining out of {len(all_ids)}"
                    )
                else:
                    instrument_ids = all_ids

                total = 0
                failed: list[int] = []

                for i, ins_id in enumerate(instrument_ids):
                    try:
                        count = self.sync_prices_for_instrument(
                            session, ins_id, from_date=from_date, max_count=max_count
                        )
                        total += count

                        # Mark as completed
                        stmt = pg_insert(InstrumentSyncStatus).values(
                            ins_id=ins_id,
                            sync_type="prices",
                            last_synced_at=datetime.utcnow(),
                            status="completed",
                            records_synced=count,
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["ins_id", "sync_type"],
                            set_={
                                "last_synced_at": stmt.excluded.last_synced_at,
                                "status": stmt.excluded.status,
                                "records_synced": stmt.excluded.records_synced,
                                "error_message": None,
                            },
                        )
                        session.execute(stmt)

                    except Exception as e:
                        failed.append(ins_id)
                        stmt = pg_insert(InstrumentSyncStatus).values(
                            ins_id=ins_id,
                            sync_type="prices",
                            last_synced_at=datetime.utcnow(),
                            status="failed",
                            error_message=str(e)[:500],
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["ins_id", "sync_type"],
                            set_={
                                "last_synced_at": stmt.excluded.last_synced_at,
                                "status": stmt.excluded.status,
                                "error_message": stmt.excluded.error_message,
                            },
                        )
                        session.execute(stmt)
                        logger.warning(f"Failed to sync prices for {ins_id}: {e}")

                    if (i + 1) % batch_size == 0:
                        session.commit()
                        logger.info(
                            f"Progress: {i + 1}/{len(instrument_ids)} "
                            f"({len(failed)} failed) - {total:,} prices"
                        )

                session.commit()
                self._complete_sync(session, sync_log, total)

                logger.info(f"Sync completed: {total:,} prices, {len(failed)} instruments failed")
                if failed:
                    logger.warning(f"Failed instrument IDs: {failed[:20]}...")

                return total

            except Exception as e:
                self._complete_sync(session, sync_log, 0, str(e))
                raise

    def get_sync_status(self, sync_type: str) -> dict[str, int]:
        """Get current sync status counts."""
        with get_session() as session:
            from sqlalchemy import func

            result = session.execute(
                select(
                    InstrumentSyncStatus.status,
                    func.count(InstrumentSyncStatus.ins_id),
                )
                .where(InstrumentSyncStatus.sync_type == sync_type)
                .group_by(InstrumentSyncStatus.status)
            )
            return {row[0]: row[1] for row in result}

    def sync_splits(self, from_date: str | None = None) -> int:
        """Sync stock splits."""
        with get_session() as session:
            sync_log = self._start_sync(session, "splits")

            try:
                data = self.client.get_stock_splits(from_date=from_date)
                if self.save_raw:
                    save_raw_json(data, "splits", self.raw_dir)

                splits = data.get("stockSplitList", [])
                for item in splits:
                    stmt = insert(StockSplit).values(
                        ins_id=item["instrumentId"],
                        split_date=parse_date(item["splitDate"]),
                        split_type=item.get("splitType"),
                        ratio=item.get("ratio"),
                    )
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_stock_splits_ins_date",
                        set_={
                            "split_type": stmt.excluded.split_type,
                            "ratio": stmt.excluded.ratio,
                        },
                    )
                    session.execute(stmt)

                count = len(splits)
                self._complete_sync(session, sync_log, count)
                logger.info(f"Synced {count} stock splits")
                return count

            except Exception as e:
                self._complete_sync(session, sync_log, 0, str(e))
                raise

    def sync_dividend_calendar(self, instrument_ids: list[int] | None = None) -> int:
        """Sync the dividend calendar (real ex-dates) for stock instruments.

        Each call returns an instrument's full calendar, so the stored rows of
        the requested instruments are replaced batch by batch.
        """
        if instrument_ids is None:
            with get_session() as session:
                instrument_ids = list(
                    session.scalars(
                        select(Instrument.ins_id)
                        .where(Instrument.instrument_type.in_(stock_instrument_types()))
                        .order_by(Instrument.ins_id)
                    )
                )

        with get_session() as session:
            sync_log = self._start_sync(session, "dividend_calendar")
        total = 0
        try:
            for start in range(0, len(instrument_ids), DIVIDEND_CALENDAR_BATCH):
                batch = instrument_ids[start : start + DIVIDEND_CALENDAR_BATCH]
                data = self.client.get_dividend_calendar(batch)
                rows = parse_dividend_calendar(data)
                with get_session() as session:
                    session.execute(
                        delete(DividendCalendarEntry).where(DividendCalendarEntry.ins_id.in_(batch))
                    )
                    if rows:
                        session.execute(insert(DividendCalendarEntry).values(rows))
                total += len(rows)
                if (start // DIVIDEND_CALENDAR_BATCH) % 20 == 0:
                    logger.info(
                        f"Dividend calendar: {start + len(batch)}/{len(instrument_ids)} instruments, "
                        f"{total} rows"
                    )
        except Exception as e:
            with get_session() as session:
                self._complete_sync(session, session.merge(sync_log), total, str(e))
            raise
        with get_session() as session:
            self._complete_sync(session, session.merge(sync_log), total)
        logger.info(f"Synced {total} dividend calendar rows for {len(instrument_ids)} instruments")
        return total

    def full_sync(self, include_global: bool = True) -> dict[str, Any]:
        """Run a full sync of all data."""
        logger.info("Starting full sync...")
        results: dict[str, Any] = {}

        # 1. Metadata first (needed for foreign keys)
        results["metadata"] = self.sync_metadata()

        # 2. Instruments
        results["instruments"] = self.sync_instruments(include_global=include_global)

        # 3. Splits (limited history from API)
        results["splits"] = self.sync_splits()

        # 4. Reports (takes longest)
        # For full sync, limit to instruments with stocks (not indices)
        with get_session() as session:
            # Get non-index instruments
            result = session.execute(
                select(Instrument.ins_id)
                .join(Market)
                .where(Market.is_index == False)  # noqa: E712
                .where(Instrument.instrument_type.in_(stock_instrument_types()))
            )
            stock_ids = [row[0] for row in result]

        logger.info(f"Syncing reports for {len(stock_ids)} stocks...")
        results["reports"] = self.sync_reports(instrument_ids=stock_ids)

        # 5. Prices (very large - do incrementally in production)
        # For full sync, just do a sample or skip
        logger.info("Skipping full price sync (use sync_prices for incremental)")
        results["prices"] = "skipped"

        logger.info(f"Full sync completed: {results}")
        return results

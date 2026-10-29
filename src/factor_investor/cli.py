"""Factor Investor CLI.

Usage: factor-investor [COMMAND] [OPTIONS]
"""

import json
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="factor-investor",
    help="Research framework for backtesting equity strategies on global data",
    no_args_is_help=True,
)

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # httpx logs full request URLs, which include the Börsdata authKey
    logging.getLogger("httpx").setLevel(logging.WARNING)


# --- Ingest commands ---
ingest_app = typer.Typer(help="Data ingestion from Börsdata")
app.add_typer(ingest_app, name="ingest")


@ingest_app.command("sync")
def ingest_sync(
    full: bool = typer.Option(False, "--full", help="Full sync (metadata + instruments + reports)"),
    metadata: bool = typer.Option(False, "--metadata", help="Sync metadata only"),
    instruments: bool = typer.Option(False, "--instruments", help="Sync instruments only"),
    reports: bool = typer.Option(False, "--reports", help="Sync reports only"),
    prices: bool = typer.Option(False, "--prices", help="Sync prices only"),
    dividends: bool = typer.Option(
        False, "--dividends", help="Sync the dividend calendar (ex-dates) for stocks"
    ),
    nordic_only: bool = typer.Option(False, "--nordic-only", help="Nordic instruments only"),
    limit: int = typer.Option(0, "--limit", help="Limit number of instruments (0=all)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Sync data from Börsdata API."""
    setup_logging(verbose)

    from factor_investor.ingest.sync import SyncService

    sync = SyncService()
    include_global = not nordic_only

    # Determine what to sync
    if full:
        console.print("[bold]Starting full sync...[/bold]")
        results = sync.full_sync(include_global=include_global)
        console.print(f"[green]Full sync completed:[/green] {results}")
        return

    # Individual syncs
    if metadata or not any([instruments, reports, prices, dividends]):
        console.print("Syncing metadata...")
        counts = sync.sync_metadata()
        console.print(f"[green]Metadata:[/green] {counts}")

    if instruments:
        console.print("Syncing instruments...")
        count = sync.sync_instruments(include_global=include_global)
        console.print(f"[green]Instruments:[/green] {count}")

    if reports:
        console.print("Syncing reports...")
        from sqlalchemy import select

        from factor_investor.db import get_session
        from factor_investor.ingest.models import Instrument, Market

        with get_session() as session:
            query = select(Instrument.ins_id).join(Market).where(Market.is_index == False)  # noqa: E712
            if not include_global:
                query = query.where(Instrument.country_id.in_([1, 2, 3, 4]))  # Nordic
            result = session.execute(query)
            instrument_ids = [row[0] for row in result]

        if limit > 0:
            instrument_ids = instrument_ids[:limit]

        console.print(f"Syncing reports for {len(instrument_ids)} instruments...")
        counts = sync.sync_reports(instrument_ids=instrument_ids)
        console.print(f"[green]Reports:[/green] {counts}")

    if prices:
        console.print("Syncing prices...")
        from sqlalchemy import select

        from factor_investor.db import get_session
        from factor_investor.ingest.models import Instrument

        with get_session() as session:
            query = select(Instrument.ins_id)
            if not include_global:
                query = query.where(Instrument.country_id.in_([1, 2, 3, 4]))
            result = session.execute(query)
            instrument_ids = [row[0] for row in result]

        if limit > 0:
            instrument_ids = instrument_ids[:limit]

        console.print(f"Syncing prices for {len(instrument_ids)} instruments...")
        count = sync.sync_prices(instrument_ids=instrument_ids)
        console.print(f"[green]Prices:[/green] {count} records")

    if dividends:
        console.print("Syncing dividend calendar...")
        count = sync.sync_dividend_calendar()
        console.print(f"[green]Dividend calendar:[/green] {count} rows")


@ingest_app.command("sync-all")
def ingest_sync_all(
    reports: bool = typer.Option(True, "--reports/--no-reports", help="Sync reports"),
    prices: bool = typer.Option(True, "--prices/--no-prices", help="Sync prices"),
    nordic_only: bool = typer.Option(False, "--nordic-only", help="Nordic instruments only"),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Resume from last position"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Sync all data with progress tracking (resumable).

    This command syncs reports and/or prices for all instruments,
    tracking progress per instrument so it can be resumed if interrupted.
    """
    setup_logging(verbose)

    from factor_investor.ingest.sync import SyncService

    sync = SyncService()
    include_global = not nordic_only

    # Show current status first
    console.print("[bold]Current sync status:[/bold]")
    for sync_type in ["reports", "prices"]:
        status = sync.get_sync_status(sync_type)
        if status:
            console.print(f"  {sync_type}: {status}")
        else:
            console.print(f"  {sync_type}: not started")

    if reports:
        console.print("\n[bold]Syncing reports...[/bold]")
        console.print("(Progress logged every 50 instruments, Ctrl+C to pause)")
        try:
            results = sync.sync_reports_resumable(
                include_global=include_global,
                skip_completed=resume,
            )
            console.print(f"[green]Reports completed:[/green] {results}")
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted - progress saved, run again to resume[/yellow]")
            return

    if prices:
        console.print("\n[bold]Syncing prices...[/bold]")
        console.print("(Progress logged every 100 instruments, Ctrl+C to pause)")
        try:
            count = sync.sync_prices_resumable(
                include_global=include_global,
                skip_completed=resume,
            )
            console.print(f"[green]Prices completed:[/green] {count:,} records")
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted - progress saved, run again to resume[/yellow]")
            return

    console.print("\n[bold green]All sync operations completed![/bold green]")


@ingest_app.command("status")
def ingest_status() -> None:
    """Show ingestion status and data coverage."""
    from sqlalchemy import func, select

    from factor_investor.db import get_session
    from factor_investor.ingest.models import (
        Country,
        Instrument,
        Market,
        ReportQuarter,
        ReportYear,
        StockPrice,
        SyncLog,
    )

    with get_session() as session:
        # Counts
        table = Table(title="Database Status")
        table.add_column("Table", style="cyan")
        table.add_column("Count", justify="right")

        for model, name in [
            (Instrument, "Instruments"),
            (StockPrice, "Stock Prices"),
            (ReportYear, "Year Reports"),
            (ReportQuarter, "Quarter Reports"),
            (Country, "Countries"),
            (Market, "Markets"),
        ]:
            count = session.execute(select(func.count()).select_from(model)).scalar()
            table.add_row(name, f"{count:,}")

        console.print(table)

        # Recent syncs
        recent = session.execute(
            select(SyncLog).order_by(SyncLog.started_at.desc()).limit(5)
        ).scalars()

        sync_table = Table(title="Recent Syncs")
        sync_table.add_column("Type")
        sync_table.add_column("Started")
        sync_table.add_column("Status")
        sync_table.add_column("Records")

        for log in recent:
            sync_table.add_row(
                log.sync_type,
                log.started_at.strftime("%Y-%m-%d %H:%M"),
                log.status,
                f"{log.records_processed:,}",
            )

        console.print(sync_table)


# --- Build commands ---
@app.command("build-pit")
def build_pit(
    force_rebuild: bool = typer.Option(
        False,
        "--force",
        help="Clear existing data and rebuild from scratch",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Build point-in-time fundamentals table.

    Extracts base metrics from reports and calculates derived metrics (ROE, ROIC, margins, etc.).
    All metrics are stamped with known_from dates for lookahead-free analysis.
    """
    setup_logging(verbose)

    from factor_investor.pit import PITService

    console.print("[bold]Building point-in-time fundamentals table...[/bold]")

    if force_rebuild:
        console.print("[yellow]Force rebuild: clearing existing PIT data[/yellow]")

    pit_service = PITService()
    stats = pit_service.build_pit(force_rebuild=force_rebuild)

    # Display results in a table
    result_table = Table(title="PIT Build Results")
    result_table.add_column("Metric", style="cyan")
    result_table.add_column("Value", justify="right", style="green")

    result_table.add_row("Reports Processed", f"{stats.total_reports_processed:,}")
    result_table.add_row("Base Metrics Inserted", f"{stats.base_metrics_inserted:,}")
    result_table.add_row("Derived Metrics Inserted", f"{stats.derived_metrics_inserted:,}")
    result_table.add_row("Total Metrics", f"{stats.total_metrics_inserted:,}")
    result_table.add_row("", "")  # Separator
    result_table.add_row("Actual Publication Dates", f"{stats.actual_dates_used:,}")
    result_table.add_row("Fallback Dates", f"{stats.fallback_dates_used:,}")
    result_table.add_row("Fallback %", f"{stats.fallback_percentage:.1f}%")

    console.print(result_table)
    console.print("[bold green]✓ PIT build complete[/bold green]")


def _read_instrument_ids(path: str | None) -> list[int] | None:
    """Instrument ids from a file with one id per line (None if no file)."""
    if path is None:
        return None
    from pathlib import Path

    return [int(line) for line in Path(path).read_text().split() if line.strip()]


@app.command("build-returns")
def build_returns(
    force_rebuild: bool = typer.Option(False, "--force", help="Clear existing data and rebuild"),
    instruments_file: str = typer.Option(
        None, "--instruments-file", help="Rebuild only these instruments (one id per line)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Build total return series (price + reinvested dividends).

    Automatically extracts dividends from reports and estimates ex-dates.
    """
    setup_logging(verbose)

    from factor_investor.universe.dividend_service import DividendService

    console.print("[bold]Building total return series...[/bold]")
    console.print("[dim]Extracting dividends from reports with estimated ex-dates...[/dim]")

    if force_rebuild:
        console.print("[yellow]Force rebuild: clearing existing total returns[/yellow]")

    service = DividendService()
    stats = service.build_total_returns(
        instrument_ids=_read_instrument_ids(instruments_file), force_rebuild=force_rebuild
    )

    # Display results
    result_table = Table(title="Total Returns Build Results")
    result_table.add_column("Metric", style="cyan")
    result_table.add_column("Value", justify="right", style="green")

    result_table.add_row("Total Instruments", f"{stats.total_instruments:,}")
    result_table.add_row("Dividends Extracted", f"{stats.dividends_extracted:,}")
    result_table.add_row("TR Rows Calculated", f"{stats.total_returns_calculated:,}")
    result_table.add_row("With Dividends", f"{stats.instruments_with_dividends:,}")
    result_table.add_row("Skipped (errors)", f"{stats.instruments_skipped:,}")
    result_table.add_row(
        "Implausible Dividends Skipped",
        f"{stats.implausible_dividends:,} in {stats.instruments_with_implausible_dividends:,} "
        "instruments",
    )

    console.print(result_table)
    console.print("[bold green]✓ Total returns build complete[/bold green]")


@app.command("build-universe")
def build_universe(
    from_date: str = typer.Option(
        None, "--from-date", help="Start date (YYYY-MM-DD, default: 2006-01-01)"
    ),
    to_date: str = typer.Option(None, "--to-date", help="End date (YYYY-MM-DD, default: today)"),
    force_rebuild: bool = typer.Option(False, "--force", help="Clear existing data and rebuild"),
    instruments_file: str = typer.Option(
        None, "--instruments-file", help="Rebuild only these instruments (one id per line)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Build investable universe (monthly month-end snapshots)."""
    setup_logging(verbose)

    from datetime import date as date_type

    from factor_investor.universe.universe_service import UniverseService

    console.print("[bold]Building monthly universe...[/bold]")

    # Parse dates
    start_date = date_type.fromisoformat(from_date) if from_date else date_type(2006, 1, 1)
    end_date = date_type.fromisoformat(to_date) if to_date else date_type.today()

    console.print(f"Date range: {start_date} to {end_date}")

    if force_rebuild:
        console.print("[yellow]Force rebuild: clearing existing universe[/yellow]")

    service = UniverseService()
    stats = service.build_universe_monthly(
        from_date=start_date,
        to_date=end_date,
        force_rebuild=force_rebuild,
        instrument_ids=_read_instrument_ids(instruments_file),
    )

    # Display results
    result_table = Table(title="Universe Build Results")
    result_table.add_column("Metric", style="cyan")
    result_table.add_column("Value", justify="right", style="green")

    result_table.add_row("Dates Processed", f"{stats.total_dates:,}")
    result_table.add_row("Total Eligible", f"{stats.total_eligible:,}")
    result_table.add_row("Total Excluded", f"{stats.total_excluded:,}")

    console.print(result_table)

    # Show exclusion breakdown
    if stats.exclusion_breakdown:
        breakdown_table = Table(title="Exclusion Breakdown")
        breakdown_table.add_column("Reason", style="cyan")
        breakdown_table.add_column("Count", justify="right", style="yellow")

        for reason, count in sorted(
            stats.exclusion_breakdown.items(), key=lambda x: x[1], reverse=True
        ):
            breakdown_table.add_row(reason, f"{count:,}")

        console.print(breakdown_table)

    console.print("[bold green]✓ Universe build complete[/bold green]")


@app.command("build-base-metrics")
def build_base_metrics(
    from_date: str = typer.Option(
        None, "--from-date", help="Start date (YYYY-MM-DD, default: 2006-01-01)"
    ),
    to_date: str = typer.Option(None, "--to-date", help="End date (YYYY-MM-DD, default: today)"),
    force_rebuild: bool = typer.Option(False, "--force", help="Clear existing data and rebuild"),
    metrics: str = typer.Option(
        None,
        "--metrics",
        help="Comma-separated list of metrics to build (e.g., 'ev_ebitda,operating_cash_flow'). If not specified, builds all metrics.",
    ),
    instruments_file: str = typer.Option(
        None,
        "--instruments-file",
        help="Replace metrics only for these instruments (one id per line)",
    ),
    price_only: bool = typer.Option(
        False, "--price-only", help="Build only price metrics (fundamental metrics untouched)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Build fundamental and price base metrics (monthly snapshots).

    Examples:
        # Build all metrics for all dates
        build-base-metrics

        # Build only specific metrics (incremental)
        build-base-metrics --metrics ev_ebitda,operating_cash_flow

        # Backfill missing metrics for specific date range
        build-base-metrics --metrics operating_cash_flow --from-date 2016-01-01 --to-date 2019-04-30
    """
    setup_logging(verbose)

    from datetime import date as date_type

    from factor_investor.factors.service import FactorService

    console.print("[bold]Building base metrics...[/bold]")

    # Parse dates
    start_date = date_type.fromisoformat(from_date) if from_date else date_type(2006, 1, 1)
    end_date = date_type.fromisoformat(to_date) if to_date else date_type.today()

    # Parse metrics filter
    metrics_list = [m.strip() for m in metrics.split(",")] if metrics else None

    console.print(f"Date range: {start_date} to {end_date}")
    if metrics_list:
        console.print(f"[cyan]Building only: {', '.join(metrics_list)}[/cyan]")
    else:
        console.print("[cyan]Building all metrics[/cyan]")

    if force_rebuild:
        console.print("[yellow]Force rebuild: clearing existing base metrics[/yellow]")

    service = FactorService()
    stats = service.build_base_metrics(
        from_date=start_date,
        to_date=end_date,
        force_rebuild=force_rebuild,
        metrics=metrics_list,
        instrument_ids=_read_instrument_ids(instruments_file),
        price_only=price_only,
    )

    # Display results
    result_table = Table(title="Base Metrics Build Results")
    result_table.add_column("Metric", style="cyan")
    result_table.add_column("Value", justify="right", style="green")

    result_table.add_row("Dates Processed", f"{stats.dates_processed:,}")
    result_table.add_row("Fundamental Metrics", f"{stats.fundamental_metrics_inserted:,}")
    result_table.add_row("Price Metrics", f"{stats.price_metrics_inserted:,}")
    result_table.add_row(
        "Total Metrics", f"{stats.fundamental_metrics_inserted + stats.price_metrics_inserted:,}"
    )

    console.print(result_table)
    console.print("[bold green]✓ Base metrics build complete[/bold green]")


@app.command("detect-delistings")
def detect_delistings_cmd(
    lookback_days: int = typer.Option(
        90, "--lookback", help="Days without prices to consider delisted"
    ),
    output: str = typer.Option(
        None, "--output", "-o", help="Output file for detected events (CSV)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Detect potential delistings via heuristics."""
    setup_logging(verbose)

    from factor_investor.universe import events

    console.print(f"[bold]Detecting delistings (lookback={lookback_days} days)...[/bold]")

    detected_events = events.detect_delistings(lookback_days=lookback_days)

    console.print(f"Found {len(detected_events)} potential delisting events")

    if output and detected_events:
        import csv

        with Path(output).open("w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "instrument_id",
                    "event_date",
                    "event_type",
                    "detection_method",
                    "final_price",
                    "notes",
                ],
            )
            writer.writeheader()
            for event in detected_events:
                writer.writerow(
                    {
                        "instrument_id": event.instrument_id,
                        "event_date": event.event_date,
                        "event_type": event.event_type,
                        "detection_method": event.detection_method,
                        "final_price": event.final_price,
                        "notes": event.notes,
                    }
                )
        console.print(f"[green]Events written to {output}[/green]")

    console.print("[bold green]✓ Delisting detection complete[/bold green]")


@app.command("build-panel")
def build_panel(
    factors: list[str] = typer.Option(None, "--factor", "-f", help="Specific factors to build"),
) -> None:
    """Build factor panel (Parquet)."""
    typer.echo(f"Building factor panel (factors={factors})... [not implemented]")


# --- Backtest commands ---
@app.command("backtest")
def backtest(
    strategy: str = typer.Argument(..., help="Path to strategy YAML file"),
    output: str = typer.Option(None, "--output", "-o", help="Output directory for results"),
) -> None:
    """Run a single backtest."""
    typer.echo(f"Running backtest for {strategy} (output={output})... [not implemented]")


# --- Research commands ---
benchmarks_app = typer.Typer(help="Index-like benchmarks and random portfolios")
app.add_typer(benchmarks_app, name="benchmarks")


@benchmarks_app.command("run")
def benchmarks_run(
    areas: list[str] = typer.Option(..., "--area", help="SE, NO, FI, DK, US or EU (repeatable)"),
    weightings: list[str] = typer.Option(
        ["equal", "cap"], "--weighting", help="equal, cap (repeatable)"
    ),
    random_runs: int = typer.Option(0, "--random", help="Number of random_pick_v1 seeds (1..N)"),
    k: int = typer.Option(30, "--k", help="Names per random portfolio"),
    from_date: str = typer.Option("2006-10-01", "--from-date"),
    to_date: str = typer.Option(None, "--to-date", help="Default: today"),
    workers: int = typer.Option(1, "--workers", help="Processes (about 5 GB each)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Run benchmarks and save daily returns to data/benchmarks/."""
    setup_logging(verbose)
    from datetime import date as date_type

    from factor_investor.benchmarks.run import AREAS, BenchmarkRun, run_many

    unknown = [a for a in areas if a not in AREAS]
    if unknown:
        raise typer.BadParameter(f"Unknown area(s) {unknown}; choose from {sorted(AREAS)}")
    runs = [BenchmarkRun(a, w) for a in areas for w in weightings]
    runs += [
        BenchmarkRun(a, "random", k, seed) for a in areas for seed in range(1, random_runs + 1)
    ]
    end = date_type.fromisoformat(to_date) if to_date else date_type.today()
    paths = run_many(runs, date_type.fromisoformat(from_date), end, workers=workers)
    console.print(f"[green]{len(paths)} benchmark runs written to data/benchmarks/[/green]")


trials_app = typer.Typer(help="Trial registry: every research backtest")
app.add_typer(trials_app, name="trials")


@trials_app.command("list")
def trials_list(
    experiment: str = typer.Option(None, "--experiment", help="Only this experiment"),
    limit: int = typer.Option(30, "--limit", help="Most recent N trials"),
) -> None:
    """List logged trials, newest first."""
    from sqlalchemy import select

    from factor_investor.db import get_session
    from factor_investor.search.models import Trial

    query = select(Trial).order_by(Trial.id.desc()).limit(limit)
    if experiment:
        query = query.where(Trial.experiment == experiment)
    table = Table(title="Trials")
    for column in (
        "id",
        "hypothesis",
        "experiment",
        "strategy",
        "params",
        "status",
        "CAGR",
        "vs EW",
    ):
        table.add_column(column)
    with get_session() as session:
        for t in session.scalars(query):
            metrics = t.metrics or {}
            excess = (metrics.get("vs") or {}).get("equal_weight_v1", {}).get("excess_cagr")
            table.add_row(
                str(t.id),
                t.hypothesis_id,
                t.experiment,
                t.strategy_id,
                json.dumps(t.params, sort_keys=True),
                t.status + (" (gross)" if t.gross else ""),
                f"{metrics['cagr']:.2%}" if metrics.get("cagr") is not None else "",
                f"{excess:+.2%}" if excess is not None else "",
            )
    console.print(table)


@trials_app.command("counts")
def trials_counts(
    hypothesis: str = typer.Option(None, "--hypothesis", help="Only this hypothesis"),
) -> None:
    """Distinct configurations tried per hypothesis and experiment."""
    from factor_investor.db import get_session
    from factor_investor.search.registry import trial_counts

    with get_session() as session:
        counts = trial_counts(session, hypothesis)
    table = Table(title="Trial counts")
    for column in counts.columns:
        table.add_column(column)
    for row in counts.iter_rows():
        table.add_row(*(str(v) for v in row))
    console.print(table)


@trials_app.command("validate")
def trials_validate(
    experiment: str = typer.Option(..., "--experiment", help="Experiment to validate"),
    blocks: int = typer.Option(8, "--blocks", help="Even number of time blocks for CSCV"),
    purge: int = typer.Option(1, "--purge", help="Months purged next to in-sample blocks"),
    total: bool = typer.Option(
        False, "--total", help="Use total returns instead of excess over equal_weight_v1"
    ),
) -> None:
    """CSCV/PBO, deflated Sharpe and block stability from logged trials."""
    from factor_investor.db import get_session
    from factor_investor.validation.experiment import VALIDATION_DIR, validate_experiment

    with get_session() as session:
        report = validate_experiment(
            session, experiment, n_blocks=blocks, purge=purge, relative=not total
        )
    c, d = report["cscv"], report["deflated_sharpe"]
    first, last, months = report["months"]
    console.print(
        f"[bold]{experiment}[/bold]: {report['configurations']} configurations, "
        f"{months} months {first[:7]}..{last[:7]}, {blocks} blocks, purge {purge}, "
        f"{report['returns']}"
    )
    console.print(
        f"PBO {c['pbo']:.0%} over {c['combinations']} splits; "
        f"IS winner loses money OOS in {c['prob_oos_loss']:.0%}; "
        f"OOS Sharpe of IS winner {c['oos_sharpe_is_best_mean'] * 12**0.5:.2f} vs "
        f"median configuration {c['oos_sharpe_median_config_mean'] * 12**0.5:.2f} (annualized)"
    )
    console.print(
        f"Deflated Sharpe of the best configuration (trial {d['trial_id']}, Sharpe "
        f"{d['sharpe_annualized']:.2f}, {report['trials_for_hypothesis']} trials): "
        f"{d['dsr']:.0%}"
    )
    table = Table(title="Excess return over equal_weight_v1 per block")
    table.add_column("trial")
    table.add_column("params", no_wrap=True)
    for start, end in report["blocks"]:
        table.add_column(f"{start[2:4]}-{end[2:4]}", justify="right")
    table.add_column("beat", justify="right")
    for row in report["block_stability"]:
        p = row["params"]
        label = " ".join(
            str(p[k]) for k in ("factor", "top_n", "rebalance", "min_turnover") if k in p
        )
        table.add_row(
            str(row["trial_id"]),
            label or json.dumps(p),
            *(f"{x:+.0%}" for x in row["excess_by_block"]),
            f"{row['share_of_blocks_beaten']:.0%}",
        )
    console.print(table)
    console.print(f"Report: {VALIDATION_DIR / (experiment + '.json')}")


research_app = typer.Typer(help="Research and analysis tools")
app.add_typer(research_app, name="research")


@research_app.command("talent")
def research_talent(
    condition: str = typer.Argument(..., help="Path to selection condition YAML"),
    output: str = typer.Option("reports/", "--output", "-o", help="Output directory"),
) -> None:
    """Run talent study for a selection condition."""
    typer.echo(f"Running talent study for {condition} (output={output})... [not implemented]")


@research_app.command("factor")
def research_factor(
    factor: str = typer.Argument(..., help="Factor ID to analyze"),
) -> None:
    """Analyze a single factor (IC, quintiles, turnover)."""
    typer.echo(f"Analyzing factor {factor}... [not implemented]")


# --- Search commands ---
search_app = typer.Typer(help="Hypothesis search and optimization")
app.add_typer(search_app, name="search")


@search_app.command("run")
def search_run(
    hypothesis: str = typer.Argument(..., help="Path to hypothesis YAML"),
    stage: int = typer.Option(1, "--stage", "-s", help="Search stage (1-5)"),
    n_trials: int = typer.Option(100, "--trials", "-n", help="Number of trials"),
) -> None:
    """Run parameter search for a hypothesis."""
    typer.echo(f"Searching {hypothesis} stage {stage} ({n_trials} trials)... [not implemented]")


@search_app.command("status")
def search_status() -> None:
    """Show search progress and trial registry."""
    typer.echo("Search status... [not implemented]")


# --- Validation commands ---
validate_app = typer.Typer(help="Validation and robustness testing")
app.add_typer(validate_app, name="validate")


@validate_app.command("walkforward")
def validate_walkforward(
    strategy: str = typer.Argument(..., help="Path to strategy YAML"),
) -> None:
    """Run walk-forward validation."""
    typer.echo(f"Walk-forward for {strategy}... [not implemented]")


@validate_app.command("robustness")
def validate_robustness(
    strategy: str = typer.Argument(..., help="Path to strategy YAML"),
) -> None:
    """Run robustness battery."""
    typer.echo(f"Robustness tests for {strategy}... [not implemented]")


# --- Report commands ---
@app.command("report")
def report(
    strategy: str = typer.Argument(..., help="Path to strategy or backtest result"),
    output: str = typer.Option("reports/", "--output", "-o", help="Output directory"),
) -> None:
    """Generate HTML report for a strategy."""
    typer.echo(f"Generating report for {strategy} (output={output})... [not implemented]")


if __name__ == "__main__":
    app()

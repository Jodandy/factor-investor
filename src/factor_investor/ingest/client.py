"""Börsdata API client with rate limiting, retry, and caching."""

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# API Configuration
BASE_URL = "https://apiservice.borsdata.se"
RATE_LIMIT_CALLS = 100
RATE_LIMIT_WINDOW = 10.0  # seconds


class RateLimiter:
    """Simple sliding window rate limiter."""

    def __init__(self, max_calls: int = RATE_LIMIT_CALLS, window: float = RATE_LIMIT_WINDOW):
        self.max_calls = max_calls
        self.window = window
        self.calls: list[float] = []

    def wait_if_needed(self) -> None:
        """Block until a call can be made within rate limits."""
        now = time.monotonic()
        # Remove calls outside the window
        self.calls = [t for t in self.calls if now - t < self.window]

        if len(self.calls) >= self.max_calls:
            # Wait until the oldest call exits the window
            sleep_time = self.window - (now - self.calls[0]) + 0.1
            if sleep_time > 0:
                time.sleep(sleep_time)
            self.calls = self.calls[1:]

        self.calls.append(time.monotonic())


class BorsdataClient:
    """Börsdata API client with rate limiting, retry, and optional caching."""

    def __init__(
        self,
        api_key: str,
        cache_dir: Path | None = None,
        use_cache: bool = True,
    ):
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.use_cache = use_cache and cache_dir is not None
        self.rate_limiter = RateLimiter()
        self._client = httpx.Client(timeout=30.0)

        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "BorsdataClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _cache_key(self, endpoint: str, params: dict[str, Any]) -> str:
        """Generate a cache key for the request."""
        # Exclude authKey from cache key
        cache_params = {k: v for k, v in sorted(params.items()) if k != "authKey"}
        key_str = f"{endpoint}:{json.dumps(cache_params, sort_keys=True)}"
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]

    def _get_cached(self, cache_key: str) -> dict[str, Any] | None:
        """Get cached response if available."""
        if not self.use_cache or not self.cache_dir:
            return None

        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            with cache_file.open() as f:
                return json.load(f)  # type: ignore[no-any-return]
        return None

    def _save_cache(self, cache_key: str, data: dict[str, Any]) -> None:
        """Save response to cache."""
        if not self.use_cache or not self.cache_dir:
            return

        cache_file = self.cache_dir / f"{cache_key}.json"
        with cache_file.open("w") as f:
            json.dump(data, f)

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def _request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        """Make an API request with rate limiting, retry, and caching."""
        params = params or {}
        params["authKey"] = self.api_key

        # Check cache first
        if not skip_cache:
            cache_key = self._cache_key(endpoint, params)
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

        # Rate limit
        self.rate_limiter.wait_if_needed()

        # Make request
        url = f"{BASE_URL}{endpoint}"
        response = self._client.get(url, params=params)

        # Handle rate limiting
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "10"))
            time.sleep(retry_after)
            return self._request(endpoint, params, skip_cache=True)

        response.raise_for_status()
        data: dict[str, Any] = response.json()

        # Cache the response
        if not skip_cache:
            self._save_cache(cache_key, data)

        return data

    # --- Metadata endpoints ---

    def get_countries(self) -> dict[str, Any]:
        """Get all countries."""
        return self._request("/v1/countries")

    def get_markets(self) -> dict[str, Any]:
        """Get all markets."""
        return self._request("/v1/markets")

    def get_sectors(self) -> dict[str, Any]:
        """Get all sectors."""
        return self._request("/v1/sectors")

    def get_branches(self) -> dict[str, Any]:
        """Get all branches (industries)."""
        return self._request("/v1/branches")

    def get_translation_metadata(self) -> dict[str, Any]:
        """Get translations for metadata."""
        return self._request("/v1/translationmetadata")

    # --- Instrument endpoints ---

    def get_instruments(self, include_global: bool = True) -> dict[str, Any]:
        """Get all instruments (Nordic + optionally Global)."""
        nordic = self._request("/v1/instruments")

        if include_global:
            try:
                global_inst = self._request("/v1/instruments/global")
                # Merge instruments lists
                if "instruments" in nordic and "instruments" in global_inst:
                    nordic["instruments"].extend(global_inst["instruments"])
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 418:
                    # No global access - that's fine for Nordic-only keys
                    pass
                else:
                    raise

        return nordic

    def get_instrument_updated(self) -> dict[str, Any]:
        """Get last update timestamps for instruments."""
        return self._request("/v1/instruments/updated")

    # --- Stock price endpoints ---

    def get_stock_prices(
        self,
        instrument_id: int,
        from_date: str | None = None,
        to_date: str | None = None,
        max_count: int | None = None,
    ) -> dict[str, Any]:
        """Get stock prices for a single instrument."""
        params: dict[str, Any] = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        if max_count:
            params["maxCount"] = max_count

        return self._request(f"/v1/instruments/{instrument_id}/stockprices", params)

    def get_stock_prices_last(self, include_global: bool = True) -> dict[str, Any]:
        """Get latest stock prices for all instruments."""
        nordic = self._request("/v1/instruments/stockprices/last")

        if include_global:
            try:
                global_prices = self._request("/v1/instruments/stockprices/global/last")
                if "stockPricesList" in nordic and "stockPricesList" in global_prices:
                    nordic["stockPricesList"].extend(global_prices["stockPricesList"])
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 418:
                    raise

        return nordic

    def get_stock_prices_date(self, date: str, include_global: bool = True) -> dict[str, Any]:
        """Get stock prices for all instruments on a specific date."""
        nordic = self._request("/v1/instruments/stockprices/date", {"date": date})

        if include_global:
            try:
                global_prices = self._request(
                    "/v1/instruments/stockprices/global/date", {"date": date}
                )
                if "stockPricesList" in nordic and "stockPricesList" in global_prices:
                    nordic["stockPricesList"].extend(global_prices["stockPricesList"])
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 418:
                    raise

        return nordic

    # --- Report endpoints ---

    def get_reports(
        self,
        instrument_id: int,
        max_year_count: int | None = None,
        max_r12q_count: int | None = None,
        original: bool = False,
    ) -> dict[str, Any]:
        """Get all reports for a single instrument."""
        params: dict[str, Any] = {}
        if max_year_count:
            params["maxYearCount"] = max_year_count
        if max_r12q_count:
            params["maxR12QCount"] = max_r12q_count
        if original:
            params["original"] = 1

        return self._request(f"/v1/instruments/{instrument_id}/reports", params)

    def get_reports_metadata(self) -> dict[str, Any]:
        """Get report field metadata."""
        return self._request("/v1/instruments/reports/metadata")

    # --- KPI endpoints ---

    def get_kpi_metadata(self) -> dict[str, Any]:
        """Get KPI metadata (definitions)."""
        return self._request("/v1/instruments/kpis/metadata")

    def get_kpi_history(
        self,
        instrument_id: int,
        kpi_id: int,
        report_type: str = "year",
        price_type: str = "mean",
        max_count: int | None = None,
    ) -> dict[str, Any]:
        """Get KPI history for a single instrument."""
        params: dict[str, Any] = {}
        if max_count:
            params["maxCount"] = max_count

        endpoint = (
            f"/v1/instruments/{instrument_id}/kpis/{kpi_id}/{report_type}/{price_type}/history"
        )
        return self._request(endpoint, params)

    # --- Dividend and split endpoints ---

    def get_stock_splits(self, from_date: str | None = None) -> dict[str, Any]:
        """Get stock splits (max 1 year of data)."""
        params: dict[str, Any] = {}
        if from_date:
            params["from"] = from_date
        return self._request("/v1/instruments/StockSplits", params)

    def get_dividend_calendar(self, instrument_ids: list[int]) -> dict[str, Any]:
        """Get dividend calendar for instruments (max 50)."""
        if len(instrument_ids) > 50:
            raise ValueError("Maximum 50 instruments per request")
        inst_list = ",".join(str(i) for i in instrument_ids)
        return self._request("/v1/instruments/dividend/calendar", {"instList": inst_list})

    def get_report_calendar(self, instrument_ids: list[int]) -> dict[str, Any]:
        """Get report calendar for instruments (max 50)."""
        if len(instrument_ids) > 50:
            raise ValueError("Maximum 50 instruments per request")
        inst_list = ",".join(str(i) for i in instrument_ids)
        return self._request("/v1/instruments/report/calendar", {"instList": inst_list})


def create_client_from_env(cache_dir: Path | None = None) -> BorsdataClient:
    """Create a client using the API key from environment."""
    import os

    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.getenv("BORSDATA_API_KEY")
    if not api_key:
        raise ValueError("BORSDATA_API_KEY environment variable not set")

    if cache_dir is None:
        cache_dir = Path("data/cache/api")

    return BorsdataClient(api_key, cache_dir=cache_dir)

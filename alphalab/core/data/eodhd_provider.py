"""EOD Historical Data provider implementation."""

from __future__ import annotations

import os
import time
from typing import Any

import pandas as pd
import requests

from alphalab.core.data.base import DataProvider
from alphalab.core.utils.errors import DataFetchError, DataValidationError

OHLCV_COLUMNS: tuple[str, str, str, str, str] = ("open", "high", "low", "close", "volume")
REQUIRED_COLUMNS: tuple[str, str, str, str, str] = ("date", "open", "high", "low", "close")
RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


def _empty_ohlcv_frame() -> pd.DataFrame:
    """Create an empty OHLCV dataframe with a UTC datetime index."""
    empty_index = pd.DatetimeIndex([], tz="UTC", name="date")
    return pd.DataFrame(columns=list(OHLCV_COLUMNS), index=empty_index, dtype=float)


class EODHDProvider(DataProvider):
    """REST client for EOD Historical Data."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://eodhd.com/api",
        session: requests.Session | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        """
        Initialize an EODHD provider.

        Args:
            api_key: API token. If omitted, reads from ``EODHD_API_KEY``.
            base_url: Base URL for the EODHD REST API.
            session: Optional requests session for dependency injection.
            timeout_seconds: Request timeout in seconds.
            max_retries: Number of retry attempts for transient failures.
            retry_backoff_seconds: Base seconds for exponential retry backoff.

        Raises:
            ValueError: If no API key is provided.
        """
        resolved_api_key = api_key or os.getenv("EODHD_API_KEY")
        if not resolved_api_key:
            raise ValueError(
                "EODHD API key is required. Set EODHD_API_KEY or pass api_key explicitly."
            )

        self._api_key = resolved_api_key
        self._base_url = base_url.rstrip("/")
        self._session = session or requests.Session()
        self._timeout_seconds = timeout_seconds
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0.")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be >= 0.")
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds

    def _sleep_before_retry(self, attempt: int) -> None:
        """Sleep deterministic exponential backoff before retry attempt."""
        if self._retry_backoff_seconds == 0:
            return
        delay_seconds = self._retry_backoff_seconds * (2**attempt)
        time.sleep(delay_seconds)

    def _request_payload(self, endpoint: str, params: dict[str, str], symbol: str) -> Any:
        """Request raw payload with deterministic retry/backoff behavior."""
        last_exception: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.get(endpoint, params=params, timeout=self._timeout_seconds)
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                    self._sleep_before_retry(attempt)
                    continue

                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as exc:
                last_exception = exc
                if attempt >= self._max_retries:
                    break
                self._sleep_before_retry(attempt)
            except ValueError as exc:
                raise DataValidationError(f"Invalid JSON response for symbol '{symbol}'.") from exc

        raise DataFetchError(f"Failed to fetch data for symbol '{symbol}': {last_exception}")

    def _validate_and_normalize_payload(self, payload: Any, symbol: str) -> pd.DataFrame:
        """Validate vendor payload schema and normalize to OHLCV format."""
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("error") or str(payload)
            raise DataValidationError(f"EODHD error for symbol '{symbol}': {message}")

        if not isinstance(payload, list):
            raise DataValidationError(f"Unexpected EODHD response type for symbol '{symbol}'.")

        if not payload:
            return _empty_ohlcv_frame()

        frame = pd.DataFrame(payload)
        missing_required = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
        if missing_required:
            raise DataValidationError(
                f"EODHD payload is missing required columns for symbol '{symbol}': "
                f"{missing_required}"
            )

        frame = frame.copy()
        frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")

        for column in OHLCV_COLUMNS:
            if column not in frame.columns:
                frame[column] = pd.NA
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

        normalized = frame.loc[:, ["date", *OHLCV_COLUMNS]].dropna(
            subset=["date", "open", "high", "low", "close"]
        )
        normalized["volume"] = normalized["volume"].fillna(0.0)

        ohlc_integrity_mask = (
            (normalized["high"] >= normalized["low"])
            & (normalized["high"] >= normalized["open"])
            & (normalized["high"] >= normalized["close"])
            & (normalized["low"] <= normalized["open"])
            & (normalized["low"] <= normalized["close"])
            & (normalized["volume"] >= 0.0)
        )
        normalized = normalized.loc[ohlc_integrity_mask]
        if normalized.empty:
            raise DataValidationError(
                f"EODHD payload failed OHLCV integrity checks for symbol '{symbol}'."
            )

        result = normalized.set_index("date")
        result.index.name = "date"
        result = result.sort_index()
        result = result[~result.index.duplicated(keep="last")]
        result = result.loc[:, list(OHLCV_COLUMNS)].astype(float)

        if result.empty:
            return _empty_ohlcv_frame()
        return result

    def fetch_ohlcv(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """
        Fetch daily OHLCV data for a symbol from EODHD.

        Args:
            symbol: Provider symbol identifier.
            start: Inclusive start date in ``YYYY-MM-DD`` format.
            end: Inclusive end date in ``YYYY-MM-DD`` format.

        Returns:
            Normalized OHLCV dataframe with UTC datetime index.
        """
        endpoint = f"{self._base_url}/eod/{symbol}"
        params = {
            "api_token": self._api_key,
            "from": start,
            "to": end,
            "period": "d",
            "order": "a",
            "fmt": "json",
        }
        payload = self._request_payload(endpoint=endpoint, params=params, symbol=symbol)
        return self._validate_and_normalize_payload(payload=payload, symbol=symbol)

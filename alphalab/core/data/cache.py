"""Parquet caching for OHLCV market data."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from alphalab.core.utils.errors import CacheError

OHLCV_COLUMNS: tuple[str, str, str, str, str] = ("open", "high", "low", "close", "volume")
_SYMBOL_SANITIZE_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


def _empty_ohlcv_frame() -> pd.DataFrame:
    """Create an empty OHLCV dataframe with a UTC datetime index."""
    empty_index = pd.DatetimeIndex([], tz="UTC", name="date")
    return pd.DataFrame(columns=list(OHLCV_COLUMNS), index=empty_index, dtype=float)


def _to_utc_timestamp(date_str: str) -> pd.Timestamp:
    """Convert a date string to a UTC timestamp at midnight."""
    timestamp = pd.to_datetime(date_str, utc=True, errors="raise")
    if isinstance(timestamp, pd.DatetimeIndex):
        if timestamp.empty:
            raise ValueError("Date conversion failed for empty date input.")
        return timestamp[0]
    return timestamp


def _sanitize_symbol(symbol: str) -> str:
    """Sanitize symbol names so they are safe as filenames."""
    clean_symbol = _SYMBOL_SANITIZE_PATTERN.sub("_", symbol.strip())
    if not clean_symbol:
        raise ValueError("Symbol cannot be empty.")
    return clean_symbol


def _normalize_ohlcv_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize data to UTC-indexed OHLCV format."""
    if frame.empty:
        return _empty_ohlcv_frame()

    normalized = frame.copy()

    if "date" in normalized.columns:
        normalized["date"] = pd.to_datetime(normalized["date"], utc=True, errors="coerce")
        normalized = normalized.set_index("date")
    elif not isinstance(normalized.index, pd.DatetimeIndex):
        raise ValueError("OHLCV dataframe must have a DatetimeIndex or a 'date' column.")
    else:
        normalized.index = pd.to_datetime(normalized.index, utc=True, errors="coerce")

    normalized = normalized.loc[~normalized.index.isna()]
    normalized.index.name = "date"

    for column in OHLCV_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = pd.NA
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized = normalized.dropna(subset=["open", "high", "low", "close"])
    normalized["volume"] = normalized["volume"].fillna(0.0)
    normalized = normalized.loc[:, list(OHLCV_COLUMNS)].astype(float)
    normalized = normalized.sort_index()
    normalized = normalized.loc[~normalized.index.duplicated(keep="last")]

    if normalized.empty:
        return _empty_ohlcv_frame()
    return normalized


class ParquetCache:
    """Handle local Parquet caching for OHLCV data."""

    def __init__(self, cache_dir: Path) -> None:
        """
        Initialize a cache manager.

        Args:
            cache_dir: Directory where per-symbol parquet files are stored.
        """
        self.cache_dir = cache_dir.expanduser().resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def cache_path(self, symbol: str) -> Path:
        """
        Build the cache file path for a symbol.

        Args:
            symbol: Provider symbol identifier.

        Returns:
            Symbol parquet file path.
        """
        return self.cache_dir / f"{_sanitize_symbol(symbol)}.parquet"

    def load(self, symbol: str) -> pd.DataFrame | None:
        """
        Load cached data for a symbol.

        Args:
            symbol: Provider symbol identifier.

        Returns:
            Normalized dataframe if cache exists, else ``None``.
        """
        path = self.cache_path(symbol)
        if not path.exists():
            return None

        try:
            cached = pd.read_parquet(path, engine="pyarrow")
        except Exception as exc:
            raise CacheError(
                f"Failed to read cache for symbol '{symbol}' at {path}: {exc}"
            ) from exc
        return _normalize_ohlcv_frame(cached)

    def save(self, symbol: str, frame: pd.DataFrame) -> None:
        """
        Save normalized symbol data to cache.

        Args:
            symbol: Provider symbol identifier.
            frame: OHLCV dataframe to persist.
        """
        normalized = _normalize_ohlcv_frame(frame)
        path = self.cache_path(symbol)
        try:
            normalized.to_parquet(path, engine="pyarrow", index=True)
        except Exception as exc:
            raise CacheError(
                f"Failed to write cache for symbol '{symbol}' at {path}: {exc}"
            ) from exc

    def get_ohlcv(
        self,
        symbol: str,
        start: str,
        end: str,
        fetcher: Callable[[str, str, str], pd.DataFrame],
    ) -> pd.DataFrame:
        """
        Load OHLCV data from cache or provider, and return the requested range.

        If cache coverage is incomplete, only missing ranges are fetched.

        Args:
            symbol: Provider symbol identifier.
            start: Inclusive start date in ``YYYY-MM-DD`` format.
            end: Inclusive end date in ``YYYY-MM-DD`` format.
            fetcher: Function that fetches OHLCV data for a range.

        Returns:
            OHLCV dataframe for the requested range.
        """
        start_ts = _to_utc_timestamp(start)
        end_ts = _to_utc_timestamp(end)
        if start_ts > end_ts:
            raise ValueError("Start date must be before or equal to end date.")

        cached = self.load(symbol)
        fetched_new_data = False
        merged_frame: pd.DataFrame

        if cached is None or cached.empty:
            merged_frame = _normalize_ohlcv_frame(
                fetcher(symbol, start_ts.strftime("%Y-%m-%d"), end_ts.strftime("%Y-%m-%d"))
            )
            fetched_new_data = True
        else:
            frames: list[pd.DataFrame] = [cached]
            cache_start = cached.index.min()
            cache_end = cached.index.max()

            if start_ts < cache_start:
                head_end = cache_start - pd.Timedelta(days=1)
                fetched_head = _normalize_ohlcv_frame(
                    fetcher(
                        symbol,
                        start_ts.strftime("%Y-%m-%d"),
                        head_end.strftime("%Y-%m-%d"),
                    )
                )
                if not fetched_head.empty:
                    frames.append(fetched_head)
                fetched_new_data = True

            if end_ts > cache_end:
                tail_start = cache_end + pd.Timedelta(days=1)
                fetched_tail = _normalize_ohlcv_frame(
                    fetcher(
                        symbol,
                        tail_start.strftime("%Y-%m-%d"),
                        end_ts.strftime("%Y-%m-%d"),
                    )
                )
                if not fetched_tail.empty:
                    frames.append(fetched_tail)
                fetched_new_data = True

            merged_frame = _normalize_ohlcv_frame(pd.concat(frames))

        if fetched_new_data:
            self.save(symbol, merged_frame)

        in_range = merged_frame.loc[
            (merged_frame.index >= start_ts) & (merged_frame.index <= end_ts)
        ]
        if in_range.empty:
            return _empty_ohlcv_frame()
        return in_range

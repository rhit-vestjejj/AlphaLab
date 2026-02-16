"""Integration tests for cache coverage and fetch behavior."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from alphalab.core.data.cache import ParquetCache
from alphalab.tests.helpers import make_price_frame


def _slice_frame(frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Slice a frame between inclusive UTC date strings."""
    start_ts = pd.to_datetime(start, utc=True)
    end_ts = pd.to_datetime(end, utc=True)
    return frame.loc[(frame.index >= start_ts) & (frame.index <= end_ts)].copy()


class TestCacheIntegration(unittest.TestCase):
    """Validate cache coverage logic for symbol data."""

    def test_uses_cache_without_refetch_when_range_covered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ParquetCache(Path(temp_dir))
            frame = make_price_frame([100.0, 101.0, 102.0, 103.0, 104.0])
            cache.save("ES", frame)

            fetch_calls: list[tuple[str, str, str]] = []

            def fetcher(symbol: str, start: str, end: str) -> pd.DataFrame:
                fetch_calls.append((symbol, start, end))
                return frame

            result = cache.get_ohlcv("ES", "2020-01-02", "2020-01-04", fetcher)
            self.assertEqual(fetch_calls, [])
            self.assertEqual(result.shape, (3, 5))

    def test_fetches_missing_tail_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ParquetCache(Path(temp_dir))
            full_frame = make_price_frame([100.0, 101.0, 102.0, 103.0, 104.0])
            cached_frame = _slice_frame(full_frame, "2020-01-01", "2020-01-03")
            cache.save("ES", cached_frame)

            fetch_calls: list[tuple[str, str, str]] = []

            def fetcher(symbol: str, start: str, end: str) -> pd.DataFrame:
                fetch_calls.append((symbol, start, end))
                return _slice_frame(full_frame, start, end)

            result = cache.get_ohlcv("ES", "2020-01-01", "2020-01-05", fetcher)
            self.assertEqual(fetch_calls, [("ES", "2020-01-04", "2020-01-05")])
            self.assertEqual(result.shape, (5, 5))


if __name__ == "__main__":
    unittest.main()

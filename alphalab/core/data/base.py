"""Abstract interfaces for market data providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class DataProvider(ABC):
    """Abstract interface for OHLCV data providers."""

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """
        Fetch daily OHLCV data for a symbol over an inclusive date range.

        Args:
            symbol: Provider symbol identifier.
            start: Inclusive start date in ``YYYY-MM-DD`` format.
            end: Inclusive end date in ``YYYY-MM-DD`` format.

        Returns:
            A dataframe with UTC datetime index named ``date`` and columns:
            ``open``, ``high``, ``low``, ``close``, ``volume``.
        """

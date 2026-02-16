"""Unit tests for EODHD provider hardening behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

from alphalab.core.data.eodhd_provider import EODHDProvider


class _FakeResponse:
    """Minimal response stub for provider tests."""

    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        """Raise HTTPError for status >= 400."""
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> object:
        """Return configured payload."""
        return self._payload


class _FakeSession:
    """Scripted session stub for deterministic responses."""

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = outcomes
        self.calls = 0

    def get(self, url: str, params: dict[str, str], timeout: float) -> _FakeResponse:
        """Return next scripted response or raise scripted exception."""
        _ = (url, params, timeout)
        self.calls += 1
        if not self._outcomes:
            raise RuntimeError("No scripted outcomes left.")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, _FakeResponse)
        return outcome


class TestEODHDProvider(unittest.TestCase):
    """Validate retry logic and schema checks."""

    def test_retries_transient_http_then_succeeds(self) -> None:
        session = _FakeSession(
            [
                _FakeResponse(503, {"message": "busy"}),
                _FakeResponse(
                    200,
                    [
                        {
                            "date": "2020-01-01",
                            "open": 100,
                            "high": 101,
                            "low": 99,
                            "close": 100,
                            "volume": 10,
                        }
                    ],
                ),
            ]
        )
        provider = EODHDProvider(
            api_key="key",
            session=session,
            max_retries=2,
            retry_backoff_seconds=0.01,
        )

        with patch("alphalab.core.data.eodhd_provider.time.sleep") as sleep_mock:
            frame = provider.fetch_ohlcv("ES", "2020-01-01", "2020-01-01")

        self.assertEqual(session.calls, 2)
        self.assertEqual(sleep_mock.call_count, 1)
        self.assertEqual(frame.shape, (1, 5))

    def test_missing_required_columns_raises(self) -> None:
        session = _FakeSession(
            [
                _FakeResponse(
                    200,
                    [
                        {
                            "date": "2020-01-01",
                            "high": 101,
                            "low": 99,
                            "close": 100,
                            "volume": 10,
                        }
                    ],
                )
            ]
        )
        provider = EODHDProvider(api_key="key", session=session, max_retries=0)
        with self.assertRaises(ValueError):
            provider.fetch_ohlcv("ES", "2020-01-01", "2020-01-01")

    def test_invalid_ohlc_rows_raise(self) -> None:
        session = _FakeSession(
            [
                _FakeResponse(
                    200,
                    [
                        {
                            "date": "2020-01-01",
                            "open": 100,
                            "high": 99,
                            "low": 98,
                            "close": 100,
                            "volume": 10,
                        }
                    ],
                )
            ]
        )
        provider = EODHDProvider(api_key="key", session=session, max_retries=0)
        with self.assertRaises(ValueError):
            provider.fetch_ohlcv("ES", "2020-01-01", "2020-01-01")


if __name__ == "__main__":
    unittest.main()

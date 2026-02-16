"""Unit tests for API entrypoint port resolution."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from alphalab.api.main import _resolve_port


class TestApiMain(unittest.TestCase):
    """Validate deterministic fallback behavior for occupied ports."""

    def test_resolve_port_uses_requested_when_available(self) -> None:
        with patch("alphalab.api.main._is_port_available", return_value=True):
            resolved = _resolve_port("127.0.0.1", 8010, max_attempts=5)
        self.assertEqual(resolved, 8010)

    def test_resolve_port_scans_forward(self) -> None:
        with patch(
            "alphalab.api.main._is_port_available",
            side_effect=[False, False, True],
        ):
            resolved = _resolve_port("127.0.0.1", 8010, max_attempts=5)
        self.assertEqual(resolved, 8012)

    def test_resolve_port_raises_when_no_candidate(self) -> None:
        with patch("alphalab.api.main._is_port_available", return_value=False):
            with self.assertRaises(RuntimeError):
                _resolve_port("127.0.0.1", 8010, max_attempts=2)


if __name__ == "__main__":
    unittest.main()

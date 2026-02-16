"""Environment variable helpers."""

from __future__ import annotations

import os
from pathlib import Path


def _strip_wrapping_quotes(value: str) -> str:
    """Remove matching single or double wrapping quotes from a value."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_dotenv(path: Path = Path(".env"), override: bool = False) -> dict[str, str]:
    """
    Load environment variables from a ``.env`` file.

    The parser supports blank lines, comment lines, and optional ``export`` prefixes.

    Args:
        path: Dotenv file path.
        override: Whether loaded values should overwrite existing environment variables.

    Returns:
        Mapping of environment variables that were set in this call.
    """
    resolved_path = path.expanduser().resolve()
    if not resolved_path.exists():
        return {}
    if not resolved_path.is_file():
        raise ValueError(f"Dotenv path is not a file: {resolved_path}")

    loaded: dict[str, str] = {}
    with resolved_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                raise ValueError(f"Invalid dotenv line at {resolved_path}:{line_number}")

            key, raw_value = line.split("=", 1)
            key = key.strip()
            value = _strip_wrapping_quotes(raw_value.strip())
            if not key:
                raise ValueError(f"Invalid dotenv key at {resolved_path}:{line_number}")

            if not override and key in os.environ:
                continue
            os.environ[key] = value
            loaded[key] = value

    return loaded

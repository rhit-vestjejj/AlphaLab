"""Executable entrypoint for AlphaLab FastAPI server."""

from __future__ import annotations

import argparse
import os
import socket


def _default_port() -> int:
    """Return API port from env with deterministic fallback."""
    raw_value = os.getenv("ALPHALAB_API_PORT", "8020")
    try:
        port = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"Invalid ALPHALAB_API_PORT value: {raw_value}") from exc
    if port < 1 or port > 65535:
        raise ValueError("ALPHALAB_API_PORT must be between 1 and 65535.")
    return port


def _parse_args() -> argparse.Namespace:
    """Parse CLI args for API server runtime settings."""
    parser = argparse.ArgumentParser(description="Run AlphaLab API server.")
    parser.add_argument(
        "--host",
        default=os.getenv("ALPHALAB_API_HOST", "127.0.0.1"),
        help="Bind host (default: 127.0.0.1 or ALPHALAB_API_HOST).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_default_port(),
        help="Bind port (default: 8020 or ALPHALAB_API_PORT).",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("ALPHALAB_API_LOG_LEVEL", "info"),
        help="Uvicorn log level (default: info or ALPHALAB_API_LOG_LEVEL).",
    )
    args = parser.parse_args()
    if args.port < 1 or args.port > 65535:
        parser.error("--port must be between 1 and 65535.")
    return args


def _is_port_available(host: str, port: int) -> bool:
    """Return True if a host/port can be bound by this process."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _resolve_port(host: str, requested_port: int, max_attempts: int = 50) -> int:
    """Resolve a free port by scanning forward from the requested port."""
    max_candidate = min(65535, requested_port + max_attempts - 1)
    for offset in range(max_attempts):
        candidate = requested_port + offset
        if candidate > 65535:
            break
        if _is_port_available(host, candidate):
            return candidate
    raise RuntimeError(f"No available port found from {requested_port} to {max_candidate}.")


def main() -> None:
    """Run AlphaLab API server with configurable host/port/log level."""
    import uvicorn

    args = _parse_args()
    resolved_port = _resolve_port(args.host, args.port)
    if resolved_port != args.port:
        print(
            (
                f"Requested port {args.port} is in use, "
                f"starting AlphaLab API on {resolved_port} instead."
            ),
            flush=True,
        )
    uvicorn.run(
        "alphalab.api.app:create_app",
        factory=True,
        host=args.host,
        port=resolved_port,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()

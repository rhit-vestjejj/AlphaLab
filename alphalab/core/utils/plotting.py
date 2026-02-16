"""Plotting utilities for local research artifacts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

from alphalab.core.utils.errors import ArtifactError


def get_matplotlib_pyplot() -> Any:
    """
    Import and return ``matplotlib.pyplot`` with a writable config directory.

    Returns:
        Imported pyplot module.
    """
    if "MPLCONFIGDIR" not in os.environ:
        mpl_config_dir = Path("/tmp/alphalab-mplconfig")
        mpl_config_dir.mkdir(parents=True, exist_ok=True)
        os.environ["MPLCONFIGDIR"] = str(mpl_config_dir)

    import matplotlib.pyplot as plt

    return plt


def save_equity_curve_plot(
    equity_curve: pd.Series,
    output_dir: Path,
    filename: str = "equity_curve.png",
) -> Path:
    """
    Save equity curve plot artifact.

    Args:
        equity_curve: Equity curve series indexed by datetime.
        output_dir: Artifact directory.
        filename: Output image filename.

    Returns:
        Saved plot path.
    """
    plt = get_matplotlib_pyplot()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        plot_path = output_dir / filename

        figure, axis = plt.subplots(figsize=(10, 4))
        axis.plot(equity_curve.index, equity_curve.values, linewidth=1.2, color="#0f3d3e")
        axis.set_title("Equity Curve")
        axis.set_xlabel("Date")
        axis.set_ylabel("Equity")
        axis.grid(alpha=0.25, linestyle="--", linewidth=0.7)
        figure.tight_layout()
        figure.savefig(plot_path, dpi=150)
        plt.close(figure)
        return plot_path
    except Exception as exc:
        raise ArtifactError(
            f"Failed to save equity curve plot to {output_dir / filename}: {exc}"
        ) from exc

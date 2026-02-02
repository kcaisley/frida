"""Matplotlib configuration for FRIDA test plots."""

import logging
import os
import sys
from io import StringIO
from pathlib import Path


def configure_matplotlib():
    """Configure matplotlib for headless plotting with LaTeX."""
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)

    os.environ["MPLBACKEND"] = "Agg"
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    finally:
        sys.stdout = old_stdout

    plt.rcParams.update(
        {
            "text.usetex": True,
            "font.family": "serif",
            "font.serif": ["Computer Modern Roman"],
            "font.size": 11,
            "axes.titlesize": 12,
            "axes.labelsize": 11,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
        }
    )
    return plt


def save_plot(
    fig, filename_base: str, output_dir: Path = Path("scratch")
) -> list[str]:
    """Save plot in both PDF and PNG formats."""
    output_dir.mkdir(exist_ok=True)
    saved = []

    fig.tight_layout()
    for ext in ["pdf", "png"]:
        path = output_dir / f"{filename_base}.{ext}"
        try:
            fig.savefig(path, dpi=150 if ext == "png" else None)
            saved.append(str(path))
        except Exception as e:
            print(f"Warning: Could not save {path}: {e}")

    return saved

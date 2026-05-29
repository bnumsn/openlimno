"""Browser UI + plotting helpers (Hour-4 [release]).

``run_app`` launches the local browser Studio. ``plot_result`` is a
pure-matplotlib helper usable from notebooks and tests.
"""

from __future__ import annotations

from typing import Any

from .solver import Result
from .studio_http import run_fishtank_studio

_INSTALL_HINT = (
    "The browser Studio uses Python's standard library HTTP server.\n"
    "Run:  python -m openlimno.fishtank studio"
)


def plot_result(result: Result, *, show: bool = False) -> Any:
    """Plot a simulation Result with matplotlib; returns the Figure.

    Two stacked panels: dissolved N (TAN/NO2/NO3) and the attached
    biofilm + DO. Used by the notebooks and tests."""
    import matplotlib.pyplot as plt

    df = result.timeseries
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)

    ax1.plot(df["day"], df["TAN"], label="TAN (NH3/NH4+)", color="#d1495b")
    ax1.plot(df["day"], df["NO2"], label="NO2", color="#edae49")
    ax1.plot(df["day"], df["NO3"], label="NO3", color="#00798c")
    ax1.set_ylabel("mg-N/L")
    ax1.set_title("Nitrogen cycle")
    ax1.legend(loc="upper right", fontsize=8)
    ax1.grid(alpha=0.3)

    ax2.plot(df["day"], df["X_AOB"], label="X_AOB (biofilm)", color="#2e933c")
    ax2.plot(df["day"], df["X_NOB"], label="X_NOB (biofilm)", color="#7d4f50")
    ax2.plot(df["day"], df["DO"], label="DO", color="#3066be", linestyle="--")
    ax2.set_ylabel("mg/L")
    ax2.set_xlabel("day")
    ax2.legend(loc="upper right", fontsize=8)
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    if show:
        plt.show()
    return fig


def run_app(host: str = "127.0.0.1", port: int = 8768, open_browser: bool = True) -> None:
    """Launch the local browser Studio."""

    run_fishtank_studio(host=host, port=port, open_browser=open_browser)


if __name__ == "__main__":  # pragma: no cover - UI path
    run_app()

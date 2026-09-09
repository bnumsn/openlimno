"""Matplotlib chart widgets embedded in Qt (thin view helpers, no model logic)."""

from __future__ import annotations

from typing import Any

import matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

# NB: do NOT call matplotlib.use("QtAgg") — we embed an explicit
# FigureCanvasQTAgg over a plain Figure and never touch pyplot, so switching the
# global backend is both unnecessary and harmful (it breaks other tests/notebooks
# that already initialised a different backend in the same process).


def _use_cjk_font() -> None:
    """Best-effort: pick a CJK-capable font so Chinese labels aren't tofu.
    Falls back silently (English half of each label still reads)."""
    from matplotlib import font_manager

    candidates = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "WenQuanYi Zen Hei",
        "WenQuanYi Micro Hei",
        "Source Han Sans SC",
        "Microsoft YaHei",
        "SimHei",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            matplotlib.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            matplotlib.rcParams["axes.unicode_minus"] = False
            return


_use_cjk_font()


# Typing note: FigureCanvasQTAgg ships without annotations, so `super().__init__`
# and every `self.draw_idle()` below are untyped calls. This package is therefore
# type-checked by `pixi run typecheck-strict-gui` (mypy --strict plus
# --allow-untyped-calls), not by `typecheck-strict-core` — same bucket as
# gui_core/studio, which construct the very same canvas class.
class LineChart(FigureCanvasQTAgg):
    """A single line chart. ``plot`` draws one dataset; ``plot_compare`` overlays
    two (ODE solid vs ABM dashed) on shared axes."""

    def __init__(self, ylabel: str = "") -> None:
        self.fig = Figure(figsize=(5.0, 3.2), layout="tight")
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self._ylabel = ylabel
        self._blank()

    def _blank(self, hint: str = "运行后在此显示结果") -> None:
        # Empty-state: a centred hint instead of bare 0–1 matplotlib axes, so a
        # just-opened (or failed) chart reads as "ready" not "broken".
        self.ax.clear()
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        for spine in self.ax.spines.values():
            spine.set_visible(False)
        self.ax.text(
            0.5,
            0.5,
            hint,
            ha="center",
            va="center",
            transform=self.ax.transAxes,
            fontsize=11,
            color="#94a3b8",
        )
        self.draw_idle()

    def plot(
        self, days: list[float], series: list[dict[str, Any]], ylabel: str | None = None
    ) -> None:
        self.ax.clear()
        for s in series:
            self.ax.plot(days, s["values"], label=s["label"], color=s["color"], linewidth=1.8)
        self.ax.set_xlabel("天 / day")
        self.ax.set_ylabel(ylabel or self._ylabel)
        self.ax.grid(True, alpha=0.3)
        if series:
            self.ax.legend(fontsize=8, loc="best", ncols=min(3, len(series)))
        self.draw_idle()

    def plot_compare(
        self,
        days_ode: list[float],
        series_ode: list[dict[str, Any]],
        days_abm: list[float],
        series_abm: list[dict[str, Any]],
        ylabel: str = "",
    ) -> None:
        self.ax.clear()
        for s in series_ode:
            self.ax.plot(days_ode, s["values"], color=s["color"], linewidth=1.8)
        for s in series_abm:
            self.ax.plot(
                days_abm, s["values"], color=s["color"], linewidth=1.5, linestyle="--", alpha=0.85
            )
        self.ax.set_xlabel("天 / day")
        self.ax.set_ylabel(ylabel)
        self.ax.grid(True, alpha=0.3)
        # Legend explains line style + colour mapping.
        from matplotlib.lines import Line2D

        handles = [
            Line2D([0], [0], color="#444", lw=1.8, label="实线 = ODE"),
            Line2D([0], [0], color="#444", lw=1.5, ls="--", label="虚线 = ABM"),
        ]
        handles += [Line2D([0], [0], color=s["color"], lw=2, label=s["label"]) for s in series_ode]
        self.ax.legend(handles=handles, fontsize=8, loc="best", ncols=2)
        self.draw_idle()

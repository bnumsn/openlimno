"""Browser UI + plotting helpers (Hour-4 [release]).

``run_app`` is a ~20-line Streamlit app (the Hour-4 live-code target).
Streamlit is a teaching-time dependency and is imported lazily, so the
``openlimno.fishtank`` package imports fine without it. ``plot_result``
is a pure-matplotlib helper usable from notebooks and the CLI with no
Streamlit requirement.
"""

from __future__ import annotations

from typing import Any

from .solver import Result, simulate
from .state import Chemistry, Params

_INSTALL_HINT = (
    "Streamlit is not installed. It is a teaching-time dependency:\n"
    "    pip install streamlit\n"
    "then run:  streamlit run -m openlimno.fishtank.studio"
)


def plot_result(result: Result, *, show: bool = False) -> Any:
    """Plot a simulation Result with matplotlib; returns the Figure.

    Two stacked panels: dissolved N (TAN/NO2/NO3) and the attached
    biofilm + DO. Works without Streamlit (used by the notebooks)."""
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


def run_app() -> None:
    """Streamlit entry point — the Hour-4 live-code deliverable."""
    try:
        import streamlit as st
    except ModuleNotFoundError as exc:  # pragma: no cover - UI path
        raise SystemExit(_INSTALL_HINT) from exc

    st.title("🐟 鱼缸生态模拟器 — fishtank")
    st.caption("inSTREAM-lineage microcosm model · openlimno.fishtank")

    vol = st.slider("缸体积 Volume (L)", 20, 500, 120)
    dose = st.slider("每日氨负荷 Ammonia dose (mg-N/L/day)", 0.0, 5.0, 2.0, 0.25)
    temp = st.slider("温度 Temperature (°C)", 10.0, 32.0, 25.0, 0.5)
    days = st.slider("模拟天数 Days", 7, 90, 42)

    params = Params(volume_l=vol, ammonia_dose_mg_n_l_day=dose, temperature_c=temp)
    result = simulate(Chemistry(), params, days=float(days))

    st.line_chart(result.timeseries.set_index("day")[["TAN", "NO2", "NO3"]])
    st.caption("经典氮循环:氨峰 → 亚硝峰(滞后)→ 硝酸盐累积,周期跨数周。")

    if result.warnings:
        for w in result.warnings:
            st.warning(w)


# ``streamlit run -m openlimno.fishtank.studio`` executes the module body.
if __name__ == "__main__":  # pragma: no cover - UI path
    run_app()

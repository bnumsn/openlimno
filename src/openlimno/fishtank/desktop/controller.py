"""Headless controller for the desktop app — NO Qt, NO matplotlib imports.

Everything the GUI needs to talk to the model lives here as plain functions
over plain dicts, so it is fully unit-testable without a display. The GUI
(``main_window``) is a thin view that reads widgets → builds an ``inputs``
dict → calls these → renders the returned series. Model logic stays in the
core (``solver``/``agent``); this only re-shapes payloads and results.
"""

from __future__ import annotations

import copy
from typing import Any

from .. import library
from ..studio_http import (
    default_studio_payload,
    list_studio_scenarios,
    run_agent_based_studio_payload,
    run_studio_payload,
)

# State variables the desktop charts plot, with display colour + zh/en label.
NITROGEN_SERIES = (
    ("TAN", "总氨氮 / TAN", "#d1495b"),
    ("NO2", "亚硝酸盐 / NO2", "#edae49"),
    ("NO3", "硝酸盐 / NO3", "#00798c"),
)
OXYGEN_SERIES = (
    ("X_AOB", "氨氧化菌 / AOB", "#2e933c"),
    ("X_NOB", "亚硝氧化菌 / NOB", "#7d4f50"),
    ("DO", "溶氧 / DO", "#3066be"),
)
# Variables shared by ODE and ABM, used for the ODE-vs-ABM compare chart.
COMPARE_SERIES = (
    ("TAN", "总氨氮", "#d1495b"),
    ("NO2", "亚硝酸盐", "#edae49"),
    ("NO3", "硝酸盐", "#00798c"),
    ("DO", "溶氧", "#3066be"),
)


def list_presets() -> list[dict[str, Any]]:
    """Bundled scenarios: ``[{id, label, label_zh, description, payload}]``."""
    return list_studio_scenarios()


def preset_payload(name: str) -> dict[str, Any]:
    """Full Studio payload for a named preset (deep-copied — caller may edit)."""
    return copy.deepcopy(library.scenario_payload(name))


def default_payload() -> dict[str, Any]:
    return default_studio_payload()


def run_ode(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the continuous (ODE) model. Returns the JSON-safe Studio result."""
    return run_studio_payload(copy.deepcopy(payload))


def run_abm(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the agent-based (ABM) model. Returns the JSON-safe ABM result."""
    return run_agent_based_studio_payload(copy.deepcopy(payload))


def series_from_timeseries(
    result: dict[str, Any], spec: tuple[tuple[str, str, str], ...]
) -> tuple[list[float], list[dict[str, Any]]]:
    """Turn a result's ``timeseries`` into (days, [{key,label,color,values}]).

    Pure data-reshaping the chart widget consumes — no plotting here, so the
    selection logic is unit-testable on its own."""
    ts = result.get("timeseries", []) or []
    days = [float(r.get("day", 0.0)) for r in ts]
    out: list[dict[str, Any]] = []
    for key, label, color in spec:
        if ts and key in ts[0]:
            out.append(
                {
                    "key": key,
                    "label": label,
                    "color": color,
                    "values": [float(r.get(key, 0.0)) for r in ts],
                }
            )
    return days, out


def summary_kpis(ode: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Headline KPI (label, value) pairs for the status strip. Empty if no run."""
    if not ode:
        return []
    ts = ode.get("timeseries", []) or []
    if not ts:
        return []
    last = ts[-1]
    min_do = min((float(r.get("DO", 0.0)) for r in ts), default=0.0)
    max_nh3 = max((float(r.get("NH3_free", 0.0)) for r in ts), default=0.0)
    return [
        ("最终总氨氮", f"{float(last.get('TAN', 0.0)):.2f} mg-N/L"),
        ("最终亚硝酸盐", f"{float(last.get('NO2', 0.0)):.2f} mg-N/L"),
        ("最终硝酸盐", f"{float(last.get('NO3', 0.0)):.2f} mg-N/L"),
        ("最低溶氧", f"{min_do:.2f} mg-O2/L"),
        ("峰值游离氨", f"{max_nh3:.3f} mg/L"),
        ("最终 pH", f"{float(last.get('pH', 0.0)):.2f}"),
    ]


def warnings_of(ode: dict[str, Any] | None) -> list[str]:
    if not ode:
        return []
    return list(ode.get("warnings", []) or [])


def status_line(ode: dict[str, Any] | None, abm: dict[str, Any] | None) -> str:
    """The combined run-status string, mirroring the browser's semantics."""
    parts: list[str] = []
    if ode and ode.get("timeseries"):
        n = len(ode["timeseries"])
        ev = len(ode.get("events_log", []) or ode.get("event_log", []) or [])
        parts.append(f"{n} 行 ODE,{ev} 个事件")
    if abm and abm.get("timeseries"):
        agents = (abm.get("provenance", {}) or {}).get("agent_count")
        parts.append(
            f"{agents} 个 ABM 个体" if agents is not None else f"{len(abm['timeseries'])} 行 ABM"
        )
    return "运行完成:" + ";".join(parts) if parts else "已就绪 —— 选预设并运行"

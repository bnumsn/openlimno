"""China SL/Z 712-2014 monthly ecological flow "four-tuple" output.

Per SPEC §4.2.4.2 + ADR-0009 + SL/Z 712-2014 §5.2-5.4:

Output table per month (Jan-Dec):
    1. min_eco_flow_m3s        — minimum ecological flow
    2. suitable_eco_flow_m3s   — suitable (preferred) ecological flow
    3. multi_year_avg_pct      — recommended flow as % of multi-year-avg discharge
    4. min_eco_flow_p90_m3s    — 90% guaranteed minimum (10-year low recurrence)

Inputs:
    discharge_series: long-term daily/monthly Q time series (datetime + Q)
    wua_q_curve:       WUA vs Q from habitat module (one species/stage)
    target_wua_pct:    fraction of peak WUA defining "suitable" (default 0.6)
    min_wua_pct:       fraction of peak WUA defining "minimum" (default 0.3)

Output: pandas DataFrame with 12 monthly rows + provenance metadata; can
write to CSV via ``render_csv(df, path)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class SL712Result:
    """SL-712 four-tuple monthly summary."""

    monthly: pd.DataFrame  # 12 rows, columns described in module docstring
    annual_avg_m3s: float
    target_wua_pct: float
    min_wua_pct: float
    discharge_series_n: int

    def to_csv(self, path: str | Path) -> Path:
        path = Path(path)
        # Header block
        header_lines = [
            "# OpenLimno SL/Z 712-2014 ecological flow four-tuple",
            f"# annual_avg_m3s={self.annual_avg_m3s:.3f}",
            f"# target_wua_pct={self.target_wua_pct:.2f}  min_wua_pct={self.min_wua_pct:.2f}",
            f"# discharge_series_n={self.discharge_series_n}",
            "# Columns:",
            "#   month=1..12",
            "#   monthly_avg_q_m3s : observed multi-year monthly average flow",
            "#   min_eco_flow_m3s : Q at which WUA = min_wua_pct * peak (recommended minimum)",
            "#   suitable_eco_flow_m3s : Q at which WUA = target_wua_pct * peak (recommended suitable)",
            "#   multi_year_avg_pct : suitable_eco_flow / multi-year annual average × 100",
            "#   min_eco_flow_p90_m3s : 90%-guarantee monthly minimum from observed series",
        ]
        with path.open("w", encoding="utf-8") as f:
            f.write("\n".join(header_lines) + "\n")
            self.monthly.to_csv(f, index=False)
        return path


def _interp_q_at_wua(wua_q: pd.DataFrame, target_wua: float, q_col: str, wua_col: str) -> float:
    """Find smallest Q whose WUA >= target_wua.

    The WUA-Q curve is typically unimodal; we want the *low-Q* limb so that the
    recommended ecological flow is the minimum needed, not the surplus side.
    """
    df = wua_q[[q_col, wua_col]].sort_values(q_col).reset_index(drop=True)
    Qs = df[q_col].to_numpy()
    Ws = df[wua_col].to_numpy()
    if Ws.max() < target_wua:
        return float(Qs[Ws.argmax()])
    # Walk from low-Q to high-Q and return first Q where W crosses up over target
    for i in range(1, len(Qs)):
        if Ws[i - 1] < target_wua <= Ws[i]:
            # Linear interp on the rising limb
            t = (target_wua - Ws[i - 1]) / (Ws[i] - Ws[i - 1])
            return float(Qs[i - 1] + t * (Qs[i] - Qs[i - 1]))
    # WUA already at target at lowest Q
    return float(Qs[0])


def compute_sl712(
    discharge_series: pd.DataFrame,
    wua_q: pd.DataFrame,
    species: str,
    life_stage: str,
    target_wua_pct: float = 0.6,
    min_wua_pct: float = 0.3,
) -> SL712Result:
    """Compute the SL-712 four-tuple from a flow record + WUA-Q curve.

    Parameters
    ----------
    discharge_series
        DataFrame with columns 'time' (datetime) and 'discharge_m3s'.
    wua_q
        DataFrame with 'discharge_m3s' and 'wua_m2_<species>_<stage>' columns
        (output of ``Case.run().wua_q``).
    species, life_stage
        Pick the relevant WUA column.
    target_wua_pct, min_wua_pct
        Fractions of peak WUA defining suitable / minimum thresholds.
    """
    if not 0 < min_wua_pct < target_wua_pct <= 1.0:
        raise ValueError("Need 0 < min_wua_pct < target_wua_pct <= 1.0")

    wua_col = f"wua_m2_{species}_{life_stage}"
    if wua_col not in wua_q.columns:
        raise ValueError(f"WUA column '{wua_col}' not in wua_q DataFrame")

    peak = float(wua_q[wua_col].max())
    target_wua = target_wua_pct * peak
    min_wua = min_wua_pct * peak

    Q_suitable = _interp_q_at_wua(wua_q, target_wua, "discharge_m3s", wua_col)
    Q_min = _interp_q_at_wua(wua_q, min_wua, "discharge_m3s", wua_col)

    # Long-term flow stats
    ds = discharge_series.copy()
    ds["time"] = pd.to_datetime(ds["time"])
    ds["month"] = ds["time"].dt.month
    annual_avg = float(ds["discharge_m3s"].mean())

    rows = []
    for m in range(1, 13):
        sub = ds[ds["month"] == m]["discharge_m3s"]
        if len(sub) == 0:
            monthly_avg = float("nan")
            p90 = float("nan")
        else:
            monthly_avg = float(sub.mean())
            # 90% guarantee = the 10th-percentile flow (90% of values exceed it)
            p90 = float(np.quantile(sub, 0.10))
        rows.append({
            "month": m,
            "monthly_avg_q_m3s": monthly_avg,
            "min_eco_flow_m3s": Q_min,
            "suitable_eco_flow_m3s": Q_suitable,
            "multi_year_avg_pct": (Q_suitable / annual_avg * 100) if annual_avg > 0 else 0.0,
            "min_eco_flow_p90_m3s": p90,
        })

    monthly = pd.DataFrame(rows)
    return SL712Result(
        monthly=monthly,
        annual_avg_m3s=annual_avg,
        target_wua_pct=target_wua_pct,
        min_wua_pct=min_wua_pct,
        discharge_series_n=len(ds),
    )


def render_csv(result: SL712Result, path: str | Path) -> Path:
    return result.to_csv(path)


__all__ = ["SL712Result", "compute_sl712", "render_csv"]

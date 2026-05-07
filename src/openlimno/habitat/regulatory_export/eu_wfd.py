"""EU Water Framework Directive ecological status output. SPEC §4.2.4.2, ADR-0009.

WFD 2000/60/EC Annex V requires classification into 5 ecological status classes:
high / good / moderate / poor / bad. 1.0 produces a habitat-based proxy:

    EQR (Ecological Quality Ratio) = mean WUA(observed Q) / WUA(reference Q)

Status mapping (WFD Common Implementation Strategy guidance):
    EQR ≥ 0.80  → high
    EQR ≥ 0.60  → good
    EQR ≥ 0.40  → moderate
    EQR ≥ 0.20  → poor
    else        → bad

1.0 reports the EQR + status class. Full BQE (Biological Quality Elements)
integration is M3+ per ADR-0009.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

EcologicalStatus = Literal["high", "good", "moderate", "poor", "bad"]


@dataclass
class WFDResult:
    eqr: float
    status: EcologicalStatus
    monthly_eqr: pd.DataFrame  # cols: month, observed_q, observed_wua, eqr_monthly, status
    reference_wua_m2: float
    target_species: str
    target_life_stage: str
    n_obs: int

    def to_csv(self, path: str | Path) -> Path:
        path = Path(path)
        header = [
            "# OpenLimno EU WFD ecological status (WUA-based proxy, BQE integration M3+)",
            f"# overall_eqr={self.eqr:.3f}",
            f"# overall_status={self.status}",
            f"# reference_wua_m2={self.reference_wua_m2:.2f}",
            f"# target={self.target_species}/{self.target_life_stage}",
            f"# n_observations={self.n_obs}",
            "# Columns:",
            "#   month=1..12",
            "#   observed_q_m3s : mean monthly observed discharge",
            "#   observed_wua_m2 : WUA at that Q from interpolated WUA-Q curve",
            "#   eqr_monthly : observed_wua / reference_wua",
            "#   status : WFD class (high/good/moderate/poor/bad)",
        ]
        with path.open("w", encoding="utf-8") as f:
            f.write("\n".join(header) + "\n")
            self.monthly_eqr.to_csv(f, index=False)
        return path


def _classify(eqr: float) -> EcologicalStatus:
    if eqr >= 0.80:
        return "high"
    if eqr >= 0.60:
        return "good"
    if eqr >= 0.40:
        return "moderate"
    if eqr >= 0.20:
        return "poor"
    return "bad"


def compute_wfd(
    discharge_series: pd.DataFrame,
    wua_q: pd.DataFrame,
    species: str,
    life_stage: str,
    reference_q_m3s: float | None = None,
) -> WFDResult:
    """Compute WFD EQR + ecological status from observed Q + WUA-Q curve.

    Reference Q defaults to the Q at peak WUA (i.e., the "ideal" condition).
    """
    wua_col = f"wua_m2_{species}_{life_stage}"
    if wua_col not in wua_q.columns:
        raise ValueError(f"WUA column '{wua_col}' not in wua_q DataFrame")

    Qs = wua_q["discharge_m3s"].to_numpy()
    Ws = wua_q[wua_col].to_numpy()
    peak_idx = int(np.argmax(Ws))
    if reference_q_m3s is None:
        reference_q_m3s = float(Qs[peak_idx])
    reference_wua = float(np.interp(reference_q_m3s, Qs, Ws))
    if reference_wua <= 0:
        raise ValueError("Reference WUA is zero — cannot compute EQR")

    ds = discharge_series.copy()
    ds["time"] = pd.to_datetime(ds["time"])
    ds["month"] = ds["time"].dt.month

    rows = []
    monthly_wuas: list[float] = []
    for m in range(1, 13):
        q = ds[ds["month"] == m]["discharge_m3s"]
        if len(q) == 0:
            continue
        q_mean = float(q.mean())
        wua_at_q = float(np.interp(q_mean, Qs, Ws))
        eqr_m = wua_at_q / reference_wua
        monthly_wuas.append(wua_at_q)
        rows.append(
            {
                "month": m,
                "observed_q_m3s": q_mean,
                "observed_wua_m2": wua_at_q,
                "eqr_monthly": eqr_m,
                "status": _classify(eqr_m),
            }
        )

    monthly_df = pd.DataFrame(rows)
    overall_eqr = float(np.mean(monthly_wuas) / reference_wua) if monthly_wuas else 0.0

    return WFDResult(
        eqr=overall_eqr,
        status=_classify(overall_eqr),
        monthly_eqr=monthly_df,
        reference_wua_m2=reference_wua,
        target_species=species,
        target_life_stage=life_stage,
        n_obs=len(ds),
    )


def render_csv(result: WFDResult, path: str | Path) -> Path:
    return result.to_csv(path)


__all__ = ["EcologicalStatus", "WFDResult", "compute_wfd", "render_csv"]

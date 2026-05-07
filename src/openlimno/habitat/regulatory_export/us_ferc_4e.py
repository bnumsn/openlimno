"""US FERC 4(e) flow regime by water-year type. SPEC §4.2.4.2, ADR-0009.

FERC re-licensing 4(e) conditions typically require recommended flows broken
out by water-year type (wet / normal / dry), often by month. Output:

    month | wet_year_q_m3s | normal_year_q_m3s | dry_year_q_m3s

Water year types are derived from total annual discharge percentile:
- dry:    bottom 25%
- normal: middle 50%
- wet:    top 25%

For each (month, year_type), recommended flow = monthly mean of historical
discharge in that year-type bucket, scaled by ``wua_q`` to the suitable WUA
threshold (analogous to SL-712 logic).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .cn_sl712 import _interp_q_at_wua


@dataclass
class FERC4eResult:
    monthly_by_year_type: pd.DataFrame  # 12 rows × cols (month, wet, normal, dry, suitable_eco)
    suitable_eco_flow_m3s: float
    annual_avg_m3s: float
    n_years: int

    def to_csv(self, path: str | Path) -> Path:
        path = Path(path)
        header = [
            "# OpenLimno FERC 4(e) flow regime by water-year type",
            f"# annual_avg_m3s={self.annual_avg_m3s:.3f}",
            f"# suitable_eco_flow_m3s={self.suitable_eco_flow_m3s:.3f}",
            f"# n_years={self.n_years}",
            "# Columns:",
            "#   month=1..12",
            "#   wet_year_q_m3s : mean monthly discharge in wet years (top 25% by annual total)",
            "#   normal_year_q_m3s : mean in normal years (middle 50%)",
            "#   dry_year_q_m3s : mean in dry years (bottom 25%)",
            "#   suitable_eco_flow_m3s : recommended flow at target WUA threshold",
        ]
        with path.open("w", encoding="utf-8") as f:
            f.write("\n".join(header) + "\n")
            self.monthly_by_year_type.to_csv(f, index=False)
        return path


def compute_ferc_4e(
    discharge_series: pd.DataFrame,
    wua_q: pd.DataFrame,
    species: str,
    life_stage: str,
    target_wua_pct: float = 0.6,
) -> FERC4eResult:
    """Compute FERC 4(e) flow regime by water-year type."""
    wua_col = f"wua_m2_{species}_{life_stage}"
    if wua_col not in wua_q.columns:
        raise ValueError(f"WUA column '{wua_col}' not in wua_q DataFrame")

    peak = float(wua_q[wua_col].max())
    Q_suitable = _interp_q_at_wua(wua_q, target_wua_pct * peak, "discharge_m3s", wua_col)

    ds = discharge_series.copy()
    ds["time"] = pd.to_datetime(ds["time"])
    ds["year"] = ds["time"].dt.year
    ds["month"] = ds["time"].dt.month

    # Annual totals → year-type classification
    annual = ds.groupby("year")["discharge_m3s"].mean()
    n_years = len(annual)
    if n_years < 4:
        # Few years; classify by simple thirds
        q33, q67 = annual.quantile([0.33, 0.67])
    else:
        q33, q67 = annual.quantile([0.25, 0.75])
    year_type = pd.Series(
        {y: ("wet" if v > q67 else "dry" if v < q33 else "normal") for y, v in annual.items()}
    )
    ds["year_type"] = ds["year"].map(year_type)

    rows = []
    for m in range(1, 13):
        sub_m = ds[ds["month"] == m]
        wet = sub_m[sub_m["year_type"] == "wet"]["discharge_m3s"].mean()
        normal = sub_m[sub_m["year_type"] == "normal"]["discharge_m3s"].mean()
        dry = sub_m[sub_m["year_type"] == "dry"]["discharge_m3s"].mean()
        rows.append(
            {
                "month": m,
                "wet_year_q_m3s": float(wet) if not np.isnan(wet) else float("nan"),
                "normal_year_q_m3s": float(normal) if not np.isnan(normal) else float("nan"),
                "dry_year_q_m3s": float(dry) if not np.isnan(dry) else float("nan"),
                "suitable_eco_flow_m3s": Q_suitable,
            }
        )

    return FERC4eResult(
        monthly_by_year_type=pd.DataFrame(rows),
        suitable_eco_flow_m3s=Q_suitable,
        annual_avg_m3s=float(ds["discharge_m3s"].mean()),
        n_years=n_years,
    )


def render_csv(result: FERC4eResult, path: str | Path) -> Path:
    return result.to_csv(path)


__all__ = ["FERC4eResult", "compute_ferc_4e", "render_csv"]

"""Hydromorphological Mesohabitat Unit (HMU) classification + reach aggregation.

SPEC §3.1.1, §4.2.3.2-3, §4.2.5; ADR-0008.

Wadeson 1994 / Parasiewicz 2007 thresholds applied to Builtin1D outputs to
classify each section as one of: cascade / step / riffle / run / glide / pool /
backwater. M2 deliverable.

Classification scheme (defaults):

| HMU type   | Froude         | Relative depth (h_mean / h_thalweg) | Notes |
|---|---|---|---|
| cascade    | Fr > 1.0       | low                                  | supercritical |
| step       | 0.7 < Fr ≤ 1.0 | low                                  | transitional |
| riffle     | 0.4 < Fr ≤ 0.7 | medium                               | shallow turbulent |
| run        | 0.2 < Fr ≤ 0.4 | medium                               | uniform flow |
| glide      | 0.05 < Fr ≤ 0.2| medium                               | smooth flow |
| pool       | Fr ≤ 0.05      | high                                 | deep slow |
| backwater  | Fr ~ 0         | high                                 | near-zero velocity |

Users can override via custom thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

HMUType = Literal[
    "cascade", "step", "riffle", "run", "glide", "pool", "backwater"
]


@dataclass
class HMUThresholds:
    """Wadeson 1994 / Parasiewicz 2007-inspired thresholds (overridable)."""

    # (lower_Fr, upper_Fr, label) — searched in order
    bands: list[tuple[float, float, HMUType]] = field(default_factory=lambda: [
        (1.0, np.inf, "cascade"),
        (0.7, 1.0, "step"),
        (0.4, 0.7, "riffle"),
        (0.2, 0.4, "run"),
        (0.05, 0.2, "glide"),
        (0.001, 0.05, "pool"),
        (0.0, 0.001, "backwater"),
    ])


def classify_hmu(
    velocity_ms: float,
    depth_m: float,
    thresholds: HMUThresholds | None = None,
) -> HMUType:
    """Classify a single section by its Froude number."""
    th = thresholds or HMUThresholds()
    if depth_m <= 0:
        return "backwater"
    Fr = velocity_ms / np.sqrt(9.81 * depth_m)
    for lo, hi, label in th.bands:
        if lo <= Fr < hi:
            return label
    return "backwater"


def classify_reach(
    velocities_ms: np.ndarray,
    depths_m: np.ndarray,
    thresholds: HMUThresholds | None = None,
) -> list[HMUType]:
    """Classify each section in a reach."""
    return [classify_hmu(v, d, thresholds) for v, d in zip(velocities_ms, depths_m, strict=False)]


def aggregate_wua_by_hmu(
    csi: np.ndarray,
    area: np.ndarray,
    hmu_labels: list[HMUType],
) -> pd.DataFrame:
    """Sum WUA by HMU type. Returns a DataFrame with one row per type present.

    Columns: hmu_type, wua_m2, n_sections.
    """
    csi = np.asarray(csi, dtype=float)
    area = np.asarray(area, dtype=float)
    if csi.shape != area.shape:
        raise ValueError(f"csi shape {csi.shape} != area shape {area.shape}")
    if len(hmu_labels) != len(csi):
        raise ValueError(f"hmu_labels length {len(hmu_labels)} != csi length {len(csi)}")

    rows: dict[str, dict[str, float]] = {}
    for label, c, a in zip(hmu_labels, csi, area, strict=False):
        rec = rows.setdefault(label, {"wua_m2": 0.0, "n_sections": 0})
        rec["wua_m2"] += c * a
        rec["n_sections"] += 1
    df = pd.DataFrame([
        {"hmu_type": k, **v} for k, v in rows.items()
    ])
    return df.sort_values("hmu_type").reset_index(drop=True)


def aggregate_wua_by_reach(
    csi: np.ndarray,
    area: np.ndarray,
    reach_labels: list[str],
) -> pd.DataFrame:
    """Sum WUA by reach (user-defined polygons). Returns DataFrame.

    Columns: reach, wua_m2, n_sections.
    """
    return aggregate_wua_by_hmu(csi, area, reach_labels).rename(
        columns={"hmu_type": "reach"}
    )


__all__ = [
    "HMUThresholds",
    "HMUType",
    "aggregate_wua_by_hmu",
    "aggregate_wua_by_reach",
    "classify_hmu",
    "classify_reach",
]

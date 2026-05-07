"""Build the Bovee 1997 PHABSIM replication data package.

Produces a self-contained dataset under ``examples/phabsim_replication/data/``:

* cross_section.parquet — 6 identical wide-rectangular prismatic sections
* hsi_curve.parquet     — stylised Bovee 1978 steelhead spawning curves
* species.parquet       — single species (oncorhynchus_mykiss)
* life_stage.parquet    — single life stage (spawning)
* expected_wua.json     — analytic / hand-computed WUA at four target Q

This is the same case used by ``benchmarks/phabsim_bovee1997`` but framed as
an end-to-end runnable example rather than a regression test.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"


def _wua_closed_form(Q: float, *, b: float = 10.0, n: float = 0.030,
                     S: float = 0.001, n_sections: int = 6) -> float:
    """Hand-computed WUA for a wide rectangular reach (geometric-mean composite).

    Matches ``openlimno.habitat.cell_wua`` semantics: per-section WUA = csi ×
    wetted_area; reach WUA = sum across sections. (No spacing multiplier; reach
    length is encoded in the section count.)
    """
    from scipy.optimize import brentq

    def residual(h: float) -> float:
        A = b * h
        P = b + 2 * h
        R = A / P
        return (1.0 / n) * A * R ** (2.0 / 3.0) * np.sqrt(S) - Q

    h = float(brentq(residual, 1e-4, 50.0))
    u = Q / (b * h)
    s_h = float(np.interp(h, [0.0, 0.30, 0.60, 1.20, 2.00],
                              [0.0, 1.0, 1.0, 0.5, 0.0]))
    s_u = float(np.interp(u, [0.0, 0.50, 1.00, 1.50, 2.00],
                              [0.0, 1.0, 1.0, 0.3, 0.0]))
    csi = float(np.sqrt(s_h * s_u))
    return csi * b * h * n_sections


def build_cross_sections() -> pd.DataFrame:
    """6 identical rectangular sections separated by 100 m at slope 0.001."""
    rows = []
    cid = str(uuid.uuid4())
    for i in range(6):
        bed = 1.0 - 0.001 * i * 100.0
        # Wide rectangle: vertical walls at ±5 m, flat bed
        for j, (dist, elev) in enumerate([
            (-5.01, bed + 5.0),
            (-5.00, bed),
            (5.00, bed),
            (5.01, bed + 5.0),
        ]):
            rows.append({
                "campaign_id": cid,
                "station_m": float(i * 100.0),
                "point_index": j,
                "distance_m": float(dist),
                "elevation_m": float(elev),
                "substrate": "gravel",
                "cover": "none",
            })
    return pd.DataFrame(rows)


def build_hsi() -> pd.DataFrame:
    """Stylised Bovee 1978 steelhead spawning curves (matches benchmark).

    Conforms to the WEDM hsi_curve schema: one row per
    (species, life_stage, variable) with ``points`` as a list of (x, s) pairs.
    """
    depth_curve = [[0.00, 0.0], [0.30, 1.0], [0.60, 1.0], [1.20, 0.5], [2.00, 0.0]]
    velocity_curve = [[0.00, 0.0], [0.50, 1.0], [1.00, 1.0], [1.50, 0.3], [2.00, 0.0]]
    rows = [
        {
            "species": "oncorhynchus_mykiss",
            "life_stage": "spawning",
            "variable": v_name,
            "points": curve,
            "category": "III",
            "geographic_origin": "Pacific-Northwest-USA",
            "transferability_score": 0.6,
            "quality_grade": "B",
            "independence_tested": False,
            "evidence": ["Bovee-1978-USFWS-Blue-Book"],
        }
        for v_name, curve in (("depth", depth_curve), ("velocity", velocity_curve))
    ]
    return pd.DataFrame(rows)


def build_species() -> pd.DataFrame:
    return pd.DataFrame([{
        "species_id": "oncorhynchus_mykiss",
        "scientific_name": "Oncorhynchus mykiss",
        "common_name": "steelhead/rainbow trout",
        "family": "Salmonidae",
    }])


def build_life_stages() -> pd.DataFrame:
    return pd.DataFrame([{
        "species_id": "oncorhynchus_mykiss",
        "stage": "spawning",
        "phenology_window": "Mar-Jun",
        "tuf": "depth+velocity+substrate",
    }])


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    build_cross_sections().to_parquet(DATA / "cross_section.parquet", index=False)
    build_hsi().to_parquet(DATA / "hsi_curve.parquet", index=False)
    build_species().to_parquet(DATA / "species.parquet", index=False)
    build_life_stages().to_parquet(DATA / "life_stage.parquet", index=False)

    expected = {
        f"{Q}": _wua_closed_form(Q)
        for Q in (0.5, 1.5, 4.0, 8.0)
    }
    (DATA / "expected_wua.json").write_text(json.dumps(expected, indent=2))

    print(f"Wrote PHABSIM replication data to {DATA}")
    for q, w in expected.items():
        print(f"  Q={q} m³/s → analytic WUA={w:.3f} m²")


if __name__ == "__main__":
    main()

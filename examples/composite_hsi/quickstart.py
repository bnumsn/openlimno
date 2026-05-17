"""composite_hsi quickstart: compare product vs geom-mean overlay
methods on a synthetic Heihe-mid-basin WUA-Q sweep.

Run from repo root:
    PYTHONPATH=src python examples/composite_hsi/quickstart.py

Output:
    examples/composite_hsi/out/wua_q_overlay_comparison.png
    examples/composite_hsi/out/composite_summary_product.json
    examples/composite_hsi/out/composite_summary_geom_mean.json
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from openlimno.habitat.composite import (
    CompositeOverlay,
    apply_overlay,
    composite_summary,
)

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

# Heihe mid-basin (38.20 °N, 100.20 °E) canonical overlay values.
# These match the smoke-point used across the v1.6 — v1.9 review chain.
HEIHE_COVER_METRICS = {"mean_si": 0.4255}
HEIHE_THERMAL_METRICS = {"mean_SI": 0.62}


def synthetic_wua_q() -> pd.DataFrame:
    """Bell-shaped depth × velocity WUA-Q curve typical of a small alpine
    reach. Two species/stage pairings so the overlay's per-series
    rescaling is visible.
    """
    q = np.linspace(0.5, 25.0, 24)
    # Schizothorax prenanti, juvenile: peaks around 4 m3/s.
    juv = 320.0 * np.exp(-((np.log(q) - np.log(4.0)) ** 2) / 0.50)
    # Schizothorax prenanti, spawning: peaks around 8 m3/s.
    spawn = 410.0 * np.exp(-((np.log(q) - np.log(8.0)) ** 2) / 0.40)
    return pd.DataFrame(
        {
            "discharge_m3s": q,
            "wua_m2_schizothorax_prenanti_juvenile": juv,
            "wua_m2_schizothorax_prenanti_spawning": spawn,
        }
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # 1. Build the overlay from FishBase + WorldCover-derived metrics.
    #    `strict=True` (default for the programmatic API) raises on
    #    out-of-range values — exactly what we want for an example
    #    script that should fail loud if someone breaks the inputs.
    overlay = CompositeOverlay.from_metrics(
        HEIHE_THERMAL_METRICS, HEIHE_COVER_METRICS, strict=True,
    )
    print(
        f"Heihe mid-basin overlay: "
        f"cover_si={overlay.cover_si:.4f}, "
        f"thermal_si={overlay.thermal_si:.4f}, "
        f"overlay_si={overlay.overlay_si:.5f}"
    )

    # 2. Sweep two methods on the SAME base table.
    base = synthetic_wua_q()

    product_df = apply_overlay(base, overlay, method="product")
    geom_df = apply_overlay(base, overlay, method="geom_mean")

    product_summary = composite_summary(base, overlay, method="product")
    geom_summary = composite_summary(base, overlay, method="geom_mean")

    (OUT / "composite_summary_product.json").write_text(
        json.dumps(product_summary, indent=2, default=str),
        encoding="utf-8",
    )
    (OUT / "composite_summary_geom_mean.json").write_text(
        json.dumps(geom_summary, indent=2, default=str),
        encoding="utf-8",
    )

    # 3. Plot: base + product + geom-mean per species/stage.
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=False)
    series_cols = [
        ("wua_m2_schizothorax_prenanti_juvenile", "S. prenanti — juvenile"),
        ("wua_m2_schizothorax_prenanti_spawning", "S. prenanti — spawning"),
    ]
    for ax, (col, title) in zip(axes, series_cols, strict=False):
        ax.plot(
            base["discharge_m3s"], base[col],
            "k-", lw=2, label="base (d × v only)",
        )
        ax.plot(
            product_df["discharge_m3s"],
            product_df[f"wua_m2_composite_{col[len('wua_m2_'):]}"],
            "C1--", lw=2, label="composite (product)",
        )
        ax.plot(
            geom_df["discharge_m3s"],
            geom_df[f"wua_m2_composite_{col[len('wua_m2_'):]}"],
            "C2:", lw=2.2, label="composite (geom_mean)",
        )
        ax.set_xlabel("Discharge (m³/s)")
        ax.set_ylabel("WUA (m²)")
        ax.set_title(title)
        ax.legend(loc="best", fontsize=8)
        ax.grid(True, alpha=0.3)

    fig.suptitle(
        "Heihe mid-basin: WUA-Q with cover × thermal composite overlay\n"
        f"cover_si={overlay.cover_si:.3f}  "
        f"thermal_si={overlay.thermal_si:.3f}  "
        f"overlay_si={overlay.overlay_si:.4f}",
        fontsize=11,
    )
    fig.tight_layout()
    png = OUT / "wua_q_overlay_comparison.png"
    fig.savefig(png, dpi=120)
    print(f"\nComposite overlay comparison saved to {png}")

    # 4. Print headline numbers so reviewers don't need to open the JSONs.
    print("\nHeadline (per species/stage):")
    print(f"{'series':38s}  {'base_max':>10s}  {'product_max':>12s}  {'geom_max':>10s}")
    for prod_series, geom_series in zip(
        product_summary["by_species_stage"],
        geom_summary["by_species_stage"],
        strict=True,
    ):
        print(
            f"{prod_series['species_stage']:38s}  "
            f"{prod_series['wua_m2_base_max']:10.2f}  "
            f"{prod_series['wua_m2_composite_max']:12.2f}  "
            f"{geom_series['wua_m2_composite_max']:10.2f}"
        )


if __name__ == "__main__":
    main()

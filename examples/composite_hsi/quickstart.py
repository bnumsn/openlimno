"""composite_hsi end-to-end quickstart (v2.8.0).

Drives the v2.7.x dual-raster (thermal + cover) per-cell composite
pipeline from a real case.yaml, no synthetic in-script construction:

    PYTHONPATH=src python examples/composite_hsi/quickstart.py

Produces in ``examples/composite_hsi/out/composite_hsi_demo/``:

    wua_q.csv / .parquet                — depth × velocity WUA per Q.
    composite_wua_q.csv / .parquet      — true 4-way per-cell composite.
    composite_hsi.json                  — overlay factors + per-series stats.
    provenance.json                     — full run audit trail.
    thermal_hsi.csv, cover_si.json      — basin-scalar overlays (kept for
                                          back-compat alongside the per-
                                          section arrays produced by
                                          v2.7.0 R9-7 + v2.7.0 synth).

Compared to the v1.10.0 quickstart that built synthetic DataFrames
inline, this v2.8.0 script exercises:

    Case.from_yaml(case.yaml)
        → loads cross_section / HSI / species / life_stage
        → reads data.thermal_raster + data.section_locations and runs
          ``rasterio.sample`` per section to build per_section_thermal_si
        → reads data.cover_raster + data.section_locations and looks up
          ``DEFAULT_RIPARIAN_COVER_SI`` per section to build
          per_section_cover_si
        → routes both arrays through apply_overlay_per_cell with
          method="geom_mean", producing a true (d × v × c × t)^(1/4)
          per-cell composite

i.e. the *full* v2.0.0 charter "YAML-driven per-cell raster overlay
end-to-end" closed by v2.7.1.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from openlimno.case import Case

HERE = Path(__file__).resolve().parent
CASE_YAML = HERE / "case.yaml"


def main() -> None:
    case = Case.from_yaml(CASE_YAML)
    print(f"Loaded case '{case.name}' from {CASE_YAML}")

    Qs = list(np.logspace(0, np.log10(30), 12))
    print(f"Sweeping {len(Qs)} discharges from {Qs[0]:.2f} to {Qs[-1]:.2f} m³/s")
    result = case.run(discharges_m3s=Qs, slope=0.002, manning_n=0.035)
    print(result.summary())
    print(f"  output_dir: {result.output_dir}")

    # Read the composite_hsi.json so we can print headline stats.
    composite_json = result.output_dir / "composite_hsi.json"
    if composite_json.exists():
        payload = json.loads(composite_json.read_text())
        print(f"\nComposite overlay (method={payload.get('method')}):")
        print(f"  cover_si      = {payload.get('cover_si')}")
        print(f"  thermal_si    = {payload.get('thermal_si')}")
        print(f"  overlay_si    = {payload.get('overlay_si')}")
        print(f"  n_overlays    = {payload.get('n_overlays')}")
        print(f"  n_discharges  = {payload.get('n_discharges')}")
        print("\nPer-series headline (composite vs base WUA):")
        print(f"  {'series':38s}  {'base_max':>10s}  {'composite_max':>14s}  {'ratio':>8s}")
        # v2.10.1 R11-25: tolerate missing per-series keys. The
        # quickstart is illustrative, not error-handling exemplary —
        # but a failed/empty series shouldn't crash the whole report.
        for s in payload.get("by_species_stage", []):
            sid = s.get("species_stage", "<unknown>")
            base_max = s.get("wua_m2_base_max", float("nan"))
            comp_max = s.get("wua_m2_composite_max", float("nan"))
            ratio = s.get("composite_to_base_ratio")
            print(
                f"  {sid:38s}  "
                f"{base_max:10.2f}  "
                f"{comp_max:14.2f}  "
                f"{ratio if ratio is None else f'{ratio:8.4f}'}"
            )
    else:
        print("\n(No composite_hsi.json produced — overlay was skipped.)")

    # Plot the WUA-Q comparison: base depth × velocity (from wua_q) vs
    # the per-cell composite (from composite_wua_q). One subplot per
    # species/stage so the dual-raster softening is visible directly.
    if result.composite_wua_q is None:
        print("\n(No composite_wua_q in result — skipping plot.)")
        return

    df_base = result.wua_q
    df_comp = result.composite_wua_q
    series = [c[len("wua_m2_"):] for c in df_base.columns if c.startswith("wua_m2_")]
    n = len(series)
    fig, axes = plt.subplots(
        1, n, figsize=(6 * n, 5), sharey=False, squeeze=False,
    )
    for ax, suffix in zip(axes[0], series, strict=True):
        ax.plot(
            df_base["discharge_m3s"],
            df_base[f"wua_m2_{suffix}"],
            "k-", lw=2, label="base (d × v only)",
        )
        comp_col = f"wua_m2_composite_{suffix}"
        if comp_col in df_comp.columns:
            ax.plot(
                df_comp["discharge_m3s"],
                df_comp[comp_col],
                "C1--", lw=2,
                label="composite (d × v × c × t)^(¼)",
            )
        ax.set_xscale("log")
        ax.set_xlabel("Discharge (m³/s)")
        ax.set_ylabel("WUA (m²)")
        ax.set_title(suffix.replace("_", " ").title())
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", fontsize=9)
    fig.suptitle(
        f"composite_hsi v2.8.0 — case '{case.name}'\n"
        f"per-cell composite via inline thermal + cover rasters",
        fontsize=11,
    )
    fig.tight_layout()
    png = result.output_dir / "composite_wua_q_comparison.png"
    fig.savefig(png, dpi=120)
    print(f"\nComparison plot saved to {png}")

    if result.warnings:
        print(f"\n{len(result.warnings)} warning(s) during the run:")
        for w in result.warnings[:8]:
            print(f"  - {w}")


if __name__ == "__main__":
    main()

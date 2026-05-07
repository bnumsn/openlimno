"""Lemhi quickstart: load the canonical case, sweep flows, plot WUA-Q.

Run from repo root:
    PYTHONPATH=src python examples/lemhi/quickstart.py

Output:
    examples/lemhi/out/lemhi_2024/wua_q.{csv,parquet}
    examples/lemhi/out/lemhi_2024/hydraulics.nc
    examples/lemhi/out/lemhi_2024/provenance.json
    examples/lemhi/out/lemhi_2024/wua_q_curve.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from openlimno.case import Case

HERE = Path(__file__).resolve().parent


def main() -> None:
    case = Case.from_yaml(HERE / "case.yaml")
    print(f"Loaded case '{case.name}' from {case.case_yaml_path}")

    # Sweep 12 flows across Lemhi's typical 1-30 m3/s range
    Qs = list(np.logspace(0, np.log10(30), 12))
    result = case.run(discharges_m3s=Qs, slope=0.002, manning_n=0.035)
    print(result.summary())

    # WUA-Q plot
    df = result.wua_q
    fig, ax = plt.subplots(figsize=(8, 5))
    species_stages = [c for c in df.columns if c.startswith("wua_m2_")]
    for col in species_stages:
        label = col.replace("wua_m2_", "").replace("_", " ").title()
        ax.plot(df["discharge_m3s"], df[col], "o-", label=label, lw=2, markersize=6)
    ax.set_xlabel("Discharge (m³/s)")
    ax.set_ylabel("WUA (m²)")
    ax.set_xscale("log")
    ax.set_title(f"Lemhi River WUA-Q curve\n(case: {case.name})")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)

    # SPEC §4.2.2.1 / ADR-0006: watermark when ≥1 C-grade HSI used
    import json as _json
    prov = _json.loads(result.provenance_path.read_text())
    grade = prov.get("wua_quality_grade", "A")
    if grade == "C":
        ax.text(
            0.5, 0.5, "C-GRADE HSI — TENTATIVE",
            transform=ax.transAxes, ha="center", va="center",
            fontsize=42, color="red", alpha=0.18,
            rotation=18, weight="bold",
        )
    elif grade == "B":
        ax.text(
            0.99, 0.01, "HSI quality: B (transferred from PNW USFWS Blue Book)",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=8, color="gray",
        )
    fig.tight_layout()

    out = result.output_dir / "wua_q_curve.png"
    fig.savefig(out, dpi=120)
    print(f"\nWUA-Q curve saved to {out}")

    if result.warnings:
        print(f"\nRun produced {len(result.warnings)} warnings:")
        for w in result.warnings[:10]:
            print(f"  - {w}")


if __name__ == "__main__":
    main()

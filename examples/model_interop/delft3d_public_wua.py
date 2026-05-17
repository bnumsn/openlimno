"""End-to-end public Delft3D NetCDF fixture -> OpenLimno WUA example.

This script downloads a small public Delft3D NetCDF result file from MHKiT,
imports all time steps into OpenLimno hydraulic-cell tables, evaluates a
demonstration HSI curve, and writes habitat/WUA outputs plus a simple report.

The HSI curves below are synthetic workflow fixtures. They are useful for
testing the OpenLimno path, not for regulatory habitat conclusions.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import urllib.request
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import xarray as xr

from openlimno.habitat import evaluate_habitat_cells, load_hsi_from_parquet
from openlimno.preprocess import inspect_netcdf_hydraulic, read_external_model

FIXTURE_URL = (
    "https://raw.githubusercontent.com/MHKiT-Software/MHKiT-Python/main/"
    "examples/data/river/d3d/turbineTest_map.nc"
)
FIXTURE_NAME = "turbineTest_map.nc"
FIXTURE_SHA256 = "1376eb803df69bfb248e2a395e23de001ed3f03f386607f3c1c02a1c6a941a9d"

SPECIES = "demo_salmonid"
LIFE_STAGE = "adult"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_fixture(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / FIXTURE_NAME
    if target.exists() and sha256(target) == FIXTURE_SHA256:
        return target

    request = urllib.request.Request(
        FIXTURE_URL,
        headers={"User-Agent": "OpenLimno public interop example"},
    )
    tmp = target.with_suffix(".download")
    with urllib.request.urlopen(request) as response, tmp.open("wb") as f:
        shutil.copyfileobj(response, f)
    actual = sha256(tmp)
    if actual != FIXTURE_SHA256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"{FIXTURE_NAME} SHA256 mismatch: expected {FIXTURE_SHA256}, got {actual}"
        )
    tmp.replace(target)
    return target


def n_timesteps(netcdf_path: Path) -> int:
    with xr.open_dataset(netcdf_path) as ds:
        if "time" not in ds.sizes:
            return 1
        return int(ds.sizes["time"])


def write_demo_hsi(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "species": SPECIES,
                "life_stage": LIFE_STAGE,
                "variable": "depth",
                "points": [[0.0, 0.0], [0.8, 0.4], [1.5, 1.0], [2.2, 1.0], [3.0, 0.4]],
                "category": "III",
                "geographic_origin": "workflow-demo",
                "transferability_score": 0.0,
                "quality_grade": "C",
                "independence_tested": False,
                "evidence": [
                    "Synthetic demonstration curve for OpenLimno interop example; "
                    "replace before ecological or regulatory use."
                ],
            },
            {
                "species": SPECIES,
                "life_stage": LIFE_STAGE,
                "variable": "velocity",
                "points": [[0.0, 0.0], [0.4, 0.5], [0.8, 1.0], [1.2, 1.0], [1.8, 0.2]],
                "category": "III",
                "geographic_origin": "workflow-demo",
                "transferability_score": 0.0,
                "quality_grade": "C",
                "independence_tested": False,
                "evidence": [
                    "Synthetic demonstration curve for OpenLimno interop example; "
                    "replace before ecological or regulatory use."
                ],
            },
        ]
    ).to_parquet(path, index=False)


def import_all_timesteps(netcdf_path: Path, count: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for time_index in range(count):
        result = read_external_model(netcdf_path, source="delft3d-netcdf", time_index=time_index)
        frames.append(result.table)
    return pd.concat(frames, ignore_index=True)


def write_plot(summary: pd.DataFrame, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.plot(summary["time_index"], summary["wua_m2"], marker="o", linewidth=2)
    ax.set_xlabel("Time index")
    ax.set_ylabel("Weighted usable area (m²)")
    ax.set_title("OpenLimno WUA from public Delft3D NetCDF fixture")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def write_report(
    *,
    out_path: Path,
    netcdf_path: Path,
    cells: pd.DataFrame,
    summary: pd.DataFrame,
    plot_name: str,
) -> None:
    best = summary.sort_values("wua_m2", ascending=False).iloc[0]
    text = f"""# Public Delft3D NetCDF -> OpenLimno WUA Report

## Source

- File: `{netcdf_path}`
- Source URL: {FIXTURE_URL}
- SHA-256: `{FIXTURE_SHA256}`
- Imported hydraulic cells: {len(cells):,}
- Time groups: {len(summary):,}

## Demonstration HSI

Species/stage: `{SPECIES}` / `{LIFE_STAGE}`

Synthetic demonstration curve warning: the HSI curves used here validate the
OpenLimno import and habitat-evaluation path, but they must be replaced with
site- and species-appropriate curves before ecological or regulatory use.

## WUA Summary

- Peak WUA: {float(best["wua_m2"]):,.3f} m²
- Peak time index: {int(best["time_index"])}
- Mean CSI at peak: {float(best["mean_csi"]):.4f}
- Total wetted cell area at peak: {float(best["area_m2"]):,.3f} m²

![WUA time series]({plot_name})
"""
    out_path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".openlimno-fixtures") / "delft3d",
        help="Directory for downloaded public fixtures.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("examples/model_interop/out/delft3d_public_wua"),
        help="Directory for generated example outputs.",
    )
    args = parser.parse_args()

    netcdf_path = download_fixture(args.cache_dir)
    inspection = inspect_netcdf_hydraulic(netcdf_path)
    if inspection.n_cells is None:
        raise RuntimeError("NetCDF fixture did not expose cell-aligned hydraulic variables")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    hsi_path = args.out_dir / "demo_hsi_curve.parquet"
    write_demo_hsi(hsi_path)

    hydraulic_cells = import_all_timesteps(netcdf_path, n_timesteps(netcdf_path))
    hydraulic_cells_path = args.out_dir / "hydraulic_cells.parquet"
    hydraulic_cells.to_parquet(hydraulic_cells_path, index=False)

    curves = load_hsi_from_parquet(hsi_path)
    habitat = evaluate_habitat_cells(
        hydraulic_cells,
        curves,
        species=SPECIES,
        life_stage=LIFE_STAGE,
        composite="min",
    )
    habitat.cells.to_parquet(args.out_dir / "habitat_cells.parquet", index=False)
    habitat.summary.to_csv(args.out_dir / "wua_summary.csv", index=False)
    habitat.hmu_summary.to_csv(args.out_dir / "wua_hmu.csv", index=False)

    plot_path = args.out_dir / "wua_timeseries.png"
    write_plot(habitat.summary, plot_path)
    write_report(
        out_path=args.out_dir / "REPORT.md",
        netcdf_path=netcdf_path,
        cells=hydraulic_cells,
        summary=habitat.summary,
        plot_name=plot_path.name,
    )
    print(f"Wrote OpenLimno Delft3D NetCDF WUA example outputs to {args.out_dir}")


if __name__ == "__main__":
    main()

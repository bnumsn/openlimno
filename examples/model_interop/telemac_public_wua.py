"""End-to-end public TELEMAC fixture -> OpenLimno WUA example.

This script downloads a small public TELEMAC Selafin result file, imports all
time steps into OpenLimno hydraulic-cell tables, evaluates a demonstration HSI
curve, and writes habitat/WUA outputs plus a simple report.

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

from openlimno.habitat import evaluate_habitat_cells, load_hsi_from_parquet
from openlimno.preprocess import inspect_telemac_selafin, read_external_model

FIXTURE_URL = (
    "https://raw.githubusercontent.com/hydro-informatics/telemac/main/"
    "unsteady2d-tutorial/r2dsteady-t15k.slf"
)
FIXTURE_NAME = "r2dsteady-t15k.slf"
FIXTURE_SHA256 = "059bcc982801a653374991f48465fac28b3a725c8f37aeab56e2c0cae8fedc4c"

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


def write_demo_hsi(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "species": SPECIES,
                "life_stage": LIFE_STAGE,
                "variable": "depth",
                "points": [[0.0, 0.0], [0.25, 0.4], [0.6, 1.0], [1.4, 1.0], [2.5, 0.2]],
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
                "points": [[0.0, 0.0], [0.25, 0.6], [0.5, 1.0], [1.2, 1.0], [2.2, 0.0]],
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


def import_all_timesteps(slf_path: Path, n_timesteps: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for time_index in range(n_timesteps):
        result = read_external_model(slf_path, source="telemac-slf", time_index=time_index)
        frames.append(result.table)
    return pd.concat(frames, ignore_index=True)


def write_plot(summary: pd.DataFrame, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    x = summary["time_s"] / 3600.0 if "time_s" in summary else summary["time_index"]
    ax.plot(x, summary["wua_m2"], marker="o", linewidth=2)
    ax.set_xlabel("Time (hours)" if "time_s" in summary else "Time index")
    ax.set_ylabel("Weighted usable area (m²)")
    ax.set_title("OpenLimno WUA from public TELEMAC Selafin fixture")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def write_report(
    *,
    out_path: Path,
    slf_path: Path,
    cells: pd.DataFrame,
    summary: pd.DataFrame,
    plot_name: str,
) -> None:
    best = summary.sort_values("wua_m2", ascending=False).iloc[0]
    text = f"""# Public TELEMAC -> OpenLimno WUA Report

## Source

- File: `{slf_path}`
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
- Peak time index: {int(best["time_index"]) if "time_index" in best else "n/a"}
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
        default=Path(".openlimno-fixtures") / "telemac",
        help="Directory for downloaded public fixtures.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("examples/model_interop/out/telemac_public_wua"),
        help="Directory for generated example outputs.",
    )
    args = parser.parse_args()

    slf_path = download_fixture(args.cache_dir)
    inspection = inspect_telemac_selafin(slf_path)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    hsi_path = args.out_dir / "demo_hsi_curve.parquet"
    write_demo_hsi(hsi_path)

    hydraulic_cells = import_all_timesteps(slf_path, inspection.n_timesteps)
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
        slf_path=slf_path,
        cells=hydraulic_cells,
        summary=habitat.summary,
        plot_name=plot_path.name,
    )
    print(f"Wrote OpenLimno TELEMAC WUA example outputs to {args.out_dir}")


if __name__ == "__main__":
    main()

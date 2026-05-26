"""Build the Wallens Bend real HEC-RAS hydraulic + IBM example.

Data source:
USGS ScienceBase data release "One-dimensional hydraulic and environmental DNA
transport models for the Wallens Bend reach of the Clinch River, near Kyles
Ford, Tennessee" (doi:10.5066/P9D7NCH1).

The script downloads/extracts the HEC-RAS model archive, imports the HEC-RAS
cross-section geometry, calibrates slope/Manning n against the 2021-09-08 field
WSE/velocity CSVs, solves steady hydraulic cells with OpenLimno's built-in 1D
solver for every published HEC-RAS flow file, and writes a runnable IBM scenario.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import zipfile
from collections.abc import Iterable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import yaml

from openlimno.hydro import (
    Builtin1D,
    CrossSection,
    SCHISMAdapter,
    read_schism_hydraulic_results,
    write_schism_hydraulic_cells_csv,
    write_schism_type1_boundary_forcing,
)
from openlimno.hydro.calibration import Builtin1DCalibrationResult, calibrate_builtin1d_normal_depth
from openlimno.ibm.scenario import run_ibm_scenario
from openlimno.preprocess import read_external_model, write_hecras_gis_ugrid

EXAMPLE_DIR = Path(__file__).resolve().parent
DATA_DIR = EXAMPLE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
MODEL_DIR = RAW_DIR / "WB_HECRAS_ModelFiles"

MODEL_ZIP_URL = (
    "https://www.sciencebase.gov/catalog/file/get/63238571d34e71c6d67acbdf?"
    "f=__disk__06%2F4f%2F09%2F064f096a09254fc43cd21d7ba5bc475bc10a185c"
)
WSE_20210908_URL = (
    "https://www.sciencebase.gov/catalog/file/get/63237e7ad34e71c6d67acbaf?"
    "f=__disk__51%2F40%2F09%2F514009c30a159f5f3a7285d0a55906868c409848"
)
VEL_20210908_URL = (
    "https://www.sciencebase.gov/catalog/file/get/63237e7ad34e71c6d67acbaf?"
    "f=__disk__f3%2F6f%2F2a%2Ff36f2aca7e1c142305315d84b381bbe786b895a2"
)
G01_PATH = MODEL_DIR / "WBmod1D.g01"
CLINCH_REACHES = ("Upper Reach", "Main Stem", "Middle Reach", "Lower Reach")


def _download(url: str, path: Path, *, offline: bool) -> None:
    if path.exists():
        return
    if offline:
        raise FileNotFoundError(f"{path} is missing and --offline was set.")
    path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "OpenLimno Wallens Bend real case builder"})
    with urlopen(request, timeout=120) as response:
        path.write_bytes(response.read())


def _ensure_raw(*, offline: bool) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    model_zip = RAW_DIR / "WB_HECRAS_ModelFiles.zip"
    _download(MODEL_ZIP_URL, model_zip, offline=offline)
    _download(WSE_20210908_URL, RAW_DIR / "WB_WaterSurfElev_20210908.csv", offline=offline)
    _download(VEL_20210908_URL, RAW_DIR / "WB_Velocity_20210908.csv", offline=offline)
    if not G01_PATH.exists():
        if offline and not model_zip.exists():
            raise FileNotFoundError(f"{model_zip} is missing and --offline was set.")
        with zipfile.ZipFile(model_zip) as zf:
            zf.extractall(RAW_DIR)
    if not G01_PATH.exists():
        raise FileNotFoundError(f"Expected HEC-RAS geometry file not found: {G01_PATH}")


def _read_flow_file(path: Path, time_index: int) -> tuple[pd.DataFrame, str]:
    lines = path.read_text(encoding="latin-1", errors="replace").splitlines()
    profile = path.stem
    for line in lines:
        if line.startswith("Profile Names="):
            profile = line.split("=", 1)[1].strip()
            break
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        if not line.startswith("River Rch & RM="):
            continue
        parts = [part.strip() for part in line.split("=", 1)[1].split(",")]
        if len(parts) < 3 or i + 1 >= len(lines):
            continue
        try:
            discharge = float(lines[i + 1].strip())
            station = float(parts[2])
        except ValueError:
            continue
        rows.append(
            {
                "time_index": time_index,
                "profile": profile,
                "date": f"{profile[:4]}-{profile[4:6]}-{profile[6:8]}"
                if len(profile) == 8
                else profile,
                "flow_file": path.name,
                "river": parts[0],
                "reach": parts[1],
                "upstream_station_m": station,
                "discharge_m3s": discharge,
            }
        )
    if not rows:
        raise ValueError(f"No flow records parsed from {path}")
    return pd.DataFrame(rows), profile


def _load_flows() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for index, path in enumerate(sorted(MODEL_DIR.glob("WBmod1D.f0*"))):
        frame, _profile = _read_flow_file(path, index)
        frames.append(frame)
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(DATA_DIR / "hecras_flows.csv", index=False)
    return out


def _cell_id(reach: str, station_m: float) -> str:
    safe_reach = "".join(ch.lower() if ch.isalnum() else "_" for ch in reach).strip("_")
    safe_station = str(round(float(station_m), 3)).replace(".", "_")
    return f"clinch_{safe_reach}_{safe_station}"


def _reach_id(reach: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in reach).strip("_")
    return f"clinch_{safe}"


def _reach_order(reach: str) -> int:
    order = {name: index for index, name in enumerate(CLINCH_REACHES, start=1)}
    return order.get(reach, 99)


def _length_by_station(section_keys: pd.DataFrame) -> dict[tuple[str, float], float]:
    lengths: dict[tuple[str, float], float] = {}
    for reach, sub in section_keys.groupby("reach"):
        stations = sorted(float(v) for v in sub["station_m"].unique())
        if len(stations) == 1:
            lengths[(reach, stations[0])] = 50.0
            continue
        diffs = np.diff(stations)
        for i, station in enumerate(stations):
            if i == 0:
                length = abs(float(diffs[0]))
            elif i == len(stations) - 1:
                length = abs(float(diffs[-1]))
            else:
                length = abs(float(stations[i + 1] - stations[i - 1])) * 0.5
            lengths[(reach, station)] = max(length, 1.0)
    return lengths


def _prepare_clinch_sections(
    cross_sections: pd.DataFrame,
    *,
    manning_n: float,
) -> tuple[pd.DataFrame, dict[tuple[str, float], float], list[tuple[str, float, CrossSection]]]:
    main = cross_sections[cross_sections["river"].eq("Clinch River")].copy()
    main = main[main["reach"].isin(CLINCH_REACHES)]
    section_keys = main[["reach", "station_m"]].drop_duplicates()
    lengths = _length_by_station(section_keys)
    sections: list[tuple[str, float, CrossSection]] = []
    for (reach, station), sub in main.groupby(["reach", "station_m"], sort=False):
        ordered = sub.sort_values("point_index")
        sections.append(
            (
                str(reach),
                float(station),
                CrossSection(
                    station_m=float(station),
                    distance_m=ordered["distance_m"].to_numpy(dtype=float),
                    elevation_m=ordered["elevation_m"].to_numpy(dtype=float),
                    manning_n=manning_n,
                ),
            )
        )
    return main, lengths, sections


def _build_hydraulic_cells(
    cross_sections: pd.DataFrame,
    flows: pd.DataFrame,
    *,
    slope: float,
    manning_n: float,
) -> pd.DataFrame:
    main, lengths, sections = _prepare_clinch_sections(cross_sections, manning_n=manning_n)
    main.to_parquet(DATA_DIR / "cross_sections_clinch.parquet", index=False)

    flow_lookup = {
        (int(row.time_index), str(row.river), str(row.reach)): float(row.discharge_m3s)
        for row in flows.itertuples(index=False)
    }
    date_lookup = {
        int(row.time_index): str(row.date)
        for row in flows[["time_index", "date"]].drop_duplicates().itertuples(index=False)
    }
    solver = Builtin1D(slope=slope)
    rows: list[dict[str, Any]] = []
    for time_index in sorted(flows["time_index"].unique()):
        for reach, station, xs in sections:
            q = flow_lookup[(int(time_index), "Clinch River", reach)]
            result = solver.solve_normal_depth(xs, q, slope=slope)
            top_width = max(float(result.top_width_m), 0.1)
            planform_length = lengths[(reach, station)]
            planform_area = max(planform_length * top_width, float(result.area_m2), 1.0)
            depth = float(result.depth_mean_m)
            velocity = float(result.velocity_mean_ms)
            depth_si = _triangular(depth, low=0.05, optimum=0.65, high=2.5)
            velocity_si = _triangular(velocity, low=0.0, optimum=0.35, high=1.8)
            csi = math.sqrt(depth_si * velocity_si)
            rows.append(
                {
                    "time_index": int(time_index),
                    "date": date_lookup[int(time_index)],
                    "cell_id": _cell_id(reach, station),
                    "reach_id": _reach_id(reach),
                    "reach_order": _reach_order(reach),
                    "river": "Clinch River",
                    "hecras_reach": reach,
                    "station_m": station,
                    "length_m": planform_length,
                    "area_m2": planform_area,
                    "discharge_m3s": q,
                    "water_surface_m": float(result.water_surface_m),
                    "depth_m": depth,
                    "velocity_ms": velocity,
                    "flow_area_m2": float(result.area_m2),
                    "top_width_m": float(result.top_width_m),
                    "hydraulic_radius_m": float(result.hydraulic_radius_m),
                    "csi": max(0.0, min(1.0, csi)),
                    "temperature_c": 12.0,
                    "turbidity_ntu": 1.0,
                    "hiding_cover": 0.25,
                    "feeding_cover": 0.20 + 0.35 * max(0.0, min(1.0, csi)),
                    "spawning_cover": 0.15,
                    "hydraulic_source": "usgs-hecras-geometry-openlimno-builtin-1d",
                    "manning_n": manning_n,
                    "slope": slope,
                }
            )
    out = pd.DataFrame(rows)
    out.to_csv(DATA_DIR / "hydraulic_cells.csv", index=False)
    return out


def _calibrate_hydraulic_parameters(
    cross_sections: pd.DataFrame,
    flows: pd.DataFrame,
    *,
    calibration_date: str,
    slopes: Iterable[float],
    manning_ns: Iterable[float],
    wse_weight: float,
    velocity_weight: float,
) -> Builtin1DCalibrationResult:
    if calibration_date != "2021-09-08":
        raise ValueError(
            "Wallens Bend currently ships observed WSE/velocity calibration for 2021-09-08"
        )
    _main, _lengths, section_rows = _prepare_clinch_sections(cross_sections, manning_n=0.04)
    flow_rows = flows[flows["date"].eq(calibration_date)]
    if flow_rows.empty:
        raise ValueError(f"No flow profile found for calibration date {calibration_date}")
    q_by_reach = {
        str(row.reach): float(row.discharge_m3s)
        for row in flow_rows[flow_rows["river"].eq("Clinch River")].itertuples(index=False)
    }
    sections = [xs for _reach, _station, xs in section_rows]
    discharges = [q_by_reach[reach] for reach, _station, _xs in section_rows]
    wse_obs = pd.read_csv(RAW_DIR / "WB_WaterSurfElev_20210908.csv").rename(
        columns={"station": "station_m", "meas_wse": "water_surface_m"}
    )
    vel_obs = pd.read_csv(RAW_DIR / "WB_Velocity_20210908.csv").rename(
        columns={"station": "station_m", "meas_vavg": "velocity_ms"}
    )
    result = calibrate_builtin1d_normal_depth(
        sections,
        discharges,
        wse_observations=wse_obs,
        velocity_observations=vel_obs,
        station_column="station_m",
        wse_column="water_surface_m",
        velocity_column="velocity_ms",
        slopes=tuple(slopes),
        manning_ns=tuple(manning_ns),
        wse_weight=wse_weight,
        velocity_weight=velocity_weight,
    )
    result.candidates.to_csv(DATA_DIR / "hydraulic_calibration_grid.csv", index=False)
    (DATA_DIR / "hydraulic_calibration_best.json").write_text(
        json.dumps(asdict(result.best), indent=2),
        encoding="utf-8",
    )
    return result


def _triangular(value: float, *, low: float, optimum: float, high: float) -> float:
    if value <= low or value >= high:
        return 0.0
    if value <= optimum:
        return (value - low) / max(optimum - low, 1e-9)
    return (high - value) / max(high - optimum, 1e-9)


def _nearest_join(obs: pd.DataFrame, pred: pd.DataFrame, obs_station_col: str) -> pd.DataFrame:
    stations = pred["station_m"].to_numpy(dtype=float)
    indices = np.abs(
        obs[obs_station_col].to_numpy(dtype=float)[:, None] - stations[None, :]
    ).argmin(axis=1)
    matched = pred.iloc[indices].reset_index(drop=True)
    return pd.concat([obs.reset_index(drop=True), matched.add_prefix("pred_")], axis=1)


def _write_calibration(hydraulic_cells: pd.DataFrame) -> pd.DataFrame:
    pred = hydraulic_cells[hydraulic_cells["date"].eq("2021-09-08")].copy()
    wse_obs = pd.read_csv(RAW_DIR / "WB_WaterSurfElev_20210908.csv")
    vel_obs = pd.read_csv(RAW_DIR / "WB_Velocity_20210908.csv")
    wse_cmp = _nearest_join(wse_obs, pred, "station")
    wse_cmp["wse_error_m"] = wse_cmp["pred_water_surface_m"] - wse_cmp["meas_wse"]
    vel_cmp = _nearest_join(vel_obs, pred, "station")
    vel_cmp["velocity_error_ms"] = vel_cmp["pred_velocity_ms"] - vel_cmp["meas_vavg"]
    wse_cmp.to_csv(DATA_DIR / "calibration_wse_20210908.csv", index=False)
    vel_cmp.to_csv(DATA_DIR / "calibration_velocity_20210908.csv", index=False)
    summary = pd.DataFrame(
        [
            {
                "metric": "wse_20210908_rmse_m",
                "n": int(len(wse_cmp)),
                "value": float(np.sqrt(np.mean(wse_cmp["wse_error_m"] ** 2))),
            },
            {
                "metric": "velocity_20210908_rmse_ms",
                "n": int(len(vel_cmp)),
                "value": float(np.sqrt(np.mean(vel_cmp["velocity_error_ms"] ** 2))),
            },
        ]
    )
    summary.to_csv(DATA_DIR / "calibration_summary.csv", index=False)
    return summary


def _write_profile() -> None:
    profile = {
        "profile_version": "0.2",
        "species": {
            "id": "rainbow_trout",
            "scientific_name": "Oncorhynchus mykiss",
            "common_name": "Rainbow trout",
            "evidence_status": "screening profile for software validation",
        },
        "parameters": {
            "thermal_min_c": {"value": 1.0, "source": "OpenLimno native IBM default"},
            "thermal_optimum_c": {"value": 12.0, "source": "OpenLimno native IBM default"},
            "thermal_max_c": {"value": 23.0, "source": "OpenLimno native IBM default"},
            "base_daily_survival": {"value": 0.997, "source": "OpenLimno native IBM default"},
            "carrying_density_per_m2": {"value": 0.08, "source": "OpenLimno native IBM default"},
        },
        "calibration": {
            "accepted": False,
            "notes": "Hydraulics are based on real HEC-RAS geometry; IBM profile is not site-calibrated.",
        },
    }
    (EXAMPLE_DIR / "profile_rainbow_trout.yaml").write_text(
        yaml.safe_dump(profile, sort_keys=False),
        encoding="utf-8",
    )


def _write_population(cell_ids: Iterable[str]) -> None:
    rng = random.Random(6323764)
    ids = list(cell_ids)
    rows: list[dict[str, Any]] = []
    for fish_id in range(260):
        length_mm = max(45.0, min(220.0, rng.gauss(112.0, 22.0)))
        mass_g = 0.0115 * (length_mm / 10.0) ** 3.0
        rows.append(
            {
                "fish_id": fish_id,
                "species": "rainbow_trout",
                "age_days": int(max(90.0, min(900.0, rng.gauss(365.0, 120.0)))),
                "length_mm": round(length_mm, 3),
                "mass_g": round(mass_g, 5),
                "cell_id": rng.choice(ids),
                "alive": True,
            }
        )
    pd.DataFrame(rows).to_csv(DATA_DIR / "initial_population.csv", index=False)


def _write_scenario(days: int) -> Path:
    scenario = {
        "ibm_version": "0.2",
        "scenario": {
            "id": "wallens-bend-clinch-real-hecras-ibm",
            "description": (
                "Wallens Bend Clinch River real HEC-RAS geometry converted to "
                "OpenLimno hydraulic cells and native IBM forcing."
            ),
            "reach_id": "clinch_wallens_bend",
            "days": days,
            "start_day": 267,
            "start_year": 2019,
            "seed": 6323764,
            "stochastic": True,
            "light_phases": ["dawn", "day", "dusk", "night"],
        },
        "profile": {"uri": "profile_rainbow_trout.yaml"},
        "forcing": {
            "habitat_cells": "data/hydraulic_cells.csv",
            "time_index_column": "time_index",
        },
        "population": {
            "initial_population": "data/initial_population.csv",
            "default_species": "rainbow_trout",
            "initial_abundance": 260,
            "initial_length_mm": 112.0,
        },
        "outputs": {
            "dir": "out/native",
            "formats": ["csv"],
            "individual_history": False,
            "manifest": True,
        },
    }
    path = EXAMPLE_DIR / "scenario.yaml"
    path.write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
    return path


def _schism_open_boundary_sections(cross_sections: pd.DataFrame) -> list[dict[str, Any]]:
    frame = cross_sections[cross_sections["river"].astype(str).eq("Clinch River")].copy()
    boundary_id = 1
    boundaries: list[dict[str, Any]] = []
    for reach in CLINCH_REACHES:
        reach_frame = frame[frame["reach"].astype(str).eq(reach)]
        stations = sorted(
            (float(v) for v in reach_frame["station_m"].dropna().unique()),
            reverse=True,
        )
        if len(stations) < 2:
            continue
        for role, station in (
            ("upstream_inflow", stations[0]),
            ("downstream_stage", stations[-1]),
        ):
            boundaries.append(
                {
                    "boundary_id": boundary_id,
                    "river": "Clinch River",
                    "reach": reach,
                    "role": role,
                    "station_m": station,
                }
            )
            boundary_id += 1
    return boundaries


def _write_schism_boundary_forcing(
    cross_sections: pd.DataFrame,
    flows: pd.DataFrame,
    hydraulic_cells: pd.DataFrame,
    work_dir: Path,
    *,
    stage_reference_m: float,
) -> dict[str, Any]:
    boundaries = _schism_open_boundary_sections(cross_sections)
    if not boundaries:
        raise ValueError("no Clinch River open boundary sections found")

    clinch_flows = flows[flows["river"].astype(str).eq("Clinch River")].copy()
    rows: list[dict[str, Any]] = []
    for boundary in boundaries:
        reach = str(boundary["reach"])
        station = float(boundary["station_m"])
        role = str(boundary["role"])
        reach_flows = clinch_flows[clinch_flows["reach"].astype(str).eq(reach)]
        reach_cells = hydraulic_cells[hydraulic_cells["hecras_reach"].astype(str).eq(reach)]
        if reach_flows.empty or reach_cells.empty:
            continue
        for flow_row in reach_flows.sort_values("time_index").itertuples(index=False):
            time_index = int(flow_row.time_index)
            cell_slice = reach_cells[reach_cells["time_index"].eq(time_index)].copy()
            if cell_slice.empty:
                continue
            nearest_idx = (cell_slice["station_m"].astype(float) - station).abs().idxmin()
            cell = cell_slice.loc[nearest_idx]
            discharge = float(flow_row.discharge_m3s)
            signed_discharge = discharge if role == "upstream_inflow" else -discharge
            rows.append(
                {
                    "boundary_id": int(boundary["boundary_id"]),
                    "river": boundary["river"],
                    "reach": reach,
                    "role": role,
                    "station_m": station,
                    "matched_station_m": float(cell["station_m"]),
                    "station_match_delta_m": abs(float(cell["station_m"]) - station),
                    "time_index": time_index,
                    "time_seconds": float(time_index * 86400.0),
                    "profile": str(flow_row.profile),
                    "date": str(flow_row.date),
                    "discharge_m3s": discharge,
                    "signed_discharge_m3s": signed_discharge,
                    "stage_m": float(cell["water_surface_m"]),
                    "depth_m": float(cell["depth_m"]),
                    "velocity_ms": float(cell["velocity_ms"]),
                    "boundary_condition_hint": "flow" if role == "upstream_inflow" else "stage",
                    "source": "USGS HEC-RAS flow profile + OpenLimno calibrated builtin-1d",
                }
            )

    forcing = pd.DataFrame(rows)
    if forcing.empty:
        raise ValueError("no SCHISM boundary forcing rows generated")
    forcing_path = work_dir / "open_boundary_forcing.csv"
    forcing.to_csv(forcing_path, index=False)
    simulation_end_seconds = float((int(forcing["time_index"].max()) + 1) * 86400.0)

    notes_path = work_dir / "open_boundary_forcing_notes.md"
    notes_path.write_text(
        "# Open boundary forcing\n\n"
        "`open_boundary_forcing.csv` maps directly to the open boundary order in "
        "`hgrid.gr3`.\n\n"
        "- `boundary_id` is 1-based and matches the SCHISM open-boundary segment order.\n"
        "- `discharge_m3s` is the positive HEC-RAS flow profile value for the reach.\n"
        "- `signed_discharge_m3s` is positive into the domain for upstream inflow and "
        "negative at downstream stage boundaries.\n"
        "- `stage_m`, `depth_m`, and `velocity_ms` come from the calibrated builtin-1d "
        "cell nearest to the boundary station.\n"
        "- `time_seconds` follows the OpenLimno scenario index, one HEC-RAS profile "
        "per simulated day; `date` preserves the source profile label.\n"
        "- `stage_m` remains the source vertical datum; `elev.th` subtracts the "
        "SCHISM depth/stage reference so boundary elevation and hgrid depth use "
        "one consistent datum.\n"
        "- `bctides.in`, `elev.th`, and `flux.th` are generated as SCHISM Type-1 "
        "time-history inputs. SCHISM uses negative flux for inflow, so `flux.th` "
        "has the opposite sign of `discharge_m3s` for upstream inflow boundaries.\n"
        "- The terminal SCHISM forcing row repeats the final source profile at "
        "the scenario end time so the numerical solver can complete the full "
        "requested duration without reading past the boundary files.\n"
        "- Review the generated flags, time step, and any missing tidal, salinity, "
        "or temperature requirements before a production SCHISM run.\n",
        encoding="utf-8",
    )
    package = write_schism_type1_boundary_forcing(
        forcing,
        work_dir,
        hgrid_path=work_dir / "hgrid.gr3",
        stage_reference_m=stage_reference_m,
        end_time_seconds=simulation_end_seconds,
    )
    return {
        "forcing_csv": str(forcing_path.relative_to(EXAMPLE_DIR)),
        "forcing_notes": str(notes_path.relative_to(EXAMPLE_DIR)),
        "forcing_rows": int(len(forcing)),
        "forcing_boundaries": int(forcing["boundary_id"].nunique()),
        "forcing_profiles": int(forcing["time_index"].nunique()),
        "max_station_match_delta_m": float(forcing["station_match_delta_m"].max()),
        "bctides": str(package.bctides_path.relative_to(EXAMPLE_DIR)),
        "elev_th": str(package.elev_th_path.relative_to(EXAMPLE_DIR))
        if package.elev_th_path is not None
        else None,
        "flux_th": str(package.flux_th_path.relative_to(EXAMPLE_DIR))
        if package.flux_th_path is not None
        else None,
        "flags_csv": str(package.flags_path.relative_to(EXAMPLE_DIR)),
        "forcing_manifest": str(package.manifest_path.relative_to(EXAMPLE_DIR)),
        "schism_elevation_boundaries": package.n_elevation_boundaries,
        "schism_flux_boundaries": package.n_flux_boundaries,
        "schism_stage_reference_m": float(stage_reference_m),
        "schism_forcing_end_time_seconds": simulation_end_seconds,
    }


def _write_schism_handoff(
    cross_sections: pd.DataFrame,
    flows: pd.DataFrame,
    hydraulic_cells: pd.DataFrame,
    scenario_path: Path,
    *,
    transverse_nodes: int,
    dry_run: bool,
    executable: str | None,
    container_image: str | None,
    container_runtime: str,
    n_procs: int,
    n_scribes: int,
    timeout_s: float | None,
) -> dict[str, Any] | None:
    if not {"x_m", "y_m"} <= set(cross_sections.columns):
        return None
    georef = cross_sections.dropna(subset=["x_m", "y_m"])
    if georef.empty:
        return None
    handoff_sections = georef[
        georef["river"].astype(str).eq("Clinch River")
        & georef["reach"].astype(str).isin(CLINCH_REACHES)
    ]
    depth_reference_m = (
        max(
            float(handoff_sections["elevation_m"].max()),
            float(hydraulic_cells["water_surface_m"].max()),
        )
        + 1.0
    )
    mesh_path = DATA_DIR / "wallens_bend_hecras_mesh_ugrid.nc"
    mesh_result = write_hecras_gis_ugrid(
        georef,
        mesh_path,
        river="Clinch River",
        reaches=CLINCH_REACHES,
        transverse_nodes=transverse_nodes,
        crs="HEC-RAS GIS project coordinates; projection metadata blank in source .g01",
        depth_reference_m=depth_reference_m,
    )
    work_dir = DATA_DIR / "schism_handoff"
    adapter = SCHISMAdapter(
        executable=executable,
        container_image=container_image,
        container_runtime=container_runtime,  # type: ignore[arg-type]
        n_procs=n_procs,
        n_scribes=n_scribes,
        timeout_s=timeout_s,
    )
    adapter.prepare(
        scenario_path,
        work_dir,
        wedm_mesh_path=mesh_path,
        param_overrides={"rnday": 9.0, "dt": 60.0},
    )
    forcing_summary = _write_schism_boundary_forcing(
        cross_sections,
        flows,
        hydraulic_cells,
        work_dir,
        stage_reference_m=depth_reference_m,
    )
    report = adapter.run(work_dir, dry_run=dry_run)
    result_summary = _maybe_write_schism_result_cells(work_dir)
    return {
        "ugrid_mesh": str(mesh_path.relative_to(EXAMPLE_DIR)),
        "work_dir": str(work_dir.relative_to(EXAMPLE_DIR)),
        "hgrid": str((work_dir / "hgrid.gr3").relative_to(EXAMPLE_DIR)),
        "param": str((work_dir / "param.nml").relative_to(EXAMPLE_DIR)),
        "n_sections": mesh_result.n_sections,
        "n_nodes": mesh_result.n_nodes,
        "n_faces": mesh_result.n_faces,
        "transverse_nodes": mesh_result.transverse_nodes,
        "n_open_boundaries": mesh_result.n_open_boundaries,
        "n_land_boundaries": mesh_result.n_land_boundaries,
        "n_open_boundary_nodes": mesh_result.n_open_boundary_nodes,
        "n_land_boundary_nodes": mesh_result.n_land_boundary_nodes,
        "schism_depth_reference_m": float(depth_reference_m),
        "boundary_forcing": forcing_summary,
        "schism_results": result_summary,
        "dry_run": report.dry_run,
        "return_code": report.return_code,
        "duration_seconds": report.duration_seconds,
        "log": str(report.log_path.relative_to(EXAMPLE_DIR)),
        "container_image": container_image,
        "container_runtime": container_runtime if container_image else None,
        "executable": executable,
        "n_procs": n_procs,
        "n_scribes": n_scribes,
    }


def _maybe_write_schism_result_cells(work_dir: Path) -> dict[str, Any]:
    try:
        results = read_schism_hydraulic_results(work_dir)
    except FileNotFoundError as exc:
        return {
            "available": False,
            "reason": str(exc),
        }
    except Exception as exc:
        return {
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    out_path = work_dir / "hydraulic_cells_schism.csv"
    write_schism_hydraulic_cells_csv(results, out_path)
    return {
        "available": True,
        "hydraulic_cells": str(out_path.relative_to(EXAMPLE_DIR)),
        "source_files": [str(path.relative_to(EXAMPLE_DIR)) for path in results.source_files],
        "rows": int(len(results.table)),
        "n_nodes": int(results.n_nodes),
        "n_times": int(results.n_times),
        "warnings": list(results.warnings),
    }


def _write_manifest(
    summary: dict[str, Any],
    calibration: pd.DataFrame,
    ibm_summary: dict[str, Any] | None,
    hydraulic_parameter_calibration: Builtin1DCalibrationResult | None,
    schism_handoff: dict[str, Any] | None,
) -> None:
    manifest = {
        "case_id": "wallens_bend_real",
        "generated_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source": {
            "title": (
                "One-dimensional hydraulic and environmental DNA transport models "
                "for the Wallens Bend reach of the Clinch River, near Kyles Ford, Tennessee"
            ),
            "doi": "10.5066/P9D7NCH1",
            "sciencebase": "https://www.sciencebase.gov/catalog/item/6323764ed34e71c6d67acb60",
        },
        "counts": summary,
        "hydraulic_parameter_calibration": asdict(hydraulic_parameter_calibration.best)
        if hydraulic_parameter_calibration is not None
        else None,
        "calibration": calibration.to_dict(orient="records"),
        "ibm": ibm_summary,
        "schism_handoff": schism_handoff,
    }
    (DATA_DIR / "source_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def build_case(
    *,
    offline: bool,
    run_ibm: bool,
    calibrate: bool,
    calibration_date: str,
    slope: float,
    manning_n: float,
    slope_grid: Iterable[float],
    manning_grid: Iterable[float],
    wse_weight: float,
    velocity_weight: float,
    schism_handoff: bool,
    schism_transverse_nodes: int,
    schism_dry_run: bool,
    schism_executable: str | None,
    schism_container_image: str | None,
    schism_container_runtime: str,
    schism_n_procs: int,
    schism_n_scribes: int,
    schism_timeout_s: float | None,
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_raw(offline=offline)
    imported = read_external_model(G01_PATH, source="hecras-geometry")
    cross_sections = imported.table
    cross_sections.to_parquet(DATA_DIR / "cross_sections_all.parquet", index=False)
    flows = _load_flows()
    hydraulic_parameter_calibration: Builtin1DCalibrationResult | None = None
    if calibrate:
        hydraulic_parameter_calibration = _calibrate_hydraulic_parameters(
            cross_sections,
            flows,
            calibration_date=calibration_date,
            slopes=slope_grid,
            manning_ns=manning_grid,
            wse_weight=wse_weight,
            velocity_weight=velocity_weight,
        )
        slope = hydraulic_parameter_calibration.best.slope
        manning_n = hydraulic_parameter_calibration.best.manning_n
    hydraulic_cells = _build_hydraulic_cells(
        cross_sections,
        flows,
        slope=slope,
        manning_n=manning_n,
    )
    calibration = _write_calibration(hydraulic_cells)
    _write_profile()
    _write_population(hydraulic_cells["cell_id"].unique())
    scenario_path = _write_scenario(days=int(hydraulic_cells["time_index"].nunique()))
    schism_handoff_summary = (
        _write_schism_handoff(
            cross_sections,
            flows,
            hydraulic_cells,
            scenario_path,
            transverse_nodes=schism_transverse_nodes,
            dry_run=schism_dry_run,
            executable=schism_executable,
            container_image=schism_container_image,
            container_runtime=schism_container_runtime,
            n_procs=schism_n_procs,
            n_scribes=schism_n_scribes,
            timeout_s=schism_timeout_s,
        )
        if schism_handoff
        else None
    )
    ibm_summary: dict[str, Any] | None = None
    if run_ibm:
        result, _paths = run_ibm_scenario(scenario_path)
        final_alive = result.final_individuals[result.final_individuals["alive"]]
        ibm_summary = {
            "final_day": int(result.population_summary["day"].max()),
            "final_abundance": int(len(final_alive)),
            "final_biomass_g": float(final_alive["mass_g"].sum()) if not final_alive.empty else 0.0,
            "survival_rate": float(len(final_alive) / len(result.final_individuals))
            if len(result.final_individuals)
            else 0.0,
        }
    summary = {
        "hecras_geometry_rows": int(len(cross_sections)),
        "hecras_sections_total": int(cross_sections["station_m"].nunique()),
        "clinch_sections": int(hydraulic_cells["cell_id"].nunique()),
        "flow_profiles": int(hydraulic_cells["time_index"].nunique()),
        "hydraulic_rows": int(len(hydraulic_cells)),
        "mean_depth_m": float(hydraulic_cells["depth_m"].mean()),
        "mean_velocity_ms": float(hydraulic_cells["velocity_ms"].mean()),
        "slope": float(slope),
        "manning_n": float(manning_n),
    }
    _write_manifest(
        summary,
        calibration,
        ibm_summary,
        hydraulic_parameter_calibration,
        schism_handoff_summary,
    )
    print(
        json.dumps(
            {
                "summary": summary,
                "hydraulic_parameter_calibration": asdict(hydraulic_parameter_calibration.best)
                if hydraulic_parameter_calibration is not None
                else None,
                "calibration": calibration.to_dict(orient="records"),
                "ibm": ibm_summary,
                "schism_handoff": schism_handoff_summary,
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--skip-ibm", action="store_true")
    parser.add_argument("--no-calibrate", action="store_true")
    parser.add_argument("--calibration-date", default="2021-09-08")
    parser.add_argument("--slope", type=float, default=0.0002)
    parser.add_argument("--manning-n", type=float, default=0.045)
    parser.add_argument("--slope-min", type=float, default=3e-5)
    parser.add_argument("--slope-max", type=float, default=1.2e-3)
    parser.add_argument("--slope-steps", type=int, default=16)
    parser.add_argument("--manning-min", type=float, default=0.025)
    parser.add_argument("--manning-max", type=float, default=0.09)
    parser.add_argument("--manning-steps", type=int, default=14)
    parser.add_argument("--wse-weight", type=float, default=1.0)
    parser.add_argument("--velocity-weight", type=float, default=1.0)
    parser.add_argument("--skip-schism-handoff", action="store_true")
    parser.add_argument(
        "--run-schism",
        action="store_true",
        help="Invoke the configured SCHISM executable/container instead of dry-run handoff.",
    )
    parser.add_argument("--schism-transverse-nodes", type=int, default=3)
    parser.add_argument(
        "--schism-executable",
        help="Path/name of a native SCHISM executable such as pschism_TVD-VL.",
    )
    parser.add_argument(
        "--schism-container-image",
        help="Run SCHISM through this container image, e.g. openlimno-schism:5.11.0.",
    )
    parser.add_argument(
        "--schism-container-runtime",
        choices=["docker", "podman", "apptainer"],
        default="docker",
    )
    parser.add_argument("--schism-n-procs", type=int, default=1)
    parser.add_argument("--schism-n-scribes", type=int, default=0)
    parser.add_argument("--schism-timeout-s", type=float)
    args = parser.parse_args()
    build_case(
        offline=args.offline,
        run_ibm=not args.skip_ibm,
        calibrate=not args.no_calibrate,
        calibration_date=args.calibration_date,
        slope=args.slope,
        manning_n=args.manning_n,
        slope_grid=np.geomspace(args.slope_min, args.slope_max, args.slope_steps),
        manning_grid=np.linspace(args.manning_min, args.manning_max, args.manning_steps),
        wse_weight=args.wse_weight,
        velocity_weight=args.velocity_weight,
        schism_handoff=not args.skip_schism_handoff,
        schism_transverse_nodes=args.schism_transverse_nodes,
        schism_dry_run=not args.run_schism,
        schism_executable=args.schism_executable,
        schism_container_image=args.schism_container_image,
        schism_container_runtime=args.schism_container_runtime,
        schism_n_procs=args.schism_n_procs,
        schism_n_scribes=args.schism_n_scribes,
        schism_timeout_s=args.schism_timeout_s,
    )


if __name__ == "__main__":
    main()

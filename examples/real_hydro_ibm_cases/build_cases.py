"""Build and run several real-data hydro + IBM screening cases.

Each case uses:

* USGS NWIS daily mean discharge (`00060`, statistic `00003`)
* USGS National Hydrography Dataset (NHD) river-area boundary
* NHD flowlines linked to that river-area permanent identifier
* OpenLimno `preprocess gis-hydraulics` / `builtin-1d` logic
* OpenLimno native IBM with a shared rainbow trout screening profile

The generated depth/velocity values are suitable for software validation and
workflow smoke testing. They are not calibrated hydraulic-study results unless
local DEM/bathymetry and observed water levels are supplied.
"""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import yaml

from openlimno.hydro import build_builtin1d_gis_hydraulics
from openlimno.ibm.scenario import run_ibm_scenario

ROOT = Path(__file__).resolve().parent
CASES_DIR = ROOT / "cases"
NWIS_BASE = "https://waterservices.usgs.gov/nwis/dv/"
NHD_BASE = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer"
FT3S_TO_M3S = 0.028316846592


@dataclass(frozen=True)
class RealCase:
    key: str
    label: str
    station_id: str
    river_name: str
    nhd_area_id: str
    bbox: str
    initial_abundance: int
    n_cells: int = 10
    slope: float = 0.001
    manning_n: float = 0.035


CASES: tuple[RealCase, ...] = (
    RealCase(
        key="boise_glenwood",
        label="Boise River at Glenwood Bridge near Boise, Idaho",
        station_id="13206000",
        river_name="Boise River",
        nhd_area_id="120008049",
        bbox="-116.35,43.55,-116.05,43.75",
        initial_abundance=160,
        n_cells=12,
    ),
    RealCase(
        key="truckee_reno",
        label="Truckee River at Reno, Nevada",
        station_id="10348000",
        river_name="Truckee River",
        nhd_area_id="120008177",
        bbox="-119.90,39.45,-119.70,39.60",
        initial_abundance=140,
        n_cells=10,
    ),
    RealCase(
        key="delaware_trenton",
        label="Delaware River at Trenton, New Jersey",
        station_id="01463500",
        river_name="Delaware River",
        nhd_area_id="167393148",
        bbox="-75.00,40.10,-74.70,40.30",
        initial_abundance=220,
        n_cells=10,
    ),
    RealCase(
        key="yakima_kiona",
        label="Yakima River at Kiona, Washington",
        station_id="12510500",
        river_name="Yakima River",
        nhd_area_id="153011766",
        bbox="-119.65,46.20,-119.40,46.35",
        initial_abundance=180,
        n_cells=10,
    ),
)


def _json_get(url: str, params: dict[str, str]) -> tuple[dict[str, Any], str]:
    full_url = f"{url}?{urlencode(params)}"
    request = Request(full_url, headers={"User-Agent": "OpenLimno real hydro IBM case builder"})
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8")), full_url


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _property_ci(properties: dict[str, Any], key: str) -> Any:
    key_lower = key.lower()
    for name, value in properties.items():
        if name.lower() == key_lower:
            return value
    return None


def _download_nwis(
    case: RealCase,
    *,
    case_dir: Path,
    start_date: str,
    end_date: str,
    offline: bool,
) -> tuple[pd.DataFrame, dict[str, Any], str]:
    raw_path = case_dir / "data" / "raw" / f"nwis_{case.station_id}_{start_date}_{end_date}.json"
    params = {
        "format": "json",
        "sites": case.station_id,
        "startDT": start_date,
        "endDT": end_date,
        "parameterCd": "00060",
        "statCd": "00003",
        "siteStatus": "all",
    }
    if offline:
        data = json.loads(raw_path.read_text(encoding="utf-8"))
        url = f"{NWIS_BASE}?{urlencode(params)}"
    else:
        data, url = _json_get(NWIS_BASE, params)
        _write_json(raw_path, data)
    series_list = data["value"].get("timeSeries") or []
    if not series_list:
        raise RuntimeError(f"{case.key}: NWIS station {case.station_id} returned no discharge series.")
    series = series_list[0]
    values = series["values"][0].get("value") or []
    if not values:
        raise RuntimeError(f"{case.key}: NWIS station {case.station_id} returned no daily values.")
    source_info = series["sourceInfo"]
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(values):
        discharge_ft3s = float(item["value"])
        rows.append(
            {
                "time_index": index,
                "date": item["dateTime"][:10],
                "discharge_ft3s": discharge_ft3s,
                "discharge_m3s": discharge_ft3s * FT3S_TO_M3S,
                "qualifier": ",".join(str(q) for q in item.get("qualifiers", [])),
                "reach_id": case.key,
            }
        )
    flow = pd.DataFrame(rows)
    flow.to_csv(case_dir / "data" / "flow_daily.csv", index=False)
    location = source_info["geoLocation"]["geogLocation"]
    metadata = {
        "station_id": case.station_id,
        "site_name": source_info.get("siteName", case.label),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "parameter": "00060 daily mean discharge",
        "statistic": "00003 mean",
        "unit": series["variable"]["unit"]["unitCode"],
        "start_date": start_date,
        "end_date": end_date,
        "n_values": len(flow),
    }
    return flow, metadata, url


def _download_nhd(
    case: RealCase,
    *,
    case_dir: Path,
    offline: bool,
) -> tuple[Path, Path, dict[str, str]]:
    gis_dir = case_dir / "data" / "gis"
    raw_dir = case_dir / "data" / "raw"
    area_path = gis_dir / f"{case.key}_nhd_area_{case.nhd_area_id}.geojson"
    flow_raw_path = raw_dir / f"{case.key}_nhd_flowlines_raw.geojson"
    flow_path = gis_dir / f"{case.key}_nhd_flowline_{case.nhd_area_id}.geojson"
    area_params = {
        "where": f"permanent_identifier='{case.nhd_area_id}'",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    flow_params = {
        "where": f"GNIS_NAME='{case.river_name}'",
        "geometry": case.bbox,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "returnExceededLimitFeatures": "true",
        "f": "geojson",
    }
    if offline:
        area_data = json.loads(area_path.read_text(encoding="utf-8"))
        flow_data = json.loads(flow_raw_path.read_text(encoding="utf-8"))
        area_url = f"{NHD_BASE}/9/query?{urlencode(area_params)}"
        flow_url = f"{NHD_BASE}/6/query?{urlencode(flow_params)}"
    else:
        area_data, area_url = _json_get(f"{NHD_BASE}/9/query", area_params)
        flow_data, flow_url = _json_get(f"{NHD_BASE}/6/query", flow_params)
        _write_json(area_path, area_data)
        _write_json(flow_raw_path, flow_data)
    if not area_data.get("features"):
        raise RuntimeError(f"{case.key}: NHD area {case.nhd_area_id} returned no features.")
    filtered = []
    for feature in flow_data.get("features", []):
        properties = feature.get("properties") or {}
        if str(_property_ci(properties, "wbarea_permanent_identifier")) == case.nhd_area_id:
            filtered.append(feature)
    if not filtered:
        raise RuntimeError(
            f"{case.key}: no NHD flowlines linked to waterbody area {case.nhd_area_id}."
        )
    _write_json(flow_path, {"type": "FeatureCollection", "features": filtered})
    return area_path, flow_path, {"nhd_area_url": area_url, "nhd_flowline_url": flow_url}


def _write_profile(case_dir: Path) -> None:
    profile = {
        "profile_version": "0.2",
        "species": {
            "id": "rainbow_trout",
            "scientific_name": "Oncorhynchus mykiss",
            "common_name": "Rainbow trout",
            "evidence_status": "shared screening profile for real-data software validation cases",
        },
        "parameters": {
            "thermal_min_c": {"value": 1.0, "source": "OpenLimno native IBM default"},
            "thermal_optimum_c": {"value": 12.0, "source": "OpenLimno native IBM default"},
            "thermal_max_c": {"value": 23.0, "source": "OpenLimno native IBM default"},
            "base_daily_survival": {"value": 0.997, "source": "OpenLimno native IBM default"},
            "carrying_density_per_m2": {"value": 0.08, "source": "OpenLimno native IBM default"},
            "maturity_length_mm": {"value": 120.0, "source": "OpenLimno native IBM default"},
        },
        "calibration": {
            "accepted": False,
            "notes": "Software validation profile; replace with calibrated local species data.",
        },
    }
    (case_dir / "profile_rainbow_trout.yaml").write_text(
        yaml.safe_dump(profile, sort_keys=False),
        encoding="utf-8",
    )


def _write_initial_population(case: RealCase, case_dir: Path, cell_ids: Iterable[str]) -> None:
    rng = random.Random(int(case.station_id))
    ids = list(cell_ids)
    rows: list[dict[str, Any]] = []
    for fish_id in range(case.initial_abundance):
        length_mm = max(45.0, min(230.0, rng.gauss(115.0, 24.0)))
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
    pd.DataFrame(rows).to_csv(case_dir / "data" / "initial_population.csv", index=False)


def _start_day(flow: pd.DataFrame) -> int:
    first = datetime.strptime(str(flow["date"].iloc[0]), "%Y-%m-%d")
    return int(first.strftime("%j"))


def _write_scenario(case: RealCase, case_dir: Path, flow: pd.DataFrame) -> Path:
    scenario = {
        "ibm_version": "0.2",
        "scenario": {
            "id": f"{case.key}-real-hydro-ibm",
            "description": f"{case.label}: NWIS/NHD real-data hydraulic + IBM smoke case.",
            "reach_id": case.key,
            "days": int(len(flow)),
            "start_day": _start_day(flow),
            "start_year": int(str(flow["date"].iloc[0])[:4]),
            "seed": int(case.station_id),
            "stochastic": True,
            "light_phases": ["dawn", "day", "dusk", "night"],
        },
        "profile": {"uri": "profile_rainbow_trout.yaml"},
        "forcing": {
            "habitat_cells": "data/hydraulics/hydraulic_cells.csv",
            "time_index_column": "time_index",
        },
        "population": {
            "initial_population": "data/initial_population.csv",
            "default_species": "rainbow_trout",
            "initial_abundance": case.initial_abundance,
            "initial_length_mm": 115.0,
        },
        "outputs": {
            "dir": "out/native",
            "formats": ["csv"],
            "individual_history": False,
            "manifest": True,
        },
    }
    path = case_dir / "scenario.yaml"
    path.write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
    return path


def build_case(
    case: RealCase,
    *,
    start_date: str,
    end_date: str,
    offline: bool,
    run_ibm: bool,
) -> dict[str, Any]:
    case_dir = CASES_DIR / case.key
    for directory in (case_dir / "data" / "raw", case_dir / "data" / "gis"):
        directory.mkdir(parents=True, exist_ok=True)
    flow, nwis_meta, nwis_url = _download_nwis(
        case,
        case_dir=case_dir,
        start_date=start_date,
        end_date=end_date,
        offline=offline,
    )
    area_path, flowline_path, nhd_urls = _download_nhd(case, case_dir=case_dir, offline=offline)
    hydraulic = build_builtin1d_gis_hydraulics(
        boundary_path=area_path,
        centerline_path=flowline_path,
        out_dir=case_dir / "data" / "hydraulics",
        discharges_m3s=flow,
        n_cells=case.n_cells,
        manning_n=case.manning_n,
        slope=case.slope,
        output_format="csv",
    )
    _write_profile(case_dir)
    _write_initial_population(case, case_dir, hydraulic.hydraulic_cells["cell_id"].unique())
    scenario_path = _write_scenario(case, case_dir, flow)
    source_manifest = {
        "case": case.__dict__,
        "generated_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "nwis": {**nwis_meta, "url": nwis_url},
        "nhd": {
            "area_url": nhd_urls["nhd_area_url"],
            "flowline_url": nhd_urls["nhd_flowline_url"],
            "area_path": str(area_path.relative_to(case_dir)),
            "flowline_path": str(flowline_path.relative_to(case_dir)),
        },
        "hydraulics_manifest": str(hydraulic.manifest_path.relative_to(case_dir)),
    }
    _write_json(case_dir / "data" / "source_manifest.json", source_manifest)
    result_row: dict[str, Any] = {
        "case": case.key,
        "station_id": case.station_id,
        "label": case.label,
        "days": len(flow),
        "hydraulic_cells": int(hydraulic.hydraulic_cells["cell_id"].nunique()),
        "hydraulic_rows": len(hydraulic.hydraulic_cells),
        "min_q_m3s": float(flow["discharge_m3s"].min()),
        "max_q_m3s": float(flow["discharge_m3s"].max()),
        "mean_depth_m": float(hydraulic.hydraulic_cells["depth_m"].mean()),
        "mean_velocity_ms": float(hydraulic.hydraulic_cells["velocity_ms"].mean()),
        "scenario": str(scenario_path),
    }
    if run_ibm:
        ibm_result, _paths = run_ibm_scenario(scenario_path)
        last = ibm_result.population_summary.tail(1).iloc[0]
        survival_value = last.get("survival_rate", last.get("survival", float("nan")))
        result_row.update(
            {
                "final_day": int(last["day"]),
                "final_abundance": int(last["abundance"]),
                "final_biomass_g": float(last["biomass_g"]),
                "survival_rate": float(survival_value),
            }
        )
    return result_row


def _select_cases(names: list[str] | None) -> list[RealCase]:
    if not names:
        return list(CASES)
    by_key = {case.key: case for case in CASES}
    missing = sorted(set(names) - set(by_key))
    if missing:
        raise SystemExit(f"Unknown case(s): {', '.join(missing)}")
    return [by_key[name] for name in names]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2025-10-01")
    parser.add_argument("--end-date", default="2025-10-07")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--skip-ibm", action="store_true")
    parser.add_argument("--case", dest="cases", action="append", help="Case key to build; repeatable.")
    args = parser.parse_args()
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    rows = [
        build_case(
            case,
            start_date=args.start_date,
            end_date=args.end_date,
            offline=args.offline,
            run_ibm=not args.skip_ibm,
        )
        for case in _select_cases(args.cases)
    ]
    summary = pd.DataFrame(rows)
    summary.to_csv(ROOT / "batch_results.csv", index=False)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()

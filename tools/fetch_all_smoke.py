#!/usr/bin/env python3
"""End-to-end smoke for the openlimno.preprocess.fetch package.

Hits every fetcher in the package against a single Heihe-mid-basin
test point so a human can verify the full chain after a refactor
without remembering 9 separate one-liners. Not in CI — it talks to
9 different public APIs + downloads ~80 MB on first run.

Usage:
    XDG_CACHE_HOME=/tmp/openlimno-smoke-cache \\
        python3 tools/fetch_all_smoke.py

Outputs a one-line PASS/FAIL summary per fetcher, plus a few
correctness cross-checks (e.g., SoilGrids texture sum ≈ 100%,
HydroSHEDS UP_AREA vs my union area).

Exit code: 0 if all fetchers PASS, 1 if any FAIL.
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path


# Heihe mid-basin (38.20°N, 100.20°E) — verified in v0.3.3-v0.3.5
# ship logs. Small but inland-river territory with mixed grassland
# + bare soil + forest, real soil/LULC heterogeneity to exercise
# all fetchers without trivial water-body answers.
LAT, LON = 38.20, 100.20
BBOX_TIGHT = (LON - 0.1, LAT - 0.1, LON + 0.1, LAT + 0.1)
BBOX_LARGE = (LON - 1.0, LAT - 1.0, LON + 1.0, LAT + 1.0)


def _row(name: str, ok: bool, msg: str, dt: float) -> None:
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name:24s} {dt:5.1f}s  {msg}")


def _smoke(name: str, fn) -> tuple[bool, str, float]:
    t0 = time.time()
    try:
        msg = fn()
        return True, msg, time.time() - t0
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return False, repr(e), time.time() - t0


def smoke_dem() -> str:
    from openlimno.preprocess.fetch import fetch_copernicus_dem
    res = fetch_copernicus_dem(*BBOX_TIGHT)
    return f"{res.n_tiles} tiles, bounds {res.bounds}, crs {res.crs}"


def smoke_nwis() -> str:
    from openlimno.preprocess.fetch import fetch_nwis_daily_discharge
    # USGS Salmon River at White Bird, ID (Lemhi-adjacent gauge).
    res = fetch_nwis_daily_discharge(
        "13317000", "2024-01-01", "2024-01-07",
    )
    return (
        f"{len(res.df)} days, "
        f"mean Q = {res.df['discharge_m3s'].mean():.1f} m³/s"
    )


def smoke_daymet() -> str:
    from openlimno.preprocess.fetch import fetch_daymet_daily
    res = fetch_daymet_daily(44.94, -113.93, 2024, 2024)
    return f"{len(res.df)} days, mean T_air {res.df['T_air_C_mean'].mean():.1f}°C"


def smoke_openmeteo() -> str:
    from openlimno.preprocess.fetch import fetch_open_meteo_daily
    res = fetch_open_meteo_daily(LAT, LON, 2024, 2024)
    return (
        f"{len(res.df)} days, tz={res.timezone}, "
        f"peak water {res.df['T_water_C_stefan'].max():.1f}°C"
    )


def smoke_hydrosheds() -> str:
    from openlimno.preprocess.fetch import (
        fetch_hydrobasins, find_basin_at, upstream_basin_ids,
    )
    layer = fetch_hydrobasins(region="as", level=12)
    pour = find_basin_at(layer.shp_path, LAT, LON)
    assert pour is not None, "no basin found at pour point"
    ups = upstream_basin_ids(layer.shp_path, int(pour["HYBAS_ID"]))
    # Cross-check: aggregate vs HydroSHEDS' own UP_AREA
    sub_areas = []
    from osgeo import ogr
    ds = ogr.Open(str(layer.shp_path))
    lyr = ds.GetLayer(0)
    ids_set = set(ups)
    lyr.SetAttributeFilter(
        "HYBAS_ID IN (" + ",".join(str(i) for i in ups) + ")"
    )
    for feat in lyr:
        if int(feat.GetField("HYBAS_ID")) in ids_set:
            sub_areas.append(float(feat.GetField("SUB_AREA")))
    agg = sum(sub_areas)
    up_area = float(pour["UP_AREA"])
    err_pct = abs(agg - up_area) / up_area * 100 if up_area else 0
    return (
        f"{len(ups)} basins, UP_AREA={up_area:.1f}, "
        f"aggregated={agg:.1f}, err {err_pct:.3f}%"
    )


def smoke_worldcover() -> str:
    from openlimno.preprocess.fetch import (
        WORLDCOVER_CLASSES, fetch_esa_worldcover,
    )
    res = fetch_esa_worldcover(*BBOX_TIGHT, year=2021)
    top = max(res.class_km2.items(), key=lambda kv: kv[1])
    return (
        f"{res.n_tiles} tiles, {sum(res.class_pixels.values()):,} px, "
        f"top class: {WORLDCOVER_CLASSES[top[0]]} ({top[1]:.1f} km²)"
    )


def smoke_soilgrids() -> str:
    from openlimno.preprocess.fetch import fetch_soilgrids
    res = fetch_soilgrids(LAT, LON)
    clay = res.get("clay", "0-5cm")
    sand = res.get("sand", "0-5cm")
    silt = res.get("silt", "0-5cm")
    total = clay + sand + silt
    # USDA texture sum should be ~100% (within measurement noise).
    assert 95 < total < 105, f"texture sum off: clay+sand+silt={total}%"
    return (
        f"{len(res.df)} rows, top 0-5 cm clay={clay:.0f}% "
        f"sand={sand:.0f}% silt={silt:.0f}% (sum {total:.1f}%)"
    )


def smoke_species() -> str:
    from openlimno.preprocess.fetch import (
        fetch_gbif_occurrences, match_species,
    )
    m = match_species("Salmo trutta")
    assert m.usage_key, f"GBIF match failed: {m.match_type}"
    # West Europe bbox so we get plenty of records cheaply.
    occ = fetch_gbif_occurrences(
        m.usage_key, (-5.0, 41.0, 5.0, 49.0),
        limit=50, max_pages=1,
    )
    return (
        f"taxon {m.canonical_name} usageKey={m.usage_key} "
        f"family={m.family}; bbox-total {occ.total_matched:,}, "
        f"page {len(occ.df)} rows"
    )


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root / "src"))
    cache_root = os.environ.get("XDG_CACHE_HOME")
    print(f"openlimno fetch-all smoke")
    print(f"  cache: {cache_root or '~/.cache (default)'}")
    print(f"  point: ({LAT}, {LON})  bbox tight: {BBOX_TIGHT}")
    print()

    cases = [
        ("dem (cop30)",     smoke_dem),
        ("nwis (us)",       smoke_nwis),
        ("daymet (us)",     smoke_daymet),
        ("openmeteo",       smoke_openmeteo),
        ("hydrosheds",      smoke_hydrosheds),
        ("worldcover",      smoke_worldcover),
        ("soilgrids",       smoke_soilgrids),
        ("species (gbif)",  smoke_species),
    ]
    fails = 0
    for name, fn in cases:
        ok, msg, dt = _smoke(name, fn)
        _row(name, ok, msg, dt)
        if not ok:
            fails += 1
    print()
    total_tag = "PASS" if fails == 0 else f"FAIL ({fails}/{len(cases)})"
    print(f"  result: {total_tag}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

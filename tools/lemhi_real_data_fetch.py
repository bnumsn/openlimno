"""Fetch public real-data layers for the Lemhi U4 evidence track.

Run from the repo root. The script only marks manifest entries as
``real: true`` after the corresponding file has been written.

Official API notes checked 2026-05-20:
USGS Water Data OGC API exposes field measurements at
https://api.waterdata.usgs.gov/ogcapi/v0/collections/field-measurements/items
and replaces the retired legacy measurements endpoint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from openlimno.preprocess.fetch import (
    fetch_copernicus_dem,
    fetch_gbif_occurrences,
    fetch_hydrobasins,
    fetch_nwis_rating_curve,
    find_basin_at,
    match_species,
    upstream_basin_ids,
    write_watershed_geojson,
)

REPO = Path(__file__).resolve().parents[1]
LEMHI = REPO / "data" / "lemhi"
MANIFEST = LEMHI / "manifest.json"
SITE_ID = "13305000"
MONITORING_LOCATION_ID = f"USGS-{SITE_ID}"
LEMHI_POUR = (44.94, -113.6391667)  # lat, lon near USGS 13305000
LEMHI_BBOX = (-113.75, 44.82, -113.50, 45.05)  # lon_min, lat_min, lon_max, lat_max
OGC_FIELD = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/field-measurements/items"
CFS_TO_M3S = 0.028316846592
FT_TO_M = 0.3048


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _mark_real(manifest: dict[str, Any], file_name: str, source: str, note: str = "") -> None:
    rec: dict[str, Any] = {"real": True, "source": source, "sha256": _sha(LEMHI / file_name)}
    if note:
        rec["note"] = note
    manifest.setdefault("files", {})[file_name] = rec


def _write_manifest(manifest: dict[str, Any]) -> None:
    manifest["generator"] = "tools/build_lemhi_dataset.py + tools/lemhi_real_data_fetch.py"
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _fetch_rating_curve_ogc() -> pd.DataFrame:
    """Fallback for OpenLimno's pre-migration fetch_nwis_rating_curve."""

    def pull(parameter_code: str) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            params = {
                "f": "json",
                "monitoring_location_id": MONITORING_LOCATION_ID,
                "parameter_code": parameter_code,
                "limit": 10000,
                "offset": offset,
            }
            payload = requests.get(OGC_FIELD, params=params, timeout=60).json()
            feats = payload.get("features", [])
            for feat in feats:
                props = feat.get("properties", {})
                rows.append(
                    {
                        "field_visit_id": props.get("field_visit_id"),
                        "time": props.get("time"),
                        "value": pd.to_numeric(props.get("value"), errors="coerce"),
                        "unit": props.get("unit_of_measure"),
                        "measurement_rated": props.get("measurement_rated"),
                    }
                )
            if len(feats) < 10000:
                break
            offset += 10000
        return pd.DataFrame(rows)

    q = pull("00060").rename(columns={"value": "Q_raw"})
    h = pull("00065").rename(columns={"value": "h_raw"})
    merged = q.merge(h, on="field_visit_id", suffixes=("_q", "_h"))
    merged = merged.dropna(subset=["Q_raw", "h_raw"])
    sigma_frac = {
        "Excellent": 0.02,
        "Good": 0.05,
        "Fair": 0.08,
        "Poor": 0.12,
    }
    rating = pd.DataFrame(
        {
            "gauge_id": SITE_ID,
            "h_m": merged["h_raw"].astype(float) * FT_TO_M,
            "Q_m3s": merged["Q_raw"].astype(float) * CFS_TO_M3S,
            "sigma_Q": merged["Q_raw"].astype(float)
            * CFS_TO_M3S
            * merged["measurement_rated_q"].map(sigma_frac).fillna(0.10),
        }
    )
    return rating[rating["h_m"] > 0].sort_values("h_m").reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-dem", action="store_true")
    parser.add_argument("--skip-hydrosheds", action="store_true")
    parser.add_argument("--skip-gbif", action="store_true")
    parser.add_argument("--skip-rating", action="store_true")
    args = parser.parse_args()

    LEMHI.mkdir(parents=True, exist_ok=True)
    manifest = _manifest()
    provenance: dict[str, Any] = {"bbox": LEMHI_BBOX, "site_id": SITE_ID, "outputs": {}}

    if not args.skip_rating:
        try:
            rating = fetch_nwis_rating_curve(SITE_ID).df
            rating_source = "USGS NWIS rating-curve fetcher"
        except NotImplementedError:
            rating = _fetch_rating_curve_ogc()
            rating_source = "USGS Water Data OGC field-measurements API"
        rating_path = LEMHI / "rating_curve.parquet"
        rating.to_parquet(rating_path, index=False)
        _mark_real(manifest, "rating_curve.parquet", rating_source, f"{len(rating)} field measurements")
        provenance["outputs"]["rating_curve.parquet"] = rating_source

    if not args.skip_dem:
        dem = fetch_copernicus_dem(*LEMHI_BBOX, out_path=LEMHI / "lemhi_cop30_dem.tif")
        _mark_real(manifest, "lemhi_cop30_dem.tif", "Copernicus DEM GLO-30", f"{dem.n_tiles} tile(s)")
        provenance["outputs"]["lemhi_cop30_dem.tif"] = [c.source_url for c in dem.cache_entries]

    if not args.skip_hydrosheds:
        layer = fetch_hydrobasins("na", level=12)
        pour = find_basin_at(layer.shp_path, *LEMHI_POUR)
        if pour is None:
            raise RuntimeError("Lemhi pour point was not inside HydroBASINS North America")
        ids = upstream_basin_ids(layer.shp_path, int(pour["HYBAS_ID"]))
        summary = write_watershed_geojson(layer.shp_path, ids, LEMHI / "lemhi_watershed.geojson")
        _mark_real(manifest, "lemhi_watershed.geojson", "HydroSHEDS HydroBASINS v1c", f"{summary['n_basins']} basins")
        provenance["outputs"]["lemhi_watershed.geojson"] = summary

    if not args.skip_gbif:
        for name in ("Salmo trutta", "Oncorhynchus mykiss"):
            match = match_species(name)
            if match.usage_key is None:
                raise RuntimeError(f"GBIF did not match {name}")
            occ = fetch_gbif_occurrences(match.usage_key, LEMHI_BBOX, max_pages=10)
            out = LEMHI / f"gbif_{name.lower().replace(' ', '_')}.csv"
            occ.df.to_csv(out, index=False)
            _mark_real(manifest, out.name, "GBIF occurrence API", f"{len(occ.df)}/{occ.total_matched} bbox records")
            provenance["outputs"][out.name] = {"usage_key": match.usage_key, "pages": occ.n_pages_fetched}

    (LEMHI / "real_fetch_provenance.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _mark_real(manifest, "real_fetch_provenance.json", "OpenLimno fetch script")
    _write_manifest(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

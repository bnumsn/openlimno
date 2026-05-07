"""Preprocess M1 reader tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from openlimno.preprocess import (
    read_adcp_qrev,
    read_cross_sections,
    read_dem,
    write_cross_sections_to_parquet,
)


# ----------------------------------------------------------
# cross-section
# ----------------------------------------------------------
def test_read_cross_sections_csv(tmp_path: Path) -> None:
    csv = tmp_path / "xs.csv"
    csv.write_text(
        "station_m,distance_m,elevation_m,substrate\n"
        "0,-5,1.5,gravel\n"
        "0,0,1.0,gravel\n"
        "0,5,1.5,gravel\n"
        "100,-5,1.4,gravel\n"
        "100,0,0.9,gravel\n"
        "100,5,1.4,gravel\n"
    )
    df = read_cross_sections(csv)
    assert len(df) == 6
    assert "campaign_id" in df.columns
    assert "point_index" in df.columns
    assert df["substrate"].iloc[0] == "gravel"
    # All rows in same campaign
    assert df["campaign_id"].nunique() == 1
    # point_index auto-assigned per station
    sub = df[df["station_m"] == 0].sort_values("point_index")
    assert list(sub["point_index"]) == [0, 1, 2]


def test_read_cross_sections_missing_required(tmp_path: Path) -> None:
    csv = tmp_path / "bad.csv"
    csv.write_text("station_m,distance_m\n0,1.0\n")
    with pytest.raises(ValueError, match="elevation_m"):
        read_cross_sections(csv)


def test_read_cross_sections_excel_smoke(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    df = pd.DataFrame(
        {
            "station_m": [0, 0, 100, 100],
            "distance_m": [-5, 5, -5, 5],
            "elevation_m": [1.5, 1.5, 1.4, 1.4],
        }
    )
    xlsx = tmp_path / "xs.xlsx"
    df.to_excel(xlsx, index=False)
    out = read_cross_sections(xlsx)
    assert len(out) == 4


def test_write_cross_sections_to_parquet_roundtrip(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "campaign_id": ["cid"] * 3,
            "station_m": [0.0, 0.0, 0.0],
            "distance_m": [-1.0, 0.0, 1.0],
            "elevation_m": [1.5, 1.0, 1.5],
            "point_index": [0, 1, 2],
        }
    )
    out = tmp_path / "xs.parquet"
    write_cross_sections_to_parquet(df, out, source_note="test")
    assert out.exists()
    re_read = pd.read_parquet(out)
    assert len(re_read) == 3
    assert (re_read["station_m"] == 0).all()


# ----------------------------------------------------------
# ADCP QRev
# ----------------------------------------------------------
def test_read_adcp_qrev_basic(tmp_path: Path) -> None:
    csv = tmp_path / "tr.csv"
    csv.write_text(
        "time,depth_m,u_ms,v_ms,backscatter_db\n"
        "2024-04-01 09:00:00,1.5,0.4,0.1,75.5\n"
        "2024-04-01 09:00:01,1.6,0.5,0.0,76.0\n"
        "2024-04-01 09:00:02,1.7,0.6,-0.1,75.8\n"
    )
    df = read_adcp_qrev(csv)
    assert len(df) == 3
    assert "campaign_id" in df.columns
    assert df["depth_m"].iloc[0] == pytest.approx(1.5)


def test_read_adcp_qrev_alias_columns(tmp_path: Path) -> None:
    csv = tmp_path / "alias.csv"
    csv.write_text(
        "datetime,depth,v_east,v_north\n2024-04-01,1.0,0.3,0.05\n2024-04-01,1.1,0.4,0.04\n"
    )
    df = read_adcp_qrev(csv)
    assert df["depth_m"].iloc[0] == pytest.approx(1.0)
    assert df["u_ms"].iloc[0] == pytest.approx(0.3)


def test_read_adcp_qrev_missing_columns_returns_nan(tmp_path: Path) -> None:
    csv = tmp_path / "minimal.csv"
    csv.write_text("time,depth_m\n2024-01-01,2.0\n")
    df = read_adcp_qrev(csv)
    assert df["u_ms"].isna().all()
    assert df["w_ms"].isna().all()


# ----------------------------------------------------------
# DEM
# ----------------------------------------------------------
def test_read_dem_synthetic(tmp_path: Path) -> None:
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    elev = np.linspace(100, 110, 100).reshape(10, 10).astype(np.float32)
    out = tmp_path / "dem.tif"
    transform = from_origin(0, 100, 1.0, 1.0)
    with rasterio.open(
        out,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype="float32",
        crs="EPSG:32612",
        transform=transform,
    ) as ds:
        ds.write(elev, 1)

    dem = read_dem(out)
    assert dem.shape == (10, 10)
    assert dem.crs == "EPSG:32612"
    # Sample at world coord (0.5, 99.5) → row 0, col 0 → elev[0, 0]
    assert dem.sample(0.5, 99.5) == pytest.approx(100.0, abs=1.5)


def test_read_dem_sample_along_line(tmp_path: Path) -> None:
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    elev = np.full((20, 20), 50.0, dtype=np.float32)
    out = tmp_path / "flat.tif"
    transform = from_origin(0, 20, 1.0, 1.0)
    with rasterio.open(
        out,
        "w",
        driver="GTiff",
        height=20,
        width=20,
        count=1,
        dtype="float32",
        crs="EPSG:32612",
        transform=transform,
    ) as ds:
        ds.write(elev, 1)

    dem = read_dem(out)
    samples = dem.sample_along_line(1.0, 1.0, 18.0, 18.0, n=10)
    assert (samples == 50.0).all()

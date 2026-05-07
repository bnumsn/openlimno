"""Biological observation reader tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from openlimno.preprocess import (
    read_edna_sample,
    read_fish_sampling,
    read_macroinvertebrate_sample,
    read_pit_tag_event,
    read_redd_count,
    read_rst_count,
    validate_biological_table,
)


# --------------------------------------------------------------
# fish_sampling
# --------------------------------------------------------------
def test_read_fish_sampling_basic(tmp_path: Path) -> None:
    csv = tmp_path / "fs.csv"
    csv.write_text(
        "time,geom_wkt,method,species,count,length_mm\n"
        "2024-08-15 09:30:00,POINT(584000 4980000),electrofishing,oncorhynchus_mykiss,12,180\n"
        "2024-08-15 09:35:00,POINT(584030 4980005),electrofishing,oncorhynchus_mykiss,8,150\n"
    )
    df = read_fish_sampling(csv, campaign_id="lemhi-2024-08")
    assert len(df) == 2
    assert df["campaign_id"].iloc[0] == "lemhi-2024-08"
    assert df["count"].sum() == 20

    errs = validate_biological_table(df, "fish_sampling")
    assert errs == [], errs


def test_read_fish_sampling_alternative_method() -> None:
    """Reader does NOT enforce method enum; validator does."""
    import io
    csv = io.StringIO(
        "time,geom_wkt,method,species,count\n"
        "2024-08-15,POINT(0 0),wrong_method,xx,5\n"
    )
    df = pd.read_csv(csv)
    df.columns = [c.lower() for c in df.columns]
    df["campaign_id"] = "test"
    errs = validate_biological_table(df, "fish_sampling")
    # Should fail enum validation on method
    assert any("method" in e for e in errs)


# --------------------------------------------------------------
# redd_count
# --------------------------------------------------------------
def test_read_redd_count_basic(tmp_path: Path) -> None:
    csv = tmp_path / "redds.csv"
    csv.write_text(
        "geom_wkt,species,count,redd_status,depth_m,velocity_ms\n"
        "POINT(584000 4980000),oncorhynchus_mykiss,4,active,0.5,0.7\n"
        "POINT(584030 4980005),oncorhynchus_mykiss,2,superimposed,0.4,0.6\n"
    )
    df = read_redd_count(csv, campaign_id="lemhi-2024-05")
    assert len(df) == 2
    errs = validate_biological_table(df, "redd_count")
    assert errs == [], errs


# --------------------------------------------------------------
# pit_tag_event
# --------------------------------------------------------------
def test_read_pit_tag_event_basic(tmp_path: Path) -> None:
    csv = tmp_path / "pit.csv"
    csv.write_text(
        "tag_id,species,length_mm,event_type,location_wkt,time,antenna_id\n"
        "TAG-001,oncorhynchus_mykiss,200,release,POINT(584000 4980000),2024-04-15T10:00:00,A1\n"
        "TAG-001,oncorhynchus_mykiss,205,detection,POINT(583980 4979900),2024-05-20T14:30:00,A2\n"
    )
    df = read_pit_tag_event(csv)
    assert len(df) == 2
    errs = validate_biological_table(df, "pit_tag_event")
    assert errs == [], errs


# --------------------------------------------------------------
# rst_count
# --------------------------------------------------------------
def test_read_rst_count_basic(tmp_path: Path) -> None:
    csv = tmp_path / "rst.csv"
    csv.write_text(
        "station_wkt,time_start,time_end,species,life_stage,count,water_temp_C,discharge_m3s\n"
        "POINT(584000 4980000),2024-04-15T20:00:00,2024-04-16T08:00:00,oncorhynchus_mykiss,smolt,42,8.5,5.2\n"
    )
    df = read_rst_count(csv, campaign_id="lemhi-rst-2024")
    # Reader normalizes header to lower-snake; restore camel for schema match
    df = df.rename(columns={"water_temp_c": "water_temp_C"})
    assert len(df) == 1
    errs = validate_biological_table(df, "rst_count")
    assert errs == [], errs


# --------------------------------------------------------------
# eDNA
# --------------------------------------------------------------
def test_read_edna_basic(tmp_path: Path) -> None:
    csv = tmp_path / "edna.csv"
    csv.write_text(
        "geom_wkt,time,water_volume_l,target_species,qpcr_copies_per_l,lab_method_doi\n"
        "POINT(584000 4980000),2024-04-15T10:00:00,2.0,oncorhynchus_mykiss,150,10.1234/edna2024\n"
    )
    df = read_edna_sample(csv, campaign_id="lemhi-edna-2024")
    # Reader doesn't normalize; we preserve user's column names.
    df = df.rename(columns={
        "water_volume_l": "water_volume_L",
        "qpcr_copies_per_l": "qPCR_copies_per_L",
    })
    errs = validate_biological_table(df, "edna_sample")
    assert errs == [], errs


# --------------------------------------------------------------
# Macroinvertebrate
# --------------------------------------------------------------
def test_read_macroinvertebrate_basic(tmp_path: Path) -> None:
    csv = tmp_path / "macro.csv"
    csv.write_text(
        "geom_wkt,method,taxa,count,biomass_g,ept_richness,bmwp_score\n"
        "POINT(584000 4980000),Surber,Ephemeroptera,150,2.5,8,72\n"
    )
    df = read_macroinvertebrate_sample(csv, campaign_id="lemhi-macro-2024")
    df = df.rename(columns={
        "ept_richness": "EPT_richness",
        "bmwp_score": "BMWP_score",
    })
    errs = validate_biological_table(df, "macroinvertebrate_sample")
    assert errs == [], errs


def test_validate_unknown_table() -> None:
    df = pd.DataFrame()
    errs = validate_biological_table(df, "no_such_table")
    assert any("Unknown" in e for e in errs)

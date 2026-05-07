"""M1 acceptance test: Lemhi case runs end-to-end and produces sensible WUA-Q.

This is the M1 vertical slice acceptance: load YAML → validate → solve → habitat → output.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from openlimno.case import Case

CASE_YAML = Path(__file__).resolve().parents[2] / "examples" / "lemhi" / "case.yaml"
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "lemhi"


@pytest.fixture(scope="module")
def lemhi_run() -> object:
    if not DATA_DIR.exists() or not (DATA_DIR / "cross_section.parquet").exists():
        pytest.skip("Lemhi data not built; run tools/build_lemhi_dataset.py")
    case = Case.from_yaml(CASE_YAML)
    return case.run(discharges_m3s=[1.0, 3.0, 5.0, 8.0, 12.0, 20.0])


def test_case_yaml_validates() -> None:
    """Case loads and schema-validates."""
    case = Case.from_yaml(CASE_YAML)
    assert case.name == "lemhi_phabsim_replication"


def test_run_returns_results(lemhi_run) -> None:
    assert lemhi_run.case_name == "lemhi_phabsim_replication"
    assert len(lemhi_run.discharges_m3s) == 6
    assert len(lemhi_run.sections) == 11


def test_wua_q_dataframe_well_formed(lemhi_run) -> None:
    df = lemhi_run.wua_q
    assert "discharge_m3s" in df.columns
    assert "wua_m2_oncorhynchus_mykiss_spawning" in df.columns
    assert "wua_m2_oncorhynchus_mykiss_fry" in df.columns
    assert (df["discharge_m3s"] > 0).all()
    # Non-negative WUA always
    for col in df.columns:
        if col.startswith("wua_m2_"):
            assert (df[col] >= 0).all(), f"Negative WUA in {col}"


def test_spawning_wua_unimodal(lemhi_run) -> None:
    """Spawning WUA should rise then fall as Q increases — classic PHABSIM shape."""
    df = lemhi_run.wua_q
    spawn = df["wua_m2_oncorhynchus_mykiss_spawning"].to_numpy()
    peak_idx = int(np.argmax(spawn))
    # Peak should not be at the boundaries (else not unimodal)
    assert 0 < peak_idx < len(spawn) - 1, (
        f"Spawning WUA peak at boundary (idx={peak_idx}); curve not unimodal: {spawn}"
    )
    # Peak value > 10 m^2 (should be order tens for Lemhi-typical reach)
    assert spawn.max() > 10, f"Suspiciously low peak WUA: {spawn.max()}"


def test_outputs_written(lemhi_run) -> None:
    out = lemhi_run.output_dir
    assert (out / "wua_q.csv").exists()
    assert (out / "hydraulics.nc").exists()
    assert (out / "provenance.json").exists()


def test_hydraulics_netcdf_cf_compliant(lemhi_run) -> None:
    ds = xr.open_dataset(lemhi_run.output_dir / "hydraulics.nc")
    try:
        for var in ["water_depth", "velocity_magnitude", "water_surface", "wetted_area"]:
            assert var in ds
            assert "units" in ds[var].attrs
        assert "discharge" in ds.coords
        assert "station" in ds.coords
    finally:
        ds.close()


def test_provenance_complete(lemhi_run) -> None:
    prov = json.loads(lemhi_run.provenance_path.read_text())
    assert "openlimno_version" in prov
    assert "wedm_version" in prov
    assert prov["case"]["name"] == "lemhi_phabsim_replication"
    assert "yaml_sha256" in prov["case"]
    assert "machine" in prov
    assert "inputs" in prov


def test_acknowledge_independence_enforced_at_run() -> None:
    """If a case requests geom mean without ack, the run must fail before computation."""
    import tempfile
    import textwrap

    bad_yaml = textwrap.dedent("""\
        openlimno: '0.1'
        case:
          name: bad_no_ack
          crs: EPSG:32612
        mesh:
          uri: file://nope.nc
        data:
          cross_section: ../../data/lemhi/cross_section.parquet
          hsi_curve: ../../data/lemhi/hsi_curve.parquet
        hydrodynamics:
          backend: builtin-1d
        habitat:
          species: [oncorhynchus_mykiss]
          stages: [spawning]
          metric: wua-q
          composite: min
        output:
          dir: ./out_bad
          formats: [csv]
    """)
    # The above passes schema (composite=min has no ack requirement).
    # Now try the actual hard guard: if YAML had geom mean without ack, schema rejects;
    # if ack=True YAML missing reason ... The hard runtime guard is only triggered
    # when schema is somehow bypassed. That's tested by unit tests (test_habitat).
    # Here we just confirm validate_case rejects geom_mean w/o ack:
    from openlimno.wedm import validate_case

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(bad_yaml.replace("composite: min", "composite: geometric_mean"))
        path = f.name
    errs = validate_case(path)
    assert any("acknowledge_independence" in e for e in errs)

"""End-to-end: case.run() auto-invokes drifting-egg evaluation when configured.

SPEC §4.2.6. Triggered by ``habitat.metric: drifting-egg`` plus a
``habitat.drifting_egg`` block in the case YAML.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from openlimno.case import Case

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "lemhi"


def _write_case(tmp_path: Path, *, with_drift: bool, with_csv_temp: bool = False) -> Path:
    case_dir = tmp_path / "case"
    case_dir.mkdir(parents=True, exist_ok=True)
    out_dir = case_dir / "out"

    drift_block = ""
    if with_drift:
        if with_csv_temp:
            csv_path = case_dir / "temperature.csv"
            csv_path.write_text("station_m,temp_C\n0,28\n5000,28\n20000,27\n200000,26\n")
            tforce = "    temperature_forcing:\n      type: csv\n      csv: ./temperature.csv\n"
        else:
            tforce = "    temperature_forcing:\n      type: constant\n      value_C: 28.0\n"
        drift_block = (
            "  drifting_egg:\n"
            "    species: ctenopharyngodon_idella\n"
            f"    params: {DATA_DIR / 'drifting_egg_params.parquet'}\n"
            "    spawning_station_m: 0\n"
            "    max_drift_km: 200\n"
            "    dt_s: 600\n" + tforce
        )

    metric = "drifting-egg" if with_drift else "wua-q"
    # v3.0.0: declare allowed_data_roots so the strict-by-default
    # sandbox lets us reach DATA_DIR (which lives at the repo's
    # data/ tree, outside the test's tmp_path case dir).
    yaml_text = (
        "openlimno: '0.1'\n"
        "case:\n"
        "  name: drift_egg_case\n"
        "  crs: EPSG:32612\n"
        f"  allowed_data_roots: ['{DATA_DIR}']\n"
        "mesh:\n"
        f"  uri: {DATA_DIR / 'mesh.ugrid.nc'}\n"
        "data:\n"
        f"  cross_section: {DATA_DIR / 'cross_section.parquet'}\n"
        f"  hsi_curve: {DATA_DIR / 'hsi_curve.parquet'}\n"
        "hydrodynamics:\n"
        "  backend: builtin-1d\n"
        "habitat:\n"
        "  species: [oncorhynchus_mykiss]\n"
        "  stages: [spawning]\n"
        f"  metric: {metric}\n"
        "  composite: min\n" + drift_block + "output:\n"
        f"  dir: {out_dir}\n"
        "  formats: [csv]\n"
    )
    p = case_dir / "case.yaml"
    p.write_text(yaml_text)
    return p


@pytest.fixture(scope="module")
def lemhi_present() -> bool:
    return (DATA_DIR / "drifting_egg_params.parquet").exists() and (
        DATA_DIR / "cross_section.parquet"
    ).exists()


def test_drift_egg_runs_with_constant_temperature(tmp_path: Path, lemhi_present: bool) -> None:
    if not lemhi_present:
        pytest.skip("Lemhi data not built; run tools/build_lemhi_dataset.py")
    case_yaml = _write_case(tmp_path, with_drift=True)
    case = Case.from_yaml(case_yaml)
    res = case.run(discharges_m3s=[5.0, 15.0, 30.0])
    drift_csv = res.output_dir / "drift_egg.csv"
    assert drift_csv.exists(), "drift_egg.csv must be auto-written"
    df = pd.read_csv(drift_csv)
    expected = {
        "discharge_m3s",
        "species",
        "spawning_station_m",
        "hatch_station_m",
        "drift_distance_km",
        "hatch_temp_C_mean",
        "mortality_fraction",
        "success",
    }
    assert expected.issubset(df.columns)
    assert (df["species"] == "ctenopharyngodon_idella").all()
    # Higher Q -> longer drift distance (monotonic with velocity for
    # steady reach), within solver numerical noise. Compare with a
    # 0.5 % tolerance — the Lagrangian integration converges to the
    # same hatch station with sub-percent jitter across small Q
    # changes since hatch is dominated by the integrated temperature
    # not the velocity field.
    df_sorted = df.sort_values("discharge_m3s").reset_index(drop=True)
    low = df_sorted["drift_distance_km"].iloc[0]
    high = df_sorted["drift_distance_km"].iloc[-1]
    assert high >= low * 0.995, (
        f"drift_distance not monotone within noise: low={low}, high={high}"
    )


def test_drift_egg_csv_temperature_forcing(tmp_path: Path, lemhi_present: bool) -> None:
    if not lemhi_present:
        pytest.skip("Lemhi data not built")
    case_yaml = _write_case(tmp_path, with_drift=True, with_csv_temp=True)
    case = Case.from_yaml(case_yaml)
    res = case.run(discharges_m3s=[10.0])
    df = pd.read_csv(res.output_dir / "drift_egg.csv")
    # CSV had T in [26, 28] — mean must land inside that range
    assert 25.5 <= df["hatch_temp_C_mean"].iloc[0] <= 28.5


def test_drift_egg_skipped_when_metric_is_wua_q(tmp_path: Path, lemhi_present: bool) -> None:
    if not lemhi_present:
        pytest.skip("Lemhi data not built")
    case_yaml = _write_case(tmp_path, with_drift=False)
    case = Case.from_yaml(case_yaml)
    res = case.run(discharges_m3s=[5.0])
    assert not (res.output_dir / "drift_egg.csv").exists()

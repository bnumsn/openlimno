"""Opt-in inSTREAM/InSALMO interoperability tests against public example inputs.

These tests intentionally do not run by default. Enable them explicitly with:

    OPENLIMNO_RUN_INSTREAM_REAL=1 pytest tests/integration/test_instream_real_fixtures.py
    OPENLIMNO_RUN_OFFICIAL_IBM=1 pytest tests/integration/test_instream_real_fixtures.py
"""

from __future__ import annotations

import hashlib
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from openlimno.ibm import (
    discover_instream7_cases,
    extract_instream7_archive,
    read_instream7_brief_population,
    run_instream7_official_benchmark,
    summarize_instream7_brief_population,
)
from openlimno.preprocess import inspect_instream_exchange, read_external_model

RUN_OFFICIAL_IBM = os.environ.get("OPENLIMNO_RUN_OFFICIAL_IBM") == "1"
RUN_REAL_INSTREAM = RUN_OFFICIAL_IBM or os.environ.get("OPENLIMNO_RUN_INSTREAM_REAL") == "1"
RUN_REAL_INSALMO = RUN_OFFICIAL_IBM or os.environ.get("OPENLIMNO_RUN_INSALMO_REAL") == "1"
RUN_NETLOGO_COMPARE = os.environ.get("OPENLIMNO_RUN_INSTREAM_NETLOGO_COMPARE") == "1"
NETLOGO_SHORT_FIXTURE_DIR = (
    Path(__file__).resolve().parents[1] / "fixtures" / "instream7" / "netlogo_702_short"
)

pytestmark = [
    pytest.mark.online,
]


INSTREAM_FIXTURE = {
    "name": "InSTREAM-7.4_2026-02-11.zip",
    "url": "https://langrailsback.com/EcoModelFiles/InSTREAM-7.4_2026-02-11.zip",
    "sha256": "c26d2b39518c66aac81ece1690b166f782542a963aba93a973efddacc32972d8",
}
INSALMO_FIXTURE = {
    "name": "InSALMO-7.4_2026-02-11.zip",
    "url": "https://langrailsback.com/EcoModelFiles/InSALMO-7.4_2026-02-11.zip",
    "sha256": "2bc73da1ec769965adc2e3b33d4a74b5d31c09e006f46ee273f5a428c9045ae0",
}


def _download_url(url: str, target: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "OpenLimno fixture validation"},
    )
    with urllib.request.urlopen(request) as response, target.open("wb") as f:
        shutil.copyfileobj(response, f)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fixture_dir(
    tmp_path_factory: pytest.TempPathFactory,
    *,
    env_var: str = "OPENLIMNO_INSTREAM_FIXTURE_DIR",
    name: str = "openlimno_instream_fixtures",
) -> Path:
    env_dir = os.environ.get(env_var)
    if env_dir:
        path = Path(env_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return tmp_path_factory.mktemp(name)


def _download_zip(
    tmp_path_factory: pytest.TempPathFactory,
    *,
    fixture: dict[str, str] = INSTREAM_FIXTURE,
    enabled: bool = RUN_REAL_INSTREAM,
    env_var: str = "OPENLIMNO_INSTREAM_FIXTURE_DIR",
    fixture_dir_name: str = "openlimno_instream_fixtures",
    skip_message: str = "set OPENLIMNO_RUN_INSTREAM_REAL=1 to download and run inSTREAM tests",
) -> Path:
    if not enabled:
        pytest.skip(skip_message)

    target = _fixture_dir(
        tmp_path_factory,
        env_var=env_var,
        name=fixture_dir_name,
    ) / fixture["name"]
    expected = fixture["sha256"]
    if target.exists() and _sha256(target) == expected:
        return target
    _download_url(fixture["url"], target)
    actual = _sha256(target)
    if actual != expected:
        target.unlink(missing_ok=True)
        raise AssertionError(f"{target.name} SHA256 mismatch: expected {expected}, got {actual}")
    return target


def _extract(zip_path: Path, member: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = _fixture_dir(tmp_path_factory) / member
    if target.exists():
        return target
    with zipfile.ZipFile(zip_path) as z:
        z.extract(member, target.parent.parent)
    return target


def test_real_instream_depth_and_velocity_matrices_import(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    zip_path = _download_zip(tmp_path_factory)
    depth_path = _extract(
        zip_path,
        "Example-Project-A_1Reach-1Species/ExampleA-Depths.csv",
        tmp_path_factory,
    )
    velocity_path = _extract(
        zip_path,
        "Example-Project-A_1Reach-1Species/ExampleA-Vels.csv",
        tmp_path_factory,
    )

    depth_inspection = inspect_instream_exchange(depth_path)
    velocity_inspection = inspect_instream_exchange(velocity_path)
    assert depth_inspection.table_type == "ibm_hydraulic_lookup"
    assert velocity_inspection.table_type == "ibm_hydraulic_lookup"
    assert depth_inspection.detected_roles["depth_m"] == "depth_m"
    assert velocity_inspection.detected_roles["velocity_ms"] == "velocity_ms"

    depth = read_external_model(depth_path, source="instream-netlogo").table
    velocity = read_external_model(velocity_path, source="instream-netlogo").table

    assert depth.attrs["openlimno_output_table"] == "ibm_hydraulic_lookup"
    assert velocity.attrs["openlimno_output_table"] == "ibm_hydraulic_lookup"
    assert len(depth) == 35698
    assert len(velocity) == 35698
    assert depth["cell_id"].nunique() == 1373
    assert velocity["discharge_m3s"].nunique() == 26
    assert depth["depth_m"].max() > 0.0
    assert velocity["velocity_ms"].max() > 0.0


def test_real_instream_example_b_string_cell_matrices_import(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    zip_path = _download_zip(tmp_path_factory)
    depth_path = _extract(
        zip_path,
        "Example-Project-B_3Reaches-3Species/UpstreamReach-Depths.csv",
        tmp_path_factory,
    )
    velocity_path = _extract(
        zip_path,
        "Example-Project-B_3Reaches-3Species/UpstreamReach-Vels.csv",
        tmp_path_factory,
    )

    depth = read_external_model(depth_path, source="instream-netlogo").table
    velocity = read_external_model(velocity_path, source="instream-netlogo").table

    assert len(depth) == 44649
    assert len(velocity) == 44649
    assert depth["cell_id"].nunique() == 1353
    assert velocity["discharge_m3s"].nunique() == 33
    assert "T-1" in set(depth["cell_id"])
    assert depth["depth_m"].max() > 0.0
    assert velocity["velocity_ms"].max() > 0.0


def test_real_instream_official_benchmark_runs_native_smoke(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    zip_path = _download_zip(tmp_path_factory)
    root = extract_instream7_archive(zip_path, _fixture_dir(tmp_path_factory) / "extracted-benchmark")
    result = run_instream7_official_benchmark(
        root,
        _fixture_dir(tmp_path_factory) / "benchmark-out",
        days=1,
        seed=11,
        stochastic=False,
    )

    assert set(result.inventory["case_id"]) == {"ExampleA", "ExampleB"}
    assert len(result.inventory) == 4
    assert set(result.inventory["reach_id"]) == {"ExampleA", "Upstream", "Middle", "Downstream"}
    assert len(result.population_summary) == 20
    assert not result.final_individuals.empty
    assert any("-" in str(cell_id) for cell_id in result.cell_use["cell_id"])


def test_real_insalmo_official_benchmark_runs_adult_arrival_smoke(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    zip_path = _download_zip(
        tmp_path_factory,
        fixture=INSALMO_FIXTURE,
        enabled=RUN_REAL_INSALMO,
        env_var="OPENLIMNO_INSALMO_FIXTURE_DIR",
        fixture_dir_name="openlimno_insalmo_fixtures",
        skip_message="set OPENLIMNO_RUN_INSALMO_REAL=1 or OPENLIMNO_RUN_OFFICIAL_IBM=1",
    )
    root = extract_instream7_archive(
        zip_path,
        _fixture_dir(
            tmp_path_factory,
            env_var="OPENLIMNO_INSALMO_FIXTURE_DIR",
            name="openlimno_insalmo_fixtures",
        )
        / "extracted-insalmo-benchmark",
    )
    cases = discover_instream7_cases(root)

    assert [(case.case_id, len(case.reaches), case.species) for case in cases] == [
        ("ExampleA", 1, ("Chinook-Spring",)),
        ("ExampleB", 3, ("Chinook-Fall", "Chinook-Spring", "Rainbow")),
    ]
    assert all(case.adult_arrival_file is not None for case in cases)

    result = run_instream7_official_benchmark(
        root,
        _fixture_dir(
            tmp_path_factory,
            env_var="OPENLIMNO_INSALMO_FIXTURE_DIR",
            name="openlimno_insalmo_fixtures",
        )
        / "insalmo-benchmark-out",
        days=1,
        seed=11,
        stochastic=False,
    )

    assert set(result.inventory["case_id"]) == {"ExampleA", "ExampleB"}
    assert int(result.inventory["n_adult_arrival_fish"].sum()) == 2560
    assert set(result.inventory["reach_id"]) == {"ExampleA", "Upstream", "Middle", "Downstream"}
    assert {"Chinook-Spring", "Chinook-Fall"}.issubset(set(result.final_individuals["species"]))
    arrivals = result.events[result.events["event"] == "arrival"]
    assert int(arrivals["n"].sum()) > 0
    example_a = result.population_summary[
        (result.population_summary["scenario_id"] == "ExampleA")
        & (result.population_summary["species"] == "Chinook-Spring")
    ]
    assert int(example_a["abundance"].max()) > 0


def _population_totals(table: pd.DataFrame) -> tuple[int, float, float]:
    abundance = int(table["abundance"].sum())
    biomass_g = float(table["biomass_g"].sum())
    mean_length_mm = float((table["mean_length_mm"] * table["abundance"]).sum() / abundance)
    return abundance, biomass_g, mean_length_mm


def _assert_close_to_netlogo(
    native: pd.DataFrame,
    netlogo: pd.DataFrame,
    *,
    case_id: str,
) -> None:
    pairings = [
        ("initial", netlogo[netlogo["light_phase"] == "At setup"], native[native["day"] == 0]),
        ("after_2_days", netlogo[netlogo["end_time"] == sorted(netlogo["end_time"].unique())[-1]], native[native["day"] == 2]),
    ]
    for stage, netlogo_rows, native_rows in pairings:
        netlogo_abundance, netlogo_biomass, netlogo_length = _population_totals(netlogo_rows)
        native_abundance, native_biomass, native_length = _population_totals(native_rows)
        if stage == "initial":
            assert native_abundance == netlogo_abundance
        abundance_error = abs(native_abundance - netlogo_abundance) / max(netlogo_abundance, 1)
        biomass_error = abs(native_biomass - netlogo_biomass) / max(netlogo_biomass, 1.0)
        length_error = abs(native_length - netlogo_length)
        assert abundance_error <= 0.02, (case_id, stage, abundance_error)
        assert biomass_error <= 0.05, (case_id, stage, biomass_error)
        assert length_error <= 2.0, (case_id, stage, length_error)


def test_real_instream_netlogo_brief_short_comparison(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    if not RUN_NETLOGO_COMPARE:
        pytest.skip("set OPENLIMNO_RUN_INSTREAM_NETLOGO_COMPARE=1")
    brief_a = os.environ.get("OPENLIMNO_INSTREAM_NETLOGO_EXAMPLE_A_BRIEF")
    brief_b = os.environ.get("OPENLIMNO_INSTREAM_NETLOGO_EXAMPLE_B_BRIEF")

    zip_path = _download_zip(tmp_path_factory)
    root = extract_instream7_archive(zip_path, _fixture_dir(tmp_path_factory) / "extracted-netlogo-compare")
    out = _fixture_dir(tmp_path_factory) / "netlogo-compare-out"
    result = run_instream7_official_benchmark(
        root,
        out,
        days=2,
        seed=11,
        stochastic=False,
    )

    if brief_a and brief_b:
        netlogo_a = summarize_instream7_brief_population(read_instream7_brief_population(brief_a))
        netlogo_b = summarize_instream7_brief_population(read_instream7_brief_population(brief_b))
    else:
        netlogo_a = pd.read_csv(NETLOGO_SHORT_FIXTURE_DIR / "exampleA_brief_summary.csv")
        netlogo_b = pd.read_csv(NETLOGO_SHORT_FIXTURE_DIR / "exampleB_brief_summary.csv")
    native_a = result.population_summary[result.population_summary["scenario_id"] == "ExampleA"]
    native_b = result.population_summary[result.population_summary["scenario_id"] == "ExampleB"]

    _assert_close_to_netlogo(native_a, netlogo_a, case_id="ExampleA")
    _assert_close_to_netlogo(native_b, netlogo_b, case_id="ExampleB")

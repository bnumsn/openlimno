"""Real PHABSIM Fortran parity harness for unfreeze gate U3.

This benchmark is opt-in via OPENLIMNO_PHABSIM_REAL_IMAGE. It runs the
USFWS IFG4/HABTAE container on the synthesized Bovee 1997 section 5.1
deck, reads the normalized HABTAE output, runs OpenLimno from the same
deck via the future PHABSIM IFG4 importer, and diffs cell WUA values.

The deck is a provenance-labelled synthesis, not a canonical USFWS deck.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from openlimno.habitat import load_hsi_from_parquet

pytestmark = pytest.mark.benchmark

ROOT = Path(__file__).resolve().parent
DECK = ROOT / "inputs" / "bovee1997_5_1.dat"
TOL = 1.0e-3


def _q_values(deck: Path) -> list[float]:
    for line in deck.read_text(encoding="utf-8").splitlines():
        if line.strip().upper().startswith("Q "):
            return [float(x) for x in line.split()[1:]]
    raise ValueError(f"no Q card found in {deck}")


def _run_phabsim_container(image: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{ROOT}:/work:ro",
            "-v",
            f"{out_dir}:/outputs",
            image,
            "/work/inputs/bovee1997_5_1.dat",
            "/outputs",
        ],
        cwd=ROOT,
        check=True,
    )
    csv_path = out_dir / "phabsim_normalised.csv"
    if not csv_path.exists():
        raise AssertionError(
            "PHABSIM run completed but did not write "
            "outputs/phabsim_normalised.csv. run_phabsim.sh must normalize "
            "HABTAE output to station_m,discharge_m3s,species,life_stage,wua_m2."
        )
    return csv_path


def _read_phabsim_cells(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    needed = {"station_m", "discharge_m3s", "species", "life_stage", "wua_m2"}
    missing = needed - set(df.columns)
    if missing:
        raise AssertionError(f"PHABSIM normalized output missing {sorted(missing)}")
    return df[list(needed)].sort_values(
        ["station_m", "discharge_m3s", "species", "life_stage"]
    ).reset_index(drop=True)


def _openlimno_case_from_deck(deck: Path, tmp_path: Path):
    """Load IFG4 via the intended importer boundary.

    The importer is not present in the repo as of 2026-05-20. This
    harness deliberately makes that remaining boundary explicit instead
    of hiding it behind a second synthetic parser.
    """
    try:
        from openlimno.preprocess.legacy import read_phabsim_ifg4_case
    except ImportError as exc:  # pragma: no cover - expected until importer lands
        raise AssertionError(
            "openlimno.preprocess.legacy.read_phabsim_ifg4_case is not "
            "implemented yet. U3 cannot close until the IFG4 deck importer "
            "creates an OpenLimno Case from the same deck the Fortran binary runs."
        ) from exc
    return read_phabsim_ifg4_case(deck, work_dir=tmp_path)


def _openlimno_cell_wua(case, q_values: list[float]) -> pd.DataFrame:
    result = case.run(discharges_m3s=q_values)
    cfg = case.config
    hsi_path = case._resolve_safe(cfg["data"]["hsi_curve"])  # noqa: SLF001
    hsi_curves = load_hsi_from_parquet(hsi_path)
    habitat = cfg["habitat"]
    composite = habitat.get("composite", "geometric_mean")
    ack = bool(habitat.get("acknowledge_independence", False))
    rows = []
    for q in result.discharges_m3s:
        for species in habitat["species"]:
            for stage in habitat["stages"]:
                csi, area = case._compute_cell_csi_and_area(  # noqa: SLF001
                    result.hydraulic_results[q],
                    hsi_curves,
                    species,
                    stage,
                    composite,
                    ack,
                    result.warnings,
                )
                if csi is None:
                    csi = [0.0] * len(area)
                for section, csi_i, area_i in zip(result.sections, csi, area, strict=True):
                    rows.append(
                        {
                            "station_m": float(section.station_m),
                            "discharge_m3s": float(q),
                            "species": species,
                            "life_stage": stage,
                            "wua_m2": float(csi_i * area_i),
                        }
                    )
    return pd.DataFrame(rows).sort_values(
        ["station_m", "discharge_m3s", "species", "life_stage"]
    ).reset_index(drop=True)


@pytest.mark.skipif(
    not os.environ.get("OPENLIMNO_PHABSIM_REAL_IMAGE"),
    reason="set OPENLIMNO_PHABSIM_REAL_IMAGE=<oci-ref> to run U3 real binary parity",
)
def test_phabsim_real_run_matches_openlimno_bovee_5_1(tmp_path: Path) -> None:
    image = os.environ["OPENLIMNO_PHABSIM_REAL_IMAGE"]
    assert DECK.exists()

    phabsim = _read_phabsim_cells(_run_phabsim_container(image, tmp_path / "phabsim"))
    case = _openlimno_case_from_deck(DECK, tmp_path / "openlimno")
    openlimno = _openlimno_cell_wua(case, _q_values(DECK))

    joined = openlimno.merge(
        phabsim,
        on=["station_m", "discharge_m3s", "species", "life_stage"],
        suffixes=("_openlimno", "_phabsim"),
        how="outer",
        indicator=True,
    )
    assert set(joined["_merge"]) == {"both"}
    joined["abs_delta"] = (
        joined["wua_m2_openlimno"] - joined["wua_m2_phabsim"]
    ).abs()
    assert joined["abs_delta"].max() <= TOL

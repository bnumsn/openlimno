"""Opt-in inSTREAM interoperability tests against public example input files.

These tests intentionally do not run by default. Enable them explicitly with:

    OPENLIMNO_RUN_INSTREAM_REAL=1 pytest tests/integration/test_instream_real_fixtures.py
"""

from __future__ import annotations

import hashlib
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

import pytest

from openlimno.preprocess import inspect_instream_exchange, read_external_model

RUN_REAL_INSTREAM = os.environ.get("OPENLIMNO_RUN_INSTREAM_REAL") == "1"

pytestmark = [
    pytest.mark.online,
]


INSTREAM_FIXTURE = {
    "name": "InSTREAM-7.4_2026-02-11.zip",
    "url": "https://langrailsback.com/EcoModelFiles/InSTREAM-7.4_2026-02-11.zip",
    "sha256": "c26d2b39518c66aac81ece1690b166f782542a963aba93a973efddacc32972d8",
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


def _fixture_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    env_dir = os.environ.get("OPENLIMNO_INSTREAM_FIXTURE_DIR")
    if env_dir:
        path = Path(env_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return tmp_path_factory.mktemp("openlimno_instream_fixtures")


def _download_zip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not RUN_REAL_INSTREAM:
        pytest.skip("set OPENLIMNO_RUN_INSTREAM_REAL=1 to download and run inSTREAM tests")

    target = _fixture_dir(tmp_path_factory) / INSTREAM_FIXTURE["name"]
    expected = INSTREAM_FIXTURE["sha256"]
    if target.exists() and _sha256(target) == expected:
        return target
    _download_url(INSTREAM_FIXTURE["url"], target)
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

"""Opt-in HABBY/CASiMiR habitat-table validation against user/public fixtures.

No stable, small, version-pinned public HABBY/CASiMiR exported table is bundled
as a default fixture yet. This test is a ready validation hook for project files
or future public fixtures:

    OPENLIMNO_RUN_HABITAT_EXCHANGE_REAL=1 \
    OPENLIMNO_HABITAT_EXCHANGE_FIXTURE=/path/to/habby_wua_cells.csv \
    pytest tests/integration/test_habitat_exchange_real_fixtures.py

or:

    OPENLIMNO_RUN_HABITAT_EXCHANGE_REAL=1 \
    OPENLIMNO_HABITAT_EXCHANGE_URL=https://.../casimir_wua_summary.csv \
    OPENLIMNO_HABITAT_EXCHANGE_SHA256=... \
    pytest tests/integration/test_habitat_exchange_real_fixtures.py

The fixture may be CSV/TSV/TXT/Parquet. HABBY's official TELEMAC tutorial
archive publishes hydraulic/substrate inputs but does not currently include the
post-calculation `*_spu.txt` or `*_detailled_mesh.txt` exports, so this hook
stays local/URL driven until a small public exported table is pinned.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import urllib.request
from pathlib import Path

import pytest

from openlimno.preprocess import inspect_habitat_exchange, read_external_model

RUN_REAL_HABITAT = os.environ.get("OPENLIMNO_RUN_HABITAT_EXCHANGE_REAL") == "1"

pytestmark = [
    pytest.mark.online,
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fixture_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    env_dir = os.environ.get("OPENLIMNO_HABITAT_EXCHANGE_FIXTURE_DIR")
    if env_dir:
        path = Path(env_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return tmp_path_factory.mktemp("openlimno_habitat_exchange_fixtures")


def _download_url(url: str, target: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "OpenLimno fixture validation"},
    )
    with urllib.request.urlopen(request) as response, target.open("wb") as f:
        shutil.copyfileobj(response, f)


def _fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not RUN_REAL_HABITAT:
        pytest.skip("set OPENLIMNO_RUN_HABITAT_EXCHANGE_REAL=1 and provide a fixture path or URL")

    local = os.environ.get("OPENLIMNO_HABITAT_EXCHANGE_FIXTURE")
    if local:
        path = Path(local)
        if not path.exists():
            raise AssertionError(f"habitat exchange fixture does not exist: {path}")
        return path

    url = os.environ.get("OPENLIMNO_HABITAT_EXCHANGE_URL")
    if not url:
        pytest.skip("set OPENLIMNO_HABITAT_EXCHANGE_FIXTURE or OPENLIMNO_HABITAT_EXCHANGE_URL")

    target = _fixture_dir(tmp_path_factory) / Path(url).name
    expected = os.environ.get("OPENLIMNO_HABITAT_EXCHANGE_SHA256")
    if target.exists() and (expected is None or _sha256(target) == expected):
        return target
    _download_url(url, target)
    if expected is not None:
        actual = _sha256(target)
        if actual != expected:
            target.unlink(missing_ok=True)
            raise AssertionError(
                f"{target.name} SHA256 mismatch: expected {expected}, got {actual}"
            )
    return target


def test_real_habby_casimir_exchange_table_imports(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    path = _fixture_path(tmp_path_factory)

    inspection = inspect_habitat_exchange(path)
    assert inspection.table_type in {"habitat_cells", "wua_summary"}

    result = read_external_model(path, source="habby-csv")

    assert result.source_key == "habby-csv"
    assert result.table.attrs["openlimno_output_table"] in {"habitat_cells", "wua_summary"}
    assert len(result.table) > 0
    assert "wua_m2" in result.table.columns

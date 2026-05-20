"""Round-20 codex A10 + gemini A7 (HIGH convergent): SCHISM run failure
must NOT silently substitute Builtin1D.

Pre-fix `Case.run` had ``if dry or report.return_code != 0:`` →
Builtin1D for both branches. Meaning a user running real SCHISM whose
container crashed mid-run got 1D math + a soft warning. The SL-712 /
FERC / WFD exports would then be 1D-derived while the case YAML
said SCHISM 2D — a regulatory-defense hazard.

Post-fix:
- ``dry_run=True``: still falls back to Builtin1D (intentional CI path)
- ``return_code != 0``: raises RuntimeError with a clear message

Both pinned here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml


def _make_schism_case(case_dir: Path) -> Any:
    """Build a minimal SCHISM-backed Case from a temp case.yaml.
    The actual SCHISM adapter is monkey-patched below; we only need
    the case.yaml + Case loader to accept the SCHISM backend."""
    from openlimno.case import Case
    case_dir.mkdir(parents=True, exist_ok=True)
    case_yaml = case_dir / "case.yaml"
    # Use the schism fixture from tests/integration/fixtures/lemhi-tiny
    # as the schema template — keep it minimal here.
    repo = Path(__file__).resolve().parents[2]
    cs = repo / "data" / "lemhi" / "cross_section.parquet"
    hsi = repo / "data" / "lemhi" / "hsi_curve.parquet"
    if not cs.exists() or not hsi.exists():
        pytest.skip("Lemhi fixtures not shipped; cannot test SCHISM path")
    case_yaml.write_text(
        yaml.safe_dump({
            "openlimno": "0.2",
            "case": {
                "name": "r20_schism_no_fallback",
                "crs": "EPSG:4326",
                "allowed_data_roots": [str(repo / "data")],
            },
            "mesh": {"uri": str(repo / "data" / "lemhi" / "mesh.ugrid.nc")},
            "data": {
                "cross_section": str(cs),
                "hsi_curve": str(hsi),
            },
            "hydrodynamics": {
                "backend": "schism",
                "schism": {"dry_run": False},
            },
            "habitat": {
                "species": ["oncorhynchus_mykiss"],
                "stages": ["spawning"],
                "metric": "wua-q",
                "composite": "min",
                "scale": "cell",
            },
            "output": {
                "dir": str(case_dir / "out"),
                "formats": ["csv"],
            },
        }),
        encoding="utf-8",
    )
    return Case.from_yaml(case_yaml)


@dataclass
class _FakeReport:
    return_code: int
    dry_run: bool
    log_path: Path


def test_round20_schism_nonzero_return_code_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """codex A10 / gemini A7: a real SCHISM failure (rc != 0) must
    raise, NOT silently substitute Builtin1D."""
    from openlimno.hydro import schism as schism_mod

    case = _make_schism_case(tmp_path / "case_dir")

    # Force the SCHISM adapter's run() to return a failure report.
    log_dir = tmp_path / "case_dir" / "out"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "schism.log"
    log_path.write_text("planted SCHISM failure\n")

    fake_report = _FakeReport(return_code=42, dry_run=False, log_path=log_path)

    def _fake_prepare(self: Any, *args: Any, **kwargs: Any) -> None:
        return None

    def _fake_run(self: Any, *args: Any, **kwargs: Any) -> _FakeReport:
        return fake_report

    monkeypatch.setattr(schism_mod.SCHISMAdapter, "prepare", _fake_prepare)
    monkeypatch.setattr(schism_mod.SCHISMAdapter, "run", _fake_run)

    with pytest.raises(RuntimeError, match="SCHISM hydrodynamic run failed"):
        case.run(discharges_m3s=[5.0])


def test_round20_schism_dry_run_still_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """codex A10 / gemini A7: the dry_run=True CI path is intentional
    and must continue to fall back to Builtin1D + emit the
    'dry_run=True' warning. Pin so the fix doesn't over-correct."""
    from openlimno.hydro import schism as schism_mod

    case = _make_schism_case(tmp_path / "case_dir2")
    # Flip dry_run on in config.
    case.config["hydrodynamics"]["schism"]["dry_run"] = True

    log_dir = tmp_path / "case_dir2" / "out"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "schism.log"
    log_path.write_text("dry run\n")

    fake_report = _FakeReport(return_code=0, dry_run=True, log_path=log_path)

    def _fake_prepare(self: Any, *args: Any, **kwargs: Any) -> None:
        return None

    def _fake_run(self: Any, *args: Any, **kwargs: Any) -> _FakeReport:
        return fake_report

    monkeypatch.setattr(schism_mod.SCHISMAdapter, "prepare", _fake_prepare)
    monkeypatch.setattr(schism_mod.SCHISMAdapter, "run", _fake_run)

    # Should NOT raise; dry-run fallback path is intentional.
    result = case.run(discharges_m3s=[5.0])
    assert any(
        "dry_run=True" in w and "Builtin1D" in w
        for w in result.warnings
    ), (
        f"Round-20 fix regression: dry_run=True path no longer emits "
        f"the explicit 'used Builtin1D approximation' warning. Got "
        f"warnings: {result.warnings}"
    )

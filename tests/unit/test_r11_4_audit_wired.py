"""R-DOC-AUDIT-WIRED — pin that R11-4 (path-safety sandbox) is
actually wired into the v2.6/v2.7 inline-raster loaders.

R11-4 (10th-round, v2.10.1 → v3.0 sandbox closure) declared that
every USER-supplied ``data.*.uri`` read must route through
``Case._resolve_safe`` so a malicious case.yaml can't read
``/etc/shadow``. SPEC_v3.md §3 lists 11 audit sites with 10/11
sandboxed. But the v2.6/v2.7 inline-raster loaders shipped BEFORE
the audit pass and used direct ``self.case_dir / uri`` joins,
bypassing the sandbox entirely. They were missed by the v3.0 sweep.

2026-05-20 R-DOC-AUDIT-WIRED routes all 5 affected loaders through
``_resolve_safe``:

1. ``_maybe_compute_per_section_thermal_si_from_raster`` (v2.6.0)
2. ``_maybe_load_per_section_thermal_si`` (v2.5.1)
3. ``_maybe_compute_per_section_cover_si_from_raster`` (v2.7.0)
4. ``_maybe_load_per_section_cover_si`` (v2.7.0)

Each now: catches ``ValueError`` from the sandbox (when
``allowed_data_roots`` is set + URI escapes), emits a fallback
warning, returns ``None`` so the run degrades to scalar SI rather
than aborting. Same contract as the existing "file missing"
fallback path.

Pin via:
1. Source-inspection that ``self._resolve_safe`` is the resolver
   in each loader (no remaining ``self.case_dir / uri.resolve()``
   pattern there).
2. Behavioural test: a case with ``allowed_data_roots: []`` and a
   ``data.thermal_raster.uri`` pointing OUTSIDE the case dir gets
   a sandbox-rejection warning and the loader returns None,
   instead of silently reading the escaped file.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from openlimno.case import Case


# ---------------------------------------------------------------------
# Source-inspection pins
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "method_name",
    [
        "_maybe_compute_per_section_thermal_si_from_raster",
        "_maybe_load_per_section_thermal_si",
        "_maybe_compute_per_section_cover_si_from_raster",
        "_maybe_load_per_section_cover_si",
    ],
)
def test_r114_inline_raster_loader_uses_resolve_safe(method_name: str) -> None:
    """R-DOC-AUDIT-WIRED #1: each of the 4 inline-raster loaders
    must use ``self._resolve_safe`` for URI resolution, not the
    unsafe ``self.case_dir / uri`` pattern that pre-v3 ships used.
    """
    method = getattr(Case, method_name)
    src = inspect.getsource(method)
    assert "self._resolve_safe(" in src, (
        f"R11-4 audit regression: {method_name} no longer routes "
        f"its data.*.uri through _resolve_safe; the v3.0 path-"
        f"safety sandbox is bypassed for this loader."
    )
    # The old unsafe pattern (case_dir / uri).resolve() must NOT
    # appear in the body — it would mean a refactor reverted the
    # audit.
    assert "self.case_dir / " not in src, (
        f"R11-4 audit regression: {method_name} reintroduced the "
        f"raw ``self.case_dir / uri`` join that bypasses the sandbox."
    )


# ---------------------------------------------------------------------
# Behavioural pin — sandbox actually rejects an out-of-case data URI
# ---------------------------------------------------------------------
def test_r114_inline_thermal_raster_rejected_when_outside_sandbox(
    tmp_path: Path,
) -> None:
    """R-DOC-AUDIT-WIRED #2: when ``allowed_data_roots: []`` (strict
    case-dir-only) is set AND ``data.thermal_raster.uri`` resolves
    OUTSIDE the case dir, the loader must emit a sandbox-rejection
    warning and return None — NOT silently read the escaped file.
    """
    case_dir = tmp_path / "case_dir"
    case_dir.mkdir()
    escape_dir = tmp_path / "escape"
    escape_dir.mkdir()
    # Plant a file outside the sandbox; if the audit fails, the
    # loader will read it. If the audit holds, the sandbox check
    # rejects the URI before any read.
    escaped_raster = escape_dir / "evil.tif"
    escaped_raster.write_bytes(b"\x00" * 32)
    escaped_locs = escape_dir / "evil_locs.csv"
    escaped_locs.write_text("station_m,lon,lat\n0,1,1\n")

    # Build a Case with strict sandbox.
    case = Case(
        config={
            "case": {
                "name": "r114_audit",
                "crs": "EPSG:4326",
                "allowed_data_roots": [],  # strict: case_dir only
            },
            "data": {
                "thermal_raster": {"uri": str(escaped_raster.resolve())},
                "section_locations": {"uri": str(escaped_locs.resolve())},
            },
        },
        case_yaml_path=(case_dir / "case.yaml").resolve(),
    )

    warnings: list[str] = []
    out = case._maybe_compute_per_section_thermal_si_from_raster(
        case.config, [object()], warnings,
    )
    assert out is None, (
        "R11-4 audit regression: inline-thermal-raster loader "
        "silently consumed a path outside allowed_data_roots."
    )
    assert any(
        "sandbox" in w.lower() or "allowed_data_roots" in w.lower() or "outside" in w.lower()
        for w in warnings
    ), (
        f"R11-4 audit regression: sandbox rejection didn't surface "
        f"in warnings: {warnings}"
    )


def test_r114_inline_cover_raster_rejected_when_outside_sandbox(
    tmp_path: Path,
) -> None:
    """R-DOC-AUDIT-WIRED #3: symmetric pin for the cover-raster
    loader — same charter, different module."""
    case_dir = tmp_path / "case_dir2"
    case_dir.mkdir()
    escape_dir = tmp_path / "escape2"
    escape_dir.mkdir()
    escaped_raster = escape_dir / "evil_cover.tif"
    escaped_raster.write_bytes(b"\x00" * 32)
    escaped_locs = escape_dir / "evil_locs.csv"
    escaped_locs.write_text("station_m,lon,lat\n0,1,1\n")

    case = Case(
        config={
            "case": {
                "name": "r114_audit_cover",
                "crs": "EPSG:4326",
                "allowed_data_roots": [],
            },
            "data": {
                "cover_raster": {"uri": str(escaped_raster.resolve())},
                "section_locations": {"uri": str(escaped_locs.resolve())},
            },
        },
        case_yaml_path=(case_dir / "case.yaml").resolve(),
    )

    warnings: list[str] = []
    out = case._maybe_compute_per_section_cover_si_from_raster(
        case.config, [object()], warnings,
    )
    assert out is None
    assert any(
        "sandbox" in w.lower() or "allowed_data_roots" in w.lower() or "outside" in w.lower()
        for w in warnings
    )


def test_r114_inline_thermal_si_per_section_rejected_when_outside_sandbox(
    tmp_path: Path,
) -> None:
    """R-DOC-AUDIT-WIRED #4: pin the CSV-input loader path too."""
    case_dir = tmp_path / "case_dir3"
    case_dir.mkdir()
    escape_dir = tmp_path / "escape3"
    escape_dir.mkdir()
    escaped_csv = escape_dir / "evil_si.csv"
    escaped_csv.write_text("station_m,thermal_si\n0,0.5\n")

    case = Case(
        config={
            "case": {
                "name": "r114_audit_csv",
                "crs": "EPSG:4326",
                "allowed_data_roots": [],
            },
            "data": {
                "thermal_si_per_section": {"uri": str(escaped_csv.resolve())},
            },
        },
        case_yaml_path=(case_dir / "case.yaml").resolve(),
    )

    warnings: list[str] = []
    out = case._maybe_load_per_section_thermal_si(
        case.config, [object()], warnings,
    )
    assert out is None
    assert any(
        "sandbox" in w.lower() or "allowed_data_roots" in w.lower() or "outside" in w.lower()
        for w in warnings
    )


def test_r114_inline_cover_si_per_section_rejected_when_outside_sandbox(
    tmp_path: Path,
) -> None:
    """R-DOC-AUDIT-WIRED #5: pin the symmetric cover CSV loader."""
    case_dir = tmp_path / "case_dir4"
    case_dir.mkdir()
    escape_dir = tmp_path / "escape4"
    escape_dir.mkdir()
    escaped_csv = escape_dir / "evil_cover_si.csv"
    escaped_csv.write_text("station_m,cover_si\n0,0.5\n")

    case = Case(
        config={
            "case": {
                "name": "r114_audit_cover_csv",
                "crs": "EPSG:4326",
                "allowed_data_roots": [],
            },
            "data": {
                "cover_si_per_section": {"uri": str(escaped_csv.resolve())},
            },
        },
        case_yaml_path=(case_dir / "case.yaml").resolve(),
    )

    warnings: list[str] = []
    out = case._maybe_load_per_section_cover_si(
        case.config, [object()], warnings,
    )
    assert out is None
    assert any(
        "sandbox" in w.lower() or "allowed_data_roots" in w.lower() or "outside" in w.lower()
        for w in warnings
    )

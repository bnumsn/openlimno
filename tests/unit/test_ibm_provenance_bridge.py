"""R-IBM-PROVENANCE: pin the Case-compatible provenance.json bridge.

Per ADR-0016 cleanup track + round-22 codex A5 / gemini A4 HIGH
(provenance fork), a standalone IBM run via
``run_native_ibm`` + ``write_native_ibm_result`` must emit BOTH:

  - ``ibm_run_manifest.json``  — IBM-specific schema (back-compat)
  - ``provenance.json``        — Case-compatible schema with an
                                  ``ibm`` extension block + SHA
                                  link to the sibling manifest

Audit tools can now read either file. The two are linked by
SHA-256 so they're verifiably consistent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from openlimno.ibm import (
    NativeIBMConfig,
    SpeciesProfile,
    build_initial_population,
    run_native_ibm,
)
from openlimno.ibm.native import write_native_ibm_result


def _habitat_cells() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cell_id": [10, 20, 30],
            "area_m2": [25.0, 30.0, 20.0],
            "depth_m": [0.2, 0.7, 1.6],
            "velocity_ms": [0.1, 0.35, 1.1],
            "csi": [0.25, 0.95, 0.35],
            "temperature_c": [12.0, 12.0, 12.0],
            "hiding_cover": [0.1, 0.8, 0.2],
            "feeding_cover": [0.1, 0.6, 0.2],
        }
    )


def _run(tmp_path: Path) -> tuple[Path, Path]:
    """Run a minimal IBM, write results, return (manifest, provenance) paths."""
    pop = build_initial_population(n=10, length_mm=120.0)
    result = run_native_ibm(
        _habitat_cells(),
        pop,
        profile=SpeciesProfile(),
        config=NativeIBMConfig(days=5, seed=42, scenario_id="prov_pin", reach_id="r1"),
    )
    paths = write_native_ibm_result(result, tmp_path)
    return Path(paths["ibm_run_manifest"]), Path(paths["provenance"])


def test_ibm_run_emits_both_manifest_and_provenance(tmp_path: Path) -> None:
    """R-IBM-PROVENANCE: ibm_run_manifest.json AND provenance.json
    must both be written by write_native_ibm_result."""
    manifest, provenance = _run(tmp_path)
    assert manifest.exists(), "back-compat: ibm_run_manifest.json must still exist"
    assert provenance.exists(), "R-IBM-PROVENANCE: provenance.json must be emitted"


def test_ibm_provenance_uses_case_schema(tmp_path: Path) -> None:
    """provenance.json's schema field identifies it as a Case-compatible
    provenance with IBM extension. Audit tools can detect IBM-extended
    provenance via this field."""
    _, provenance = _run(tmp_path)
    data = json.loads(provenance.read_text(encoding="utf-8"))
    assert data["schema"] == "openlimno-provenance/0.1+ibm", (
        "R-IBM-PROVENANCE regression: provenance.json schema field "
        "no longer marks the IBM extension correctly. Audit tools "
        "may misclassify the file."
    )


def test_ibm_provenance_has_standard_case_fields(tmp_path: Path) -> None:
    """The standard Case provenance fields must be present so audit
    tools that only know the openlimno-provenance schema can still
    read the file."""
    _, provenance = _run(tmp_path)
    data = json.loads(provenance.read_text(encoding="utf-8"))
    required_keys = {
        "openlimno_version",
        "schema",
        "run_at",
        "machine",
        "parameter_fingerprint",
        "inputs",
        "outputs",
        "dependencies",
        "warnings",
        "studyplan_present",
    }
    missing = required_keys - set(data.keys())
    assert not missing, (
        f"R-IBM-PROVENANCE: provenance.json missing Case-compatible fields: {missing}"
    )


def test_ibm_provenance_links_to_manifest_by_sha(tmp_path: Path) -> None:
    """The bridge contract: provenance.json's ``ibm.manifest_sha256``
    must equal the SHA-256 of ibm_run_manifest.json on disk. This
    makes the two files an audit chain."""
    import hashlib

    manifest_path, provenance_path = _run(tmp_path)
    data = json.loads(provenance_path.read_text(encoding="utf-8"))
    ibm_block = data["ibm"]
    assert ibm_block["manifest_path"] == manifest_path.name
    claimed_sha = ibm_block["manifest_sha256"]
    actual_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert claimed_sha == actual_sha, (
        f"R-IBM-PROVENANCE regression: provenance.json claims "
        f"manifest_sha256={claimed_sha[:16]}... but the actual "
        f"ibm_run_manifest.json hashes to {actual_sha[:16]}... — "
        f"the audit chain is broken."
    )


def test_ibm_provenance_fingerprint_stable_across_runs(tmp_path: Path) -> None:
    """Reproducibility companion: same seed → same parameter_fingerprint
    → audit-chain hashes match between two reproductions."""
    manifest_a, provenance_a = _run(tmp_path / "a")
    manifest_b, provenance_b = _run(tmp_path / "b")
    fp_a = json.loads(provenance_a.read_text())["parameter_fingerprint"]
    fp_b = json.loads(provenance_b.read_text())["parameter_fingerprint"]
    assert fp_a == fp_b, (
        f"R-IBM-PROVENANCE: same-seed runs produced different parameter_"
        f"fingerprint (a={fp_a[:16]}..., b={fp_b[:16]}...). Either the "
        f"seed isn't deterministic OR the fingerprint is salted with "
        f"non-input data (run timestamp, hostname, etc.)."
    )

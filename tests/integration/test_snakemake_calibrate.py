"""Snakefile workflow integration test.

When ``snakemake`` is on PATH, dry-runs the calibrate.smk workflow against
the Lemhi sample to confirm the rule graph resolves. Otherwise asserts the
file is well-formed and the configured commands compose correctly.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAKEFILE = REPO_ROOT / "src" / "openlimno" / "workflows" / "snakefiles" / "calibrate.smk"
LEMHI_DIR = REPO_ROOT / "data" / "lemhi"


def test_snakefile_exists_and_well_formed() -> None:
    """Snakefile is present and contains the canonical rules."""
    assert SNAKEFILE.exists(), f"Snakefile missing: {SNAKEFILE}"
    text = SNAKEFILE.read_text()
    # Required rules / config knobs (SPEC §3.5)
    assert "rule all:" in text
    assert "rule calibrate:" in text
    assert "config.get(\"case\")" in text or 'config.get("case")' in text
    assert "openlimno calibrate" in text


def test_snakefile_rejects_missing_config() -> None:
    """When neither case nor observed are passed, the smk must error fast."""
    if shutil.which("snakemake") is None:
        pytest.skip("snakemake not installed")
    proc = subprocess.run(
        ["snakemake", "-s", str(SNAKEFILE), "--cores", "1", "-n"],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=30,
    )
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "case=" in combined or "observed" in combined or "Snakefile" in combined


def test_snakefile_dry_run_with_lemhi() -> None:
    """End-to-end --dry-run resolves the rule graph for Lemhi config."""
    if shutil.which("snakemake") is None:
        pytest.skip("snakemake not installed")
    if not (LEMHI_DIR / "rating_curve.parquet").exists():
        pytest.skip("Lemhi data not built")
    case = REPO_ROOT / "examples" / "lemhi" / "case.yaml"
    observed = LEMHI_DIR / "rating_curve.parquet"
    proc = subprocess.run(
        ["snakemake", "-s", str(SNAKEFILE),
         "--cores", "1", "-n",
         "--config", f"case={case}", f"observed={observed}",
         "out=/tmp/openlimno_calib_dryrun"],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=60,
    )
    assert proc.returncode == 0, (
        f"snakemake dry-run failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert "calibrate" in proc.stdout

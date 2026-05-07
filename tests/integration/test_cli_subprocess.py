"""CLI integration tests that spawn ``python -m openlimno`` as a subprocess.

The other CLI tests use ``click.testing.CliRunner`` (in-process) which is fast
but only exercises the Click decorators. These tests confirm the binary path
through the entry-point registered in ``pyproject.toml`` works end-to-end
(import-time errors, missing data, exit codes are all surfaced realistically).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LEMHI_CASE = REPO / "examples" / "lemhi" / "case.yaml"
LEMHI_DATA = REPO / "data" / "lemhi"


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    return subprocess.run(
        [sys.executable, "-m", "openlimno", *args],
        capture_output=True, text=True, cwd=cwd or REPO, env=env,
        timeout=120,
    )


def test_help_invokes_successfully() -> None:
    proc = _run("--help")
    assert proc.returncode == 0
    assert "Usage:" in proc.stdout
    # Verify all 10 top-level commands are registered (SPEC §3.4)
    for cmd in ("init", "validate", "run", "wua", "passage",
                "calibrate", "reproduce", "studyplan", "hsi", "preprocess"):
        assert cmd in proc.stdout, f"command '{cmd}' missing from --help"


def test_version_runs() -> None:
    proc = _run("--version")
    assert proc.returncode == 0
    assert "openlimno" in proc.stdout.lower()


def test_validate_lemhi_case_via_subprocess() -> None:
    if not LEMHI_CASE.exists():
        pytest.skip("Lemhi case missing")
    proc = _run("validate", str(LEMHI_CASE))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_validate_rejects_missing_file(tmp_path: Path) -> None:
    proc = _run("validate", str(tmp_path / "no_such_case.yaml"))
    assert proc.returncode != 0


def test_init_creates_skeleton(tmp_path: Path) -> None:
    target = tmp_path / "subproc_proj"
    proc = _run("init", str(target), "--basin", "test-basin")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (target / "case.yaml").exists()
    assert (target / "studyplan.yaml").exists()


def test_run_lemhi_via_subprocess(tmp_path: Path) -> None:
    """Smoke-test the ``run`` command on a tiny redirect of the Lemhi case."""
    if not LEMHI_DATA.exists() or not LEMHI_CASE.exists():
        pytest.skip("Lemhi data missing")
    # Copy case YAML into tmp_path with output redirected so we don't pollute
    # the canonical examples/ tree
    out_dir = tmp_path / "out"
    redirected = tmp_path / "case.yaml"
    yaml_text = LEMHI_CASE.read_text()
    yaml_text = yaml_text.replace("./out/lemhi_2024/", str(out_dir) + "/")
    yaml_text = yaml_text.replace(
        "../../data/lemhi/", str(LEMHI_DATA) + "/"
    )
    redirected.write_text(yaml_text)

    proc = _run("run", str(redirected))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (out_dir / "wua_q.csv").exists()
    assert (out_dir / "provenance.json").exists()


def test_studyplan_validate_lemhi_via_subprocess() -> None:
    sp = REPO / "examples" / "lemhi" / "studyplan.yaml"
    if not sp.exists():
        pytest.skip("studyplan missing")
    proc = _run("studyplan", "validate", str(sp))
    assert proc.returncode == 0, proc.stdout + proc.stderr

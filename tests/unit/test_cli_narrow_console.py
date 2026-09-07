"""The CLI must survive a console whose codec cannot encode its own output.

Regression net for a real Windows CI break. ``openlimno.fishtank.cli`` hardened
``sys.stdout``/``sys.stderr`` as a module-scope side effect; ``openlimno.cli``
imported that module eagerly, so every subcommand inherited the protection
without asking for it. Making the fishtank import lazy removed ~750 ms from
every invocation — and silently removed the hardening from every non-fishtank
command, so ``openlimno validate``'s ``✓`` aborted with UnicodeEncodeError on
Windows cp1252 while Linux and macOS stayed green.

``PYTHONIOENCODING`` reproduces that condition on any platform, which is the
point: these tests would have caught the break on the Linux box where it was
written, without waiting for the Windows matrix job.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LEMHI_CASE = REPO_ROOT / "examples" / "lemhi" / "case.yaml"

#: Narrow codecs that cannot represent the glyphs the CLI prints. "ascii" stands
#: in for the general case; "cp1252" is literally what Windows CI runs.
NARROW_ENCODINGS = ["ascii", "cp1252"]


def _run(args: list[str], encoding: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONIOENCODING": encoding,
        "PYTHONNOUSERSITE": "1",
    }
    return subprocess.run(
        [sys.executable, "-m", "openlimno", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=REPO_ROOT,
        timeout=300,
    )


@pytest.mark.parametrize("encoding", NARROW_ENCODINGS)
def test_validate_prints_check_mark_without_crashing(encoding: str) -> None:
    """``openlimno validate`` prints U+2713, the exact glyph that broke."""
    proc = _run(["validate", str(LEMHI_CASE)], encoding)
    assert "UnicodeEncodeError" not in proc.stderr, (
        f"CLI aborted on a {encoding} console. The stdio hardening in "
        f"openlimno._console is not reaching this command.\n{proc.stderr}"
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize("encoding", NARROW_ENCODINGS)
@pytest.mark.parametrize("args", [["--help"], ["fishtank", "--help"], ["--version"]])
def test_cli_surfaces_survive_a_narrow_console(args: list[str], encoding: str) -> None:
    proc = _run(args, encoding)
    assert "UnicodeEncodeError" not in proc.stderr, proc.stderr
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_importing_the_cli_hardens_stdio() -> None:
    """Pin the mechanism, not just the symptom.

    Asserting only on rendered output would let someone "fix" a future
    regression by deleting the glyph rather than restoring the hardening.
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import openlimno.cli; print(sys.stdout.errors)",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONNOUSERSITE": "1"},
        cwd=REPO_ROOT,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "replace", (
        "importing openlimno.cli no longer hardens stdout; a narrow console "
        f"will abort on non-ASCII output. Got errors={proc.stdout.strip()!r}"
    )


def test_hardening_does_not_reintroduce_the_eager_fishtank_import() -> None:
    """The fix must not be 'import fishtank again'.

    openlimno._console is stdlib + rich only; pulling scipy/pandas back in
    would undo the lazy-import work this hardening was collateral damage from.
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, openlimno.cli; "
            "print(','.join(m for m in ('scipy', 'pandas', 'openlimno.fishtank') "
            "if m in sys.modules))",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONNOUSERSITE": "1"},
        cwd=REPO_ROOT,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "", (
        f"importing openlimno.cli pulled in heavy modules: {proc.stdout.strip()}"
    )

"""R-DOC-AUDIT-WIRED — pin that R18-4 (codex+gemini LOW, opened in the
18th-round review) is no longer ``CLOSED-API-ONLY``.

R18-4 was: ``_yaml_rt.dump_round_trip`` gained an optional
``case=`` kwarg in v3.6.0 (R16-8) to route through the v3.0 path-
safety sandbox, but as of v3.6.1 no production caller passed
``case=``. The 2026-05-19 strategic review flagged this as
"API exists ≠ capability exists" (codex S5).

2026-05-20 R-DOC-AUDIT-WIRED ships:

1. ``workflows.calibrate.apply_optimised_params_to_case_yaml`` now
   constructs a ``Case`` from the loaded config + path and passes
   ``case=`` to ``dump_round_trip``.
2. ``cli`` fetch-chain patcher (the WEDM v0.2 multi-fetcher write-
   back) passes ``case=``.
3. ``cli`` NWIS rating-curve auto-wire passes ``case=``.

Pin all three via source-inspection AND a behavioural test that a
calibrate-style yaml patch routed THROUGH the sandbox now refuses
to write outside ``allowed_data_roots``.

These pins guarantee R18-4 stays closed. If a future refactor drops
``case=``, the pin fails loudly.
"""
from __future__ import annotations

import inspect
import textwrap
from pathlib import Path

import pytest
import yaml

from openlimno import cli
from openlimno.workflows import calibrate


# ---------------------------------------------------------------------
# Source-inspection pins (cheap, catches a refactor that drops ``case=``)
# ---------------------------------------------------------------------
def test_r184_calibrate_apply_optimised_params_passes_case_kwarg() -> None:
    """R-DOC-AUDIT-WIRED #1: calibrate.apply_optimised_params_to_case_yaml
    must pass ``case=`` to dump_round_trip."""
    src = inspect.getsource(calibrate.apply_optimised_params_to_case_yaml)
    assert "dump_round_trip(config, dst, case=" in src, (
        "R18-4 regression: calibrate write-back no longer passes "
        "case= — sandbox routing dropped. R-DOC-AUDIT-WIRED "
        "marker lost."
    )


def test_r184_cli_fetch_chain_passes_case_kwarg() -> None:
    """R-DOC-AUDIT-WIRED #2: the cli fetch-chain WEDM v0.2 patcher
    must pass ``case=``."""
    src = inspect.getsource(cli)
    # Find the fetcher block - look for the two case= usages in cli.py.
    assert src.count("dump_round_trip(case_doc, case_yaml_path, case=") >= 2, (
        "R18-4 regression: cli fetch-chain or NWIS auto-wire patcher "
        "dropped case= kwarg. Both must route through the sandbox."
    )


# ---------------------------------------------------------------------
# Behavioural pin — sandbox actually fires when the destination
# escapes allowed_data_roots
# ---------------------------------------------------------------------
def test_r184_apply_optimised_params_blocks_outside_sandbox(
    tmp_path: Path,
) -> None:
    """R-DOC-AUDIT-WIRED #3 (the real bite): if a malicious / buggy
    caller asks ``apply_optimised_params_to_case_yaml`` to write the
    patched YAML to an ``out_yaml`` outside the case dir AND outside
    ``allowed_data_roots``, the sandbox must refuse — proving the
    ``case=`` plumbing is alive end-to-end.

    Pre-R-DOC-AUDIT-WIRED: dump_round_trip skipped the sandbox
    (case=None default), so this would have silently written
    /tmp/escape.yaml. v3.6.1 + this audit pass makes it raise.
    """
    case_dir = tmp_path / "case_dir"
    case_dir.mkdir()
    case_yaml = case_dir / "case.yaml"
    case_yaml.write_text(
        textwrap.dedent("""
            openlimno: '0.2'
            case:
              name: r184_audit
              crs: EPSG:4326
              allowed_data_roots: []  # strict: case_dir only
            mesh:
              uri: ./mesh.nc
            hydrodynamics:
              backend: builtin-1d
            habitat:
              species: [oncorhynchus_mykiss]
              stages: [spawning]
              metric: wua-q
              composite: min
            output:
              dir: ./out
              formats: [csv]
        """).lstrip(),
        encoding="utf-8",
    )

    # Pick an out_yaml that's outside both the case dir AND
    # allowed_data_roots.
    escape_dir = tmp_path / "escape"
    escape_dir.mkdir()
    out_yaml = escape_dir / "patched.yaml"

    with pytest.raises(ValueError, match="allowed_data_roots|sandbox|outside"):
        calibrate.apply_optimised_params_to_case_yaml(
            case_yaml=case_yaml,
            params={"manning_n": 0.035},
            out_yaml=out_yaml,
        )

    assert not out_yaml.exists(), (
        "R18-4 regression: the sandbox raised but the file was "
        "still written — atomic-write contract broken OR sandbox "
        "fires AFTER the write."
    )


def test_r184_apply_optimised_params_permits_inside_case_dir(
    tmp_path: Path,
) -> None:
    """R-DOC-AUDIT-WIRED #4 — counterpart: writing to a path INSIDE
    the case_dir must still succeed (the wiring must not be over-
    eager and block legitimate in-place patches)."""
    case_dir = tmp_path / "case_dir2"
    case_dir.mkdir()
    case_yaml = case_dir / "case.yaml"
    case_yaml.write_text(
        textwrap.dedent("""
            openlimno: '0.2'
            case:
              name: r184_happy
              crs: EPSG:4326
            mesh:
              uri: ./mesh.nc
            hydrodynamics:
              backend: builtin-1d
              builtin_1d:
                slope: 0.001
                manning_n: 0.03
            habitat:
              species: [oncorhynchus_mykiss]
              stages: [spawning]
              metric: wua-q
              composite: min
            output:
              dir: ./out
              formats: [csv]
        """).lstrip(),
        encoding="utf-8",
    )

    out_yaml = case_dir / "patched.yaml"  # in-case-dir
    result = calibrate.apply_optimised_params_to_case_yaml(
        case_yaml=case_yaml,
        params={"manning_n": 0.04},
        out_yaml=out_yaml,
    )
    assert result == out_yaml.resolve()
    written = yaml.safe_load(out_yaml.read_text())
    assert written["hydrodynamics"]["builtin_1d"]["manning_n"] == 0.04

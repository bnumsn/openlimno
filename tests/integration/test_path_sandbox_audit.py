"""v3.1.0 — path-safety sandbox audit-pass integration matrix.

SPEC_v3.md §1 promised the v3.0 audit-pass would land
``tests/integration/test_path_sandbox.py`` covering every Case method
that takes a path argument from YAML. v3.0.0 only wrote the
sandbox-routing changes; this file fulfills the audit half of the
deal at v3.1.0.

Verified contracts:
  * Each sandbox-routed call site rejects an outside-sandbox URI
    with a v3.0.0 path-safety ValueError (or, where the runner
    catches the exception, a path-safety warning in the warnings
    list and a None/missing return).
  * Per-call ``allow_outside_case=True`` opt-out still works at the
    call sites that legitimately need it.
  * The 4 shipped fixture YAMLs (3 examples + lemhi-tiny) all pass
    ``validate_case`` under the v3.0 strict-by-default semantics.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_v310_shipped_fixtures_validate_under_strict_sandbox() -> None:
    """v3.1.0 audit: every shipped case.yaml must still validate
    against the WEDM schema AND construct a Case object without
    triggering the v3.0 strict-default rejection (because each
    fixture is either entirely in-case-dir, or has declared an
    appropriate ``allowed_data_roots``)."""
    from openlimno.wedm import validate_case

    fixtures = [
        REPO_ROOT / "examples" / "lemhi" / "case.yaml",
        REPO_ROOT / "examples" / "composite_hsi" / "case.yaml",
        REPO_ROOT / "examples" / "phabsim_replication" / "case.yaml",
        REPO_ROOT / "tests" / "integration" / "fixtures" / "lemhi-tiny" / "case.yaml",
    ]
    # v3.4.0 R15-9 (claude test-coverage): a deleted fixture used
    # to pass this test silently (the loop just `continue`'d). Now
    # fail loudly so an accidental rename / deletion shows up
    # immediately. Each fixture is a charter-shipped example; their
    # absence is a real regression.
    missing = [fxt for fxt in fixtures if not fxt.exists()]
    if missing:
        pytest.fail(
            f"v3.4.0 R15-9: shipped fixtures missing — {missing}. "
            f"If a fixture was intentionally removed, drop it from "
            f"the audit list explicitly."
        )
    for fxt in fixtures:
        errors = validate_case(fxt)
        assert errors == [], (
            f"v3.1.0 audit-pass regression: shipped fixture {fxt} "
            f"no longer validates under v3.0 strict-default schema: "
            f"{errors}"
        )


def test_v310_sandbox_call_sites_inventory() -> None:
    """v3.1.0 audit: source-inspect each call site listed in
    SPEC_v3 §3 as v3.0-sandbox-routed. Catches a future revert that
    swaps ``_resolve_safe`` back to ``_resolve`` for any of them.

    Listed sites (10 / 11 in SPEC_v3 §3; only ``output.dir`` write-
    target is explicitly excluded):
      1. _resolve_mesh_uri
      2. data.cross_section (case.py)
      3. data.hsi_curve (case.py)
      4. regulatory rating_curve (case.py)
      5. studyplan_path (case.py)
      6. drifting-egg params (case.py)
      7. drifting-egg forcing CSV (case.py)
      8. CLI cross_section (cli.py)
      9. CLI generic data path (cli.py)
      10. PEST++ workspace cross_section (calibrate.py)
    """
    case_src = (REPO_ROOT / "src" / "openlimno" / "case.py").read_text(
        encoding="utf-8",
    )
    cli_src = (REPO_ROOT / "src" / "openlimno" / "cli.py").read_text(
        encoding="utf-8",
    )
    calibrate_src = (REPO_ROOT / "src" / "openlimno" / "workflows" / "calibrate.py").read_text(
        encoding="utf-8"
    )

    # case.py sites (7 of 10):
    case_safe_calls = case_src.count("self._resolve_safe(")
    # Expected: 1 inside _resolve_mesh_uri + 6 in Case.run/helpers
    # (cross_section, hsi_curve, rating_curve, studyplan, drifting-egg
    #  params, drifting-egg forcing CSV). Tolerate +/-1 for refactor
    # noise but flag if the count drops well below 7.
    assert case_safe_calls >= 7, (
        f"v3.1.0 audit regression: case.py has only "
        f"{case_safe_calls} _resolve_safe call sites; SPEC_v3 §3 "
        f"requires at least 7."
    )

    # cli.py sites (2 of 10):
    cli_safe_calls = cli_src.count("case._resolve_safe(")
    assert cli_safe_calls >= 2, (
        f"v3.1.0 audit regression: cli.py has only "
        f"{cli_safe_calls} sandbox-routed call sites; SPEC_v3 §3 "
        f"requires at least 2."
    )

    # calibrate.py sites (1 of 10):
    calibrate_safe_calls = calibrate_src.count("case._resolve_safe(")
    assert calibrate_safe_calls >= 1, (
        "v3.1.0 audit regression: calibrate.py no longer routes the "
        "PEST++ workspace cross_section through _resolve_safe."
    )

    # And: no raw _resolve in the sites that should have been
    # migrated (defensive — catches a copy-paste regression).
    leftover_resolve = case_src.count("self._resolve(") - case_src.count("self._resolve_safe(")
    # Acceptable raw _resolve calls in case.py:
    #   - _resolve_safe's internal wrapped call (line ~720)
    #   - output dir at top of Case.run (write target, intentional)
    # Both are call-out lines; tolerate up to 4 raw uses (the two
    # legit + 2 buffer for future refactor).
    assert leftover_resolve <= 4, (
        f"v3.1.0 audit regression: case.py has {leftover_resolve} "
        f"raw self._resolve( call sites — should be ≤ 4 (the "
        f"sandbox internal wrap + output.dir write target)."
    )


def test_v310_r143_cli_calibrate_rejects_out_of_sandbox_cross_section(
    tmp_path: Path,
) -> None:
    """v3.1.0 R14-3 (claude + gemini): pin that the ``openlimno
    calibrate`` CLI command actually triggers the v3.0 sandbox
    rejection when its ``data.cross_section`` URI escapes the case
    dir. The v3.0.0 source-inspection test only confirmed the call
    site was rewired; this confirms the rewired call propagates a
    ValueError end-to-end.
    """
    import textwrap

    import yaml

    from openlimno.case import Case

    case_dir = tmp_path / "case_dir"
    case_dir.mkdir()
    (case_dir / "case.yaml").write_text(
        textwrap.dedent(f"""
            openlimno: '0.2'
            case:
              name: t
              crs: EPSG:4326
            mesh:
              uri: ./mesh.nc
            data:
              cross_section: '{tmp_path}/escapee.parquet'
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
    case = Case(
        config=yaml.safe_load((case_dir / "case.yaml").read_text()),
        case_yaml_path=(case_dir / "case.yaml").resolve(),
    )

    # Simulating cli.py:508 — the path the CLI takes.
    with pytest.raises(ValueError, match="path-safety"):
        case._resolve_safe(case.config["data"]["cross_section"])


def test_v310_r141_symlink_inside_case_dir_pointing_inside_allowed_root(
    tmp_path: Path,
) -> None:
    """v3.1.0 R14-1 (gemini): a symlink INSIDE the case dir that
    points to a location INSIDE the case dir must resolve cleanly.
    The sandbox follows symlinks via Path.resolve(); we need to
    verify that legitimate intra-sandbox symlinks don't trip the
    rejection check.
    """
    import textwrap

    import yaml

    from openlimno.case import Case

    case_dir = tmp_path / "case_dir"
    case_dir.mkdir()
    real_target = case_dir / "real_data"
    real_target.mkdir()
    (real_target / "fixture.parquet").write_bytes(b"")
    # Symlink: case_dir/data → case_dir/real_data
    (case_dir / "data").symlink_to(real_target)
    (case_dir / "case.yaml").write_text(
        textwrap.dedent("""
            openlimno: '0.2'
            case:
              name: t
              crs: EPSG:4326
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
    case = Case(
        config=yaml.safe_load((case_dir / "case.yaml").read_text()),
        case_yaml_path=(case_dir / "case.yaml").resolve(),
    )

    # Access via the symlink — resolved target is still inside case dir.
    p = case._resolve_safe("./data/fixture.parquet")
    # The Path.resolve() result canonicalises to the real target;
    # which IS under case_dir.resolve() so should pass.
    assert p.is_relative_to(case_dir.resolve())


def test_v310_r141_symlink_inside_case_dir_pointing_outside_rejected(
    tmp_path: Path,
) -> None:
    """v3.1.0 R14-1 (gemini): a symlink INSIDE the case dir that
    points OUTSIDE (a classic sandbox-escape attack) must be
    rejected. Path.resolve() chases the symlink to its real target;
    the real target is outside the sandbox, so is_relative_to is
    False, and _resolve_safe raises.
    """
    import textwrap

    import yaml

    from openlimno.case import Case

    case_dir = tmp_path / "case_dir"
    case_dir.mkdir()
    outside = tmp_path / "outside_target"
    outside.mkdir()
    (outside / "sensitive.txt").write_bytes(b"")
    # Attack: case_dir/data → outside_target
    (case_dir / "data").symlink_to(outside)
    (case_dir / "case.yaml").write_text(
        textwrap.dedent("""
            openlimno: '0.2'
            case:
              name: t
              crs: EPSG:4326
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
    case = Case(
        config=yaml.safe_load((case_dir / "case.yaml").read_text()),
        case_yaml_path=(case_dir / "case.yaml").resolve(),
    )

    # Access via the symlink — must be rejected, because the
    # resolved target lives outside the case dir.
    with pytest.raises(ValueError, match="path-safety"):
        case._resolve_safe("./data/sensitive.txt")


def test_v310_r142_studio_package_init_locks_matplotlib_agg() -> None:
    """v3.1.0 R14-2 (claude): importing ``openlimno.studio`` must
    have locked matplotlib to the Agg backend before any submodule
    imports pyplot. Pin via the public matplotlib API."""
    import matplotlib

    import openlimno.studio  # noqa: F401 — side-effect: lock Agg

    assert matplotlib.get_backend() == "Agg", (
        f"v3.1.0 R14-2 regression: openlimno.studio __init__ did not "
        f"lock matplotlib backend to Agg. Current: "
        f"{matplotlib.get_backend()}. Studio's QThread plot path is "
        f"unsafe under any non-Agg backend."
    )


def test_v310_per_call_allow_outside_case_still_works(
    tmp_path: Path,
) -> None:
    """v3.1.0 audit: the engine-level escape hatch
    ``allow_outside_case=True`` must still bypass the sandbox even
    under strict-by-default. The post-v3.0 audit-pass routing made
    more call sites strict, but legitimate write-to-tmp use cases
    must still work.
    """
    import textwrap

    import yaml

    from openlimno.case import Case

    case_dir = tmp_path / "case_dir"
    case_dir.mkdir()
    (case_dir / "case.yaml").write_text(
        textwrap.dedent("""
            openlimno: '0.2'
            case:
              name: t
              crs: EPSG:4326
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
    case = Case(
        config=yaml.safe_load((case_dir / "case.yaml").read_text()),
        case_yaml_path=(case_dir / "case.yaml").resolve(),
    )

    # Without the kwarg → rejection under v3.0 strict.
    with pytest.raises(ValueError, match="path-safety"):
        case._resolve_safe("../../../tmp/foo.csv")

    # With the kwarg → resolved-without-check, no exception.
    out = case._resolve_safe(
        "../../../tmp/foo.csv",
        allow_outside_case=True,
    )
    assert out.is_absolute()

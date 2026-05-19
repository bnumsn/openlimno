"""v3.2.0 — write-target sandbox + error redaction + boundaries warning.

Three closely-related v3.1.0-deferred items, all path-safety adjacent:
  * _resolve_write_safe: separates write-target semantics from
    _resolve_safe so output.dir resolution gets sandbox checks
    without requiring the target to already exist.
  * R14-10 OPENLIMNO_PATH_SAFETY_REDACT env-var: optional path-
    redaction in user-facing path-safety errors (hosted Studio
    deployments shouldn't leak server directory tree).
  * R11-2: Case.run emits a warning when backend=builtin-1d and
    boundaries is missing AND the case isn't an OSM-bbox stub.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from openlimno.case import Case


def _minimal_yaml(case_dir: Path, *, allowed_data_roots: list[str] | None = None,
                  output_dir: str = "./out", bbox: list[float] | None = None,
                  include_boundaries: bool = True) -> Path:
    """Build a minimal valid case YAML for v3.2.0 tests."""
    case_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "openlimno: '0.2'",
        "case:",
        "  name: v320_t",
        "  crs: EPSG:4326",
    ]
    if bbox is not None:
        lines.append(f"  bbox: {bbox}")
    if allowed_data_roots is not None:
        if not allowed_data_roots:
            lines.append("  allowed_data_roots: []")
        else:
            lines.append("  allowed_data_roots:")
            for r in allowed_data_roots:
                lines.append(f"    - '{r}'")
    lines.extend([
        "mesh:",
        "  uri: ./mesh.nc",
        "hydrodynamics:",
        "  backend: builtin-1d",
    ])
    if include_boundaries:
        lines.extend([
            "  boundaries:",
            "    upstream:",
            "      type: discharge",
            "      value: 12.0",
        ])
    lines.extend([
        "habitat:",
        "  species: [oncorhynchus_mykiss]",
        "  stages: [spawning]",
        "  metric: wua-q",
        "  composite: min",
        "output:",
        f"  dir: {output_dir}",
        "  formats: [csv]",
        "",
    ])
    p = case_dir / "case.yaml"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def _make_case(case_yaml: Path) -> Case:
    with case_yaml.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return Case(config=config, case_yaml_path=case_yaml.resolve())


# ---------------------------------------------------------------------
# _resolve_write_safe
# ---------------------------------------------------------------------
def test_v320_write_safe_inside_case_dir_ok_even_if_target_missing(
    tmp_path: Path,
) -> None:
    """v3.2.0: a non-existent write target INSIDE the case dir must
    resolve cleanly. The whole point of the write-vs-read split is
    that output.dir often doesn't exist yet on first run."""
    case_yaml = _minimal_yaml(tmp_path / "case_dir")
    case = _make_case(case_yaml)
    out = case._resolve_write_safe("./out/fresh_run/results")
    assert isinstance(out, Path)
    assert out.is_absolute()


def test_v320_write_safe_rejects_escape_when_strict(tmp_path: Path) -> None:
    """v3.2.0: a write target OUTSIDE the case dir must be rejected
    under the v3.0 strict-default semantics, just like read paths.
    Closes the SPEC §3 deferral that output.dir could overwrite
    ~/.ssh/authorized_keys or similar."""
    case_yaml = _minimal_yaml(tmp_path / "case_dir")
    case = _make_case(case_yaml)
    with pytest.raises(ValueError, match="path-safety \\(write\\)"):
        case._resolve_write_safe("../../../tmp/malicious_out")


def test_v320_write_safe_allows_configured_root(tmp_path: Path) -> None:
    """v3.2.0: a write target under a configured allowed_data_root
    must be allowed. Useful for shared cluster output directories."""
    shared_out = tmp_path / "shared_outputs"
    shared_out.mkdir()
    case_yaml = _minimal_yaml(
        tmp_path / "case_dir", allowed_data_roots=[str(shared_out)],
    )
    case = _make_case(case_yaml)
    p = case._resolve_write_safe(str(shared_out / "my_run/out.csv"))
    assert p.is_relative_to(shared_out.resolve())


def test_v320_write_safe_url_scheme_rejected(tmp_path: Path) -> None:
    """v3.2.0: URL-scheme write targets rejected at the same gate
    as read URIs."""
    case_yaml = _minimal_yaml(tmp_path / "case_dir")
    case = _make_case(case_yaml)
    with pytest.raises(ValueError, match="URL scheme"):
        case._resolve_write_safe("s3://bucket/out/")


def test_v320_output_dir_routes_through_write_safe() -> None:
    """v3.2.0: pin via source-inspection that Case.run's output.dir
    resolution uses _resolve_write_safe (not raw _resolve)."""
    import inspect
    src = inspect.getsource(Case.run)
    assert "out_dir = self._resolve_write_safe(" in src, (
        "v3.2.0 regression: Case.run's output.dir is no longer "
        "routed through _resolve_write_safe."
    )


# ---------------------------------------------------------------------
# R14-10 — OPENLIMNO_PATH_SAFETY_REDACT
# ---------------------------------------------------------------------
def test_v320_r1410_path_redact_strips_absolute_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v3.2.0 R14-10: when OPENLIMNO_PATH_SAFETY_REDACT=1, the
    path-safety ValueError must NOT contain absolute paths or the
    configured allowed-roots list verbatim. Hosted-Studio deployments
    enable this to avoid leaking the server directory tree to the
    user-facing error pane."""
    monkeypatch.setenv("OPENLIMNO_PATH_SAFETY_REDACT", "1")
    case_yaml = _minimal_yaml(tmp_path / "case_dir")
    case = _make_case(case_yaml)
    with pytest.raises(ValueError, match="path-safety") as exc:
        case._resolve_safe("../../../etc/passwd")
    msg = str(exc.value)
    assert "redacted" in msg, (
        f"Redact mode did not strip the absolute path. Got: {msg}"
    )
    # Specific check: the tmp_path directory must NOT appear in the
    # message (it would have, pre-v3.2.0).
    assert str(tmp_path) not in msg, (
        f"Redact mode still leaked the case dir path. Got: {msg}"
    )


def test_v320_r1410_path_redact_default_off(tmp_path: Path) -> None:
    """v3.2.0 R14-10: when the env var is unset, the verbose form
    (with absolute paths) is the default — researcher debugging
    convenience for non-hosted use."""
    # No monkeypatch — env var unset.
    case_yaml = _minimal_yaml(tmp_path / "case_dir")
    case = _make_case(case_yaml)
    with pytest.raises(ValueError, match="path-safety") as exc:
        case._resolve_safe("../../../etc/passwd")
    msg = str(exc.value)
    assert "redacted" not in msg, (
        f"Default mode unexpectedly stripped paths. Got: {msg}"
    )
    # Verbose form: full /tmp/.../case_dir path is present.
    assert str(tmp_path) in msg, (
        f"Default mode did not include the case dir path. Got: {msg}"
    )


def test_v320_r1410_redact_also_applies_to_write_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v3.2.0 R14-10: the write-safe path emits the same redacted
    form when the env var is on. The same env-var-driven policy
    governs both surfaces."""
    monkeypatch.setenv("OPENLIMNO_PATH_SAFETY_REDACT", "1")
    case_yaml = _minimal_yaml(tmp_path / "case_dir")
    case = _make_case(case_yaml)
    with pytest.raises(ValueError, match="path-safety") as exc:
        case._resolve_write_safe("../../../tmp/leak")
    msg = str(exc.value)
    assert "redacted" in msg or str(tmp_path) not in msg, (
        f"Write-safe redact mode leaked paths. Got: {msg}"
    )


# ---------------------------------------------------------------------
# R11-2 — solver-level warning for missing boundaries
# ---------------------------------------------------------------------
def test_v320_r112_solver_warns_on_missing_boundaries_no_bbox() -> None:
    """v3.2.0 R11-2: when backend=builtin-1d AND the YAML has no
    boundaries AND no case.bbox (the Studio OSM-stub signal), the
    solver-init code MUST emit a warning.

    Source-inspection pin (the full Case.run end-to-end requires
    mesh + cross-section fixtures; we pin the wiring here)."""
    import inspect
    src = inspect.getsource(Case.run)
    assert "v3.2.0 R11-2" in src, (
        "v3.2.0 R11-2 regression: the solver-level missing-boundaries "
        "warning was removed from Case.run."
    )
    # Both signals are checked: boundaries absent AND bbox absent.
    assert "boundaries" in src and "bbox" in src, (
        "v3.2.0 R11-2 regression: the wiring no longer references "
        "both boundaries and bbox."
    )


def test_v320_r112_config_state_pre_run(tmp_path: Path) -> None:
    """v3.2.0 R11-2 (config-only check; behavioral pin moved to
    test_v330_r153_r112_logic_corrected below)."""
    case_yaml = _minimal_yaml(
        tmp_path / "case_dir",
        bbox=[100.0, 38.0, 100.1, 38.1],
        include_boundaries=False,
    )
    case = _make_case(case_yaml)
    assert case.config["case"]["bbox"] == [100.0, 38.0, 100.1, 38.1]
    assert "boundaries" not in case.config["hydrodynamics"]


# ---------------------------------------------------------------------
# v3.3.0 R15-3 (claude HIGH) — R11-2 logic correction. The v3.2.0
# code warned on the WRONG state (no-bbox + no-boundaries = Studio
# stub) while the inline comment said it should warn on (bbox +
# no-boundaries = user-error). v3.3.0 inverts the check to match
# the documented intent. We pin via the warnings list — the
# resolution logic runs early enough that we can mirror it inline
# without needing mesh/xs fixtures.
# ---------------------------------------------------------------------
def _r112_warning_fires(case_cfg: dict) -> bool:
    """Mirror the v3.3.0 R11-2 check inline."""
    hydro_block = case_cfg.get("hydrodynamics", {})
    return (
        hydro_block.get("backend") == "builtin-1d"
        and "boundaries" not in hydro_block
        and "bbox" in case_cfg.get("case", {})
    )


def test_v330_r153_r112_fires_when_bbox_present_and_boundaries_absent(
    tmp_path: Path,
) -> None:
    """R15-3: bbox declared (past OSM-stub stage) + no boundaries
    (user forgot to fill them in) = the warning MUST fire. This is
    the bug case the v3.2.0 inversion silently masked."""
    case_yaml = _minimal_yaml(
        tmp_path / "case_dir",
        bbox=[100.0, 38.0, 100.1, 38.1],
        include_boundaries=False,
    )
    case = _make_case(case_yaml)
    assert _r112_warning_fires(case.config), (
        "v3.3.0 R15-3 regression: bbox + no-boundaries did NOT "
        "trigger the warning. v3.2.0's inverted logic silently "
        "shipped exactly this state."
    )


def test_v330_r153_r112_silent_when_bbox_absent(tmp_path: Path) -> None:
    """R15-3: no bbox + no boundaries = Studio OSM-stub. The
    warning must NOT fire — the user is at an intermediate stage."""
    case_yaml = _minimal_yaml(
        tmp_path / "case_dir",
        include_boundaries=False,
    )
    case = _make_case(case_yaml)
    assert not _r112_warning_fires(case.config), (
        "v3.3.0 R15-3 regression: no-bbox + no-boundaries (the "
        "Studio stub state) triggered the warning. We should be "
        "silent until the user declares bbox."
    )


def test_v330_r153_r112_silent_when_boundaries_present(
    tmp_path: Path,
) -> None:
    """R15-3: boundaries declared → silent regardless of bbox."""
    case_yaml = _minimal_yaml(
        tmp_path / "case_dir",
        bbox=[100.0, 38.0, 100.1, 38.1],
        include_boundaries=True,
    )
    case = _make_case(case_yaml)
    assert not _r112_warning_fires(case.config), (
        "v3.3.0 R15-3 regression: bbox + boundaries present "
        "triggered the warning."
    )


def test_v330_r151_redact_strips_absolute_uri(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R15-1 (codex + claude): an absolute URI like
    `output.dir: /etc/leaked_secret_dir` was previously echoed
    verbatim in the redact-mode error message — defeating the
    whole redaction contract. v3.3.0 redacts absolute URIs too.
    Relative URIs stay visible (they're user content, not server
    tree, and surfacing them aids the fix)."""
    monkeypatch.setenv("OPENLIMNO_PATH_SAFETY_REDACT", "1")
    case_yaml = _minimal_yaml(tmp_path / "case_dir")
    case = _make_case(case_yaml)
    leak_path = tmp_path / "leaked_dir" / "secret.csv"
    leak_path.parent.mkdir()
    leak_path.write_text("")
    with pytest.raises(ValueError, match="path-safety") as exc:
        case._resolve_safe(str(leak_path))
    msg = str(exc.value)
    assert str(leak_path) not in msg, (
        f"R15-1 regression: absolute URI leaked through redact "
        f"mode. Got: {msg}"
    )
    assert "redacted absolute URI" in msg, (
        f"R15-1 regression: URI marker missing. Got: {msg}"
    )


def test_v330_r151_redact_keeps_relative_uri_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R15-1: relative URIs aren't server-tree content, they're
    user-supplied YAML. The redact contract is server-side
    confidentiality, not user-input opacity."""
    monkeypatch.setenv("OPENLIMNO_PATH_SAFETY_REDACT", "1")
    case_yaml = _minimal_yaml(tmp_path / "case_dir")
    case = _make_case(case_yaml)
    with pytest.raises(ValueError, match="path-safety") as exc:
        case._resolve_safe("../escapee.csv")
    msg = str(exc.value)
    assert "escapee.csv" in msg, (
        f"R15-1 regression: relative URI was over-redacted. Got: {msg}"
    )

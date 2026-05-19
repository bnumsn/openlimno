"""v2.11.0 path-safety sandbox prototype (R11-4 v3.0 cut blocker shift-left).

Pins the contract for ``Case._resolve_safe`` and
``Case._allowed_data_roots``. The v3.0 ship will route every
``_resolve`` call site through ``_resolve_safe`` and tighten the
back-compat path; these tests establish the v2.11.0 API surface so
that future tightening doesn't accidentally break opt-in consumers.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from openlimno.case import Case


def _write_case_yaml(
    case_dir: Path,
    *,
    allowed_data_roots: list[str] | None = None,
) -> Path:
    """Write a minimal valid case YAML at ``case_dir / case.yaml``,
    optionally with ``case.allowed_data_roots`` configured."""
    case_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "openlimno: '0.2'",
        "case:",
        "  name: sandbox_t",
        "  crs: EPSG:4326",
    ]
    if allowed_data_roots is not None:
        lines.append("  allowed_data_roots:")
        for r in allowed_data_roots:
            lines.append(f"    - '{r}'")
    lines.extend([
        "mesh:",
        "  uri: ./mesh.nc",
        "hydrodynamics:",
        "  backend: builtin-1d",
        "habitat:",
        "  species: [oncorhynchus_mykiss]",
        "  stages: [spawning]",
        "  metric: wua-q",
        "  composite: min",
        "output:",
        "  dir: ./out",
        "  formats: [csv]",
        "",
    ])
    p = case_dir / "case.yaml"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def _make_case(case_yaml: Path) -> Case:
    """Bypass the schema validator path (validate_case opens the
    file; we just need a Case object with the right config dict and
    case_yaml_path). The sandbox helpers don't touch the rest of
    Case.run, so a minimal hand-rolled config is enough."""
    with case_yaml.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return Case(config=config, case_yaml_path=case_yaml.resolve())


# ---------------------------------------------------------------------
# Back-compat: when allowed_data_roots is unset, _resolve_safe is
# exactly equivalent to _resolve.
# ---------------------------------------------------------------------
def test_v2110_no_sandbox_falls_back_to_resolve(tmp_path: Path) -> None:
    """Default v2.11.0 behavior: no allowed_data_roots → permissive
    (existing cases keep working with no schema change)."""
    case_yaml = _write_case_yaml(tmp_path / "case_dir")
    case = _make_case(case_yaml)

    # Relative path inside case dir — exactly like _resolve.
    p = case._resolve_safe("./data/file.csv")
    assert p == case._resolve("./data/file.csv")

    # Even traversal escapes are permitted in back-compat mode —
    # v2.11.0 is opt-in; this is the existing v2.10.x behavior.
    escape = case._resolve_safe("../../../etc/passwd")
    assert escape == case._resolve("../../../etc/passwd")


# ---------------------------------------------------------------------
# Sandbox-on: paths under the case dir are allowed.
# ---------------------------------------------------------------------
def test_v2110_sandbox_allows_under_case_dir(tmp_path: Path) -> None:
    case_dir = tmp_path / "case_dir"
    # Configure an unrelated allow-list to turn on strict mode.
    case_yaml = _write_case_yaml(
        case_dir, allowed_data_roots=["/mnt/openlimno-data"],
    )
    case = _make_case(case_yaml)

    # Path under case_dir itself — must always be allowed (the case
    # dir is implicitly the first allowed root).
    p = case._resolve_safe("./data/fixture.parquet")
    assert p.is_relative_to(case_dir.resolve())


# ---------------------------------------------------------------------
# Sandbox-on: paths under an explicit allowed root are allowed.
# ---------------------------------------------------------------------
def test_v2110_sandbox_allows_under_configured_root(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "case_dir"
    shared = tmp_path / "shared_data"
    shared.mkdir()
    case_yaml = _write_case_yaml(
        case_dir, allowed_data_roots=[str(shared)],
    )
    case = _make_case(case_yaml)

    # Absolute URI pointing at the configured shared root — allowed.
    p = case._resolve_safe(str(shared / "regional_climate.nc"))
    assert p == (shared / "regional_climate.nc").resolve()


# ---------------------------------------------------------------------
# Sandbox-on: traversal IS rejected (the core security property).
# ---------------------------------------------------------------------
def test_v2110_sandbox_rejects_traversal(tmp_path: Path) -> None:
    case_dir = tmp_path / "case_dir"
    case_yaml = _write_case_yaml(
        case_dir, allowed_data_roots=["./local_data"],
    )
    case = _make_case(case_yaml)

    with pytest.raises(ValueError, match="v2.11.0 path-safety") as exc:
        case._resolve_safe("../../../etc/passwd")
    msg = str(exc.value)
    assert "../../../etc/passwd" in msg or "etc/passwd" in msg, (
        f"Rejection should name the offending URI: {msg}"
    )


# ---------------------------------------------------------------------
# Sandbox-on: absolute path outside every allowed root rejected.
# ---------------------------------------------------------------------
def test_v2110_sandbox_rejects_absolute_outside_roots(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "case_dir"
    shared = tmp_path / "shared_data"
    shared.mkdir()
    case_yaml = _write_case_yaml(
        case_dir, allowed_data_roots=[str(shared)],
    )
    case = _make_case(case_yaml)

    # An absolute path NOT under the case dir AND NOT under shared:
    outsider = tmp_path / "other_unrelated_dir" / "data.csv"
    outsider.parent.mkdir(exist_ok=True)
    with pytest.raises(ValueError, match="v2.11.0 path-safety"):
        case._resolve_safe(str(outsider))


# ---------------------------------------------------------------------
# Sandbox-on: explicit allow_outside_case=True bypasses the sandbox.
# ---------------------------------------------------------------------
def test_v2110_sandbox_allow_outside_case_kwarg(tmp_path: Path) -> None:
    case_dir = tmp_path / "case_dir"
    case_yaml = _write_case_yaml(
        case_dir, allowed_data_roots=["./local_data"],
    )
    case = _make_case(case_yaml)

    # This would normally raise (traversal under strict sandbox);
    # the kwarg explicitly opts out for this single call.
    p = case._resolve_safe(
        "../../../tmp/fetcher_output.tif",
        allow_outside_case=True,
    )
    # No exception; returns the resolved path verbatim.
    assert isinstance(p, Path)
    assert p.is_absolute()


# ---------------------------------------------------------------------
# _allowed_data_roots always includes the case dir itself, even
# when allowed_data_roots is empty in the YAML.
# ---------------------------------------------------------------------
def test_v2110_allowed_data_roots_always_has_case_dir(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "case_dir"
    case_yaml = _write_case_yaml(case_dir)  # no allowed_data_roots
    case = _make_case(case_yaml)

    roots = case._allowed_data_roots()
    assert len(roots) == 1
    assert roots[0] == case_dir.resolve()


# ---------------------------------------------------------------------
# Schema-level: case.allowed_data_roots validates as an optional
# array of strings (no breakage to existing cases that don't set it).
# ---------------------------------------------------------------------
def test_v2110_schema_accepts_allowed_data_roots(tmp_path: Path) -> None:
    from openlimno.wedm import validate_case

    case_yaml = _write_case_yaml(
        tmp_path / "case_dir",
        allowed_data_roots=["./data", "/mnt/shared", "~/openlimno-data"],
    )
    errors = validate_case(case_yaml)
    assert errors == [], (
        f"v2.11.0 schema regression: valid allowed_data_roots "
        f"rejected: {errors}"
    )


def test_v2110_schema_rejects_unknown_case_field(tmp_path: Path) -> None:
    """Pin that adding allowed_data_roots didn't accidentally loosen
    case's additionalProperties:false guard."""
    from openlimno.wedm import validate_case

    case_dir = tmp_path / "case_dir"
    case_dir.mkdir()
    (case_dir / "case.yaml").write_text(
        textwrap.dedent("""
            openlimno: '0.2'
            case:
              name: t
              crs: EPSG:4326
              made_up_field: 42
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
    errors = validate_case(case_dir / "case.yaml")
    assert any("made_up_field" in e for e in errors), (
        f"v2.11.0 regression: unknown case-level field was silently "
        f"accepted. Errors: {errors}"
    )

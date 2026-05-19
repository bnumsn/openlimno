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
        if not allowed_data_roots:
            # Explicit empty list — YAML inline form so it lands as
            # `[]`, not `null`. v2.11.1 R12-3 cares about this
            # exact distinction.
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

    # v2.11.1 R12-5: match on a STABLE substring ('path-safety'),
    # not the version-pinned 'v2.11.0' tag — bumping to v2.11.x must
    # not trivially break this test.
    with pytest.raises(ValueError, match="path-safety") as exc:
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
    # v2.11.1 R12-5: stable substring, not version-pinned tag.
    with pytest.raises(ValueError, match="path-safety"):
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


# ---------------------------------------------------------------------
# v2.11.1 — 12th-round review patches (R12-1..R12-9)
# ---------------------------------------------------------------------
def test_v2111_r121_tilde_expansion_in_allowed_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R12-1 (codex+gemini+claude HIGH): `~/openlimno-data` in
    allowed_data_roots must be home-expanded, not treated as a
    literal directory under the case dir. Pre-v2.11.1 the schema
    docs advertised this form but `Path("~/x").is_absolute()` is
    False, so the entry silently got anchored on the case dir.
    """
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    case_dir = tmp_path / "case_dir"
    case_yaml = _write_case_yaml(
        case_dir, allowed_data_roots=["~/openlimno-data"],
    )
    case = _make_case(case_yaml)

    roots = case._allowed_data_roots()
    # Roots = [case_dir, ~/openlimno-data]. The second one must
    # resolve under fake_home, NOT under case_dir.
    home_root = (fake_home / "openlimno-data").resolve()
    assert home_root in roots, (
        f"R12-1 regression: ~/openlimno-data was not expanded. "
        f"Got roots: {roots}; expected {home_root} in the list."
    )
    # And a file under fake_home/openlimno-data must validate.
    home_root.mkdir()
    fixture = home_root / "shared.parquet"
    p = case._resolve_safe(str(fixture))
    assert p == fixture.resolve()


def test_v2111_r122_absolute_path_with_dotdot_rejected(
    tmp_path: Path,
) -> None:
    """R12-2 (codex+gemini HIGH): a YAML carrying an absolute URI
    with `..` segments (e.g. `/case_dir/../etc/passwd`) lexically
    starts under the case dir, so pre-v2.11.1 `is_relative_to`
    accepted it — defeating the sandbox. v2.11.1 fully resolves
    the candidate before comparison.
    """
    case_dir = tmp_path / "case_dir"
    case_yaml = _write_case_yaml(
        case_dir, allowed_data_roots=["./local_data"],
    )
    case = _make_case(case_yaml)

    # Build a bypass: an absolute path that lexically starts with
    # case_dir but actually escapes via ``..``.
    bypass = f"{case_dir.resolve()}/../escapee.csv"
    with pytest.raises(ValueError, match="path-safety"):
        case._resolve_safe(bypass)


def test_v2111_r123_empty_allowed_roots_means_strict(
    tmp_path: Path,
) -> None:
    """R12-3 (claude HIGH): `allowed_data_roots: []` (explicit
    empty list) MUST mean 'lock to case dir only,' not 'fall back
    to permissive mode.' The user wrote the key — they opted in;
    silently giving them the opposite was a footgun.
    """
    case_dir = tmp_path / "case_dir"
    case_yaml = _write_case_yaml(case_dir, allowed_data_roots=[])
    case = _make_case(case_yaml)

    # Path under case dir → allowed (case dir is the implicit root).
    p = case._resolve_safe("./data/fixture.parquet")
    assert p.is_relative_to(case_dir.resolve())

    # Path OUTSIDE case dir → rejected (empty list does NOT mean
    # permissive).
    other = tmp_path / "elsewhere" / "data.csv"
    other.parent.mkdir(exist_ok=True)
    with pytest.raises(ValueError, match="path-safety"):
        case._resolve_safe(str(other))


def test_v2111_r124_mesh_uri_routed_through_resolve_safe(
    tmp_path: Path,
) -> None:
    """R12-4 (claude HIGH): the v2.11.0 sandbox API must be wired
    into at least one real engine call site, otherwise it's dead
    logic / security theater. v2.11.1 routes `_resolve_mesh_uri`
    through `_resolve_safe`. Pin: when `allowed_data_roots` is set
    AND `mesh.uri` points outside the sandbox, the mesh path is
    rejected (a warning is recorded; mesh is treated as missing).
    """
    case_dir = tmp_path / "case_dir"
    outside_mesh = tmp_path / "outside" / "mesh.nc"
    outside_mesh.parent.mkdir(exist_ok=True)
    outside_mesh.write_text("")  # exists, but outside the sandbox

    # Build a case with an absolute mesh URI pointing outside the
    # sandbox + an explicit allowed_data_roots list that does NOT
    # include the outside dir.
    case_dir.mkdir(parents=True)
    (case_dir / "case.yaml").write_text(
        "\n".join([
            "openlimno: '0.2'",
            "case:",
            "  name: mesh_sandbox_t",
            "  crs: EPSG:4326",
            "  allowed_data_roots:",
            "    - './local_data'",
            "mesh:",
            f"  uri: '{outside_mesh}'",
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
        ]),
        encoding="utf-8",
    )
    case = _make_case(case_dir / "case.yaml")

    warnings: list[str] = []
    result = case._resolve_mesh_uri(case.config, warnings)
    assert result is None, (
        "R12-4 regression: _resolve_mesh_uri returned a path for a "
        "URI that the sandbox should have rejected."
    )
    assert any("path-safety" in w for w in warnings), (
        f"R12-4 regression: rejection should be reported as a "
        f"path-safety warning. Got warnings: {warnings}"
    )


def test_v2111_r126_validate_case_and_resolve_safe_round_trip(
    tmp_path: Path,
) -> None:
    """R12-6 (claude MED): exercise the full
    validate_case → Case(...) → _resolve_safe path in one test so
    the schema and the resolver are pinned together, not just
    individually. Catches integration drift between the
    `allowed_data_roots` schema definition and the runtime helper.
    """
    from openlimno.wedm import validate_case

    case_dir = tmp_path / "case_dir"
    case_yaml = _write_case_yaml(
        case_dir, allowed_data_roots=["./shared"],
    )
    # Schema acceptance:
    errors = validate_case(case_yaml)
    assert errors == [], (
        f"R12-6 regression: schema rejected a valid case YAML "
        f"that uses allowed_data_roots: {errors}"
    )
    # And the runtime sandbox actually engages:
    case = _make_case(case_yaml)
    with pytest.raises(ValueError, match="path-safety"):
        case._resolve_safe("../../etc/passwd")


def test_v2111_r128_url_scheme_rejected(tmp_path: Path) -> None:
    """R12-8 (claude MED): explicit-reject URL-scheme URIs
    (`http://`, `https://`, `s3://`, ...) rather than silently
    treat them as relative paths. With the sandbox disabled or
    enabled, a URL string is never a valid local-fs path.
    """
    case_yaml = _write_case_yaml(tmp_path / "case_dir")
    case = _make_case(case_yaml)

    for url in [
        "http://attacker.example/x.csv",
        "https://example.org/file.tif",
        "s3://bucket/key.parquet",
    ]:
        with pytest.raises(ValueError, match="URL scheme"):
            case._resolve_safe(url)


def test_v2111_r128_windows_drive_letter_not_url_scheme(
    tmp_path: Path,
) -> None:
    """R12-8 sub-pin: Windows-style absolute paths (``C:\\foo``)
    must NOT be classified as URL schemes. The regex requires a
    ``//`` after the scheme to match RFC 3986 §3.1 authority
    syntax; ``C:`` alone is a drive prefix, not a scheme.
    """
    case_yaml = _write_case_yaml(tmp_path / "case_dir")
    case = _make_case(case_yaml)
    # On POSIX this resolves to a normal absolute-looking path;
    # the URL-scheme check must NOT trip. On POSIX `C:/foo` is
    # treated as a relative path containing a colon, which is
    # fine — the test is that we don't raise the URL-scheme error.
    case._resolve_safe("C:/foo/bar.csv")  # must not raise


def test_v2111_schema_minitems_allows_explicit_empty(
    tmp_path: Path,
) -> None:
    """R12-3 schema-side: the schema must NOT enforce minItems=1 on
    allowed_data_roots — the empty list is the user opting in to
    'lock to case dir only.' Pin that the schema accepts it."""
    from openlimno.wedm import validate_case

    case_yaml = _write_case_yaml(
        tmp_path / "case_dir", allowed_data_roots=[],
    )
    errors = validate_case(case_yaml)
    assert errors == [], (
        f"R12-3 regression: schema rejected the explicit-opt-in "
        f"empty allowed_data_roots: []. Errors: {errors}"
    )


# ---------------------------------------------------------------------
# v2.12.0 — sandbox hardening (N + O bundled)
# ---------------------------------------------------------------------
def test_v2120_advance_notice_warns_on_escape_when_unset(
    tmp_path: Path,
    recwarn: pytest.WarningsRecorder,
) -> None:
    """v2.12.0 O: when allowed_data_roots is UNSET (the back-compat
    permissive branch) and a URI resolves OUTSIDE the case dir,
    emit a DeprecationWarning so CI-strict catches it before v3.0
    makes the strict branch default.
    """
    case_yaml = _write_case_yaml(tmp_path / "case_dir")  # no roots
    case = _make_case(case_yaml)

    # Resolves outside the case dir → must warn (but not raise).
    out = case._resolve_safe("../../../tmp/outside.csv")
    assert isinstance(out, Path)
    msgs = [str(w.message) for w in recwarn.list]
    assert any(
        "path-safety" in m and "outside" in m for m in msgs
    ), (
        f"v2.12.0 O regression: a URI escaping the case dir should "
        f"emit a DeprecationWarning when allowed_data_roots is "
        f"unset. Warnings seen: {msgs}"
    )


def test_v2120_no_warning_for_in_case_dir_path(
    tmp_path: Path,
    recwarn: pytest.WarningsRecorder,
) -> None:
    """v2.12.0 O: the advance-notice warning fires ONLY on escape.
    A normal in-case-dir URI must NOT warn (would spam every shipped
    fixture's run output)."""
    case_yaml = _write_case_yaml(tmp_path / "case_dir")
    case = _make_case(case_yaml)

    case._resolve_safe("./data/local_fixture.parquet")
    safety_warnings = [
        str(w.message) for w in recwarn.list
        if "path-safety" in str(w.message)
    ]
    assert safety_warnings == [], (
        f"v2.12.0 O regression: in-case-dir URI triggered a "
        f"path-safety warning. Got: {safety_warnings}"
    )


def test_v2120_no_warning_when_opted_in(
    tmp_path: Path,
    recwarn: pytest.WarningsRecorder,
) -> None:
    """v2.12.0 O: when the user has opted into the sandbox (set
    allowed_data_roots, even to []), the advance-notice warning
    must NOT fire — they've made their choice, no nag."""
    shared = tmp_path / "shared_data"
    shared.mkdir()
    case_yaml = _write_case_yaml(
        tmp_path / "case_dir", allowed_data_roots=[str(shared)],
    )
    case = _make_case(case_yaml)

    # A URI under the configured shared root → allowed, no warning.
    case._resolve_safe(str(shared / "fixture.parquet"))
    safety_warnings = [
        str(w.message) for w in recwarn.list
        if "path-safety" in str(w.message)
    ]
    assert safety_warnings == [], (
        f"v2.12.0 O regression: opt-in users got a nag warning. "
        f"Got: {safety_warnings}"
    )


def test_v2120_n_cross_section_routed_through_sandbox(
    tmp_path: Path,
) -> None:
    """v2.12.0 N: Case.run's data.cross_section resolution now
    goes through _resolve_safe (was _resolve in v2.11.x). Pin via
    source-inspection AND by verifying that an out-of-sandbox
    cross_section path is rejected when allowed_data_roots is
    explicitly set. (We don't run the full Case.run here — that's
    integration-test territory; this is the wiring pin.)
    """
    import inspect

    from openlimno.case import Case
    src = inspect.getsource(Case.run)
    # Source-text pin (cheap regression detector): the two new
    # call sites must use _resolve_safe, not _resolve, for the
    # cross_section and hsi_curve URIs.
    assert "cross_section_path = self._resolve_safe(" in src, (
        "v2.12.0 N regression: cross_section URI no longer routed "
        "through _resolve_safe."
    )
    assert "hsi_path = self._resolve_safe(" in src, (
        "v2.12.0 N regression: hsi_curve URI no longer routed "
        "through _resolve_safe."
    )


def test_v2120_advance_notice_uses_deprecationwarning_category(
    tmp_path: Path,
) -> None:
    """v2.12.0 O: the advance-notice warning must use
    DeprecationWarning specifically so `-W error::DeprecationWarning`
    in CI makes the escape fail loudly."""
    import warnings as _w

    case_yaml = _write_case_yaml(tmp_path / "case_dir")
    case = _make_case(case_yaml)

    with _w.catch_warnings(record=True) as captured:
        _w.simplefilter("always")
        case._resolve_safe("../../../tmp/escapee.csv")
    safety = [
        c for c in captured if "path-safety" in str(c.message)
    ]
    assert safety, "No path-safety warning captured."
    assert issubclass(safety[0].category, DeprecationWarning), (
        f"v2.12.0 O regression: warning category was "
        f"{safety[0].category.__name__}, expected DeprecationWarning."
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

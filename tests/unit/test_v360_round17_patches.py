"""v3.6.0 — 17th-round triple-AI review patches (R17-1, R17-2,
R17-3, R17-4, R17-5, R17-10).

R17-1: _uri_looks_absolute Windows literal bugs + case-insensitive
       scheme check.
R17-2: _open_safe_fd docstring honest about no-Windows-protection.
R17-3: trust-roots fallback scoped except + diagnostic.
R17-4: AEQD antimeridian-aware longitude mean.
R17-5: Transformer.from_crs cached.
R17-10: _open_safe context-manager wrapper.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from openlimno.case import Case, _uri_looks_absolute


def _make_case(case_dir: Path) -> Case:
    case_dir.mkdir(parents=True, exist_ok=True)
    case_yaml = case_dir / "case.yaml"
    case_yaml.write_text(
        textwrap.dedent("""
            openlimno: '0.2'
            case:
              name: v360_r17_t
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
    return Case(
        config=yaml.safe_load(case_yaml.read_text()),
        case_yaml_path=case_yaml.resolve(),
    )


# ---------------------------------------------------------------------
# R17-1 — Windows literal bugs + case-insensitive scheme
# ---------------------------------------------------------------------
def test_v360_r171_windows_extended_path_detected() -> None:
    r"""v3.6.0 R17-1 (claude + gemini): v3.5.0 had a literal-string
    bug — ``r"\\?\\"`` was 5 chars (with trailing backslash), not
    the 4-char Windows extended-path prefix ``\\?\``. v3.6.0
    fixes it. Pin the literal forms here."""
    assert _uri_looks_absolute(r"\\?\C:\secret"), (
        r"v3.6.0 R17-1 regression: Windows extended-path prefix \\?\ "
        r"not detected as absolute."
    )


def test_v360_r171_unc_path_detected() -> None:
    r"""v3.6.0 R17-1: UNC paths ``\\server\share\...`` must be
    detected. v3.5.0's literal had too many backslashes; fixed."""
    assert _uri_looks_absolute(r"\\fileserver\share\data.csv"), (
        "v3.6.0 R17-1 regression: UNC path not detected as absolute."
    )


def test_v360_r171_posix_unc_form_detected() -> None:
    """v3.6.0 R17-1: ``//server/share/...`` form also covered."""
    assert _uri_looks_absolute("//fileserver/share/data.csv")


def test_v360_r171_file_uri_case_insensitive() -> None:
    """v3.6.0 R17-1 (gemini): ``FILE://`` (uppercase scheme) is
    a valid RFC 3986 §3.1 form and must redact the same as
    ``file://``. Pre-v3.6.0 only the lowercase form matched."""
    for form in ("file:///etc/secret", "FILE:///etc/secret", "File:///etc/secret"):
        assert _uri_looks_absolute(form), (
            f"v3.6.0 R17-1 regression: {form!r} not detected as absolute (case-sensitivity bug)."
        )


def test_v360_r171_relative_uri_not_misclassified() -> None:
    """v3.6.0 R17-1: a true relative URI (no prefix) must NOT
    be flagged as absolute. The widening must not over-redact."""
    assert not _uri_looks_absolute("data/file.csv")
    assert not _uri_looks_absolute("./local.parquet")


# ---------------------------------------------------------------------
# R17-2 — docstring honesty
# ---------------------------------------------------------------------
def test_v360_r172_open_safe_fd_docstring_no_false_windows_claim() -> None:
    """v3.6.0 R17-2 (claude + gemini): v3.5.0 docstring claimed a
    "post-open fstat consistency check" Windows fallback existed.
    It did NOT — the code just degraded to no protection. v3.6.0
    is honest about this. Pin via source-inspection that the
    false claim is gone."""
    import inspect

    src = inspect.getsource(Case._open_safe_fd)
    assert "post-open fstat consistency check" not in src, (
        "v3.6.0 R17-2 regression: the false Windows-fstat claim "
        "is back in the docstring. Be honest about scope."
    )


# ---------------------------------------------------------------------
# R17-4 — antimeridian-aware AEQD centre
# ---------------------------------------------------------------------
def test_v360_r174_aeqd_antimeridian_centre() -> None:
    """v3.6.0 R17-4 (claude + gemini HIGH): a polyline crossing
    ±180° must NOT collapse the AEQD centre to lon≈0. Verify the
    geodesic buffer still produces a valid geometry near the
    dateline."""
    from openlimno.habitat.cover import riparian_buffer_from_polyline

    # Two vertices on opposite sides of the dateline at high lat.
    coords = [(179.5, 70.0), (-179.5, 70.0)]
    geom = riparian_buffer_from_polyline(coords, buffer_m=5000.0)
    assert geom.is_valid, (
        "v3.6.0 R17-4 regression: dateline-crossing polyline produced an invalid geometry."
    )
    assert geom.area > 0


# ---------------------------------------------------------------------
# R17-5 — Transformer caching
# ---------------------------------------------------------------------
def test_v360_r175_transformer_cached_across_calls() -> None:
    """v3.6.0 R17-5: the AEQD Transformer factory must cache so
    a per-reach loop doesn't re-init PROJ on every call. Verify
    via the lru_cache hit metric."""
    from openlimno.habitat.cover import (
        _aeqd_transformer_from,
        _aeqd_transformer_to,
    )

    # Reset the cache state so we observe fresh misses.
    _aeqd_transformer_to.cache_clear()
    _aeqd_transformer_from.cache_clear()

    # Five calls at the same rounded centre — should be 1 miss + 4 hits.
    for _ in range(5):
        _aeqd_transformer_to(70, -120)
    info = _aeqd_transformer_to.cache_info()
    assert info.misses == 1 and info.hits == 4, (
        f"v3.6.0 R17-5 regression: cache stats wrong — {info}. Expected 1 miss + 4 hits."
    )


# ---------------------------------------------------------------------
# R17-10 — context-manager wrapper
# ---------------------------------------------------------------------
def test_v360_r1710_open_safe_context_manager(tmp_path: Path) -> None:
    """v3.6.0 R17-10 (gemini): the raw-fd ``_open_safe_fd`` is
    leak-prone. The ``_open_safe`` wrapper closes on exit even
    if the body raises.
    """
    case = _make_case(tmp_path / "case_dir")
    target = case.case_dir / "data.txt"
    # write_bytes (not write_text) so the newline isn't translated to \r\n on
    # Windows — _open_safe reads in binary and the assertion is byte-exact.
    target.write_bytes(b"safe-open test\n")

    with case._open_safe(str(target.relative_to(case.case_dir))) as f:
        content = f.read()
    assert content == b"safe-open test\n"
    # No fd leak — the context manager closed cleanly.


def test_v360_r1710_open_safe_closes_on_exception(tmp_path: Path) -> None:
    """v3.6.0 R17-10: if the body raises, the fd must still close.
    Verify by exhausting fd-limit budget would be too invasive;
    instead, just confirm the exception propagates AND no
    ResourceWarning is emitted."""
    import warnings

    case = _make_case(tmp_path / "case_dir")
    target = case.case_dir / "data.txt"
    target.write_text("hi\n")

    def _raise_inside_open() -> None:
        with case._open_safe(
            str(target.relative_to(case.case_dir)),
        ) as f:
            f.read()
            raise RuntimeError("body-exception")

    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        with pytest.raises(RuntimeError, match="body-exception"):
            _raise_inside_open()
    # If we got here, the ResourceWarning filter didn't trip —
    # the fd was properly closed despite the exception.


# ---------------------------------------------------------------------
# R17-3 — trust-roots fallback diagnostic
# ---------------------------------------------------------------------
def test_v360_r173_trust_roots_fallback_emits_diagnostic(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v3.6.0 R17-3 (claude HIGH): pre-v3.6.0 the
    ``_run_case_for_worker`` fallback silently swallowed
    Case.from_yaml errors. v3.6.0 scopes the except to
    OSError/ValueError/YAMLError and emits a stderr diagnostic
    so the worker traceback path still shows what went wrong.
    """
    # Mock run_case_with_plots so we don't need actual mesh/xs.
    from types import SimpleNamespace

    from openlimno.gui_core import controller as ctl_mod

    fake_result = SimpleNamespace(
        case_name="t",
        wua_quality_grade="A",
        n_discharges=1,
        output_dir=tmp_path / "out",
        wua_q_plot=tmp_path / "out" / "wua_q_curve.png",
    )
    monkeypatch.setattr(
        ctl_mod,
        "run_case_with_plots",
        lambda *a, **kw: fake_result,
    )

    # Build a SYNTACTICALLY-BROKEN YAML so Case.from_yaml raises
    # YAMLError on parse — the new except path.
    broken_yaml = tmp_path / "broken.yaml"
    broken_yaml.write_text(
        "openlimno: '0.2'\ncase: { name: t,\n",
        encoding="utf-8",
    )
    summary, _png, trust_roots = ctl_mod._run_case_for_worker(broken_yaml)
    captured = capsys.readouterr()
    assert "trust_roots fallback" in captured.err, (
        "v3.6.0 R17-3 regression: trust_roots fallback path no "
        "longer emits the stderr diagnostic. Errors will silently "
        "disappear inside the worker thread."
    )
    # Fallback should give just the case dir.
    assert trust_roots == [broken_yaml.parent.resolve()]

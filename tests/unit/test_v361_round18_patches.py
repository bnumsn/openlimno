"""v3.6.1 — 18th-round triple-AI review patches (R18-1, R18-2,
R18-3).

R18-1 (codex HIGH): ``Case._open_safe`` could double-close the fd
       when the consumer's ``with``-body raised. The inner
       ``os.fdopen``'s ``__exit__`` already closed the fd; the
       outer ``except BaseException: os.close(fd)`` then ran
       again, possibly closing a recycled-by-the-kernel unrelated
       fd in a multithreaded process.
R18-2 (codex MEDIUM): AEQD inverse projection of a buffer that
       straddled ±180° produced a Shapely polygon spanning nearly
       the whole world in longitude — Shapely is planar and has
       no notion of seam wrap. Downstream ``rasterio.mask.mask``
       would crop the wrong global bbox.
R18-3 (codex MEDIUM): the v3.6.0 R17-4 circular-mean longitude
       used ``atan2(sum_sin, sum_cos)`` with no magnitude guard.
       For antipodal longitude pairs like ``{0°, 180°}`` the
       resultant vector collapses to (0, 0) and ``atan2(0,0)`` is
       implementation-defined.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest
import yaml

from openlimno.case import Case


def _make_case(case_dir: Path) -> Case:
    case_dir.mkdir(parents=True, exist_ok=True)
    case_yaml = case_dir / "case.yaml"
    case_yaml.write_text(
        textwrap.dedent("""
            openlimno: '0.2'
            case:
              name: v361_r18_t
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
# R18-1 — _open_safe must not double-close
# ---------------------------------------------------------------------
def test_v361_r181_open_safe_does_not_double_close_on_body_exception(
    tmp_path: Path,
) -> None:
    """v3.6.1 R18-1 (codex HIGH): when the consumer's body raises
    inside ``with case._open_safe(...) as f``, the inner
    ``os.fdopen`` must take fd ownership and close it ONCE on
    ``__exit__``. The v3.6.0 cut would then call ``os.close(fd)``
    AGAIN from the outer try-except — potentially closing a
    different fd that the kernel had since recycled to the same
    integer in a multithreaded process. Pin by patching
    ``os.close`` and asserting the fd is closed at most once.
    """
    case = _make_case(tmp_path / "case_dir")
    target = case.case_dir / "data.txt"
    target.write_text("body-raises test\n")

    real_close = os.close
    closes: list[int] = []
    fd_seen_box: list[int] = []

    def _track_close(fd: int) -> None:
        closes.append(fd)
        real_close(fd)

    def _body_that_raises() -> None:
        with case._open_safe(
            str(target.relative_to(case.case_dir)),
        ) as f:
            fd_seen_box.append(f.fileno())
            raise RuntimeError("planted")

    try:
        os.close = _track_close  # type: ignore[assignment]
        with pytest.raises(RuntimeError, match="planted"):
            _body_that_raises()
    finally:
        os.close = real_close  # type: ignore[assignment]

    assert fd_seen_box, "test plumbing: body never executed"
    fd_seen = fd_seen_box[0]

    # The fd should appear at most once in `closes`. v3.6.0's bug
    # caused it to appear twice (once from os.fdopen.__exit__, once
    # from the outer try-except's manual os.close).
    n_closes = closes.count(fd_seen)
    assert n_closes <= 1, (
        f"v3.6.1 R18-1 regression: fd {fd_seen} was closed "
        f"{n_closes} times — double-close after fdopen took "
        f"ownership. In a multithreaded process this would close "
        f"an unrelated recycled fd."
    )


def test_v361_r181_open_safe_closes_fd_when_fdopen_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v3.6.1 R18-1: if ``os.fdopen`` raises (e.g. invalid mode),
    we still own the raw fd from ``_open_safe_fd`` — the wrapper
    MUST close it before re-raising, or we leak.
    """
    case = _make_case(tmp_path / "case_dir")
    target = case.case_dir / "data.txt"
    target.write_text("fdopen-fail test\n")

    real_close = os.close
    real_fdopen = os.fdopen
    closes: list[int] = []

    def _track_close(fd: int) -> None:
        closes.append(fd)
        real_close(fd)

    captured_fd: list[int] = []

    def _bad_fdopen(fd: int, *args: object, **kwargs: object) -> object:
        captured_fd.append(fd)
        raise OSError("planted fdopen failure")

    monkeypatch.setattr(os, "close", _track_close)
    monkeypatch.setattr(os, "fdopen", _bad_fdopen)

    def _try_open() -> None:
        with case._open_safe(
            str(target.relative_to(case.case_dir)),
        ):
            pass  # never reached — fdopen raised

    with pytest.raises(OSError, match="planted fdopen failure"):
        _try_open()

    assert captured_fd, "test plumbing: bad_fdopen never ran"
    fd = captured_fd[0]
    assert fd in closes, (
        f"v3.6.1 R18-1 regression: when fdopen fails, the raw fd "
        f"{fd} was leaked (close never called)."
    )


# ---------------------------------------------------------------------
# R18-3 — circular-mean magnitude guard
# ---------------------------------------------------------------------
def test_v361_r183_circular_mean_rejects_antipodal_pair() -> None:
    """v3.6.1 R18-3 (codex MEDIUM): a polyline whose longitudes
    sum to a zero-magnitude resultant unit-vector (e.g.
    ``{0°, 180°}`` or ``{-90°, +90°}``) has no well-defined
    local AEQD centre. The pre-v3.6.1 code would silently use
    ``atan2(0, 0) = 0`` (glibc) and build a buffer at lon=0,
    which can be hundreds of degrees away from where the
    polyline actually lives. v3.6.1 raises a clear ValueError.
    """
    from openlimno.habitat.cover import _riparian_buffer_geodesic

    # Antipodal pair at high latitude (forces geodesic path).
    coords_antipodal = [(0.0, 70.0), (180.0, 70.0)]
    with pytest.raises(ValueError, match="circular-mean"):
        _riparian_buffer_geodesic(coords_antipodal, buffer_m=5000.0)


def test_v361_r183_circular_mean_rejects_orthogonal_quartet() -> None:
    """v3.6.1 R18-3: {0°, 90°, 180°, -90°} also has resultant
    magnitude zero (the four unit vectors form a balanced cross).
    """
    from openlimno.habitat.cover import _riparian_buffer_geodesic

    coords_cross = [(0, 70), (90, 70), (180, 70), (-90, 70)]
    with pytest.raises(ValueError, match="circular-mean"):
        _riparian_buffer_geodesic(coords_cross, buffer_m=5000.0)


# ---------------------------------------------------------------------
# R18-2 — antimeridian split keeps lon bounds local
# ---------------------------------------------------------------------
def test_v361_r182_antimeridian_buffer_lon_bounds_stay_local() -> None:
    """v3.6.1 R18-2 (codex MEDIUM): the v3.6.0 R17-4 fix centred
    AEQD correctly, but the inverse projection of a buffer that
    crossed the dateline yielded a Shapely polygon whose lon
    bounds spanned nearly the whole world (e.g. from -180 to
    +180). Downstream rasterio cropping would then operate on
    the wrong bbox. v3.6.1 splits the geometry at ±180° into a
    MultiPolygon whose parts each respect the seam.

    Pin: a 5 km buffer around a 100 m dateline-crossing polyline
    at 70°N must have a total lon-bounds-span no greater than
    a small fraction of the globe, NOT ~360°.
    """
    from openlimno.habitat.cover import riparian_buffer_from_polyline

    # Short polyline straddling ±180° at 70°N. The buffer should
    # be a small dateline-local strip, not a world-spanning ring.
    coords = [(179.95, 70.0), (-179.95, 70.0)]
    geom = riparian_buffer_from_polyline(coords, buffer_m=5000.0)

    # The geometry should be a MultiPolygon with parts on both
    # sides of the seam.
    assert geom.is_valid
    minx, _, maxx, _ = geom.bounds
    # v3.6.0 would have produced bounds spanning ~360° (-180 .. +180).
    # v3.6.1 splits at the seam, so each piece's local bounds are
    # tiny (a few degrees), and the MultiPolygon as a whole has
    # one piece near +180 and one near -180 — meaning the OVERALL
    # bounds still span ~360, but each PART is small. Assert the
    # part-bounds-span is local.
    assert geom.geom_type == "MultiPolygon", (
        f"v3.6.1 R18-2 regression: expected MultiPolygon split "
        f"across the seam, got {geom.geom_type} with bounds "
        f"({minx:.2f}, {maxx:.2f}) — split logic didn't fire."
    )
    for part in geom.geoms:
        p_minx, _, p_maxx, _ = part.bounds
        assert (p_maxx - p_minx) < 5.0, (
            f"v3.6.1 R18-2 regression: dateline-split part has lon "
            f"span {p_maxx - p_minx:.1f}° — should be a few degrees "
            f"at most for a 5 km buffer."
        )


def test_v361_r182_non_dateline_buffer_unchanged() -> None:
    """v3.6.1 R18-2: the new antimeridian split is a no-op for
    buffers that don't actually cross ±180°. Regression-pin a
    mid-latitude polyline still produces a single Polygon.
    """
    from openlimno.habitat.cover import riparian_buffer_from_polyline

    # Wyoming-ish: 45°N, well away from the dateline.
    coords = [(-108.0, 43.0), (-107.9, 43.1)]
    geom = riparian_buffer_from_polyline(coords, buffer_m=200.0)
    assert geom.is_valid
    # Below 60° → cos-lat path, doesn't touch the seam logic.
    # Either way, the result must be a single Polygon, not a
    # spurious MultiPolygon.
    assert geom.geom_type == "Polygon", (
        f"v3.6.1 R18-2 regression: a non-dateline buffer "
        f"unexpectedly became {geom.geom_type}; the seam-split "
        f"logic should have short-circuited."
    )

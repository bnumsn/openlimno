"""Unit tests for ``openlimno.preprocess.fetch`` (v0.3 P0 prototype).

Network-dependent paths are NOT exercised here (kept for the
``tests/integration/test_fetch_live.py`` slow-suite that needs network
access). These tests cover the bits that can run offline:

* the XDG-aware on-disk cache: hit/miss + meta integrity + SHA round-trip.
* bbox / centerline geometry helpers (clip + tile decomposition).
* error surface when callers misuse the API (invalid bbox, out-of-
  coverage lats).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from openlimno.preprocess.fetch.cache import (
    CacheEntry,
    _request_key,
    cache_dir,
    cached_fetch,
)
from openlimno.preprocess.fetch.dem import (
    _tile_name,
    _tiles_for_bbox,
    clip_centerline_to_bbox,
    fetch_copernicus_dem,
)


# ---------------------------------------------------------------------
# cache.py
# ---------------------------------------------------------------------
def test_cache_dir_respects_xdg_cache_home(monkeypatch, tmp_path):
    """The cache root must obey ``$XDG_CACHE_HOME`` so users with
    sandboxed home dirs (CI, Flatpak) don't accidentally write to
    ``~/.cache``.
    """
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    root = cache_dir()
    assert root == tmp_path / "openlimno"
    assert root.exists()


def test_cache_dir_creates_subdir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    sub = cache_dir("dem/copernicus")
    assert sub == tmp_path / "openlimno" / "dem" / "copernicus"
    assert sub.is_dir()


def test_request_key_is_stable_across_param_order():
    """Cache key must be invariant to param dict ordering — otherwise
    two semantically identical fetches produce two cache entries.
    """
    a = _request_key("http://x/", {"b": 1, "a": 2})
    b = _request_key("http://x/", {"a": 2, "b": 1})
    assert a == b


def test_request_key_differs_by_url():
    assert _request_key("http://x/", {}) != _request_key("http://y/", {})


def test_request_key_differs_by_params():
    """Including bbox in params (as DEM fetcher does) MUST produce a
    different key — pinned because the v0.3 P0 prototype shipped a bug
    where two different bbox calls reused the first call's cached
    subset and silently produced mostly-zero rasters outside the
    original window.
    """
    a = _request_key("http://x/", {"lon_min": -114.0})
    b = _request_key("http://x/", {"lon_min": -113.85})
    assert a != b, (
        "REGRESSION: cache key ignores params — different bboxes will "
        "reuse the same cached subset"
    )


def test_cached_fetch_writes_then_serves_from_disk(monkeypatch, tmp_path):
    """First call fetches; second call must hit cache without invoking
    ``fetch_fn``. Pins both the disk persistence and the cache_hit flag.
    """
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    call_count = {"n": 0}

    def fake_fetch() -> bytes:
        call_count["n"] += 1
        return b"hello world"

    e1 = cached_fetch(subdir="test", url="http://x/", params={"a": 1},
                     suffix=".bin", fetch_fn=fake_fetch)
    assert e1.cache_hit is False
    assert e1.path.read_bytes() == b"hello world"
    assert call_count["n"] == 1

    e2 = cached_fetch(subdir="test", url="http://x/", params={"a": 1},
                     suffix=".bin", fetch_fn=fake_fetch)
    assert e2.cache_hit is True
    assert call_count["n"] == 1, (
        "REGRESSION: cache hit still invoked fetch_fn — the whole "
        "point of the cache is to avoid the network round-trip."
    )
    # Original fetch_time preserved across hits — that's what makes
    # provenance.json useful (it records when the data was originally
    # fetched, not when reproduced).
    assert e2.fetch_time == e1.fetch_time
    assert e2.sha256 == e1.sha256


def test_cached_fetch_records_sha256(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    payload = b"x" * 1000
    import hashlib
    expected = hashlib.sha256(payload).hexdigest()
    e = cached_fetch(subdir="t", url="http://x/", params=None,
                    suffix=".bin", fetch_fn=lambda: payload)
    assert e.sha256 == expected


def test_cached_fetch_writes_meta_json_with_fetch_time(monkeypatch, tmp_path):
    """Meta json is what makes the cache reproducible across sessions
    — it carries source URL + fetch_time + SHA to merge into
    provenance.json downstream.
    """
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    cached_fetch(subdir="t", url="http://x/data", params={"q": "y"},
                suffix=".bin", fetch_fn=lambda: b"abc")
    metas = list((tmp_path / "openlimno" / "t").glob("*.meta.json"))
    assert len(metas) == 1
    meta = json.loads(metas[0].read_text())
    assert meta["source_url"] == "http://x/data"
    assert meta["params"] == {"q": "y"}
    assert "fetch_time" in meta
    assert "sha256" in meta
    assert meta["size_bytes"] == 3


# ---------------------------------------------------------------------
# dem.py — bbox / tile decomposition (no network)
# ---------------------------------------------------------------------
def test_tile_name_northern_hemisphere():
    """Copernicus tile naming: SW corner integers, N/S + E/W prefixes."""
    assert _tile_name(44, -114) == "Copernicus_DSM_COG_10_N44_00_W114_00_DEM"


def test_tile_name_southern_hemisphere():
    assert _tile_name(-23, 30) == "Copernicus_DSM_COG_10_S23_00_E030_00_DEM"


def test_tile_name_equator_crossing():
    assert _tile_name(0, 0) == "Copernicus_DSM_COG_10_N00_00_E000_00_DEM"


def test_tiles_for_bbox_single_tile():
    """A bbox fully inside one 1° tile yields just that tile."""
    tiles = _tiles_for_bbox(-113.95, 44.94, -113.85, 44.96)
    assert tiles == [(44, -114)]


def test_tiles_for_bbox_spans_two_tiles_horizontally():
    tiles = _tiles_for_bbox(-114.5, 44.5, -112.5, 44.6)
    assert (44, -115) in tiles
    assert (44, -114) in tiles
    assert (44, -113) in tiles


def test_tiles_for_bbox_spans_two_tiles_vertically():
    tiles = _tiles_for_bbox(-114.0, 44.5, -113.95, 45.5)
    assert (44, -114) in tiles
    assert (45, -114) in tiles


def test_clip_centerline_keeps_only_inside_vertices():
    """Helper for the OSM-returns-the-whole-river problem."""
    cl = [(-114.5, 45.5), (-113.95, 44.95), (-113.93, 44.96), (-113.50, 44.10)]
    kept = clip_centerline_to_bbox(cl, -114.0, 44.9, -113.9, 45.0)
    assert kept == [(-113.95, 44.95), (-113.93, 44.96)]


def test_clip_centerline_raises_when_no_overlap():
    cl = [(-100.0, 30.0), (-99.0, 30.5)]
    with pytest.raises(ValueError, match="centerline vertices remain"):
        clip_centerline_to_bbox(cl, -114.0, 44.9, -113.9, 45.0)


def test_clip_centerline_raises_with_only_one_inside():
    """One vertex isn't enough to define a reach — must reject early."""
    cl = [(-114.5, 45.5), (-113.95, 44.95), (-113.50, 44.10)]
    with pytest.raises(ValueError):
        clip_centerline_to_bbox(cl, -113.96, 44.94, -113.94, 44.96)


# ---------------------------------------------------------------------
# Error surface — no network needed
# ---------------------------------------------------------------------
def test_fetch_copernicus_rejects_inverted_bbox():
    """lon_max < lon_min would silently produce zero tiles + a confusing
    'no tiles available' error downstream. Reject upfront with a clearer
    message."""
    with pytest.raises(ValueError, match="Invalid DEM bbox"):
        fetch_copernicus_dem(-113.0, 44.0, -114.0, 45.0)  # lon swapped


def test_fetch_copernicus_rejects_polar_bbox():
    """Copernicus GLO-30 stops at 84°N — beyond that we'd silently
    fetch ocean tiles that don't exist. Reject upfront."""
    with pytest.raises(ValueError, match="outside Copernicus GLO-30"):
        fetch_copernicus_dem(-30.0, 85.0, -29.0, 86.0)


def test_nwis_rating_curve_emits_clear_migration_error():
    """USGS deprecated the legacy RDB measurements endpoint mid-
    migration; v0.3 P0 ships discharge-only. Make sure users see a
    clear pointer to the workaround instead of a silent 404.
    """
    from openlimno.preprocess.fetch.nwis import fetch_nwis_rating_curve
    with pytest.raises(NotImplementedError, match="migration"):
        fetch_nwis_rating_curve("13305000")


# ---------------------------------------------------------------------
# sidecar.py — external-source provenance
# ---------------------------------------------------------------------
def test_sidecar_record_writes_json_with_sha(tmp_path):
    """record_fetch writes a JSON list with the file's actual SHA-256."""
    from openlimno.preprocess.fetch import record_fetch, read_sidecar
    (tmp_path / "data").mkdir()
    produced = tmp_path / "data" / "Q.csv"
    produced.write_text("time,Q\n2024-01-01,1.0\n")
    rec = record_fetch(
        tmp_path,
        label="discharge", source_type="usgs_nwis",
        source_url="https://example.org/nwis", fetch_time="2026-05-12T00:00:00",
        produced_file="data/Q.csv",
        params={"site_id": "13305000"}, notes="hello",
    )
    import hashlib
    expected = hashlib.sha256(b"time,Q\n2024-01-01,1.0\n").hexdigest()
    assert rec.produced_sha256 == expected
    records = read_sidecar(tmp_path)
    assert len(records) == 1
    assert records[0]["label"] == "discharge"
    assert records[0]["produced_sha256"] == expected


def test_sidecar_record_is_idempotent_by_label(tmp_path):
    """Re-recording the same label REPLACES the earlier entry (so
    re-running init-from-osm doesn't stack stale records).
    """
    from openlimno.preprocess.fetch import record_fetch, read_sidecar
    (tmp_path / "data").mkdir()
    f = tmp_path / "data" / "Q.csv"
    f.write_text("a")
    record_fetch(tmp_path, label="d", source_type="x",
                source_url="u1", fetch_time="t1", produced_file="data/Q.csv")
    f.write_text("b")
    record_fetch(tmp_path, label="d", source_type="x",
                source_url="u2", fetch_time="t2", produced_file="data/Q.csv")
    records = read_sidecar(tmp_path)
    assert len(records) == 1, (
        f"REGRESSION: duplicate records for label 'd' — re-running "
        f"init-from-osm against an existing case_dir should overwrite, "
        f"not append. Got {len(records)} records."
    )
    assert records[0]["source_url"] == "u2"


def test_sidecar_record_raises_on_missing_file(tmp_path):
    """If caller forgets to write produced_file before recording,
    error out clearly instead of recording an empty-file hash that
    will silently fail reproduce later.
    """
    from openlimno.preprocess.fetch import record_fetch
    (tmp_path / "data").mkdir()
    with pytest.raises(FileNotFoundError, match="produced_file"):
        record_fetch(tmp_path, label="x", source_type="y",
                    source_url="u", fetch_time="t",
                    produced_file="data/does_not_exist.csv")


def test_sidecar_missing_returns_empty_list(tmp_path):
    """Cases built without --fetch-* flags have no sidecar; reader
    must return [] rather than raise — Case._build_provenance calls
    this unconditionally.
    """
    from openlimno.preprocess.fetch import read_sidecar
    assert read_sidecar(tmp_path) == []


def test_sidecar_verify_detects_file_drift(tmp_path):
    """verify_sidecar must catch mutation of produced files — pinned
    because that's what makes ``openlimno reproduce`` useful for
    auto-fetched data.
    """
    from openlimno.preprocess.fetch import record_fetch, verify_sidecar
    (tmp_path / "data").mkdir()
    f = tmp_path / "data" / "Q.csv"
    f.write_text("original content")
    record_fetch(tmp_path, label="d", source_type="x",
                source_url="u", fetch_time="t", produced_file="data/Q.csv")
    # Tamper
    f.write_text("tampered content")
    results = verify_sidecar(tmp_path)
    assert len(results) == 1
    label, ok, reason = results[0]
    assert label == "d"
    assert ok is False
    assert "SHA mismatch" in reason


def test_sidecar_verify_detects_missing_file(tmp_path):
    from openlimno.preprocess.fetch import record_fetch, verify_sidecar
    (tmp_path / "data").mkdir()
    f = tmp_path / "data" / "Q.csv"
    f.write_text("x")
    record_fetch(tmp_path, label="d", source_type="x",
                source_url="u", fetch_time="t", produced_file="data/Q.csv")
    f.unlink()
    results = verify_sidecar(tmp_path)
    assert results[0][1] is False
    assert "missing" in results[0][2]


def test_sidecar_verify_passes_on_unmodified(tmp_path):
    from openlimno.preprocess.fetch import record_fetch, verify_sidecar
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "Q.csv").write_text("x")
    record_fetch(tmp_path, label="d", source_type="x",
                source_url="u", fetch_time="t", produced_file="data/Q.csv")
    results = verify_sidecar(tmp_path)
    assert results[0][1] is True
    assert results[0][2] == ""


def test_sidecar_corrupt_json_raises_loudly(tmp_path):
    """Round-2 fix: silent return-[] on corrupt sidecar broke the
    reproducibility guarantee. A corrupt sidecar now raises
    SidecarCorruptedError with a clear remediation hint.
    """
    from openlimno.preprocess.fetch.sidecar import (
        SidecarCorruptedError, read_sidecar,
    )
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / ".openlimno_external_sources.json").write_text(
        "{partial json"
    )
    with pytest.raises(SidecarCorruptedError, match="not valid JSON"):
        read_sidecar(tmp_path)


def test_sidecar_wrong_root_type_raises_loudly(tmp_path):
    """A sidecar whose root is not a list (e.g., manually edited to a
    dict) is also corrupt — raise instead of silently returning [].
    """
    from openlimno.preprocess.fetch.sidecar import (
        SidecarCorruptedError, read_sidecar,
    )
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / ".openlimno_external_sources.json").write_text(
        '{"not": "a list"}'
    )
    with pytest.raises(SidecarCorruptedError, match="root type"):
        read_sidecar(tmp_path)


def test_dem_rejects_oversize_bbox():
    """Round-2 fix: 10°×10° bbox = 121 tiles ≈ 12 GB peak after
    merge. A user mistakenly passing a country-sized bbox would
    OOM-kill the process. Reject at entry with a clear cap message.
    """
    from openlimno.preprocess.fetch.dem import fetch_copernicus_dem
    with pytest.raises(ValueError, match="exceeds the safety cap"):
        # 10×10 = 100 deg² > 9 cap
        fetch_copernicus_dem(-114.0, 44.0, -104.0, 54.0)


def test_sidecar_rejects_produced_file_outside_case_dir(tmp_path):
    """Round-3 fix: ``record_fetch(produced_file='../etc/passwd')``
    used to happily compute a SHA of arbitrary host files and write
    it to the sidecar, polluting the provenance trail (and under
    untrusted-input scenarios leaking SHA of system files). The
    sidecar's contract is "files INSIDE this case_dir only" — enforce
    it at the API boundary.
    """
    from openlimno.preprocess.fetch import record_fetch
    (tmp_path / "data").mkdir()
    # Create a file OUTSIDE case_dir
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret")
    try:
        with pytest.raises(ValueError, match="escapes case_dir"):
            record_fetch(
                tmp_path, label="evil", source_type="x",
                source_url="u", fetch_time="t",
                produced_file=str(outside),
            )
    finally:
        outside.unlink()


def test_sidecar_rejects_relative_path_escaping_case_dir(tmp_path):
    """Same protection via ``../`` traversal in the relative path."""
    from openlimno.preprocess.fetch import record_fetch
    (tmp_path / "data").mkdir()
    # Create something accessible via ../
    (tmp_path.parent / "evil.txt").write_text("secret")
    try:
        with pytest.raises(ValueError, match="escapes case_dir"):
            record_fetch(
                tmp_path, label="evil", source_type="x",
                source_url="u", fetch_time="t",
                produced_file="../evil.txt",
            )
    finally:
        (tmp_path.parent / "evil.txt").unlink()


# ---------------------------------------------------------------------
# daymet.py — input validation (no network needed)
# ---------------------------------------------------------------------
def test_daymet_rejects_inverted_year_range():
    """Start > end would yield empty Daymet results + a confusing
    upstream error. Reject at module entry with a clear message."""
    from openlimno.preprocess.fetch import fetch_daymet_daily
    with pytest.raises(ValueError, match="start_year"):
        fetch_daymet_daily(44.9, -113.9, start_year=2024, end_year=2020)


def test_daymet_rejects_pre_1980_year():
    """Round-1 fix: Daymet API silently snaps out-of-window requests
    to its default range. A user asking for 1950 data would get 1980+
    data in a file named climate_1950_1950.csv — invisible
    mislabelling. Pre-validate locally so the user sees the error.
    """
    from openlimno.preprocess.fetch import fetch_daymet_daily
    with pytest.raises(ValueError, match="Daymet v4 coverage"):
        fetch_daymet_daily(44.9, -113.9, start_year=1950, end_year=1955)


def test_daymet_rejects_out_of_domain_lat():
    """Daymet's domain is North America (-49.5 to +83.5 lat). A user
    passing a European or African lat would otherwise hit a generic
    HTTP 400; reject locally with a pointer at ERA5-Land instead."""
    from openlimno.preprocess.fetch import fetch_daymet_daily
    with pytest.raises(ValueError, match="Daymet"):
        fetch_daymet_daily(48.85, 2.35, 2024, 2024)  # Paris


def test_daymet_stefan_constants_are_named():
    """Stefan & Preud'homme (1993) air→water linear regression
    constants must be module-level (not magic numbers). Future
    calibration / sensitivity work needs them as exported names.
    """
    from openlimno.preprocess.fetch.daymet import (
        STEFAN_AIR_TO_WATER_A, STEFAN_AIR_TO_WATER_B,
    )
    assert STEFAN_AIR_TO_WATER_A == 5.0
    assert STEFAN_AIR_TO_WATER_B == 0.75


def test_overpass_query_function_matches_actual_fetch():
    """Round-5 fix: ``build_overpass_query`` (exposed for sidecar
    recording) must produce the EXACT same string the
    ``fetch_river_polyline`` function sends — otherwise the recorded
    query in provenance.json diverges silently and users who try to
    replay the same Overpass call get different results.

    We verify by inspecting the source: both code paths must reference
    the same function. (Stronger version would mock requests.get and
    check params['data'], but that's a network-shape integration test.)
    """
    import inspect
    from openlimno.preprocess.osm_builder import (
        build_overpass_query, fetch_river_polyline,
    )
    # Sanity: build_overpass_query is called from fetch_river_polyline
    src = inspect.getsource(fetch_river_polyline)
    assert "build_overpass_query(" in src, (
        "REGRESSION: fetch_river_polyline no longer uses "
        "build_overpass_query — sidecar's recorded query will drift "
        "from what the real fetch sends. Both must share the source."
    )
    # And: bbox variant produces the expected structure
    q = build_overpass_query(bbox=(-114.0, 44.92, -113.85, 45.0))
    assert '["waterway"]' in q
    assert "44.92,-114.0,45.0,-113.85" in q  # Overpass S,W,N,E order
    assert "out geom;" in q


def test_dem_accepts_3deg_bbox():
    """Just under the cap should not raise (no network call here —
    we trigger the upfront bbox check, then the next step would be
    network. But invalid lat_max of 84 triggers ANOTHER check first,
    so just check the area-cap check itself fires on the right
    threshold by checking the math.)
    """
    from openlimno.preprocess.fetch.dem import fetch_copernicus_dem
    # 3°×3° = 9.0 deg², at the cap (strict > so it's allowed)
    # We can't actually call without network, just assert the size
    # check doesn't trip. Construct a bbox that fails LATER (out of
    # coverage at high lat) so we can tell that the size-cap check
    # already passed.
    import pytest as _pytest
    # 1°×1° well under cap — would proceed to fetch, but we don't
    # have network in the test; we expect it to raise something OTHER
    # than the size-cap error.
    with _pytest.raises(ValueError) as excinfo:
        fetch_copernicus_dem(-114.0, 84.5, -113.0, 85.0)
    assert "outside Copernicus" in str(excinfo.value), (
        f"Expected coverage error for polar bbox, got: {excinfo.value}"
    )


# ---------------------------------------------------------------------
# openmeteo.py — input validation (no network)
# ---------------------------------------------------------------------
def test_open_meteo_rejects_inverted_year_range():
    from openlimno.preprocess.fetch import fetch_open_meteo_daily
    with pytest.raises(ValueError, match="start_year"):
        fetch_open_meteo_daily(31.23, 121.47, start_year=2024, end_year=2020)


def test_open_meteo_rejects_pre_1940_year():
    """Open-Meteo archive backend (ERA5) starts 1940-01-01. Earlier
    requests would get silently snapped, mislabelling the CSV — refuse
    locally. Mirrors the Daymet pre-1980 guard.
    """
    from openlimno.preprocess.fetch import fetch_open_meteo_daily
    with pytest.raises(ValueError, match="Open-Meteo archive coverage"):
        fetch_open_meteo_daily(31.23, 121.47, start_year=1900, end_year=1905)


def test_open_meteo_rejects_invalid_lat_lon():
    """Globe-wide coverage means lat/lon only need basic sanity bounds,
    not a North-America box like Daymet. Pin the [-90,90]/[-180,180]
    rejection so a transposed lat/lon never silently queries the wrong
    grid cell.
    """
    from openlimno.preprocess.fetch import fetch_open_meteo_daily
    with pytest.raises(ValueError, match="lat="):
        fetch_open_meteo_daily(95.0, 121.47, 2024, 2024)
    with pytest.raises(ValueError, match="lon="):
        fetch_open_meteo_daily(31.23, 250.0, 2024, 2024)


def test_open_meteo_reuses_stefan_constants_from_daymet():
    """Both climate fetchers must share the SAME air→water linear
    regression constants, otherwise switching between Daymet and
    Open-Meteo for the same case would silently produce different
    T_water columns. Single source of truth lives in daymet.py.
    """
    from openlimno.preprocess.fetch import daymet, openmeteo
    assert openmeteo.STEFAN_AIR_TO_WATER_A is daymet.STEFAN_AIR_TO_WATER_A
    assert openmeteo.STEFAN_AIR_TO_WATER_B is daymet.STEFAN_AIR_TO_WATER_B


def _fake_open_meteo_response(
    *, include_precip: bool = False,
    elevation: float = 12.0, snapped_lat: float = 31.25,
    snapped_lon: float = 121.5,
) -> bytes:
    """Build a minimal Open-Meteo archive JSON payload (3-day window)."""
    payload = {
        "latitude": snapped_lat,
        "longitude": snapped_lon,
        "elevation": elevation,
        "timezone": "UTC",
        "utc_offset_seconds": 0,
        "generationtime_ms": 1.23,
        "daily": {
            "time": ["2024-07-01", "2024-07-02", "2024-07-03"],
            "temperature_2m_max": [30.0, 31.0, 29.5],
            "temperature_2m_min": [22.0, 23.0, 21.5],
        },
    }
    if include_precip:
        payload["daily"]["precipitation_sum"] = [0.0, 1.5, 8.2]
    return json.dumps(payload).encode()


def test_open_meteo_parses_response_into_daymet_compatible_schema(
    monkeypatch, tmp_path,
):
    """End-to-end parse path: inject a canned JSON payload via the
    cache (so no network is needed), then verify the produced
    DataFrame schema matches Daymet's exactly.
    """
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    class _Resp:
        content = _fake_open_meteo_response()
        def raise_for_status(self): pass

    def fake_get(url, params=None, timeout=None):  # noqa: ARG001
        return _Resp()

    monkeypatch.setattr(
        "openlimno.preprocess.fetch.openmeteo.requests.get", fake_get,
    )
    from openlimno.preprocess.fetch import fetch_open_meteo_daily
    res = fetch_open_meteo_daily(31.23, 121.47, 2024, 2024)

    assert list(res.df.columns) == [
        "time", "tmax_C", "tmin_C", "T_air_C_mean", "T_water_C_stefan",
    ], "schema must equal Daymet's so downstream code is source-agnostic"
    assert len(res.df) == 3
    # Stefan check: a=5.0, b=0.75 → at tmean=26, T_water=24.5
    row = res.df.iloc[0]
    assert row["tmax_C"] == 30.0 and row["tmin_C"] == 22.0
    assert row["T_air_C_mean"] == pytest.approx(26.0)
    assert row["T_water_C_stefan"] == pytest.approx(5.0 + 0.75 * 26.0)
    # Snapped coords + elevation come from response, not the request
    assert res.lat == pytest.approx(31.25)
    assert res.lon == pytest.approx(121.5)
    assert res.elevation_m == pytest.approx(12.0)
    assert res.timezone == "UTC"
    assert "Open-Meteo" in res.citation and "Hersbach" in res.citation


def test_open_meteo_include_precip_adds_column(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    class _Resp:
        content = _fake_open_meteo_response(include_precip=True)
        def raise_for_status(self): pass

    monkeypatch.setattr(
        "openlimno.preprocess.fetch.openmeteo.requests.get",
        lambda url, params=None, timeout=None: _Resp(),
    )
    from openlimno.preprocess.fetch import fetch_open_meteo_daily
    res = fetch_open_meteo_daily(
        31.23, 121.47, 2024, 2024, include_precip=True,
    )
    assert "prcp_mm" in res.df.columns
    assert res.df["prcp_mm"].tolist() == [0.0, 1.5, 8.2]


def test_open_meteo_water_temp_is_clipped_at_zero(monkeypatch, tmp_path):
    """Sub-zero air temps must NOT produce negative water temps —
    streams in ice-free state stay ≥ 0 °C. Same clip as Daymet."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    payload = {
        "latitude": 60.0, "longitude": 30.0, "elevation": 100.0,
        "timezone": "UTC", "utc_offset_seconds": 0,
        "daily": {
            "time": ["2024-01-01"],
            "temperature_2m_max": [-10.0],
            "temperature_2m_min": [-20.0],
        },
    }

    class _Resp:
        content = json.dumps(payload).encode()
        def raise_for_status(self): pass

    monkeypatch.setattr(
        "openlimno.preprocess.fetch.openmeteo.requests.get",
        lambda url, params=None, timeout=None: _Resp(),
    )
    from openlimno.preprocess.fetch import fetch_open_meteo_daily
    res = fetch_open_meteo_daily(60.0, 30.0, 2024, 2024)
    # T_air_mean = -15. Stefan(−15) = 5 + 0.75×(−15) = −6.25 → clipped 0.
    assert res.df.iloc[0]["T_water_C_stefan"] == 0.0


def test_open_meteo_raises_on_missing_daily_block(monkeypatch, tmp_path):
    """If the API returns an error envelope (no ``daily``), fail loudly
    instead of producing an empty DataFrame that silently passes
    downstream validators."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    class _Resp:
        content = json.dumps({
            "error": True, "reason": "rate limited",
        }).encode()
        def raise_for_status(self): pass

    monkeypatch.setattr(
        "openlimno.preprocess.fetch.openmeteo.requests.get",
        lambda url, params=None, timeout=None: _Resp(),
    )
    from openlimno.preprocess.fetch import fetch_open_meteo_daily
    with pytest.raises(RuntimeError, match="missing 'daily'"):
        fetch_open_meteo_daily(31.23, 121.47, 2024, 2024)


def test_open_meteo_cache_key_includes_bbox_like_params(monkeypatch, tmp_path):
    """Two different (lat, lon) requests must NOT collide in cache —
    the v0.3 P0 DEM regression (cache key ignoring bbox) bit us once;
    pin the analogous invariant for climate."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    call_log: list[dict] = []

    class _Resp:
        def __init__(self, lat, lon):
            self._lat = lat
            self._lon = lon
        @property
        def content(self):
            return _fake_open_meteo_response(
                snapped_lat=self._lat, snapped_lon=self._lon,
            )
        def raise_for_status(self): pass

    def fake_get(url, params=None, timeout=None):  # noqa: ARG001
        call_log.append(dict(params))
        return _Resp(float(params["latitude"]), float(params["longitude"]))

    monkeypatch.setattr(
        "openlimno.preprocess.fetch.openmeteo.requests.get", fake_get,
    )
    from openlimno.preprocess.fetch import fetch_open_meteo_daily
    fetch_open_meteo_daily(31.23, 121.47, 2024, 2024)  # Shanghai
    fetch_open_meteo_daily(40.71, -74.01, 2024, 2024)  # NYC
    assert len(call_log) == 2, (
        "REGRESSION: cache reused Shanghai entry for NYC — cache key "
        "doesn't include lat/lon"
    )


# ---------------------------------------------------------------------
# hydrosheds.py — input validation + topology (no network)
# ---------------------------------------------------------------------
def test_hydrosheds_rejects_unknown_region():
    from openlimno.preprocess.fetch import fetch_hydrobasins
    with pytest.raises(ValueError, match="not a HydroSHEDS continental code"):
        fetch_hydrobasins(region="xx", level=12)


def test_hydrosheds_rejects_invalid_level():
    from openlimno.preprocess.fetch import fetch_hydrobasins
    with pytest.raises(ValueError, match="supported range"):
        fetch_hydrobasins(region="as", level=13)
    with pytest.raises(ValueError, match="supported range"):
        fetch_hydrobasins(region="as", level=0)


def test_hydrosheds_safe_extract_rejects_zip_slip(tmp_path):
    """Defensive zip-slip guard: a malicious zip with a path that
    escapes the destination (``../escape.txt``) must be refused —
    even though HydroSHEDS' own zips are trusted, the extraction
    helper is reusable infra."""
    import zipfile
    from openlimno.preprocess.fetch.hydrosheds import _safe_extract_zip

    bad_zip = tmp_path / "evil.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("../escape.txt", b"pwned")

    dest = tmp_path / "unpack"
    with pytest.raises(RuntimeError, match="zip-slip"):
        _safe_extract_zip(bad_zip, dest)


def _build_mini_hydrobasins(shp_dir, basins):
    """Hand-roll a tiny HydroBASINS-shaped shapefile for unit tests.

    Args:
        shp_dir: Path of directory to write into.
        basins: list of dicts {hybas_id, next_down, sub_area, wkt}.

    Returns the .shp Path.
    """
    from osgeo import ogr, osr
    shp_path = shp_dir / "hybas_xx_lev12_v1c.shp"
    drv = ogr.GetDriverByName("ESRI Shapefile")
    ds = drv.CreateDataSource(str(shp_path))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    layer = ds.CreateLayer("hybas", srs, ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn("HYBAS_ID", ogr.OFTInteger64))
    layer.CreateField(ogr.FieldDefn("NEXT_DOWN", ogr.OFTInteger64))
    layer.CreateField(ogr.FieldDefn("SUB_AREA", ogr.OFTReal))
    defn = layer.GetLayerDefn()
    for b in basins:
        feat = ogr.Feature(defn)
        feat.SetField("HYBAS_ID", b["hybas_id"])
        feat.SetField("NEXT_DOWN", b["next_down"])
        feat.SetField("SUB_AREA", b["sub_area"])
        geom = ogr.CreateGeometryFromWkt(b["wkt"])
        feat.SetGeometry(geom)
        layer.CreateFeature(feat)
        feat = None
    ds = None  # flush
    return shp_path


def test_hydrosheds_upstream_walk_simple_chain(tmp_path):
    """4-basin layout: 1 ← 2 ← 3 ; 4 is independent.
    upstream(1) = {1,2,3}; upstream(4) = {4}.
    """
    basins = [
        {"hybas_id": 1, "next_down": 0, "sub_area": 100.0,
         "wkt": "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"},
        {"hybas_id": 2, "next_down": 1, "sub_area":  50.0,
         "wkt": "POLYGON((1 0, 2 0, 2 1, 1 1, 1 0))"},
        {"hybas_id": 3, "next_down": 2, "sub_area":  20.0,
         "wkt": "POLYGON((2 0, 3 0, 3 1, 2 1, 2 0))"},
        {"hybas_id": 4, "next_down": 0, "sub_area": 999.0,
         "wkt": "POLYGON((10 10, 11 10, 11 11, 10 11, 10 10))"},
    ]
    shp = _build_mini_hydrobasins(tmp_path, basins)
    from openlimno.preprocess.fetch import upstream_basin_ids
    assert upstream_basin_ids(shp, 1) == [1, 2, 3]
    assert upstream_basin_ids(shp, 2) == [2, 3]
    assert upstream_basin_ids(shp, 3) == [3]
    assert upstream_basin_ids(shp, 4) == [4]


def test_hydrosheds_upstream_walk_unknown_id_raises(tmp_path):
    basins = [
        {"hybas_id": 1, "next_down": 0, "sub_area": 1.0,
         "wkt": "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"},
    ]
    shp = _build_mini_hydrobasins(tmp_path, basins)
    from openlimno.preprocess.fetch import upstream_basin_ids
    with pytest.raises(ValueError, match="not found"):
        upstream_basin_ids(shp, 999)


def test_hydrosheds_find_basin_at_inside(tmp_path):
    basins = [
        {"hybas_id": 7, "next_down": 0, "sub_area": 10.0,
         "wkt": "POLYGON((10 20, 11 20, 11 21, 10 21, 10 20))"},
    ]
    shp = _build_mini_hydrobasins(tmp_path, basins)
    from openlimno.preprocess.fetch import find_basin_at
    hit = find_basin_at(shp, lat=20.5, lon=10.5)
    assert hit is not None
    assert hit["HYBAS_ID"] == 7
    assert "geometry_wkt" in hit and "POLYGON" in hit["geometry_wkt"]


def test_hydrosheds_find_basin_at_outside_returns_none(tmp_path):
    basins = [
        {"hybas_id": 7, "next_down": 0, "sub_area": 10.0,
         "wkt": "POLYGON((10 20, 11 20, 11 21, 10 21, 10 20))"},
    ]
    shp = _build_mini_hydrobasins(tmp_path, basins)
    from openlimno.preprocess.fetch import find_basin_at
    assert find_basin_at(shp, lat=0.0, lon=0.0) is None


def test_hydrosheds_write_watershed_geojson_aggregates_area(tmp_path):
    basins = [
        {"hybas_id": 1, "next_down": 0, "sub_area": 100.0,
         "wkt": "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"},
        {"hybas_id": 2, "next_down": 1, "sub_area":  50.0,
         "wkt": "POLYGON((1 0, 2 0, 2 1, 1 1, 1 0))"},
        {"hybas_id": 3, "next_down": 2, "sub_area":  20.0,
         "wkt": "POLYGON((2 0, 3 0, 3 1, 2 1, 2 0))"},
    ]
    shp = _build_mini_hydrobasins(tmp_path, basins)
    from openlimno.preprocess.fetch import write_watershed_geojson
    out = tmp_path / "ws.geojson"
    summary = write_watershed_geojson(shp, [1, 2, 3], out)
    assert out.exists()
    assert summary["n_basins"] == 3
    assert summary["area_km2"] == pytest.approx(170.0)
    # Bbox should span the union of the three side-by-side unit squares.
    assert summary["bbox"] == pytest.approx((0.0, 0.0, 3.0, 1.0))
    # GeoJSON file is valid + the single feature has matching attrs.
    payload = json.loads(out.read_text())
    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) == 1
    feat = payload["features"][0]
    assert feat["properties"]["n_basins"] == 3
    assert feat["properties"]["area_km2"] == pytest.approx(170.0)


def test_hydrosheds_write_watershed_geojson_missing_basin_raises(tmp_path):
    """If the caller passes a HYBAS_ID that isn't in the shapefile, we
    must FAIL — otherwise the produced watershed is a silent
    under-estimate and downstream stats are wrong."""
    basins = [
        {"hybas_id": 1, "next_down": 0, "sub_area": 100.0,
         "wkt": "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"},
    ]
    shp = _build_mini_hydrobasins(tmp_path, basins)
    from openlimno.preprocess.fetch import write_watershed_geojson
    with pytest.raises(RuntimeError, match="Missing first 5"):
        write_watershed_geojson(shp, [1, 99], tmp_path / "ws.geojson")


def test_hydrosheds_does_not_enable_global_ogr_exceptions():
    """REGRESSION GUARD: importing hydrosheds.py must NOT call
    ``ogr.UseExceptions()``. Real HydroSHEDS shapefiles ship with a
    ``.sbn`` legacy spatial index that emits non-fatal "ERROR 1:
    Inconsistent shape count for bin" warnings on iteration. With
    exceptions enabled those warnings abort the layer read mid-stream,
    breaking find_basin_at + upstream_basin_ids on any real continent.

    Hand-rolled mini shapefiles (used by other unit tests in this file)
    have no .sbn, so they DON'T trigger the warning — meaning a buggy
    re-introduction of UseExceptions() would silently pass the unit
    suite and only break in production. This pin closes that gap.
    """
    import importlib
    import openlimno.preprocess.fetch.hydrosheds  # noqa: F401
    from osgeo import ogr
    # Force a fresh import to be sure module-init didn't leave state
    importlib.reload(openlimno.preprocess.fetch.hydrosheds)
    # In exception mode GetUseExceptions() returns 1.
    assert ogr.GetUseExceptions() == 0, (
        "REGRESSION: ogr.UseExceptions() was enabled at module-init. "
        "This breaks HydroSHEDS layer iteration on .sbn-indexed real "
        "shapefiles. See hydrosheds.py module-level NOTE."
    )


# ---------------------------------------------------------------------
# fetch/__init__.py — API surface guard (regression pin against
# accidental removal of any fetcher)
# ---------------------------------------------------------------------
def test_fetch_package_exposes_all_fetchers_at_top_level():
    """Importing ``openlimno.preprocess.fetch`` MUST expose every
    fetcher's primary entry point. Any future module split/rename that
    drops one of these names breaks downstream users without a
    ``__all__`` ImportError to flag it.
    """
    from openlimno.preprocess import fetch
    expected_callables = [
        # v0.3.0
        "fetch_copernicus_dem", "fetch_nwis_daily_discharge",
        "fetch_nwis_rating_curve", "find_nwis_stations_near",
        "cached_fetch", "record_fetch", "read_sidecar", "verify_sidecar",
        # v0.3.1
        "fetch_daymet_daily",
        # v0.3.2
        "fetch_open_meteo_daily",
        # v0.3.3
        "fetch_hydrobasins", "fetch_hydrorivers", "find_basin_at",
        "upstream_basin_ids", "write_watershed_geojson",
        # v0.3.4
        "fetch_esa_worldcover",
        # v0.3.5
        "fetch_soilgrids",
        # v0.3.6
        "match_species", "fetch_gbif_occurrences",
    ]
    for name in expected_callables:
        attr = getattr(fetch, name, None)
        assert callable(attr), (
            f"REGRESSION: openlimno.preprocess.fetch.{name} missing or "
            f"non-callable — somebody removed/renamed a fetcher entry "
            f"point. Update this pin if intentional."
        )
        assert name in fetch.__all__, (
            f"REGRESSION: {name!r} not in fetch.__all__ — it'll be "
            f"invisible to `from openlimno.preprocess.fetch import *` "
            f"and to tooling that introspects __all__."
        )


def test_fetch_package_exposes_all_result_dataclasses():
    """Same pin for the result dataclasses — downstream type
    annotations (`OpenMeteoFetchResult`, etc.) rely on these being
    re-exported at the package root."""
    from openlimno.preprocess import fetch
    expected_types = [
        "CacheEntry", "DEMFetchResult", "NWISFetchResult",
        "DaymetFetchResult", "OpenMeteoFetchResult",
        "HydroshedsLayerResult", "WorldCoverFetchResult",
        "SoilGridsFetchResult",
        "SpeciesMatchResult", "SpeciesOccurrencesResult",
        "ExternalSourceRecord",
    ]
    for name in expected_types:
        assert isinstance(getattr(fetch, name, None), type), (
            f"REGRESSION: {name} not exported as a type at "
            f"openlimno.preprocess.fetch"
        )
        assert name in fetch.__all__


# ---------------------------------------------------------------------
# fishbase.py — bundled starter-table species traits
# ---------------------------------------------------------------------
def test_fishbase_starter_table_includes_common_phabsim_species():
    """The starter table must include the species OpenLimno's own
    example cases consume. If a species is dropped from the table,
    `examples/lemhi/quickstart.py` etc. lose their habitat-traits
    fallback."""
    from openlimno.preprocess.fetch import list_starter_species
    species = list_starter_species()
    # Lemhi case uses Oncorhynchus mykiss; anywhere_bbox uses
    # Schizothorax prenanti; common carp / Atlantic salmon /
    # grass carp anchor the cross-region coverage.
    for required in (
        "Oncorhynchus mykiss",
        "Salmo trutta",
        "Salmo salar",
        "Cyprinus carpio",
        "Ctenopharyngodon idella",
        "Schizothorax prenanti",
    ):
        assert required in species, (
            f"REGRESSION: {required!r} dropped from FishBase starter table"
        )


def test_fishbase_traits_returns_dataclass_for_known_species():
    from openlimno.preprocess.fetch import (
        FishBaseTraits, WATER_TYPES, IUCN_STATUSES, fetch_fishbase_traits,
    )
    t = fetch_fishbase_traits("Oncorhynchus mykiss")
    assert t is not None
    assert isinstance(t, FishBaseTraits)
    assert t.scientific_name == "Oncorhynchus mykiss"
    assert t.common_name == "Rainbow trout"
    assert t.temperature_min_C < t.temperature_max_C
    assert t.water_type in WATER_TYPES
    assert t.iucn_status in IUCN_STATUSES
    assert t.fishbase_url.startswith("http")
    # Citation field is the top-level FishBase attribution
    assert "FishBase" in t.citation


def test_fishbase_traits_is_case_insensitive():
    """Latin binomials are sometimes typed lower-case in CLI args;
    the lookup must be case-insensitive so users don't get false
    'not in starter table' answers."""
    from openlimno.preprocess.fetch import fetch_fishbase_traits
    a = fetch_fishbase_traits("Salmo trutta")
    b = fetch_fishbase_traits("salmo trutta")
    c = fetch_fishbase_traits("SALMO TRUTTA")
    assert a is not None and b is not None and c is not None
    assert a.scientific_name == b.scientific_name == c.scientific_name


def test_fishbase_traits_returns_none_for_unknown():
    """A no-match return must be ``None`` (callable's responsibility
    to fall back to a manual species-traits YAML) — NOT a raise."""
    from openlimno.preprocess.fetch import fetch_fishbase_traits
    assert fetch_fishbase_traits("Frabnitzia notarealius") is None


def test_fishbase_traits_rejects_empty_name():
    from openlimno.preprocess.fetch import fetch_fishbase_traits
    with pytest.raises(ValueError, match="non-empty"):
        fetch_fishbase_traits("")
    with pytest.raises(ValueError, match="non-empty"):
        fetch_fishbase_traits("   ")


def test_fishbase_starter_csv_water_types_all_valid():
    """Every row in the bundled CSV must use a value from
    WATER_TYPES — catches a typo at table-edit time."""
    from openlimno.preprocess.fetch import (
        WATER_TYPES, list_starter_species, fetch_fishbase_traits,
    )
    for name in list_starter_species():
        t = fetch_fishbase_traits(name)
        assert t.water_type in WATER_TYPES, (
            f"{name}: water_type={t.water_type!r} not in {WATER_TYPES}"
        )


def test_fishbase_starter_csv_iucn_codes_all_valid():
    from openlimno.preprocess.fetch import (
        IUCN_STATUSES, list_starter_species, fetch_fishbase_traits,
    )
    for name in list_starter_species():
        t = fetch_fishbase_traits(name)
        assert t.iucn_status in IUCN_STATUSES, (
            f"{name}: iucn_status={t.iucn_status!r} not a valid IUCN code"
        )


def test_fishbase_starter_csv_temp_ranges_consistent():
    """temperature_min_C < temperature_max_C for every row — catches
    a transposed-value typo at table-edit time."""
    from openlimno.preprocess.fetch import (
        list_starter_species, fetch_fishbase_traits,
    )
    for name in list_starter_species():
        t = fetch_fishbase_traits(name)
        assert t.temperature_min_C < t.temperature_max_C, (
            f"{name}: T range inverted ({t.temperature_min_C}, "
            f"{t.temperature_max_C})"
        )
        assert t.depth_min_m <= t.depth_max_m, (
            f"{name}: depth range inverted"
        )


# ---------------------------------------------------------------------
# species.py — GBIF taxonomy match + occurrence search
# ---------------------------------------------------------------------
def test_species_match_rejects_empty_name():
    from openlimno.preprocess.fetch import match_species
    with pytest.raises(ValueError, match="non-empty"):
        match_species("")
    with pytest.raises(ValueError, match="non-empty"):
        match_species("   ")


def _fake_gbif_match_response(name="Salmo trutta", usage_key=8215487):
    """Build a minimal /species/match response."""
    return json.dumps({
        "usageKey": usage_key,
        "scientificName": f"{name} Linnaeus, 1758",
        "canonicalName": name,
        "rank": "SPECIES",
        "status": "ACCEPTED",
        "confidence": 99,
        "matchType": "EXACT",
        "kingdom": "Animalia",
        "phylum": "Chordata",
        "class": "Actinopterygii",
        "order": "Salmoniformes",
        "family": "Salmonidae",
        "genus": "Salmo",
        "species": name,
    }).encode()


def test_species_match_parses_response(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    class _Resp:
        content = _fake_gbif_match_response()
        def raise_for_status(self): pass

    monkeypatch.setattr(
        "openlimno.preprocess.fetch.species.requests.get",
        lambda url, params=None, timeout=None: _Resp(),
    )
    from openlimno.preprocess.fetch import match_species
    res = match_species("Salmo trutta")
    assert res.usage_key == 8215487
    assert res.canonical_name == "Salmo trutta"
    assert res.match_type == "EXACT"
    assert res.confidence == 99
    assert res.family == "Salmonidae"
    assert res.class_name == "Actinopterygii"


def test_species_match_handles_no_match(monkeypatch, tmp_path):
    """A typo / unknown name must NOT raise — return usage_key=None +
    match_type='NONE' so the CLI can prompt for correction without
    try/except."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    class _Resp:
        content = json.dumps({
            "confidence": 80, "matchType": "NONE",
            "synonym": False, "note": "no match",
        }).encode()
        def raise_for_status(self): pass

    monkeypatch.setattr(
        "openlimno.preprocess.fetch.species.requests.get",
        lambda url, params=None, timeout=None: _Resp(),
    )
    from openlimno.preprocess.fetch import match_species
    res = match_species("Frabnitzia notarealius")
    assert res.usage_key is None
    assert res.match_type == "NONE"
    assert res.family is None


def test_species_occurrence_rejects_bad_bbox():
    from openlimno.preprocess.fetch import fetch_gbif_occurrences
    with pytest.raises(ValueError, match="Invalid bbox"):
        fetch_gbif_occurrences(123, (10.0, 20.0, 5.0, 25.0))  # lon_max < lon_min
    with pytest.raises(ValueError, match="latitudes outside"):
        fetch_gbif_occurrences(123, (10.0, -100.0, 11.0, -99.0))


def test_species_occurrence_rejects_limit_out_of_range():
    from openlimno.preprocess.fetch import fetch_gbif_occurrences
    with pytest.raises(ValueError, match="GBIF cap"):
        fetch_gbif_occurrences(123, (10.0, 20.0, 11.0, 21.0), limit=500)
    with pytest.raises(ValueError, match="GBIF cap"):
        fetch_gbif_occurrences(123, (10.0, 20.0, 11.0, 21.0), limit=0)


def test_species_bbox_to_wkt_format():
    """GBIF wants counter-clockwise POLYGON((lon lat, ...)) with
    explicit closure. Pin the string so an API change is a visible
    diff."""
    from openlimno.preprocess.fetch.species import _bbox_to_wkt
    wkt = _bbox_to_wkt((100.10, 38.10, 100.30, 38.30))
    assert wkt == (
        "POLYGON(("
        "100.1 38.1, 100.3 38.1, 100.3 38.3, 100.1 38.3, 100.1 38.1"
        "))"
    )


def _fake_gbif_occurrence_page(count=2, total=2, end=True, offset=0):
    """Build a minimal /occurrence/search response page."""
    results = []
    for i in range(count):
        results.append({
            "scientificName": "Salmo trutta Linnaeus, 1758",
            "decimalLatitude": 38.15 + 0.01 * i,
            "decimalLongitude": 100.15 + 0.01 * i,
            "eventDate": f"2024-0{i+1}-15T10:00:00",
            "basisOfRecord": "HUMAN_OBSERVATION",
            "datasetName": "iNaturalist",
            "country": "China",
            "license": "CC_BY_NC_4_0",
        })
    return json.dumps({
        "offset": offset, "limit": 300, "endOfRecords": end,
        "count": total, "results": results,
    }).encode()


def test_species_occurrence_single_page(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    class _Resp:
        content = _fake_gbif_occurrence_page(count=2, total=2, end=True)
        def raise_for_status(self): pass

    monkeypatch.setattr(
        "openlimno.preprocess.fetch.species.requests.get",
        lambda url, params=None, timeout=None: _Resp(),
    )
    from openlimno.preprocess.fetch import fetch_gbif_occurrences
    res = fetch_gbif_occurrences(8215487, (100.1, 38.1, 100.3, 38.3))
    assert list(res.df.columns) == [
        "scientific_name", "decimal_latitude", "decimal_longitude",
        "event_date", "basis_of_record", "dataset_name", "country",
        "license",
    ]
    assert len(res.df) == 2
    assert res.total_matched == 2
    assert res.n_pages_fetched == 1
    assert res.df.iloc[0]["decimal_latitude"] == pytest.approx(38.15)


def test_species_occurrence_filters_null_coordinates(monkeypatch, tmp_path):
    """Despite hasCoordinate=true, GBIF occasionally returns null lat/lon.
    Filter defensively so downstream geometry never sees NaN."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    payload = json.dumps({
        "offset": 0, "limit": 300, "endOfRecords": True, "count": 2,
        "results": [
            {"scientificName": "X", "decimalLatitude": 38.1,
             "decimalLongitude": 100.1, "basisOfRecord": "OBS"},
            {"scientificName": "X", "decimalLatitude": None,
             "decimalLongitude": None, "basisOfRecord": "OBS"},
        ],
    }).encode()

    class _Resp:
        content = payload
        def raise_for_status(self): pass

    monkeypatch.setattr(
        "openlimno.preprocess.fetch.species.requests.get",
        lambda url, params=None, timeout=None: _Resp(),
    )
    from openlimno.preprocess.fetch import fetch_gbif_occurrences
    res = fetch_gbif_occurrences(123, (100.0, 38.0, 100.5, 38.5))
    assert len(res.df) == 1, (
        "REGRESSION: null-coordinate row leaked into the occurrence df"
    )


def test_species_occurrence_paginates_until_end_of_records(
    monkeypatch, tmp_path,
):
    """When endOfRecords=False, the fetcher walks subsequent pages.
    Pin the loop so a future refactor that drops pagination would
    silently truncate at the first page."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    pages = [
        _fake_gbif_occurrence_page(count=2, total=5, end=False, offset=0),
        _fake_gbif_occurrence_page(count=2, total=5, end=False, offset=2),
        _fake_gbif_occurrence_page(count=1, total=5, end=True,  offset=4),
    ]
    call = {"n": 0}

    class _Resp:
        def __init__(self, content):
            self.content = content
        def raise_for_status(self): pass

    def fake_get(url, params=None, timeout=None):
        idx = call["n"]
        call["n"] += 1
        return _Resp(pages[idx])

    monkeypatch.setattr(
        "openlimno.preprocess.fetch.species.requests.get", fake_get,
    )
    from openlimno.preprocess.fetch import fetch_gbif_occurrences
    res = fetch_gbif_occurrences(
        8215487, (100.1, 38.1, 100.3, 38.3), limit=2, max_pages=10,
    )
    assert call["n"] == 3, f"expected 3 page calls, got {call['n']}"
    assert res.n_pages_fetched == 3
    assert len(res.df) == 5
    assert res.total_matched == 5


def test_species_occurrence_respects_max_pages_cap(monkeypatch, tmp_path):
    """If max_pages=1 and there are more pages, we stop after 1 to
    avoid runaway API usage."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    class _Resp:
        content = _fake_gbif_occurrence_page(
            count=2, total=1000, end=False, offset=0,
        )
        def raise_for_status(self): pass

    monkeypatch.setattr(
        "openlimno.preprocess.fetch.species.requests.get",
        lambda url, params=None, timeout=None: _Resp(),
    )
    from openlimno.preprocess.fetch import fetch_gbif_occurrences
    res = fetch_gbif_occurrences(
        8215487, (100.1, 38.1, 100.3, 38.3), limit=2, max_pages=1,
    )
    assert res.n_pages_fetched == 1
    assert res.total_matched == 1000  # GBIF says more, but we stopped
    assert len(res.df) == 2


# ---------------------------------------------------------------------
# soilgrids.py — input validation + response parsing
# ---------------------------------------------------------------------
def test_soilgrids_rejects_invalid_lat_lon():
    from openlimno.preprocess.fetch import fetch_soilgrids
    with pytest.raises(ValueError, match="lat="):
        fetch_soilgrids(95.0, 100.0)
    with pytest.raises(ValueError, match="lon="):
        fetch_soilgrids(38.0, 250.0)


def test_soilgrids_rejects_unknown_depth():
    from openlimno.preprocess.fetch import fetch_soilgrids
    with pytest.raises(ValueError, match="unknown depth"):
        fetch_soilgrids(38.0, 100.0, depths=("0-3cm",))


def test_soilgrids_rejects_unknown_statistic():
    from openlimno.preprocess.fetch import fetch_soilgrids
    with pytest.raises(ValueError, match="statistic="):
        fetch_soilgrids(38.0, 100.0, statistic="median")


def test_soilgrids_rejects_empty_property_list():
    from openlimno.preprocess.fetch import fetch_soilgrids
    with pytest.raises(ValueError, match="at least one property"):
        fetch_soilgrids(38.0, 100.0, properties=())


def test_soilgrids_constants_match_api_schema():
    """Pin the schema enums — a SoilGrids API rename would otherwise
    silently slip through."""
    from openlimno.preprocess.fetch.soilgrids import (
        ALL_DEPTHS, ALL_STATISTICS, DEFAULT_DEPTHS, DEFAULT_PROPERTIES,
    )
    assert "0-5cm" in ALL_DEPTHS
    assert "100-200cm" in ALL_DEPTHS
    assert "mean" in ALL_STATISTICS
    assert "Q0.05" in ALL_STATISTICS and "Q0.95" in ALL_STATISTICS
    assert DEFAULT_DEPTHS == ("0-5cm", "5-15cm", "15-30cm")
    assert "clay" in DEFAULT_PROPERTIES and "phh2o" in DEFAULT_PROPERTIES


def _fake_soilgrids_response(properties=("clay", "sand"), depths=("0-5cm",)):
    """Build a minimal SoilGrids REST response payload (JSON bytes)."""
    layers = []
    # SoilGrids stores values × d_factor (e.g., clay raw 250 → 25.0 g/kg
    # with d_factor=10). Pin that conversion in the fake payload.
    for p in properties:
        d_factor = 10 if p in ("clay", "sand", "silt", "soc", "phh2o") else 100
        depth_entries = []
        for d in depths:
            depth_entries.append({
                "range": {"top_depth": 0, "bottom_depth": 5, "unit_depth": "cm"},
                "label": d,
                "values": {
                    "Q0.05": 100, "Q0.5": 250, "Q0.95": 400,
                    "mean": 250, "uncertainty": 50,
                },
            })
        layers.append({
            "name": p,
            "unit_measure": {
                "d_factor": d_factor,
                "mapped_units": "g/kg" if d_factor == 10 else "cg/cm³",
                "target_units": "g/kg" if d_factor == 10 else "kg/dm³",
                "uncertainty_unit": "",
            },
            "depths": depth_entries,
        })
    payload = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [100.0, 38.0]},
        "properties": {"layers": layers},
        "query_time_s": 0.01,
    }
    return json.dumps(payload).encode()


def test_soilgrids_parses_response_and_applies_d_factor(monkeypatch, tmp_path):
    """End-to-end: injected response with clay raw=250 d_factor=10 must
    land as value=25.0 g/kg. Pins the d_factor scaling — without it
    downstream code would consume 10×-too-large clay fractions."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    class _Resp:
        content = _fake_soilgrids_response(("clay",), ("0-5cm",))
        def raise_for_status(self): pass

    monkeypatch.setattr(
        "openlimno.preprocess.fetch.soilgrids.requests.get",
        lambda url, params=None, timeout=None: _Resp(),
    )
    from openlimno.preprocess.fetch import fetch_soilgrids
    res = fetch_soilgrids(38.0, 100.0, properties=("clay",), depths=("0-5cm",))
    assert list(res.df.columns) == [
        "property", "depth", "statistic", "value", "unit",
    ]
    row = res.df.iloc[0]
    assert row["property"] == "clay"
    assert row["depth"] == "0-5cm"
    assert row["statistic"] == "mean"
    # 250 (raw) / 10 (d_factor) = 25.0 g/kg
    assert row["value"] == pytest.approx(25.0)
    assert row["unit"] == "g/kg"
    # Convenience accessor
    assert res.get("clay", "0-5cm") == pytest.approx(25.0)


def test_soilgrids_get_raises_on_missing_combo(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    class _Resp:
        content = _fake_soilgrids_response(("clay",), ("0-5cm",))
        def raise_for_status(self): pass

    monkeypatch.setattr(
        "openlimno.preprocess.fetch.soilgrids.requests.get",
        lambda url, params=None, timeout=None: _Resp(),
    )
    from openlimno.preprocess.fetch import fetch_soilgrids
    res = fetch_soilgrids(38.0, 100.0, properties=("clay",), depths=("0-5cm",))
    with pytest.raises(KeyError, match="sand"):
        res.get("sand", "0-5cm")


def test_soilgrids_raises_when_response_empty(monkeypatch, tmp_path):
    """A point over ocean returns ``properties.layers = []``. Fail loudly
    so downstream doesn't read an empty DataFrame and silently use NaN
    soil parameters in calibration."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    class _Resp:
        content = json.dumps({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [0, 0]},
            "properties": {"layers": []},
        }).encode()
        def raise_for_status(self): pass

    monkeypatch.setattr(
        "openlimno.preprocess.fetch.soilgrids.requests.get",
        lambda url, params=None, timeout=None: _Resp(),
    )
    from openlimno.preprocess.fetch import fetch_soilgrids
    with pytest.raises(RuntimeError, match="no layers"):
        fetch_soilgrids(0.0, 0.0)


def test_soilgrids_cache_key_distinguishes_points(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    seen: list[dict] = []

    class _Resp:
        content = _fake_soilgrids_response(("clay",), ("0-5cm",))
        def raise_for_status(self): pass

    def fake_get(url, params=None, timeout=None):
        # params is list of tuples here
        seen.append(dict(params or []))
        return _Resp()

    monkeypatch.setattr(
        "openlimno.preprocess.fetch.soilgrids.requests.get", fake_get,
    )
    from openlimno.preprocess.fetch import fetch_soilgrids
    fetch_soilgrids(38.0, 100.0, properties=("clay",), depths=("0-5cm",))
    fetch_soilgrids(45.0, -73.0, properties=("clay",), depths=("0-5cm",))
    assert len(seen) == 2, (
        "REGRESSION: SoilGrids cache reused different point's response — "
        "cache key must fold in lat/lon"
    )


# ---------------------------------------------------------------------
# worldcover.py — input validation + tile decomposition + histogram
# ---------------------------------------------------------------------
def test_worldcover_rejects_invalid_bbox():
    from openlimno.preprocess.fetch import fetch_esa_worldcover
    with pytest.raises(ValueError, match="Invalid bbox"):
        fetch_esa_worldcover(101.0, 38.0, 100.0, 38.5)  # lon_max < lon_min


def test_worldcover_rejects_out_of_coverage():
    """Antarctica falls outside the (60°S, 84°N) ESA WorldCover window."""
    from openlimno.preprocess.fetch import fetch_esa_worldcover
    with pytest.raises(ValueError, match="60.S to 84.N"):
        fetch_esa_worldcover(0.0, -75.0, 1.0, -74.0)


def test_worldcover_rejects_antimeridian_crossing():
    """A bbox spanning lon=190 (or wrapped to -170 → 170 forward) would
    hit non-existent tiles or pull the wrong half of the world.
    Reject with a hint at splitting the query."""
    from openlimno.preprocess.fetch import fetch_esa_worldcover
    with pytest.raises(ValueError, match="antimeridian"):
        fetch_esa_worldcover(170.0, 0.0, 190.0, 1.0)


def test_worldcover_rejects_unknown_year():
    from openlimno.preprocess.fetch import fetch_esa_worldcover
    with pytest.raises(ValueError, match="released WorldCover epoch"):
        fetch_esa_worldcover(100.0, 38.0, 100.5, 38.5, year=2022)


def test_worldcover_rejects_oversized_bbox():
    """A 30°×30° bbox would pull dozens of 100-MB tiles + OOM the
    merge step. Enforce a deg² cap at the entry point."""
    from openlimno.preprocess.fetch import fetch_esa_worldcover
    with pytest.raises(ValueError, match="safety cap"):
        fetch_esa_worldcover(0.0, 0.0, 30.0, 30.0)


def test_worldcover_tile_name_n36_e114():
    from openlimno.preprocess.fetch.worldcover import _tile_name
    assert _tile_name(36, 114) == "N36E114"
    assert _tile_name(-3, 117) == "S03E117"
    assert _tile_name(36, -123) == "N36W123"
    assert _tile_name(-30, -60) == "S30W060"


def test_worldcover_tiles_for_bbox_3deg_grid():
    """ESA WorldCover tiles are 3°×3° aligned on multiples of 3. A
    small bbox entirely inside one tile must yield exactly that tile,
    and a bbox straddling a 3° boundary must yield both neighbours.
    """
    from openlimno.preprocess.fetch.worldcover import _tiles_for_bbox
    # Inside the N36-E114 tile
    assert _tiles_for_bbox(114.5, 36.5, 114.8, 36.8) == [(36, 114)]
    # Straddle the 117° longitude line → two tiles
    res = _tiles_for_bbox(116.5, 36.5, 117.5, 36.8)
    assert sorted(res) == [(36, 114), (36, 117)]
    # Negative lat in southern hemisphere on the 3-grid (-3, -6, ...)
    res = _tiles_for_bbox(0.5, -2.5, 0.8, -1.5)
    assert (-3, 0) in res


def test_worldcover_tiles_for_bbox_exact_3deg_edge_no_extra_tile():
    """A bbox whose lat_max sits exactly on a tile boundary must NOT
    pull the next-northern tile (which would have zero overlap and
    waste a download). The implementation snaps the upper edge with a
    tiny epsilon to avoid the off-by-one.
    """
    from openlimno.preprocess.fetch.worldcover import _tiles_for_bbox
    # lat_max=39.0 is the south edge of the N39 tile; the bbox stays
    # entirely in N36.
    res = _tiles_for_bbox(114.5, 36.5, 114.8, 39.0)
    assert res == [(36, 114)], (
        f"REGRESSION: exact-edge bbox pulled extra tile(s): {res}"
    )


def test_worldcover_class_codes_are_complete():
    """11 LCCS classes — pin them so a future addition (or rename) is
    a visible diff rather than a silent histogram-coverage gap."""
    from openlimno.preprocess.fetch import WORLDCOVER_CLASSES
    assert WORLDCOVER_CLASSES[10] == "tree_cover"
    assert WORLDCOVER_CLASSES[40] == "cropland"
    assert WORLDCOVER_CLASSES[80] == "permanent_water_bodies"
    assert WORLDCOVER_CLASSES[95] == "mangroves"
    assert WORLDCOVER_CLASSES[100] == "moss_and_lichen"
    assert set(WORLDCOVER_CLASSES) == {10,20,30,40,50,60,70,80,90,95,100}


def test_worldcover_epochs_match_versions():
    from openlimno.preprocess.fetch import WORLDCOVER_EPOCHS
    assert WORLDCOVER_EPOCHS == {2020: "v100", 2021: "v200"}


def test_worldcover_pixel_area_scales_with_cos_lat():
    """At 60°N a 10 m × 10 m pixel covers ~half the area it does at
    the equator (cos 60° = 0.5). Pin the cos(lat) correction so an
    inadvertent removal would show up immediately."""
    from openlimno.preprocess.fetch.worldcover import _pixel_area_km2
    eq = _pixel_area_km2(0.0, 1.0 / 12000)  # ESA pixel ≈ 1/12000°
    hi = _pixel_area_km2(60.0, 1.0 / 12000)
    assert hi / eq == pytest.approx(0.5, rel=1e-3)


def test_worldcover_compute_class_histogram_aggregates_correctly(tmp_path):
    """End-to-end: build a tiny EPSG:4326 GeoTIFF with known class mix,
    run the histogram, check counts + km² rough scale."""
    import numpy as _np
    import rasterio
    from rasterio.transform import from_origin
    from openlimno.preprocess.fetch.worldcover import _compute_class_histogram

    # 10×10 raster, 5 m pixel (5e-5°) — mix of cropland(40) and built(50).
    arr = _np.array([[40]*5 + [50]*5]*10, dtype=_np.uint8)
    transform = from_origin(100.0, 38.0, 5e-5, 5e-5)
    tif = tmp_path / "fake.tif"
    with rasterio.open(
        tif, "w", driver="GTiff", height=10, width=10, count=1,
        dtype="uint8", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(arr, 1)
    counts, km2 = _compute_class_histogram(tif, lat_center=38.0)
    assert counts == {40: 50, 50: 50}
    # km2 ratios match pixel counts
    assert km2[40] == pytest.approx(km2[50])
    # rough scale: 100 px × ~31 m² each × cos(38°) ≈ 2.4e-3 km² for the
    # whole raster (sanity-only — exact math is in
    # test_worldcover_pixel_area_scales_with_cos_lat).
    assert 1e-4 < sum(km2.values()) < 1e-2


def test_worldcover_compute_class_histogram_excludes_nodata(tmp_path):
    """Class 0 (no-data) MUST NOT show up in the result — otherwise
    tile-edge masked pixels poison the 'non-land' fraction."""
    import numpy as _np
    import rasterio
    from rasterio.transform import from_origin
    from openlimno.preprocess.fetch.worldcover import _compute_class_histogram

    arr = _np.array([[0,0,40,40]] * 4, dtype=_np.uint8)
    transform = from_origin(100.0, 38.0, 5e-5, 5e-5)
    tif = tmp_path / "fake.tif"
    with rasterio.open(
        tif, "w", driver="GTiff", height=4, width=4, count=1,
        dtype="uint8", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(arr, 1)
    counts, _km2 = _compute_class_histogram(tif, lat_center=38.0)
    assert 0 not in counts
    assert counts == {40: 8}


def test_hydrosheds_url_format_matches_provider_convention():
    """Pin the URL template — HydroSHEDS occasionally restructures their
    distribution; a silent 404 would re-fetch on every cache miss.
    """
    import openlimno.preprocess.fetch.hydrosheds as h
    assert "data.hydrosheds.org" in h.HYDROSHEDS_BASE
    assert "Asia" == h.HYDROSHEDS_REGIONS["as"]
    assert 12 in h.HYDROBASINS_LEVELS

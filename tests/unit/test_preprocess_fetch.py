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

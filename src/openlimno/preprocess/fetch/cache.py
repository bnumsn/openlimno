"""Filesystem cache for online data fetches.

Both NWIS and DEM fetchers route through ``cached_fetch`` so repeated
calls in the same session — or across sessions — don't re-hit upstream
servers. Cache lives under ``$XDG_CACHE_HOME/openlimno/`` (typically
``~/.cache/openlimno/``); per-fetcher subdirs keep the layout tidy.

Cache keys are SHA-256 of the canonical request (URL + method + sorted
params). Hits never expire automatically — water-data archives are
historically stable, and stale-cache symptoms are detectable via
``provenance.json`` (which records the fetch_time at *original* fetch).
Users can wipe the cache dir to force refresh.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


def cache_dir(subdir: str = "") -> Path:
    """Resolve $XDG_CACHE_HOME/openlimno/<subdir>, creating it on demand."""
    xdg = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    root = Path(xdg) / "openlimno"
    if subdir:
        root = root / subdir
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class CacheEntry:
    """Result of a cached fetch.

    Attributes:
        path: location of the cached payload on disk.
        cache_hit: True if served from existing cache, False if just fetched.
        source_url: URL that was (or would have been) requested.
        fetch_time: ISO-8601 timestamp recorded when payload was originally
            written. For cache hits this is the ORIGINAL fetch time, not
            the time of the current call — that's what makes it useful
            for provenance.
        sha256: SHA-256 of the payload bytes (for downstream integrity
            checks + reproducibility).
    """

    path: Path
    cache_hit: bool
    source_url: str
    fetch_time: str
    sha256: str


def _request_key(url: str, params: dict | None = None, method: str = "GET") -> str:
    canonical = json.dumps(
        {"u": url, "p": dict(sorted((params or {}).items())), "m": method.upper()},
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def cached_fetch(
    *,
    subdir: str,
    url: str,
    params: dict | None = None,
    suffix: str = ".bin",
    fetch_fn: Callable[[], bytes],
) -> CacheEntry:
    """Fetch + cache binary payload.

    Args:
        subdir: per-fetcher subdir under the openlimno cache root.
        url: canonical source URL (used both as cache key + provenance).
        params: query params (folded into the cache key).
        suffix: file extension for the cached payload (e.g., ``".csv"``,
            ``".tif"``); affects the disk filename only, not behaviour.
        fetch_fn: zero-arg callable returning the payload bytes. Called
            only on cache miss.
    """
    key = _request_key(url, params)
    dirpath = cache_dir(subdir)
    payload_path = dirpath / f"{key}{suffix}"
    meta_path = dirpath / f"{key}.meta.json"

    if payload_path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        return CacheEntry(
            path=payload_path,
            cache_hit=True,
            source_url=meta["source_url"],
            fetch_time=meta["fetch_time"],
            sha256=meta["sha256"],
        )

    payload = fetch_fn()
    payload_path.write_bytes(payload)
    sha = hashlib.sha256(payload).hexdigest()
    fetch_time = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    meta_path.write_text(
        json.dumps(
            {
                "source_url": url,
                "params": params or {},
                "fetch_time": fetch_time,
                "sha256": sha,
                "size_bytes": len(payload),
            },
            indent=2,
        )
    )
    return CacheEntry(
        path=payload_path,
        cache_hit=False,
        source_url=url,
        fetch_time=fetch_time,
        sha256=sha,
    )

"""GBIF species + occurrence fetcher (v0.3.6 P0).

GBIF (Global Biodiversity Information Facility) is the open backbone
of biodiversity-occurrence aggregation: ~2.5 billion records from
2 000+ institutions, free + no auth via a REST API. We expose:

* **Species taxonomy match** — given a scientific name, resolve the
  GBIF backbone taxon (usageKey + family / order / kingdom). Lets us
  validate that a case-config species name is recognised + canonical.
* **Occurrence search** — given a usageKey + bbox, pull
  georeferenced observations (lat, lon, event date, dataset, basis
  of record). Lets us cross-check that a target species is actually
  recorded in the case's geographic area before running habitat
  models calibrated for it.

Out of scope: GBIF download API (asynchronous batch tickets) — we
use the synchronous /occurrence/search endpoint which caps at 100 000
records per query and ~300/page, more than enough for reach-scale
verification. FishBase is intentionally NOT integrated here because
its only fully-open distribution is via rfishbase's R dataset dumps;
that's tracked as a v0.4 P2 follow-up.

API docs:
    https://techdocs.gbif.org/en/openapi/v1/species
    https://techdocs.gbif.org/en/openapi/v1/occurrence

Citation:
    GBIF: The Global Biodiversity Information Facility (2024).
    What is GBIF? Available from https://www.gbif.org/what-is-gbif —
    CC0 for occurrence records (per-dataset licence varies; see each
    occurrence's ``license`` field for downstream re-use).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import requests

from openlimno.preprocess.fetch.cache import CacheEntry, cached_fetch

GBIF_SPECIES_MATCH = "https://api.gbif.org/v1/species/match"
GBIF_OCCURRENCE_SEARCH = "https://api.gbif.org/v1/occurrence/search"

GBIF_CITATION = (
    "GBIF.org (2024). GBIF Occurrence API. "
    "https://www.gbif.org/. Backbone taxonomy: "
    "https://doi.org/10.15468/39omei. Individual records carry per-"
    "dataset licences — consult each row's ``license`` field for "
    "downstream re-use."
)


@dataclass
class SpeciesMatchResult:
    """Outcome of a GBIF species name match.

    Attributes:
        scientific_name: input name (echoed for provenance).
        usage_key: GBIF backbone taxon ID — pass to occurrence fetches.
        canonical_name: the cleaned-up species name GBIF resolved.
        rank: ``"SPECIES"`` / ``"GENUS"`` / ``"SUBSPECIES"`` etc.
        match_type: ``"EXACT"`` / ``"FUZZY"`` / ``"HIGHERRANK"`` / ``"NONE"``.
        confidence: GBIF's 0-100 confidence score.
        kingdom, phylum, class_name, order, family, genus, species:
            full taxonomic path returned by GBIF (None if unresolved).
        cache: provenance trail entry.
        citation: APA-style citation string.
    """

    scientific_name: str
    usage_key: int | None
    canonical_name: str | None
    rank: str | None
    match_type: str | None
    confidence: int | None
    kingdom: str | None = None
    phylum: str | None = None
    class_name: str | None = None
    order: str | None = None
    family: str | None = None
    genus: str | None = None
    species: str | None = None
    cache: CacheEntry | None = None
    citation: str = GBIF_CITATION


@dataclass
class SpeciesOccurrencesResult:
    """Outcome of a GBIF occurrence search.

    Attributes:
        df: DataFrame with columns ``[scientific_name, decimal_latitude,
            decimal_longitude, event_date, basis_of_record, dataset_name,
            country, license]``. Rows missing coordinates are filtered
            out so downstream geometry consumers never trip.
        usage_key: GBIF usageKey queried.
        bbox: ``(lon_min, lat_min, lon_max, lat_max)`` queried.
        total_matched: GBIF's reported total count across all pages
            (may exceed ``len(df)`` if ``limit`` truncated).
        n_pages_fetched: how many ``limit``-sized pages we walked.
        cache: provenance trail entry (one CacheEntry per page).
        citation: APA-style citation string.
    """

    df: pd.DataFrame
    usage_key: int
    bbox: tuple[float, float, float, float]
    total_matched: int
    n_pages_fetched: int
    cache: list[CacheEntry] = field(default_factory=list)
    citation: str = GBIF_CITATION


def match_species(scientific_name: str) -> SpeciesMatchResult:
    """Resolve a scientific name to the GBIF backbone taxon.

    Args:
        scientific_name: Latin binomial (e.g., ``"Salmo trutta"``). Any
            authorship suffix is allowed; GBIF will strip it.

    Returns:
        :class:`SpeciesMatchResult` — even on no-match returns an
        object with ``usage_key=None`` + ``match_type="NONE"`` so
        callers can branch without try/except.
    """
    if not scientific_name or not scientific_name.strip():
        raise ValueError("scientific_name must be non-empty")
    name = scientific_name.strip()
    params = {"name": name}

    def _do_fetch() -> bytes:
        resp = requests.get(GBIF_SPECIES_MATCH, params=params, timeout=30)
        resp.raise_for_status()
        return resp.content

    cache = cached_fetch(
        subdir="gbif/species_match", url=GBIF_SPECIES_MATCH,
        params=params, suffix=".json", fetch_fn=_do_fetch,
    )
    payload = json.loads(cache.path.read_text())
    return SpeciesMatchResult(
        scientific_name=name,
        usage_key=payload.get("usageKey"),
        canonical_name=payload.get("canonicalName"),
        rank=payload.get("rank"),
        match_type=payload.get("matchType"),
        confidence=payload.get("confidence"),
        kingdom=payload.get("kingdom"),
        phylum=payload.get("phylum"),
        class_name=payload.get("class"),
        order=payload.get("order"),
        family=payload.get("family"),
        genus=payload.get("genus"),
        species=payload.get("species"),
        cache=cache,
    )


def _bbox_to_wkt(bbox: tuple[float, float, float, float]) -> str:
    """Convert (lon_min, lat_min, lon_max, lat_max) to WKT POLYGON in
    counter-clockwise order, GBIF's expected geometry format.
    """
    lo_min, la_min, lo_max, la_max = bbox
    return (
        f"POLYGON(("
        f"{lo_min} {la_min}, {lo_max} {la_min}, "
        f"{lo_max} {la_max}, {lo_min} {la_max}, "
        f"{lo_min} {la_min}))"
    )


def fetch_gbif_occurrences(
    usage_key: int,
    bbox: tuple[float, float, float, float],
    *,
    limit: int = 300,
    max_pages: int = 10,
) -> SpeciesOccurrencesResult:
    """Fetch georeferenced GBIF occurrences for a taxon inside a bbox.

    Args:
        usage_key: GBIF backbone usageKey (from :func:`match_species`).
        bbox: ``(lon_min, lat_min, lon_max, lat_max)`` in EPSG:4326.
        limit: page size, ≤300 (GBIF's per-page cap). Default 300.
        max_pages: stop walking after this many pages even if
            ``endOfRecords=false``. Default 10 → up to 3000 records,
            enough for case-scale verification without abusing the API.

    Returns:
        :class:`SpeciesOccurrencesResult`.
    """
    if limit <= 0 or limit > 300:
        raise ValueError(f"limit={limit} must be in (0, 300] (GBIF cap)")
    if max_pages <= 0:
        raise ValueError(f"max_pages={max_pages} must be positive")
    lo_min, la_min, lo_max, la_max = bbox
    if lo_max <= lo_min or la_max <= la_min:
        raise ValueError(
            f"Invalid bbox: ({lo_min}, {la_min}, {lo_max}, {la_max}). "
            f"Need lon_max > lon_min and lat_max > lat_min."
        )
    if not (la_min >= -90 and la_max <= 90):
        raise ValueError(f"latitudes outside [-90, 90]: {la_min}, {la_max}")
    if not (lo_min >= -180 and lo_max <= 180):
        raise ValueError(
            f"longitudes outside [-180, 180]: {lo_min}, {lo_max}"
        )

    wkt = _bbox_to_wkt(bbox)
    all_rows: list[dict] = []
    all_cache: list[CacheEntry] = []
    total_matched = 0
    n_pages = 0
    offset = 0
    end_of_records = False

    while n_pages < max_pages and not end_of_records:
        params = {
            "taxonKey": usage_key,
            "geometry": wkt,
            "hasCoordinate": "true",
            "hasGeospatialIssue": "false",
            "limit": limit,
            "offset": offset,
        }
        # offset becomes part of the cache key — each page is its own
        # cache entry so a re-run is page-by-page reproducible.
        def _do_fetch(p: dict[str, Any] = params) -> bytes:
            resp = requests.get(
                GBIF_OCCURRENCE_SEARCH, params=p, timeout=60,
            )
            resp.raise_for_status()
            return resp.content

        cache = cached_fetch(
            subdir="gbif/occurrence",
            url=GBIF_OCCURRENCE_SEARCH,
            params=params,
            suffix=".json",
            fetch_fn=_do_fetch,
        )
        all_cache.append(cache)
        payload = json.loads(cache.path.read_text())

        if n_pages == 0:
            total_matched = int(payload.get("count", 0))
        results = payload.get("results", []) or []
        for r in results:
            lat = r.get("decimalLatitude")
            lon = r.get("decimalLongitude")
            if lat is None or lon is None:
                continue  # despite hasCoordinate=true, defensive
            all_rows.append({
                "scientific_name": r.get("scientificName"),
                "decimal_latitude": lat,
                "decimal_longitude": lon,
                "event_date": r.get("eventDate"),
                "basis_of_record": r.get("basisOfRecord"),
                "dataset_name": r.get("datasetName"),
                "country": r.get("country"),
                "license": r.get("license"),
            })
        n_pages += 1
        end_of_records = bool(payload.get("endOfRecords"))
        offset += limit

    df = pd.DataFrame(
        all_rows,
        columns=[
            "scientific_name", "decimal_latitude", "decimal_longitude",
            "event_date", "basis_of_record", "dataset_name",
            "country", "license",
        ],
    )
    return SpeciesOccurrencesResult(
        df=df, usage_key=usage_key, bbox=bbox,
        total_matched=total_matched, n_pages_fetched=n_pages,
        cache=all_cache,
    )

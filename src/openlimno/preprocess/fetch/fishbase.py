"""FishBase species-traits lookup (v0.8.1 P0).

FishBase (Froese & Pauly 2024, https://www.fishbase.org/) is the de-
facto open database of fish species ecology + biology. It indexes
~35,000 species with temperature tolerance ranges, depth preferences,
habitat type (freshwater / brackish / marine / anadromous /
catadromous), maximum length, IUCN status, and many other traits
fish-ecology models care about.

Live programmatic access has trade-offs:

* The official FishBase site (`fishbase.org` / `fishbase.se`) ships
  HTML summary pages, not a stable REST API.
* The rOpenSci `rfishbase` R package consumes parquet dumps at
  `https://fishbase.ropensci.org/`, but the dump URL surface is
  documented only via R-package metadata (subject to silent
  versioning), not a public REST spec.
* The unofficial Azure-hosted FB-API has uptime swings.

Rather than couple OpenLimno to any of those — and to keep with the
v0.4 "subscription-free public sources" charter — v0.8.1 ships a
**curated starter table** of ~12 fish species commonly modelled in
PHABSIM / IFIM workflows (rainbow / brown / brook / chinook / Atlantic
salmon, grass / common / silver carp, Yangtze schizothoracines, Chinese
sturgeon, European eel). Each row cites the canonical FishBase summary
page so users can verify + extend.

For the live-REST extension (post-1.0 P3), the dataclass + lookup
surface here is the contract a future ``fetch_fishbase_live(...)``
would conform to.

Citation:
    Froese, R. and D. Pauly. Editors. 2024. FishBase. World Wide Web
    electronic publication. www.fishbase.org. Per-species citations
    via the ``fishbase_url`` column in the returned trait dict.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# Bundled starter table — packaged via [tool.hatch.build] in pyproject.
_STARTER_TABLE_PATH = (
    Path(__file__).parent / "data" / "fishbase_traits_starter.csv"
)

FISHBASE_CITATION = (
    "Froese, R. and D. Pauly. Editors. 2024. FishBase. World Wide "
    "Web electronic publication. www.fishbase.org. CC-BY-NC."
)

# Categorical enums used to validate ``water_type``.
WATER_TYPES = (
    "freshwater", "brackish", "marine", "anadromous", "catadromous",
)
# IUCN Red List status codes (subset relevant to fishes).
IUCN_STATUSES = ("LC", "NT", "VU", "EN", "CR", "EW", "EX", "DD", "NE")


@dataclass
class FishBaseTraits:
    """Curated FishBase-derived traits for a single species.

    Attributes:
        scientific_name: Latin binomial (matches GBIF canonical).
        common_name: English common name.
        temperature_min_C / temperature_max_C: preferred temperature
            range in degrees Celsius. NaN if FishBase didn't report.
        depth_min_m / depth_max_m: water-column depth range, metres.
        water_type: one of :data:`WATER_TYPES`.
        length_max_cm: maximum recorded body length, centimetres.
        iucn_status: IUCN Red List category code.
        fishbase_url: canonical FishBase summary page (the citation
            for this specific row).
        citation: top-level FishBase citation.
    """

    scientific_name: str
    common_name: str
    temperature_min_C: float
    temperature_max_C: float
    depth_min_m: float
    depth_max_m: float
    water_type: str
    length_max_cm: float
    iucn_status: str
    fishbase_url: str
    citation: str = FISHBASE_CITATION


def list_starter_species() -> list[str]:
    """Return the scientific names available in the bundled starter
    table — handy for tests + CLI introspection."""
    df = pd.read_csv(_STARTER_TABLE_PATH)
    return sorted(df["scientific_name"].tolist())


def fetch_fishbase_traits(scientific_name: str) -> FishBaseTraits | None:
    """Look up FishBase traits for ``scientific_name``.

    Args:
        scientific_name: Latin binomial (case-insensitive match).

    Returns:
        :class:`FishBaseTraits` if the species is in the starter
        table, ``None`` otherwise. A no-match return is NOT an
        error — the starter table only covers ~12 commonly-modelled
        species. Callers can detect ``None`` and fall back to a
        manual species-traits YAML in their case directory.
    """
    if not scientific_name or not scientific_name.strip():
        raise ValueError("scientific_name must be non-empty")
    name = scientific_name.strip()
    df = pd.read_csv(_STARTER_TABLE_PATH)
    matches = df[df["scientific_name"].str.lower() == name.lower()]
    if matches.empty:
        return None
    row = matches.iloc[0]
    return FishBaseTraits(
        scientific_name=row["scientific_name"],
        common_name=row["common_name"],
        temperature_min_C=float(row["temperature_min_C"]),
        temperature_max_C=float(row["temperature_max_C"]),
        depth_min_m=float(row["depth_min_m"]),
        depth_max_m=float(row["depth_max_m"]),
        water_type=row["water_type"],
        length_max_cm=float(row["length_max_cm"]),
        iucn_status=row["iucn_status"],
        fishbase_url=row["fishbase_url"],
    )
